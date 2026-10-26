"""HW7 Part 3 runner: Reflexion demo + original-vs-Reflexion comparison on the three fixed tasks.

Run from code/ with Ollama running:
    python scripts/run_reflexion_hw07.py demo --only B --temperature 0.7    # screenshot: fail -> reflect -> retry
    python scripts/run_reflexion_hw07.py compare --trials 7                 # comparison table + raw data

Output is appended to reports/hw07/RUN_LOG.txt. Raw data goes to reports/hw07/raw/:
part3_comparison.csv (one row per run), part3_runs.jsonl (traces), part3_reflections.jsonl (stored
reflections + evidence), part3_false_rejections.jsonl, part3_comparison_summary.md.
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
sys.path.insert(0, str(CODE_DIR / "scripts"))

from run_agent_hw07 import CASES_FILE, RAW_DIR, setup_logging  # noqa: E402

from agent_loop import make_client, run_agent  # noqa: E402
from reflexion import MAX_RETRIES, TOKEN_BUDGET, TOOL_BUDGET, ReflectionStore, run_reflexion  # noqa: E402
from verifier import oracle_correct, verify  # noqa: E402

log = logging.getLogger("hw07.part3")


def _banner(case: dict, label: str) -> None:
    log.info("=" * 78)
    log.info("Nathan Pak (s1066) | HW7 Part 3 | %s | Task %s - %s", label, case["id"], case["title"])
    log.info("USER: %s", case["prompt"])


def _show_verdict(verdict: dict) -> None:
    for c in verdict["checks"]:
        log.info("    [%s] %-16s %s", "PASS" if c["passed"] else "FAIL", c["name"], c["detail"])


def _seq(result: dict) -> str:
    """One-line tool sequence, e.g. aggregate_route_stats(Route 22) > search_incidents(Route 22)."""
    return " > ".join(f"{c['name']}({next(iter(c['args'].values()), '')})" for c in result["tool_calls"]) or "(no tools)"


def _short(text: str, n: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def _failed(verdict: dict) -> str:
    """Compact list of failed checks with a short reason each."""
    parts = []
    for c in verdict["checks"]:
        if not c["passed"]:
            detail = c["detail"].split("; ")[1] if c["name"] == "chain_order" and "; " in c["detail"] else c["detail"]
            parts.append(f"{c['name']} ({_short(detail, 70)})")
    return " | ".join(parts)


def _print_compact(case: dict, out: dict, earlier_passes: int) -> None:
    """Screenshot-sized summary of one Reflexion run."""
    log.info("=" * 78)
    log.info("Nathan Pak (s1066) | HW7 Part 3 | Reflexion demo | Task %s - %s", case["id"], case["title"])
    log.info("USER: %s", _short(case["prompt"], 160))
    if earlier_passes:
        log.info("(%d earlier run(s) passed on the first attempt, so no reflection was needed - showing the next run)",
                 earlier_passes)
    refl_by_attempt = {r["attempt"]: r for r in out["reflections"]}
    for a in out["attempts"]:
        r, v = a["result"], a["verdict"]
        log.info("ATTEMPT %d%s: %s", a["attempt"], " (reflection in context)" if a["reflection_in_context"] else "",
                 _seq(r))
        log.info("  answer  : %s", _short(r["final_answer"]))
        log.info("  verifier: %s", "PASS (4/4 checks)" if v["passed"] else "FAIL - " + _failed(v))
        rf = refl_by_attempt.get(a["attempt"])
        if rf:
            ev = rf["evidence"]
            log.info("REFLECTION stored (user=%s, run=%s, from attempt %d, written by %s):",
                     rf["user_id"], rf["run_id"], rf["attempt"], rf["source"])
            log.info("  failure : %s", rf["reflection"]["failure"])
            log.info("  strategy: %s", rf["reflection"]["strategy"])
            log.info("  evidence: failed checks %s; tool calls %s; unsupported claims %s",
                     [c["check"] for c in ev["failed_checks"]],
                     [f"{c['tool']}({next(iter(c['args'].values()), '')})" for c in ev["tool_calls"]],
                     ev["unsupported_claims"] or "none")
    log.info("RESULT: stop_reason=%s | retries=%d | tool calls=%d | tokens=%d | %.0f ms",
             out["stop_reason"], out["retries"], out["tool_calls"], out["tokens"], out["latency_ms"])
    log.info("full reflection + evidence record: reports/hw07/raw/part3_reflections.jsonl")


def cmd_demo(args: argparse.Namespace, cases: dict) -> None:
    """Run Reflexion on one task, repeating (up to --max-tries) until a failed-then-retried run occurs."""
    case = next(c for c in cases["cases"] if c["id"] == args.only)
    client = make_client(args.model)
    store = ReflectionStore(RAW_DIR / "part3_reflections.jsonl")
    quiet = [logging.getLogger(n) for n in ("agent", "reflexion")]
    if not args.verbose:  # live per-call logging off; the compact summary is printed at the end
        for lg in quiet:
            lg.setLevel(logging.WARNING)
    log.info("model=%s temperature=%s | max retries=%d tool budget=%d token budget=%d",
             client.model, args.temperature, MAX_RETRIES, TOOL_BUDGET, TOKEN_BUDGET)
    passes = 0
    for t in range(1, args.max_tries + 1):
        if args.verbose:
            _banner(case, f"Reflexion demo (try {t})")
        else:
            log.info("running try %d/%d ...", t, args.max_tries)
        out = run_reflexion(case, client, temperature=args.temperature, store=store)
        if out["retries"] > 0 or not args.until_retry or t == args.max_tries:
            break
        passes += 1
    if args.verbose:
        for a in out["attempts"]:
            log.info("--- attempt %d%s", a["attempt"], " (reflection in context)" if a["reflection_in_context"] else "")
            log.info("    tools: %s", _seq(a["result"]))
            log.info("    ANSWER: %s", a["result"]["final_answer"])
            _show_verdict(a["verdict"])
        for rf in out["reflections"]:
            log.info("STORED REFLECTION:\n%s", json.dumps({k: rf[k] for k in ("user_id", "run_id", "attempt",
                                                                             "reflection", "evidence")}, indent=2))
    else:
        _print_compact(case, out, passes)
    for lg in quiet:
        lg.setLevel(logging.NOTSET)


def cmd_compare(args: argparse.Namespace, cases: dict) -> None:
    """Same fixed tasks, same settings: original loop vs Reflexion loop, interleaved per trial."""
    client = make_client(args.model)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("part3_reflections.jsonl", "part3_runs.jsonl", "part3_false_rejections.jsonl"):
        (RAW_DIR / name).write_text("", encoding="utf-8")
    store = ReflectionStore(RAW_DIR / "part3_reflections.jsonl")
    runs_fh = (RAW_DIR / "part3_runs.jsonl").open("a", encoding="utf-8")
    fr_fh = (RAW_DIR / "part3_false_rejections.jsonl").open("a", encoding="utf-8")
    log.info("PART 3 COMPARISON %s | model=%s temperature=%s trials/case=%d | retries<=%d tools<=%d tokens<=%d",
             datetime.now().isoformat(timespec="seconds"), client.model, args.temperature, args.trials,
             MAX_RETRIES, TOOL_BUDGET, TOKEN_BUDGET)
    rows = []
    for trial in range(1, args.trials + 1):
        for case in cases["cases"]:
            # ---- original Part 2 loop: one attempt, judged by the same verifier
            r = run_agent(case["prompt"], client=client, temperature=args.temperature)
            v = verify(case, r)
            oc = oracle_correct(case, r["final_answer"])
            rows.append({"loop": "original", "trial": trial, "case_id": case["id"], "passed": v["passed"],
                         "stop_reason": "success" if v["passed"] else "failed", "retries": 0,
                         "unsupported_claims": len(v["unsupported_claims"]), "tool_calls": r["total_tool_calls"],
                         "tokens": r["tokens"], "latency_ms": r["latency_ms"],
                         "verifier_rejections": int(not v["passed"]), "false_rejections": int(not v["passed"] and oc),
                         "failed_checks": ";".join(c["name"] for c in v["checks"] if not c["passed"]),
                         "final_answer": r["final_answer"][:300]})
            runs_fh.write(json.dumps({"loop": "original", "trial": trial, "case_id": case["id"], "verdict": v,
                                      "oracle_correct": oc, "trace": {k: x for k, x in r.items() if k != "messages"}},
                                     default=str) + "\n")
            if not v["passed"] and oc:
                fr_fh.write(json.dumps({"loop": "original", "trial": trial, "case_id": case["id"],
                                        "answer": r["final_answer"], "checks": v["checks"]}) + "\n")
            log.info("trial %d case %s | original : %s (tools %d, tokens %d)", trial, case["id"],
                     "PASS" if v["passed"] else "FAIL", r["total_tool_calls"], r["tokens"])

            # ---- Reflexion loop
            x = run_reflexion(case, client, temperature=args.temperature, store=store)
            final_v = x["attempts"][-1]["verdict"]
            rejections = sum(1 for a in x["attempts"] if not a["verdict"]["passed"])
            false_rej = [a for a in x["attempts"] if not a["verdict"]["passed"] and a["oracle_correct"]]
            rows.append({"loop": "reflexion", "trial": trial, "case_id": case["id"], "passed": x["passed"],
                         "stop_reason": x["stop_reason"], "retries": x["retries"],
                         "unsupported_claims": len(final_v["unsupported_claims"]), "tool_calls": x["tool_calls"],
                         "tokens": x["tokens"], "latency_ms": x["latency_ms"],
                         "verifier_rejections": rejections, "false_rejections": len(false_rej),
                         "failed_checks": ";".join(c["name"] for c in final_v["checks"] if not c["passed"]),
                         "final_answer": x["final_answer"][:300]})
            runs_fh.write(json.dumps({"loop": "reflexion", "trial": trial, "case_id": case["id"], "run_id": x["run_id"],
                                      "stop_reason": x["stop_reason"],
                                      "attempts": [{"attempt": a["attempt"], "verdict": a["verdict"],
                                                    "oracle_correct": a["oracle_correct"],
                                                    "reflection_in_context": a["reflection_in_context"],
                                                    "trace": {k: y for k, y in a["result"].items() if k != "messages"}}
                                                   for a in x["attempts"]]}, default=str) + "\n")
            for a in false_rej:
                fr_fh.write(json.dumps({"loop": "reflexion", "trial": trial, "case_id": case["id"],
                                        "attempt": a["attempt"], "answer": a["result"]["final_answer"],
                                        "checks": a["verdict"]["checks"]}) + "\n")
            log.info("trial %d case %s | reflexion: %s stop=%s retries=%d (tools %d, tokens %d)", trial, case["id"],
                     "PASS" if x["passed"] else "FAIL", x["stop_reason"], x["retries"], x["tool_calls"], x["tokens"])
    runs_fh.close()
    fr_fh.close()

    with (RAW_DIR / "part3_comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def agg(loop: str) -> dict:
        rs = [r for r in rows if r["loop"] == loop]
        n = len(rs)
        return {
            "success": f"{sum(r['passed'] for r in rs)}/{n} ({sum(r['passed'] for r in rs) / n:.0%})",
            "unsupported": f"{sum(r['unsupported_claims'] for r in rs)} in {sum(r['unsupported_claims'] > 0 for r in rs)}/{n} final answers",
            "retry": f"{sum(r['retries'] > 0 for r in rs)}/{n} ({sum(r['retries'] > 0 for r in rs) / n:.0%}); {sum(r['retries'] for r in rs)} retries total",
            "tools": f"{sum(r['tool_calls'] for r in rs) / n:.2f} avg ({sum(r['tool_calls'] for r in rs)} total)",
            "tokens": f"{sum(r['tokens'] for r in rs) / n:,.0f} avg",
            "latency": f"{sum(r['latency_ms'] for r in rs) / n:,.0f} avg",
            "false_rej": f"{sum(r['false_rejections'] for r in rs)} of {sum(r['verifier_rejections'] for r in rs)} rejections",
        }

    o, x = agg("original"), agg("reflexion")
    labels = [("Task success", "success"), ("Unsupported claims", "unsupported"), ("Retry rate", "retry"),
              ("Tool calls", "tools"), ("Tokens", "tokens"), ("Latency (ms)", "latency"),
              ("Verifier false rejections", "false_rej")]
    lines = [f"### Part 3 - original vs Reflexion ({args.trials} trials x 3 tasks, model {client.model}, "
             f"temperature {args.temperature})", "", "| Metric | Original loop | Reflexion loop |", "|---|---|---|",
             *[f"| {lab} | {o[k]} | {x[k]} |" for lab, k in labels], "",
             "| Task | Original success | Reflexion success | Reflexion stop reasons |", "|---|---|---|---|"]
    for case in cases["cases"]:
        ro = [r for r in rows if r["loop"] == "original" and r["case_id"] == case["id"]]
        rx = [r for r in rows if r["loop"] == "reflexion" and r["case_id"] == case["id"]]
        stops = {}
        for r in rx:
            stops[r["stop_reason"]] = stops.get(r["stop_reason"], 0) + 1
        lines.append(f"| {case['id']} | {sum(r['passed'] for r in ro)}/{len(ro)} | {sum(r['passed'] for r in rx)}/{len(rx)} | "
                     + ", ".join(f"{k} {v}" for k, v in sorted(stops.items())) + " |")
    summary = "\n".join(lines)
    (RAW_DIR / "part3_comparison_summary.md").write_text(summary + "\n", encoding="utf-8")
    log.info("\n%s", summary)
    log.info("raw data: %s", RAW_DIR)


def main() -> None:
    """Parse CLI args and dispatch."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["demo", "compare"])
    p.add_argument("--only", choices=["A", "B", "C"], default="B")
    p.add_argument("--trials", type=int, default=7, help="trials per task (compare)")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--max-tries", type=int, default=5, help="demo: repeat until a retry happens, at most N times")
    p.add_argument("--no-until-retry", dest="until_retry", action="store_false")
    p.add_argument("--verbose", action="store_true", help="demo: print every tool call and the full evidence JSON")
    p.add_argument("--model", default=None)
    args = p.parse_args()
    setup_logging()
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    {"demo": cmd_demo, "compare": cmd_compare}[args.mode](args, cases)


if __name__ == "__main__":
    main()
