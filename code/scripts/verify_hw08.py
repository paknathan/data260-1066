"""HW8 self-check -> reports/hw08/verification.json.

Checks the code (offline unit tests), the live broker topics, and the saved run evidence in reports/hw08/raw/.
Checks objective values only (status, counts, offsets, order), never wording.
From code/:   python scripts/verify_hw08.py      (Kafka container s1066_kafka should be running)
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
REPO = CODE.parent
RAW = REPO / "reports" / "hw08" / "raw"
OUT = REPO / "reports" / "hw08" / "verification.json"
sys.path.insert(0, str(CODE))
SID4, SEED, VERIFY_SEED, PORT_BASE = 1066, 1066, 261066, 8166
checks: list[dict] = []


def check(name: str):
    def wrap(fn):
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return fn
    return wrap


def load(name: str) -> dict:
    return json.loads((RAW / name).read_text())


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


@check("unit_tests_offline")
def _():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_kafka_incident.py",
                        "tests/test_kafka_agents.py"], cwd=CODE, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout.strip().splitlines() or ["no output"])[-1]


@check("live_topics_and_partitions")
def _():
    from confluent_kafka.admin import AdminClient

    from kafka_agents.config import BOOTSTRAP, PARTITIONS
    from kafka_service.config import REQUEST_TOPIC, RESPONSE_TOPIC
    md = AdminClient({"bootstrap.servers": BOOTSTRAP}).list_topics(timeout=10)
    want = {**PARTITIONS, REQUEST_TOPIC: None, RESPONSE_TOPIC: None}
    got = {t: len(md.topics[t].partitions) if t in md.topics else 0 for t in want}
    ok = all(got[t] > 0 and (n is None or got[t] == n) for t, n in want.items())
    return ok, got


@check("part1_create_get_over_kafka")
def _():
    d = load("part1_demo.json")
    ok = (d["create"]["success"] and d["get"]["success"]
          and d["get"]["incident"]["incident_id"] == d["create"]["incident_id"]
          and d["create"]["correlation_id"] == d["create_correlation_id"]
          and d["get"]["correlation_id"] == d["get_correlation_id"])
    return ok, {"incident_id": d["create"]["incident_id"], "correlation_ids_preserved": ok}


@check("part2_full_journey_inbox_to_final")
def _():
    f = sorted(RAW.glob("part2_final_*.json"))[-1]
    d = json.loads(f.read_text())
    corr = d["final"]["correlation_id"]
    sent = {r["agent"] for r in d["journey"] if r["event"] == "sent" and r["correlation_id"] == corr}
    ok = d["final"]["status"] in ("approved", "rejected") and bool(d["final"]["answer"]) \
        and corr == d["sent"]["correlation_id"] and {"planner", "writer", "reviewer"} <= sent
    return ok, {"correlation_id": corr, "status": d["final"]["status"], "stages_sent": sorted(sent)}


@check("part3_duplicate_delivery")
def _():
    b, a = load("part3_dup_before.json"), load("part3_dup_after.json")
    ok = b["final_messages"] == 2 and a["final_messages"] == 1 and a["duplicates_skipped"] >= 1
    return ok, {"before_finals": b["final_messages"], "after_finals": a["final_messages"],
                "after_duplicates_skipped": a["duplicates_skipped"]}


@check("part3_consumer_death")
def _():
    b, a = load("part3_crash_before.json"), load("part3_crash_after.json")
    redelivered = sum(" received " in e for e in a["writer_events"]) >= 2
    ok = (not b["final_received"]) and a["final_received"] and redelivered
    return ok, {"before_final_received": b["final_received"], "after_final_received": a["final_received"],
                "after_redelivered_same_offset": redelivered}


@check("part3_poison_message")
def _():
    b, a = load("part3_poison_before.json"), load("part3_poison_after.json")
    ok = (not b["good_message_completed"]) and not b["dead_letter"] and a["good_message_completed"] \
        and a["dead_letter"] and a["dead_letter"][0]["attempts"] == 3
    return ok, {"before_blocked": not b["good_message_completed"], "after_attempts": a["dead_letter"][0]["attempts"],
                "after_good_completed": a["good_message_completed"]}


@check("part3_ordering_unkeyed_vs_keyed")
def _():
    u, k = load("part3_order_unkeyed.json"), load("part3_order_keyed.json")
    u_ok = sum(v["in_order"] for v in u["per_entity"].values())
    k_ok = sum(v["in_order"] for v in k["per_entity"].values())
    one_part = all(len(v["partitions"]) == 1 for v in k["per_entity"].values())
    ok = u["verify_seed"] == k["verify_seed"] == VERIFY_SEED and u_ok < 4 and k_ok == 4 and one_part
    return ok, {"unkeyed_entities_in_order": f"{u_ok}/4", "keyed_entities_in_order": f"{k_ok}/4",
                "keyed_one_partition_per_entity": one_part}


result = {
    "homework": 8, "sid4": SID4, "commit": git("rev-parse", "HEAD"),
    "commit_tags": git("tag", "--points-at", "HEAD").split(),
    "working_tree_clean": git("status", "--porcelain", "--", "code") == "",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "model": {"name": "qwen3:8b (Ollama, local)", "part3_agents": "--rule (deterministic, no model)"},
    "config": {"PORT_BASE": PORT_BASE, "PREFIX": f"s{SID4}", "DOMAIN": "municipal transit incidents"},
    "seed": SEED, "verify_seed": VERIFY_SEED, "checks": checks,
    "summary": {"passed": sum(c["passed"] for c in checks), "total": len(checks),
                "all_passed": all(c["passed"] for c in checks)},
}
OUT.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
print(f"\n{result['summary']['passed']}/{result['summary']['total']} checks passed -> {OUT}")
