"""Part 3 - run the same 30-message conversation under several memory settings, ask the
5 probes, and write raw per-turn data, probe scores, METRICS tables and the cost estimate.

Needs MongoDB + Ollama running (same as the API). Run from the code/ folder:
    python scripts/run_memory_experiments.py            # LLM episode extraction (slower)
    python scripts/run_memory_experiments.py --fast     # heuristic extraction (much faster)
    python scripts/run_memory_experiments.py --turns 6  # quick smoke run
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

OUT = ROOT / "reports" / "hw06"
RAW = OUT / "raw"

CONVERSATION = [
    "Hi! My name is Nathan and I commute every weekday from Campbell light rail station.",
    "I ride the Green Line light rail and I usually leave home at 7:15 am.",
    "Please always send me service alerts by email, I never read SMS.",
    "This morning I reported incident INC-2026-104: a bus broke down on Winchester Blvd.",
    "What information should an incident report usually contain?",
    "How do you decide whether a delay is minor or severe?",
    "Can you explain what a congestion index is in our system?",
    "What does the status 'investigating' mean for an incident?",
    "Give me a one-sentence tip for writing a clear incident title.",
    "What is the difference between a bus and a light_rail incident category?",
    "How long should we keep resolved incidents in the database?",
    "Why would a congestion index with linked incidents be impossible to delete?",
    "Last Friday there was a 25 minute subway delay at Market Street station.",
    "Should signal failures be logged as separate incidents or as notes?",
    "What is a reasonable SLA for moving an incident from reported to investigating?",
    "Suggest three fields a dashboard of incidents should show.",
    "How can riders be notified quickly during a major outage?",
    "What is a good way to estimate passenger impact for a delay?",
    "Give an example incident description for a light rail door malfunction.",
    "How should we handle duplicate incident reports from different riders?",
    "What does 'resolved' require before an incident can be closed?",
    "How could weather data help predict congestion?",
    "Summarize best practices for incident codes in one sentence.",
    "What is one risk of storing everything in a single collection?",
    "How would you prioritize two incidents that happen at the same time?",
    "What metrics show whether the incident process is improving?",
    "Give me a short checklist for a night-shift dispatcher.",
    "How can we reduce false-alarm incident reports?",
    "What is one thing to remember when updating an incident's category?",
    "Thanks, that is all the general questions for today.",
]

SETTINGS = [
    {"label": "SHORT_TERM_N=4", "short_term_n": 4, "policy": "none"},
    {"label": "SHORT_TERM_N=12", "short_term_n": 12, "policy": "none"},
    {"label": "SHORT_TERM_N=30", "short_term_n": 30, "policy": "none"},
    {"label": "Compress policy (N=12)", "short_term_n": 12, "policy": "compress"},
]

PRICE_IN, PRICE_OUT = 1.0 / 1_000_000, 5.0 / 1_000_000


class Tee:
    def __init__(self, path):
        self.fh = open(path, "a")

    def __call__(self, msg):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()


def score_probe(reply: str, probe: dict) -> int:
    text = reply.lower()
    matched = sum(1 for crit in probe["criteria"] if any(k.lower() in text for k in crit))
    score = 1 + round(4 * matched / len(probe["criteria"]))
    if any(f.lower() in text for f in probe.get("forbidden", [])):
        score = min(score, 2)
    return score


def mean(xs):
    return round(statistics.mean(xs), 1) if xs else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="heuristic episode extraction")
    ap.add_argument("--turns", type=int, default=30)
    ap.add_argument("--only", default=None, help="run only settings whose label contains this text")
    args = ap.parse_args()

    os.environ["FILE_MEMORY"] = "0"  # measure MongoDB memory only
    os.environ["EXTRACT_MODE"] = "heuristic" if args.fast else "llm"
    import memory_core  # noqa: E402 (after env is set)
    import llm_adapter

    RAW.mkdir(parents=True, exist_ok=True)
    log = Tee(OUT / "RUN_LOG.txt")
    probes = yaml.safe_load((ROOT / "memory_probes.yaml").read_text())["probes"]
    run_id = uuid.uuid4().hex[:6]
    log(f"=== Part 3 experiments run_id={run_id} model={llm_adapter.MODEL} extract={os.environ['EXTRACT_MODE']} "
        f"turns={args.turns} ===")

    summary_rows, all_probe_results = [], {}
    for s in SETTINGS:
        if args.only and args.only not in s["label"]:
            continue
        user_id = f"exp-{run_id}-{s['short_term_n']}-{s['policy']}"
        session_id = f"{user_id}-sess"
        overrides = {"short_term_n": s["short_term_n"], "policy": s["policy"],
                     "log_path": str(RAW / "chat_log.jsonl")}
        rows = []
        log(f"--- {s['label']} user_id={user_id}")
        for i, msg in enumerate(CONVERSATION[:args.turns], 1):
            r = memory_core.chat_turn(user_id, session_id, msg, overrides, run_label=s["label"])
            u = r["usage"]
            rows.append({"setting": s["label"], "turn": i, **{k: u[k] for k in (
                "prompt_tokens", "completion_tokens", "system_primer_tokens", "long_term_tokens",
                "short_term_tokens", "episodic_tokens", "current_message_tokens",
                "model_latency_ms", "request_latency_ms")},
                "short_term_count": r["memory_used"]["short_term_count"],
                "episodes_retrieved": len(r["memory_used"]["episodic_facts"])})
            log(f"{s['label']} turn {i:02d}: prompt={u['prompt_tokens']} completion={u['completion_tokens']} "
                f"window={r['memory_used']['short_term_count']} latency={u['request_latency_ms']}ms")

        probe_results = []
        for p in probes:
            r = memory_core.chat_turn(user_id, session_id, p["question"], overrides, run_label=s["label"] + " probe")
            sc = score_probe(r["reply"], p)
            probe_results.append({"id": p["id"], "question": p["question"], "reply": r["reply"], "score": sc,
                                  "prompt_tokens": r["usage"]["prompt_tokens"],
                                  "episodic_facts": [e["fact"] for e in r["memory_used"]["episodic_facts"]]})
            log(f"{s['label']} probe {p['id']}: score={sc} reply={r['reply'][:120]!r}")
        all_probe_results[s["label"]] = probe_results

        fname = RAW / f"turns_{s['label'].replace(' ', '_').replace('=', '').replace('(', '').replace(')', '')}.csv"
        with fname.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        summary_rows.append({
            "setting": s["label"],
            "mean_prompt_tokens": mean([r["prompt_tokens"] for r in rows]),
            "mean_completion_tokens": mean([r["completion_tokens"] for r in rows]),
            "mean_latency_ms": mean([r["request_latency_ms"] for r in rows]),
            "mean_short_term_tokens": mean([r["short_term_tokens"] for r in rows]),
            "mean_long_term_tokens": mean([r["long_term_tokens"] for r in rows]),
            "mean_episodic_tokens": mean([r["episodic_tokens"] for r in rows]),
            "probe_quality": round(statistics.mean(p["score"] for p in probe_results), 2),
        })

    for row in summary_rows:
        per_conv = args.turns * (row["mean_prompt_tokens"] * PRICE_IN + row["mean_completion_tokens"] * PRICE_OUT)
        row["cost_per_conversation_usd"] = round(per_conv, 6)
        row["cost_10k_conversations_usd"] = round(per_conv * 10_000, 2)

    top = max(r["probe_quality"] for r in summary_rows)
    eligible = [r for r in summary_rows if r["probe_quality"] >= top - 0.5]
    best = min(eligible, key=lambda r: r["cost_10k_conversations_usd"])
    worst = max(summary_rows, key=lambda r: r["cost_10k_conversations_usd"])

    base = next((r for r in summary_rows if r["setting"] == "SHORT_TERM_N=12"), None)
    comp = next((r for r in summary_rows if r["setting"].startswith("Compress")), None)
    comparison = None
    if base and comp:
        comparison = {
            "baseline": base["setting"], "policy": comp["setting"],
            "prompt_tokens_saved_per_turn": round(base["mean_prompt_tokens"] - comp["mean_prompt_tokens"], 1),
            "prompt_token_savings_pct": round(100 * (1 - comp["mean_prompt_tokens"] / base["mean_prompt_tokens"]), 1),
            "probe_quality_change": round(comp["probe_quality"] - base["probe_quality"], 2),
        }

    (RAW / "probe_scores.json").write_text(json.dumps(all_probe_results, indent=2))
    (RAW / "experiment_summary.json").write_text(json.dumps({
        "run_id": run_id, "model": llm_adapter.MODEL, "extract_mode": os.environ["EXTRACT_MODE"],
        "turns": args.turns, "settings": summary_rows, "best": best["setting"], "worst": worst["setting"],
        "eviction_compression_comparison": comparison}, indent=2))

    md = ["# HW6 METRICS (generated by scripts/run_memory_experiments.py)", "",
          f"Model: `{llm_adapter.MODEL}` · episode extraction: {os.environ['EXTRACT_MODE']} · "
          f"turns per run: {args.turns} · run_id {run_id}", "",
          "## Part 3.3/3.4 - memory settings", "",
          "| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |",
          "|---|---|---|---|"]
    md += [f"| {r['setting']} | {r['mean_prompt_tokens']} | {r['mean_latency_ms']} | {r['probe_quality']} |"
           for r in summary_rows]
    md += ["", "### Prompt-token breakdown (mean per turn, approx.)", "",
           "| Setting | Short-term | Long-term summary | Episodic | Completion tokens |", "|---|---|---|---|---|"]
    md += [f"| {r['setting']} | {r['mean_short_term_tokens']} | {r['mean_long_term_tokens']} | "
           f"{r['mean_episodic_tokens']} | {r['mean_completion_tokens']} |" for r in summary_rows]
    if comparison:
        md += ["", "## Part 3.4 - compression policy vs baseline", "",
               f"- Baseline: {comparison['baseline']}; policy: {comparison['policy']}",
               f"- Prompt tokens saved per turn: {comparison['prompt_tokens_saved_per_turn']} "
               f"({comparison['prompt_token_savings_pct']}%)",
               f"- Probe quality change: {comparison['probe_quality_change']:+}"]
    md += ["", "## Part 3.5 - cost of 10,000 conversations ($1/M input, $5/M output)", "",
           "| Setting | Cost / conversation | Cost / 10,000 conversations |", "|---|---|---|"]
    md += [f"| {r['setting']} | ${r['cost_per_conversation_usd']:.4f} | ${r['cost_10k_conversations_usd']:,.2f} |"
           for r in summary_rows]
    md += ["", f"- **Best setting:** {best['setting']} - cheapest setting whose probe quality is within 0.5 "
               f"of the best score ({top}).",
           f"- **Worst setting:** {worst['setting']} - highest cost per conversation.",
           f"- Best vs worst for 10,000 conversations: ${best['cost_10k_conversations_usd']:,.2f} vs "
           f"${worst['cost_10k_conversations_usd']:,.2f}.", ""]
    (OUT / "METRICS.md").write_text("\n".join(md))
    log(f"Wrote {OUT / 'METRICS.md'}; best={best['setting']} worst={worst['setting']}")


if __name__ == "__main__":
    main()
