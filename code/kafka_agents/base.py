"""Shared Kafka agent runner for Planner / Writer / Reviewer (HW8 Parts 2-3).

Each agent: consume its input topic -> handler(message) -> produce to its output topic, preserving correlation_id.
Failure-handling switches (Part 3), all ON by default ("after fix"):
  --no-idempotency     process a replayed correlation_id again (before fix)
  --commit-before      commit the offset as soon as a message is received (before fix: lost on crash)
  --no-dlq             retry a failing message forever, blocking the partition (before fix)
  --max-retries N      bounded retries before moving the message to s1066_dead_letter (default 3)
"""

import argparse
import json
import os
import signal
import socket
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from confluent_kafka import Consumer, KafkaError, Producer
from confluent_kafka.admin import AdminClient

from kafka_service.common import get_logger

from .config import BOOTSTRAP, DEAD_LETTER, PARTITIONS

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw08" / "raw"
FLOW = RAW / "agents_flow.jsonl"
STATE = RAW / "state"


def flow(agent: str, instance: str, event: str, corr: str | None, **extra: Any) -> None:
    """Structured event line shared by all agents (journey + ordering evidence)."""
    RAW.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "agent": agent,
           "instance": instance, "event": event, "correlation_id": corr, **extra}
    with FLOW.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


class ProcessedStore:
    """Idempotency store: correlation_ids this agent already completed (persisted, survives restarts)."""

    def __init__(self, agent: str) -> None:
        STATE.mkdir(parents=True, exist_ok=True)
        self.path = STATE / f"{agent}_processed.json"
        self.ids: set[str] = set(json.loads(self.path.read_text())) if self.path.exists() else set()

    def seen(self, corr: str) -> bool:
        return corr in self.ids

    def add(self, corr: str) -> None:
        self.ids.add(corr)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(self.ids)))
        os.replace(tmp, self.path)


def check_topics(log, bootstrap: str = BOOTSTRAP) -> None:
    """Topics are created with the Kafka CLI (scripts/create_topics_hw8.sh); fail clearly if one is missing/wrong."""
    md = AdminClient({"bootstrap.servers": bootstrap}).list_topics(timeout=10)
    problems = []
    for topic, want in PARTITIONS.items():
        if topic not in md.topics:
            problems.append(f"{topic} missing")
        elif len(md.topics[topic].partitions) != want:
            problems.append(f"{topic} has {len(md.topics[topic].partitions)} partitions, expected {want}")
    if problems:
        raise SystemExit("Create the topics first with scripts/create_topics_hw8.sh: " + "; ".join(problems))
    log.info("topics OK: %s", ", ".join(f"{t}({n}p)" for t, n in PARTITIONS.items()))


def agent_args(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--instance", default=f"{socket.gethostname().split('.')[0]}-{os.getpid()}")
    ap.add_argument("--no-idempotency", action="store_true")
    ap.add_argument("--commit-before", action="store_true")
    ap.add_argument("--no-dlq", action="store_true")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.0, help="extra seconds of work per message (crash test)")
    ap.add_argument("--rule", action="store_true", help="deterministic handler without the LLM (fast tests)")
    return ap


