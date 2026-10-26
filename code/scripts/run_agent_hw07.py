"""HW7 Part 2 runner: verification tasks A/B/C, the nonexistent-ID case, and the reliability measurement.

Run from code/ with Ollama running:
    python scripts/run_agent_hw07.py tasks                 # A, B, C, then E (screenshots)
    python scripts/run_agent_hw07.py tasks --only B        # one task per screenshot
    python scripts/run_agent_hw07.py error                 # nonexistent-ID case only
    python scripts/run_agent_hw07.py reliability --attempts 21 --temperature 0.7

Console output is also appended (with timestamps) to reports/hw07/RUN_LOG.txt; reliability raw data
goes to reports/hw07/raw/part2_reliability.{csv,jsonl}.
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from agent_loop import MAX_ITERATIONS, MAX_REPAIRS, MAX_TOOL_CALLS, check_chain, make_client, run_agent  # noqa: E402

REPORT_DIR = CODE_DIR.parent / "reports" / "hw07"
CASES_FILE = REPORT_DIR / "cases" / "part2_tasks.json"
RAW_DIR = REPORT_DIR / "raw"
FAILURE_TYPES = ["malformed_arguments", "unknown_tool", "text_when_tool_required", "lost_multi_step_chain"]

log = logging.getLogger("hw07")


def setup_logging() -> None:
    """Send everything to the console and append it to RUN_LOG.txt with timestamps."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.handlers.clear()  # domain_server.py installs its own handler at import time
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(REPORT_DIR / "RUN_LOG.txt", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(logging.INFO)
    logging.getLogger("transit_domain_server").setLevel(logging.WARNING)  # keep screenshots readable
    for noisy in ("httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run_one(case: dict, client, temperature: float) -> dict:
    """Run a single case with banner + summary lines, return the agent result."""
    log.info("=" * 78)
    log.info("Nathan Pak (s1066) | HW7 Part 2 | Task %s - %s", case["id"], case["title"])
    log.info("USER: %s", case["prompt"])
    result = run_agent(case["prompt"], client=client, temperature=temperature)
    log.info("FINAL ANSWER: %s", result["final_answer"])
    log.info("total tool calls: %d | stop_reason: %s | iterations: %d | repairs: %d | tokens: %d | %.0f ms",
             result["total_tool_calls"], result["stop_reason"], result["iterations"],
             result["repairs_used"], result["tokens"], result["latency_ms"])
    if case["id"] != "E":
        log.info("multi-step chain check: %s", "PASS" if check_chain(case, result) else "FAIL")
    return result


def cmd_tasks(args: argparse.Namespace, cases: dict) -> None:
    """Run A, B, C (or --only one) and then the error case."""
    client = make_client(args.model)
    log.info("model=%s temperature=%s limits: iterations=%d tool_calls=%d repairs=%d",
             client.model, args.temperature, MAX_ITERATIONS, MAX_TOOL_CALLS, MAX_REPAIRS)
    todo = [c for c in cases["cases"] if not args.only or c["id"] == args.only]
    if not args.only or args.only == "E":
        todo.append(cases["error_case"])
    for case in todo:
        run_one(case, client, args.temperature)


def cmd_error(args: argparse.Namespace, cases: dict) -> None:
    """Run only the nonexistent-ID case."""
    run_one(cases["error_case"], make_client(args.model), args.temperature)


def classify(case: dict, result: dict) -> dict:
    """Per-attempt row: call-level well-formedness before/after repair and failure types."""
    counts = {t: 0 for t in FAILURE_TYPES}
    for p in result["problems"]:
        counts[p["type"]] += 1
    chain_ok = check_chain(case, result)
    counts["lost_multi_step_chain"] = 0 if chain_ok else 1
    opportunities = result["proposals"]
    bad_first = len(result["problems"])
    still_bad = sum(1 for p in result["problems"] if not p["repaired"])
    return {
        "case_id": case["id"],
        "stop_reason": result["stop_reason"],
        "tool_calls_executed": result["total_tool_calls"],
        "call_opportunities": opportunities,
        "well_formed_first_try": opportunities - bad_first,
        "well_formed_after_repair": opportunities - still_bad,
        **counts,
        "repairs_used": result["repairs_used"],
        "chain_ok": chain_ok,
        "first_try_success": chain_ok and bad_first == 0,
        "tools_sequence": " > ".join(f"{c['name']}({next(iter(c['args'].values()), '')})" for c in result["tool_calls"]),
        "tokens": result["tokens"],
        "latency_ms": result["latency_ms"],
        "final_answer": result["final_answer"][:300],
    }


def cmd_reliability(args: argparse.Namespace, cases: dict) -> None:
    """Run >= 20 attempts round-robin over A/B/C with identical settings; save raw rows + print summary."""
    client = make_client(args.model)
    fixed = cases["cases"]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    log.info("RELIABILITY RUN %s | model=%s temperature=%s attempts=%d", stamp, client.model, args.temperature, args.attempts)
    rows = []
    jsonl = (RAW_DIR / "part2_reliability.jsonl").open("w", encoding="utf-8")
    for i in range(args.attempts):
        case = fixed[i % len(fixed)]
        log.info("--- attempt %d/%d (case %s)", i + 1, args.attempts, case["id"])
        result = run_agent(case["prompt"], client=client, temperature=args.temperature)
        row = {"attempt": i + 1, "model": client.model, "temperature": args.temperature, **classify(case, result)}
        rows.append(row)
        log.info("    stop=%s calls=%d first-try=%d/%d after-repair=%d/%d chain_ok=%s",
                 row["stop_reason"], row["tool_calls_executed"], row["well_formed_first_try"],
                 row["call_opportunities"], row["well_formed_after_repair"], row["call_opportunities"], row["chain_ok"])
        trace = {k: v for k, v in result.items() if k != "messages"}
        jsonl.write(json.dumps({"attempt": i + 1, "case_id": case["id"], "row": row, "trace": trace}, default=str) + "\n")
    jsonl.close()
    with (RAW_DIR / "part2_reliability.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    opp = sum(r["call_opportunities"] for r in rows)
    before = sum(r["well_formed_first_try"] for r in rows)
    after = sum(r["well_formed_after_repair"] for r in rows)
    n = len(rows)
    lines = [
        f"### Part 2 reliability ({n} attempts, model {client.model}, temperature {args.temperature})",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Attempts (A/B/C round-robin) | {n} |",
        f"| Tool-call opportunities | {opp} |",
        f"| Well-formed call rate - before repair | {before}/{opp} = {before / opp:.1%} |" if opp else "| Well-formed before | n/a |",
        f"| Well-formed call rate - after repair | {after}/{opp} = {after / opp:.1%} |" if opp else "| Well-formed after | n/a |",
        f"| Attempts fully correct on first try | {sum(r['first_try_success'] for r in rows)}/{n} |",
        f"| Attempts with correct multi-step chain (after repair) | {sum(r['chain_ok'] for r in rows)}/{n} |",
        "",
        "| Failure type | Count |",
        "|---|---|",
        *[f"| {t.replace('_', ' ')} | {sum(r[t] for r in rows)} |" for t in FAILURE_TYPES],
        "",
        "| Case | Attempts | Chain OK | Avg tool calls | Avg tokens | Avg latency (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for c in fixed:
        rs = [r for r in rows if r["case_id"] == c["id"]]
        lines.append(f"| {c['id']} | {len(rs)} | {sum(r['chain_ok'] for r in rs)}/{len(rs)} | "
                     f"{sum(r['tool_calls_executed'] for r in rs) / len(rs):.1f} | "
                     f"{sum(r['tokens'] for r in rs) / len(rs):.0f} | {sum(r['latency_ms'] for r in rs) / len(rs):.0f} |")
    summary = "\n".join(lines)
    (RAW_DIR / "part2_reliability_summary.md").write_text(summary + "\n", encoding="utf-8")
    log.info("\n%s", summary)
    log.info("raw data: %s", RAW_DIR)


def main() -> None:
    """Parse CLI args and dispatch."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["tasks", "error", "reliability"])
    parser.add_argument("--only", choices=["A", "B", "C", "E"], help="run a single task (tasks mode)")
    parser.add_argument("--attempts", type=int, default=21)
    parser.add_argument("--temperature", type=float, default=None,
                        help="default 0.0 for tasks/error, 0.7 for reliability")
    parser.add_argument("--model", default=None, help="override the HW1 adapter's default model")
    args = parser.parse_args()
    if args.temperature is None:
        args.temperature = 0.7 if args.mode == "reliability" else 0.0
    if args.mode == "reliability" and args.attempts < 20:
        parser.error("the assignment requires at least 20 attempts")
    setup_logging()
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    {"tasks": cmd_tasks, "error": cmd_error, "reliability": cmd_reliability}[args.mode](args, cases)


if __name__ == "__main__":
    main()
