"""HW8 Part 3 - failure-behavior driver (run from code/ while the agents are running).

  python part3.py dup                  duplicate delivery: send the SAME correlation_id twice, count finals
  python part3.py crash                consumer death: send one question, kill -9 the Writer mid-work, restart it
  python part3.py poison               poison message: send a non-JSON message, then a good question behind it
  python part3.py order --mode unkeyed 20 related messages (VERIFY_SEED) through 2-partition s1066_tasks
  python part3.py order --mode keyed   same 20 messages, keyed by entity
Each run prints the evidence and saves it to reports/hw08/raw/part3_<test>_<label>.json.
"""

import argparse
import json
import random
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from confluent_kafka import Consumer, Producer, TopicPartition

from kafka_agents.base import FLOW, RAW, flow
from kafka_agents.config import BOOTSTRAP, DEAD_LETTER, FINAL, INBOX, VERIFY_SEED
from kafka_service.common import get_logger

log = get_logger("part3")
ENTITIES = ["Route 22", "Blue Line", "Route 68", "Orange Line"]
EVENTS = ["incident reported", "crew dispatched", "crew on scene", "single-tracking in effect",
          "bus bridge started", "delay estimate updated", "service restoring", "incident cleared"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def listener(topics: list[str]) -> Consumer:
    """Read the given topics starting at their current end (only messages produced after this call)."""
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"s1066_part3_{uuid.uuid4().hex[:8]}",
                  "enable.auto.commit": False})
    tps = []
    for t in topics:
        for p in c.list_topics(t, timeout=10).topics[t].partitions:
            _, high = c.get_watermark_offsets(TopicPartition(t, p), timeout=10)
            tps.append(TopicPartition(t, p, high))
    c.assign(tps)
    return c


def collect(c: Consumer, wanted, timeout: float, stop=None) -> list[dict]:
    out, t0 = [], time.time()
    while time.time() - t0 < timeout:
        m = c.poll(0.5)
        if m is None or m.error():
            continue
        try:
            body = json.loads(m.value())
        except json.JSONDecodeError:
            continue
        rec = {"topic": m.topic(), "partition": m.partition(), "offset": m.offset(), "received_at": now(), "body": body}
        if wanted(rec):
            out.append(rec)
            log.info("<- %s [p%d o%d] correlation_id=%s %s", m.topic(), m.partition(), m.offset(),
                     body.get("correlation_id"), body.get("status") or body.get("error", "")[:60])
            if stop and stop(out):
                break
    return out


def produce(items: list[tuple[str, bytes]]) -> None:
    p = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    for key, value in items:
        p.produce(INBOX, key=key.encode(), value=value)
    p.flush(10)


def q(corr: str, question: str, **extra) -> bytes:
    return json.dumps({"correlation_id": corr, "question": question, "created_at": now(), **extra}).encode()


