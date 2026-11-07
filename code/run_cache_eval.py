"""HW9 Part 2 - run 14 transit questions through the semantic cache and report hit rate + latency.

Mix: new questions, exact duplicates, paraphrases, and "related but different" questions
(same wording pattern, different route/incident - these SHOULD miss; useful for the Part 3 threshold study).

Run from code/ with Redis 8, Kafka and the three HW8 agents running:
    python run_cache_eval.py                    # starts from an empty cache, threshold 0.85
    python run_cache_eval.py --threshold 0.80
    python run_cache_eval.py --version-demo     # also bump the data version and re-ask one question
Writes reports/hw09/raw/part2_cache_eval.json
"""

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from semantic_cache import SemanticCache
from semantic_gateway import CachedQA

RAW = Path(__file__).resolve().parents[1] / "reports" / "hw09" / "raw"

# (category, expected, question)
QUERIES = [
    ("new",        "miss", "A bus on Route 22 broke down at 1st and Santa Clara during the morning rush. What should riders do?"),
    ("new",        "miss", "Why is the Blue Line light rail delayed at Tasman station?"),
    ("new",        "miss", "How do I get a refund if my train was cancelled because of an incident?"),
    ("exact",      "hit",  "A bus on Route 22 broke down at 1st and Santa Clara during the morning rush. What should riders do?"),
    ("paraphrase", "hit",  "What is causing the delays on the Blue Line at Tasman station?"),
    ("new",        "miss", "What safety steps should passengers follow if a train stops between stations?"),
    ("exact",      "hit",  "Why is the Blue Line light rail delayed at Tasman station?"),
    ("paraphrase", "hit",  "My train got cancelled due to an incident. How can I get my money back?"),
    ("related",    "miss", "A bus on Route 64 broke down at Alum Rock station. What should riders do?"),
    ("paraphrase", "hit",  "Route 22 bus broke down at 1st & Santa Clara in the morning rush - what should passengers do?"),
    ("new",        "miss", "How does the transit agency decide the severity level of an incident?"),
    ("paraphrase", "hit",  "If my train stops between stations, what safety steps should I follow?"),
    ("related",    "miss", "Why is the Green Line light rail delayed at Ohlone/Chynoweth station?"),
    ("exact",      "hit",  "How does the transit agency decide the severity level of an incident?"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--keep-cache", action="store_true", help="do not clear the cache first")
    ap.add_argument("--version-demo", action="store_true")
    ap.add_argument("--out", default=str(RAW / "part2_cache_eval.json"))
    args = ap.parse_args()

    cache = SemanticCache(threshold=args.threshold)
    if not args.keep_cache:
        cache.clear()
    qa = CachedQA(cache)

    print(f"=== Semantic cache evaluation | threshold={args.threshold} | {len(QUERIES)} queries | "
          f"embed={cache.embedder.model_name} ===\n")
    rows = []
    for i, (category, expected, question) in enumerate(QUERIES, 1):
        r = qa.ask(question)
        sim = "  n/a " if r["similarity"] is None else f"{r['similarity']:.4f}"
        print(f"[{i:02d}] {category:<10} expected={expected:<4} is_cached={r['is_cached']!s:<5} "
              f"similarity={sim}  latency={r['latency_ms']:>10.1f} ms | {question}")
        if r["is_cached"]:
            print(f"      matched: {r['matched_query']}")
        print(f"      answer : {r['answer'][:160]}{'...' if len(r['answer']) > 160 else ''}\n")
        rows.append({"n": i, "category": category, "expected": expected, **r})

    version_demo = None
    if args.version_demo:
        new_version = cache.bump_data_version("eval: simulated incident data update")
        r = qa.ask(QUERIES[1][2])
        print(f"[version demo] data_version -> {new_version}; re-asked #{2}: is_cached={r['is_cached']} "
              f"latency={r['latency_ms']:.1f} ms (older answers are no longer served)\n")
        version_demo = r

    cached = [r["latency_ms"] for r in rows if r["is_cached"]]
    fresh = [r["latency_ms"] for r in rows if not r["is_cached"]]
    correct = sum((r["is_cached"] and r["expected"] == "hit") or (not r["is_cached"] and r["expected"] == "miss")
                  for r in rows)
    summary = {
        "threshold": args.threshold,
        "queries": len(rows),
        "cache_hits": len(cached),
        "cache_misses": len(fresh),
        "hit_rate_pct": round(100 * len(cached) / len(rows), 1),
        "avg_latency_cached_ms": round(statistics.mean(cached), 2) if cached else None,
        "avg_latency_uncached_ms": round(statistics.mean(fresh), 2) if fresh else None,
        "median_latency_cached_ms": round(statistics.median(cached), 2) if cached else None,
        "median_latency_uncached_ms": round(statistics.median(fresh), 2) if fresh else None,
        "matched_expectation": f"{correct}/{len(rows)}",
    }
    if cached and fresh:
        summary["observed_speedup_x"] = round(summary["avg_latency_uncached_ms"] / summary["avg_latency_cached_ms"], 1)

    print("=== Summary ===")
    print(f"Cache hit rate          : {summary['hit_rate_pct']}% ({len(cached)}/{len(rows)})")
    print(f"Avg latency (cached)    : {summary['avg_latency_cached_ms']} ms")
    print(f"Avg latency (non-cached): {summary['avg_latency_uncached_ms']} ms")
    if "observed_speedup_x" in summary:
        print(f"Observed speed-up       : {summary['observed_speedup_x']}x")
    print(f"Hit/miss as expected    : {summary['matched_expectation']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "summary": summary, "results": rows, "version_demo": version_demo},
                              indent=2, ensure_ascii=False))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