def run_agent(name: str, in_topic: str, out_topic: str, handler: Callable[[dict], tuple[dict, str | None]],
              args: argparse.Namespace) -> None:
    """handler(msg) -> (out_message, out_key). Raises on failure (-> bounded retries -> dead letter)."""
    log = get_logger(f"{name}:{args.instance}")
    check_topics(log)
    group = f"s1066_{name}_group"
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": group, "enable.auto.commit": False,
                         "auto.offset.reset": "earliest", "session.timeout.ms": 10000})
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all", "enable.idempotence": True})
    store = ProcessedStore(name)
    running = {"on": True}
    signal.signal(signal.SIGTERM, lambda *_: running.update(on=False))
    signal.signal(signal.SIGINT, lambda *_: running.update(on=False))

    def on_assign(c, parts):
        log.info("%s ready and listening on %s partitions=%s group=%s | idempotency=%s commit=%s dlq=%s retries=%d",
                 name, in_topic, [p.partition for p in parts], group, not args.no_idempotency,
                 "before-processing" if args.commit_before else "after-processing", not args.no_dlq, args.max_retries)

    consumer.subscribe([in_topic], on_assign=on_assign)
    try:
        while running["on"]:
            m = consumer.poll(1.0)
            if m is None:
                continue
            if m.error():
                if m.error().code() != KafkaError._PARTITION_EOF:
                    log.info("consumer error: %s", m.error())
                continue
            raw = m.value()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                msg = None
            corr = msg.get("correlation_id") if isinstance(msg, dict) else None
            where = {"topic": m.topic(), "partition": m.partition(), "offset": m.offset()}
            log.info("RECEIVED <- %s [p%d o%d] correlation_id=%s", m.topic(), m.partition(), m.offset(), corr)
            flow(name, args.instance, "received", corr, **where, entity=(msg or {}).get("entity"),
                 seq=(msg or {}).get("seq"))
            if args.commit_before:
                consumer.commit(message=m, asynchronous=False)
                log.info("COMMITTED offset %d BEFORE processing (unsafe mode)", m.offset() + 1)
            if corr and not args.no_idempotency and store.seen(corr):
                log.info("DUPLICATE correlation_id=%s already processed -> skipped (no new output)", corr)
                flow(name, args.instance, "duplicate_skipped", corr, **where)
                consumer.commit(message=m, asynchronous=False)
                continue
            attempt = 0
            while running["on"]:
                attempt += 1
                try:
                    if not isinstance(msg, dict) or not corr:
                        raise ValueError(f"poison message: not a valid JSON object with correlation_id: {raw[:80]!r}")
                    log.info("PROCESSING correlation_id=%s attempt=%d%s", corr, attempt,
                             f" (working {args.delay:.0f}s)" if args.delay else "")
                    if args.delay:
                        time.sleep(args.delay)
                    out, key = handler(msg)
                    out["correlation_id"] = corr  # preserved unchanged through every stage
                    producer.produce(out_topic, key=(key or corr).encode(), value=json.dumps(out).encode())
                    producer.flush(10)
                    log.info("SENT -> %s correlation_id=%s", out_topic, corr)
                    flow(name, args.instance, "sent", corr, out_topic=out_topic, **where,
                         entity=msg.get("entity"), seq=msg.get("seq"))
                    if not args.no_idempotency:
                        store.add(corr)
                    break
                except Exception as exc:
                    log.info("FAILED correlation_id=%s attempt=%d error=%s", corr, attempt, exc)
                    flow(name, args.instance, "failed", corr, attempt=attempt, error=str(exc)[:200], **where)
                    if args.no_dlq:
                        time.sleep(1.0)  # before fix: retry the same message forever -> partition blocked
                        continue
                    if attempt >= args.max_retries:
                        dead = {"correlation_id": corr, "agent": name, "error": str(exc)[:500], "attempts": attempt,
                                "source": where, "original": raw.decode("utf-8", errors="replace")[:2000]}
                        producer.produce(DEAD_LETTER, key=(corr or "poison").encode(), value=json.dumps(dead).encode())
                        producer.flush(10)
                        log.info("DEAD-LETTER -> %s after %d attempts correlation_id=%s", DEAD_LETTER, attempt, corr)
                        flow(name, args.instance, "dead_lettered", corr, attempts=attempt, **where)
                        break
                    time.sleep(0.5 * 2 ** (attempt - 1))  # bounded exponential backoff
            if not args.commit_before:
                consumer.commit(message=m, asynchronous=False)  # only after success or dead-lettering
                log.info("COMMITTED offset %d after processing", m.offset() + 1)
    finally:
        consumer.close()
        log.info("%s stopped", name)
