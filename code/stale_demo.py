"""HW9 Part 3.5 - stale cached answers and data-version invalidation.

The cached question depends on one row of the relational DB (incidents in Municipal_rel):
    "What is the current delay for incident INC-2026-0001, and what should riders expect?"
On a cache miss the pipeline input is the question plus that row (record-grounded answer).

Steps
  1. Set the record's delay to --before minutes. Ask -> MISS (agents answer from the record). Ask -> HIT.
  2. NAIVE write path: UPDATE the row to --after minutes, cache untouched. Ask -> HIT with the OLD answer
     although the database now says --after  => STALE HIT.
  3. FIXED write path: the same UPDATE plus cache.bump_data_version() in one function. Ask -> MISS
     (old entry is under the previous data version), fresh answer from the updated row. Ask -> HIT (new answer).
  4. Restore the original delay (through the fixed write path) unless --keep.

Run from code/ with DATABASE_URL, Redis 8, Kafka and the HW8 agents running:
    python stale_demo.py
    python stale_demo.py --incident INC-2026-0002 --before 25 --after 55
Writes reports/hw09/raw/part3_stale_demo.json
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

import semantic_gateway
from semantic_cache import SemanticCache
from semantic_gateway import CachedQA
from sql_db import SessionLocal, engine

RAW = Path(__file__).resolve().parents[1] / "reports" / "hw09" / "raw"
DB_NAME = engine.url.database


def fetch_record(code: str) -> dict:
    with SessionLocal() as db:
        row = db.execute(text("SELECT id, title, incident_code, delay_minutes, updated_at FROM incidents "
                              "WHERE incident_code = :c"), {"c": code}).mappings().first()
    if row is None:
        raise SystemExit(f"incident {code} not found in {DB_NAME}.incidents - run seed.py or pass --incident")
    return dict(row)


def update_delay(code: str, minutes: int, cache: SemanticCache | None = None) -> None:
    """Write path for incident delays. With `cache`, invalidates cached answers (fixed); without, it doesn't (naive)."""
    with SessionLocal() as db:
        db.execute(text("UPDATE incidents SET delay_minutes = :m, updated_at = CURRENT_TIMESTAMP "
                        "WHERE incident_code = :c"), {"m": minutes, "c": code})
        db.commit()
    if cache is not None:
        cache.bump_data_version(f"incident {code} delay_minutes -> {minutes}")


def record_pipeline(question: str) -> dict:
    """HW8 pipeline, grounded on the current DB row for the incident code named in the question."""
    code = re.search(r"INC-\d{4}-\d{4}", question).group(0)
    r = fetch_record(code)
    context = (f"\nIncident record from the {DB_NAME} database: incident_code={r['incident_code']}, "
               f"title={r['title']}, delay_minutes={r['delay_minutes']}, last_updated={r['updated_at']}. "
               "Use this record for the delay.")
    return semantic_gateway.run_agent_pipeline(question + context)


def mentions(answer: str, minutes: int) -> bool:
    return re.search(rf"\b{minutes}\b", answer) is not None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident", default="INC-2026-0001")
    ap.add_argument("--before", type=int, default=25)
    ap.add_argument("--after", type=int, default=55)
    ap.add_argument("--keep", action="store_true", help="do not restore the original delay at the end")
    args = ap.parse_args()

    question = f"What is the current delay for incident {args.incident}, and what should riders expect?"
    cache = SemanticCache()
    cache.clear()  # start from an empty cache so step 1 is a real miss
    qa = CachedQA(cache, pipeline=record_pipeline)
    original = fetch_record(args.incident)["delay_minutes"]
    log = []

    def ask(step: str) -> dict:
        db_delay = fetch_record(args.incident)["delay_minutes"]
        r = qa.ask(question)
        stale = r["is_cached"] and mentions(r["answer"], args.before) and db_delay != args.before
        verdict = ("STALE (answer is for an older record)" if stale else
                   "matches DB" if mentions(r["answer"], db_delay) else "delay value not stated in answer")
        sim = "n/a" if r["similarity"] is None else f"{r['similarity']:.4f}"
        print(f"[{step}] DB delay_minutes={db_delay} | is_cached={r['is_cached']} similarity={sim} "
              f"latency={r['latency_ms']:.1f}ms data_version={r['data_version']} -> {verdict}")
        print(f"         answer: {r['answer']}\n")
        log.append({"step": step, "db_delay_minutes": db_delay, "verdict": verdict, **r})
        return r

    print(f"=== Stale-answer demo | {DB_NAME}.incidents {args.incident} (original delay {original} min) ===")
    print(f"question: {question}\n")

    print(f"--- Step 1: record delay = {args.before} min; first ask is a miss, second a hit ---")
    update_delay(args.incident, args.before)
    ask("1a fresh miss")
    ask("1b fresh hit")

    print(f"--- Step 2: NAIVE update to {args.after} min (database changed, cache NOT invalidated) ---")
    update_delay(args.incident, args.after)
    ask("2  stale hit")

    print(f"--- Step 3: FIXED write path: update to {args.after} min + bump data version ---")
    update_delay(args.incident, args.after, cache=cache)
    ask("3a after invalidation")
    ask("3b new answer cached")

    if not args.keep:
        update_delay(args.incident, original, cache=cache)
        print(f"(restored {args.incident} delay_minutes to {original}; data version bumped again)")

    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / "part3_stale_demo.json"
    out.write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "database": DB_NAME, "incident": args.incident, "question": question,
                               "before": args.before, "after": args.after, "original": original, "steps": log},
                              indent=2, ensure_ascii=False, default=str))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
