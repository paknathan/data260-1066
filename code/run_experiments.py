"""
Part 4 experiment runner for DATA-260 HW2.

Usage (run from the same directory as agent_graph.py, against your live
Ollama instance):

    python run_experiments.py schema        # Part 4 Sec 3
    python run_experiments.py ceiling        # Part 4 Sec 4
    python run_experiments.py adversarial    # Part 4 Sec 5
    python run_experiments.py all            # all three, in order

Writes:
    reports/hw02/cases/schema_input.json
    reports/hw02/cases/adversarial_input.json
    reports/hw02/raw/schema_validation_runs.{json,csv}
    reports/hw02/raw/ceiling_comparison_runs.{json,csv}
    reports/hw02/raw/adversarial_runs.{json,csv}
    reports/hw02/RUN_LOG.txt   (appended, real console output + timestamps)

Each run uses stream=False internally (faster over 75 total runs), but the
Planner/Reviewer/Supervisor node functions still print unconditionally to
stderr, so RUN_LOG.txt still captures a real per-node trace of every run.
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

import agent_graph as ag

REPORTS_DIR = "reports/hw02"
CASES_DIR = os.path.join(REPORTS_DIR, "cases")
RAW_DIR = os.path.join(REPORTS_DIR, "raw")

SCHEMA_INPUT_PATH = os.path.join(CASES_DIR, "schema_input.json")
ADVERSARIAL_INPUT_PATH = os.path.join(CASES_DIR, "adversarial_input.json")

# --- Part 4 Sec 3/4: fixed domain input, frozen before the experiment ---
FROZEN_TITLE = "Route 22 -- Mechanical Breakdown"
FROZEN_CONTENT = (
    "incident_type=Mechanical Breakdown; transit_mode=Bus; "
    "route_or_line=Route 22; location=Downtown Transit Center; "
    "severity=Moderate; delay_minutes=20; description=A Route 22 bus "
    "experienced a mechanical breakdown near the Downtown Transit "
    "Center during evening rush hour. The engine stalled at a signal "
    "and could not restart, blocking one lane of traffic. Riders were "
    "transferred to the following bus after a 20-minute delay. A "
    "maintenance crew towed the disabled vehicle off-route roughly 45 "
    "minutes after the initial report."
)

# --- Part 4 Sec 5: adversarial input ---
# Deliberately sparse and repetitive: almost no concrete, distinct details
# to ground 3 *distinct* tags in (everything is "unknown" or hedged), which
# tends to push the Planner toward vague/overlapping candidate tags and the
# Reviewer toward either duplicate-ish picks or a rambling, hedge-filled
# summary that creeps past the 25-word cap.
ADVERSARIAL_TITLE = "Incident"
ADVERSARIAL_CONTENT = (
    "incident_type=Other; transit_mode=Bus; route_or_line=Unknown; "
    "location=Unknown; severity=Low; description=Something happened, "
    "possibly, though it is not fully clear what. It may or may not have "
    "affected service in some way, possibly related to a bus, or maybe "
    "not, riders were unsure, staff were unsure, no further details were "
    "recorded, and it is not clear if this was even a real incident or "
    "a false report."
)


def ensure_dirs():
    os.makedirs(CASES_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)


def save_case(path, title, content):
    if os.path.exists(path):
        return  # frozen -- don't overwrite an input already used for a run
    with open(path, "w") as f:
        json.dump({"title": title, "content": content}, f, indent=2)


def load_case(path):
    with open(path) as f:
        data = json.load(f)
    return data["title"], data["content"]


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    with open(os.path.join(REPORTS_DIR, "RUN_LOG.txt"), "a") as f:
        f.write(line + "\n")


def classify(result: dict) -> str:
    if result.get("abandoned"):
        return "hit_turn_ceiling"
    attempts = result.get("attempts", 1)
    if attempts <= 1:
        return "valid_first_attempt"
    if attempts == 2:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"


def run_single(title, content, turn_ceiling, strict=True):
    start = time.perf_counter()
    result = ag.run_pipeline(
        title, content, strict=strict, turn_ceiling=turn_ceiling, stream=False,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    result["latency_ms"] = round(latency_ms, 1)
    result["classification"] = classify(result)
    return result


def write_raw(records, path_json, path_csv):
    with open(path_json, "w") as f:
        json.dump(records, f, indent=2)
    if records:
        keys = sorted({k for r in records for k in r.keys()})
        with open(path_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in records:
                row = {k: r.get(k, "") for k in keys}
                for k, v in row.items():
                    if isinstance(v, (list, dict)):
                        row[k] = json.dumps(v)
                writer.writerow(row)


def summarize(records):
    buckets = [
        "valid_first_attempt", "valid_after_1_retry",
        "valid_after_2plus_retries", "hit_turn_ceiling",
    ]
    summary = {}
    for b in buckets:
        matching = [r["latency_ms"] for r in records if r["classification"] == b]
        summary[b] = {
            "count": len(matching),
            "mean_latency_ms": round(statistics.mean(matching), 1) if matching else None,
        }
    return summary


def print_metrics_table(header, summary):
    label_map = {
        "valid_first_attempt": "Valid first attempt",
        "valid_after_1_retry": "Valid after 1 retry",
        "valid_after_2plus_retries": "Valid after 2+ retries",
        "hit_turn_ceiling": "Hit turn ceiling",
    }
    print(f"\n{header}")
    print(f"{'Outcome':<28}{'Count':<8}{'Mean latency (ms)':<20}")
    for key, label in label_map.items():
        s = summary[key]
        mean = s["mean_latency_ms"] if s["mean_latency_ms"] is not None else "-"
        print(f"{label:<28}{s['count']:<8}{mean:<20}")


# ---------------------------------------------------------------------
# Part 4 Sec 3: 30 runs on the frozen schema input, classified
# ---------------------------------------------------------------------
def experiment_schema_validation(n=30, turn_ceiling=ag.DEFAULT_TURN_CEILING):
    ensure_dirs()
    save_case(SCHEMA_INPUT_PATH, FROZEN_TITLE, FROZEN_CONTENT)
    title, content = load_case(SCHEMA_INPUT_PATH)

    log(f"=== Part 4 Sec 3: schema-validation experiment, n={n}, turn_ceiling={turn_ceiling} ===")
    records = []
    for i in range(1, n + 1):
        result = run_single(title, content, turn_ceiling)
        result["run_index"] = i
        records.append(result)
        log(
            f"run {i}/{n}: classification={result['classification']} "
            f"attempts={result.get('attempts')} latency_ms={result['latency_ms']}"
        )

    write_raw(
        records,
        os.path.join(RAW_DIR, "schema_validation_runs.json"),
        os.path.join(RAW_DIR, "schema_validation_runs.csv"),
    )

    summary = summarize(records)
    log(f"schema-validation summary: {json.dumps(summary)}")
    print_metrics_table("Part 4 Sec 3 -- Outcome over 30 runs", summary)
    return records, summary


# ---------------------------------------------------------------------
# Part 4 Sec 4: ceiling comparison, 2 vs 10, 20 runs each
# ---------------------------------------------------------------------
def experiment_ceiling_comparison(n=20, ceilings=(2, 10)):
    ensure_dirs()
    save_case(SCHEMA_INPUT_PATH, FROZEN_TITLE, FROZEN_CONTENT)
    title, content = load_case(SCHEMA_INPUT_PATH)  # same frozen input as Sec 3

    log(f"=== Part 4 Sec 4: turn-ceiling comparison, n={n} per ceiling, ceilings={ceilings} ===")
    all_records = []
    results_by_ceiling = {}
    for ceiling in ceilings:
        records = []
        for i in range(1, n + 1):
            result = run_single(title, content, ceiling)
            result["run_index"] = i
            result["turn_ceiling"] = ceiling
            records.append(result)
            all_records.append(result)
            log(
                f"ceiling={ceiling} run {i}/{n}: valid={not result['abandoned']} "
                f"latency_ms={result['latency_ms']}"
            )

        completed = [r for r in records if not r["abandoned"]]
        completion_rate = len(completed) / len(records)
        mean_latency = statistics.mean(r["latency_ms"] for r in records)
        results_by_ceiling[ceiling] = {
            "completion_rate": round(completion_rate, 3),
            "mean_latency_ms": round(mean_latency, 1),
        }
        log(
            f"ceiling={ceiling} summary: completion_rate={completion_rate:.1%} "
            f"mean_latency_ms={mean_latency:.1f}"
        )

    write_raw(
        all_records,
        os.path.join(RAW_DIR, "ceiling_comparison_runs.json"),
        os.path.join(RAW_DIR, "ceiling_comparison_runs.csv"),
    )

    print(f"\nPart 4 Sec 4 -- Turn ceiling comparison (n={n} each)")
    print(f"{'Ceiling':<10}{'Completion rate':<18}{'Mean latency (ms)':<20}")
    for ceiling, s in results_by_ceiling.items():
        print(f"{ceiling:<10}{s['completion_rate']:<18}{s['mean_latency_ms']:<20}")

    faster = min(results_by_ceiling, key=lambda c: results_by_ceiling[c]["mean_latency_ms"])
    more_complete = max(results_by_ceiling, key=lambda c: results_by_ceiling[c]["completion_rate"])
    print(
        f"\nFaster ceiling: {faster} "
        f"({results_by_ceiling[faster]['mean_latency_ms']} ms mean). "
        f"Higher completion rate: {more_complete} "
        f"({results_by_ceiling[more_complete]['completion_rate']:.1%})."
    )
    print(
        "Use this pair of numbers to justify your deployment pick in "
        "METRICS.md -- e.g. 'ceiling=10 chosen: completion rate rose from "
        "X% to Y% for only Z ms extra mean latency', or the reverse if the "
        "lower ceiling barely loses completion rate for much less latency."
    )
    return results_by_ceiling


# ---------------------------------------------------------------------
# Part 4 Sec 5: adversarial input, 5 runs
# ---------------------------------------------------------------------
def experiment_adversarial(n=5, turn_ceiling=ag.DEFAULT_TURN_CEILING):
    ensure_dirs()
    save_case(ADVERSARIAL_INPUT_PATH, ADVERSARIAL_TITLE, ADVERSARIAL_CONTENT)
    title, content = load_case(ADVERSARIAL_INPUT_PATH)

    log(f"=== Part 4 Sec 5: adversarial input, n={n}, turn_ceiling={turn_ceiling} ===")
    records = []
    for i in range(1, n + 1):
        result = run_single(title, content, turn_ceiling)
        result["run_index"] = i
        records.append(result)
        log(
            f"adversarial run {i}/{n}: abandoned={result['abandoned']} "
            f"attempts={result.get('attempts')} latency_ms={result['latency_ms']}"
        )

    write_raw(
        records,
        os.path.join(RAW_DIR, "adversarial_runs.json"),
        os.path.join(RAW_DIR, "adversarial_runs.csv"),
    )

    hit_ceiling = sum(1 for r in records if r["abandoned"])
    rate = hit_ceiling / len(records)
    log(f"adversarial summary: hit_ceiling={hit_ceiling}/{len(records)} ({rate:.1%})")
    print(
        f"\nPart 4 Sec 5 -- Adversarial input hit the turn ceiling in "
        f"{hit_ceiling}/{len(records)} runs ({rate:.1%})."
    )
    if hit_ceiling < 4:
        print(
            "Note: this did not reach the ceiling in >=4/5 runs as preferred "
            "by the assignment -- report the observed rate above rather than "
            "claiming it's deterministic, and consider strengthening the "
            "adversarial input (e.g. even sparser detail, or push the draft "
            "summary closer to/over the 25-word limit) if you want a higher "
            "failure rate."
        )
    return records, rate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Part 4 experiment runner for HW2.")
    parser.add_argument(
        "experiment", choices=["schema", "ceiling", "adversarial", "all"],
    )
    args = parser.parse_args()

    ensure_dirs()
    if args.experiment in ("schema", "all"):
        experiment_schema_validation()
    if args.experiment in ("ceiling", "all"):
        experiment_ceiling_comparison()
    if args.experiment in ("adversarial", "all"):
        experiment_adversarial()
