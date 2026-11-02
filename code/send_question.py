"""HW8 Part 2 - send one question to s1066_inbox and wait for its final JSON on s1066_final.

Run from code/:
  python send_question.py
  python send_question.py --question "Why is the Blue Line delayed at Tasman station?"
  python send_question.py --correlation-id <id>      # replay the same correlation_id (Part 3 duplicate test)
Prints the final JSON and the full journey inbox -> tasks -> drafts -> final reconstructed from the agents' flow log.
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Consumer, Producer, TopicPartition

from kafka_agents.base import FLOW, RAW, flow
from kafka_agents.config import BOOTSTRAP, FINAL, INBOX
from kafka_service.common import get_logger

DEFAULT_Q = ("A bus on Route 22 broke down at 1st and Santa Clara during the morning rush and riders report a "
             "20-minute delay. What happened and what should riders do?")


def final_listener(log):
    """Consumer assigned to s1066_final at its current end, so we only see answers produced after we send."""
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"s1066_sender_{uuid.uuid4().hex[:8]}",
                  "enable.auto.commit": False, "auto.offset.reset": "latest"})
    parts = c.list_topics(FINAL, timeout=10).topics[FINAL].partitions
    tps = []
    for p in parts:
        _, high = c.get_watermark_offsets(TopicPartition(FINAL, p), timeout=10)
        tps.append(TopicPartition(FINAL, p, high))
    c.assign(tps)
    log.info("listening on %s from offsets %s", FINAL, [tp.offset for tp in tps])
    return c


def journey(corr: str) -> list[dict]:
    if not FLOW.exists():
        return []
    rows = [json.loads(line) for line in FLOW.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted((r for r in rows if r.get("correlation_id") == corr), key=lambda r: r["ts"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", default=DEFAULT_Q)
    ap.add_argument("--correlation-id", default=None)
    ap.add_argument("--timeout", type=float, default=600)
    args = ap.parse_args()
    log = get_logger("sender")
    corr = args.correlation_id or str(uuid.uuid4())
    consumer = final_listener(log)
    msg = {"correlation_id": corr, "question": args.question,
           "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    producer.produce(INBOX, key=corr.encode(), value=json.dumps(msg).encode())
    producer.flush(10)
    log.info("SENT -> %s correlation_id=%s question=%r", INBOX, corr, args.question)
    flow("sender", "cli", "sent", corr, out_topic=INBOX)
    t0, final = time.time(), None
    try:
        while time.time() - t0 < args.timeout:
            m = consumer.poll(1.0)
            if m is None or m.error():
                continue
            body = json.loads(m.value())
            if body.get("correlation_id") == corr:
                final = body
                log.info("FINAL <- %s [p%d o%d] correlation_id=%s status=%s (%.1fs)", m.topic(), m.partition(),
                         m.offset(), corr, body.get("status"), time.time() - t0)
                flow("sender", "cli", "final_received", corr, topic=m.topic(), partition=m.partition(),
                     offset=m.offset(), status=body.get("status"))
                break
    finally:
        consumer.close()
    if final is None:
        log.info("no final answer for %s within %.0fs", corr, args.timeout)
        return 1
    print("\n===== FINAL JSON (s1066_final) =====")
    print(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\n===== JOURNEY correlation_id={corr} (inbox -> tasks -> drafts -> final) =====")
    time.sleep(0.5)
    for r in journey(corr):
        where = f"{r.get('topic')}[p{r.get('partition')} o{r.get('offset')}]"
        dest = f" -> {r['out_topic']}" if r.get("out_topic") else ""
        print(f"{r['ts']}  {r['agent']:<8} {r['event']:<17} {where}{dest}")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"part2_final_{corr[:8]}.json").write_text(json.dumps({"sent": msg, "final": final,
                                                                   "journey": journey(corr)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