def save(name: str, data: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    print(f"\nsaved -> {path}")


def flow_rows(pred) -> list[dict]:
    if not FLOW.exists():
        return []
    rows = [json.loads(x) for x in FLOW.read_text(encoding="utf-8").splitlines() if x.strip()]
    return sorted((r for r in rows if pred(r)), key=lambda r: r["ts"])


# ----------------------------------------------------------------------------- I. duplicate delivery
def dup(a) -> None:
    corr = f"dup-{uuid.uuid4().hex[:8]}"
    c = listener([FINAL])
    msg = q(corr, "Route 22 bus breakdown at 1st and Santa Clara - what should riders do?")
    produce([(corr, msg), (corr, msg)])  # replay: the identical message (same correlation_id) delivered twice
    log.info("SENT the same message twice -> %s correlation_id=%s", INBOX, corr)
    finals = collect(c, lambda r: r["body"].get("correlation_id") == corr, a.wait)
    c.close()
    time.sleep(0.5)
    ev = [(r["agent"], r["event"]) for r in flow_rows(lambda r: r.get("correlation_id") == corr)]
    summary = {"correlation_id": corr, "label": a.label, "messages_sent": 2, "final_messages": len(finals),
               "planner_processed": ev.count(("planner", "sent")), "writer_processed": ev.count(("writer", "sent")),
               "reviewer_processed": ev.count(("reviewer", "sent")),
               "duplicates_skipped": sum(e == "duplicate_skipped" for _, e in ev)}
    print("\n===== DUPLICATE DELIVERY =====\n" + json.dumps(summary, indent=2))
    print("RESULT:", "duplicate side effect (2 finals)" if len(finals) > 1 else
          "replay caused no extra side effect (exactly 1 final)" if len(finals) == 1 else "no final received")
    save(f"part3_dup_{a.label}", {**summary, "finals": finals})


# ----------------------------------------------------------------------------- II. consumer death
def crash(a) -> None:
    corr = f"crash-{uuid.uuid4().hex[:8]}"
    c = listener([FINAL])
    produce([(corr, q(corr, "Blue Line stalled near Tasman station - what should riders do?"))])
    log.info("SENT -> %s correlation_id=%s", INBOX, corr)
    print(">>> When the Writer prints PROCESSING for this id, run in another terminal:  pkill -9 -f writer.py")
    print(">>> Then restart the Writer (python writer.py --rule). Waiting up to %ds for the final answer..." % a.wait)
    finals = collect(c, lambda r: r["body"].get("correlation_id") == corr, a.wait, stop=lambda o: o)
    c.close()
    ev = flow_rows(lambda r: r.get("correlation_id") == corr and r["agent"] == "writer")
    summary = {"correlation_id": corr, "label": a.label, "final_received": bool(finals),
               "writer_events": [f"{r['ts']} {r['instance']} {r['event']} {r['topic']}[p{r['partition']} o{r['offset']}]"
                                 for r in ev]}
    print("\n===== CONSUMER DEATH =====\n" + json.dumps(summary, indent=2))
    print("RESULT:", "message redelivered after restart and completed" if finals else
          "message LOST - offset was committed before the Writer finished, nothing was redelivered")
    save(f"part3_crash_{a.label}", {**summary, "finals": finals})


# ----------------------------------------------------------------------------- III. poison message
def poison(a) -> None:
    start = now()
    tag = f"POISON-{uuid.uuid4().hex[:6]}"
    good = f"good-{uuid.uuid4().hex[:8]}"
    c = listener([FINAL, DEAD_LETTER])
    produce([(tag, f"{tag} this is not JSON {{{{".encode()),
             (good, q(good, "Route 68 detour at Monterey Rd - what should riders do?"))])
    log.info("SENT poison message %r then good message correlation_id=%s (behind it in partition 0)", tag, good)
    got = collect(c, lambda r: r["body"].get("correlation_id") == good or tag in str(r["body"].get("original", "")),
                  a.wait, stop=lambda o: any(r["topic"] == FINAL for r in o))
    c.close()
    dead = [r for r in got if r["topic"] == DEAD_LETTER]
    fin = [r for r in got if r["topic"] == FINAL]
    fails = flow_rows(lambda r: r["agent"] == "planner" and r["event"] == "failed" and r["ts"] >= start)
    summary = {"label": a.label, "poison_tag": tag, "good_correlation_id": good,
               "dead_letter": [{"attempts": r["body"]["attempts"], "agent": r["body"]["agent"],
                                "error": r["body"]["error"][:120], "source": r["body"]["source"]} for r in dead],
               "good_message_completed": bool(fin), "planner_failed_attempts_logged": len(fails)}
    print("\n===== POISON MESSAGE =====\n" + json.dumps(summary, indent=2))
    print("RESULT:", f"poison retried {dead[0]['body']['attempts']}x -> {DEAD_LETTER}; later message completed"
          if dead and fin else "poison message BLOCKED the partition - later good message never completed")
    save(f"part3_poison_{a.label}", {**summary, "records": got})


# ----------------------------------------------------------------------------- IV. ordering
def order(a) -> None:
    rng = random.Random(VERIFY_SEED)
    batch = f"ord-{a.mode}-{uuid.uuid4().hex[:4]}"
    seq = defaultdict(int)
    msgs = []
    for i in range(20):
        ent = rng.choice(ENTITIES)
        seq[ent] += 1
        corr = f"{batch}-{i:02d}"
        msgs.append((corr, q(corr, f"{ent} update {seq[ent]}: {rng.choice(EVENTS)}. What should riders know?",
                             entity=ent, seq=seq[ent], key_mode="entity" if a.mode == "keyed" else "none")))
    c = listener([FINAL])
    produce(msgs)
    log.info("SENT 20 related messages (VERIFY_SEED=%d) batch=%s key_mode=%s counts=%s", VERIFY_SEED, batch,
             "entity" if a.mode == "keyed" else "none (key=correlation_id)", dict(seq))
    finals = collect(c, lambda r: str(r["body"].get("correlation_id", "")).startswith(batch), a.wait,
                     stop=lambda o: len(o) >= 20)
    c.close()
    time.sleep(0.5)
    wsent = flow_rows(lambda r: str(r.get("correlation_id", "")).startswith(batch) and r["agent"] == "writer"
                      and r["event"] == "sent")
    print(f"\n===== ORDERING ({a.mode}) - Writer processing order (s1066_tasks) =====")
    for r in wsent:
        print(f"{r['ts'][11:23]}  {r['instance']:<9} tasks[p{r['partition']} o{r['offset']:>3}]  "
              f"{r['entity']:<12} seq={r['seq']}")
    per = {}
    for ent in ENTITIES:
        w = [r for r in wsent if r["entity"] == ent]
        f = [r["body"]["seq"] for r in finals if r["body"].get("entity") == ent]
        per[ent] = {"sent_seq": list(range(1, seq[ent] + 1)), "writer_seq": [r["seq"] for r in w], "final_seq": f,
                    "partitions": sorted({r["partition"] for r in w}), "writers": sorted({r["instance"] for r in w}),
                    "in_order": f == sorted(f) and [r["seq"] for r in w] == sorted(r["seq"] for r in w)}
    print("\nper entity:")
    for ent, d in per.items():
        print(f"  {ent:<12} partitions={d['partitions']} writers={d['writers']} final order={d['final_seq']} "
              f"-> {'IN ORDER' if d['in_order'] else 'OUT OF ORDER'}")
    ok = sum(d["in_order"] for d in per.values())
    print(f"RESULT: {len(finals)}/20 finals; {ok}/{len(per)} entities kept their order")
    save(f"part3_order_{a.mode}", {"batch": batch, "verify_seed": VERIFY_SEED, "mode": a.mode, "per_entity": per,
                                   "writer_order": wsent, "final_order": [r["body"]["correlation_id"] for r in finals]})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("test", choices=["dup", "crash", "poison", "order"])
    ap.add_argument("--label", default="after", help="before | after (used in the saved file name)")
    ap.add_argument("--mode", choices=["unkeyed", "keyed"], default="unkeyed")
    ap.add_argument("--wait", type=int, default=None)
    args = ap.parse_args()
    args.wait = args.wait or {"dup": 20, "crash": 90, "poison": 30, "order": 90}[args.test]
    flow("part3", "cli", f"start_{args.test}", None, label=args.label, mode=args.mode)
    {"dup": dup, "crash": crash, "poison": poison, "order": order}[args.test](args)
