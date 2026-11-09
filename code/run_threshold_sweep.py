"""HW9 Part 3.2-3.4 - threshold sweep + cost model over the 40 labeled cases in cache_cases.yaml.

Method (same cache contents for every threshold, so results do not depend on question order):
  1. Clear the cache, answer the 10 seeds with the HW8 agent pipeline, store them. These are the
     only cache entries during the sweep; case answers are never written back to the cache.
  2. For each of the 40 cases: embed + KNN-1 search (timed = lookup latency), record the best seed
     and its cosine similarity.
  3. Run the HW8 agent pipeline once for every case that could miss (similarity below the highest
     threshold) and for every should-miss case. This gives each case's measured miss latency and
     the pipeline's own answer for it (the "correct answer" used in 3.3).
  4. For each threshold: hit = similarity >= threshold. A hit is correct only if the case is
     labeled `hit` AND the matched entry is its own seed; every other hit is a false hit.
     latency = lookup (hit) or lookup + agent (miss).
     total cost = misses * MISS_COST + false_hits * FALSE_HIT_COST.

Agent answers are saved to reports/hw09/raw/part3_agent_runs.json and reused on re-runs (--fresh to redo).

Run from code/ with Redis 8, Kafka and the three HW8 agents running:
    python run_threshold_sweep.py
    python run_threshold_sweep.py --miss-cost 0.01 --false-hit-cost 5
"""

import argparse
import csv
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

import semantic_gateway
from semantic_cache import SemanticCache

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "reports" / "hw09" / "raw"
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]

# ---- cost model (3.4) -----------------------------------------------------------------------
# MISS_COST: one run of the 3-agent pipeline = 3 qwen3:8b calls, ~18-32 s of local compute per
#   question in Part 2 (~23 s average), plus the rider waiting ~20 s. Priced like ~3 hosted
#   LLM calls (~2-3k tokens total) plus the compute/wait -> $0.01 per miss.
# FALSE_HIT_COST: a rider receives the answer to a DIFFERENT incident (wrong line, wrong
#   direction, fire treated as a breakdown). Typical outcome is a missed trip and a customer
#   service contact; a contact-centre call is commonly costed at ~$5, and safety cases are
#   worse -> $5.00 per false hit. One false hit therefore costs as much as 500 misses.
MISS_COST = 0.01
FALSE_HIT_COST = 5.00


def ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


class AgentRuns:
    """Run the real HW8 pipeline once per query; persist answers + latency for re-runs."""

    def __init__(self, path: Path, fresh: bool):
        self.path = path
        self.data = {} if fresh or not path.exists() else json.loads(path.read_text())

    def get(self, query: str) -> dict:
        if query not in self.data:
            t = time.perf_counter()
            final = semantic_gateway.run_agent_pipeline(query)
            self.data[query] = {"answer": final.get("answer", ""), "status": final.get("status"),
                                "agent_ms": ms(t),
                                "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
            print(f"      agent run: {self.data[query]['agent_ms'] / 1000:.1f}s status={final.get('status')}")
        return self.data[query]


def load_cases(path: Path) -> tuple[list[dict], list[dict]]:
    doc = yaml.safe_load(path.read_text())
    seeds, cases = doc["seeds"], doc["cases"]
    counts = {c: sum(1 for x in cases if x["category"] == c) for c in ("exact", "paraphrase", "similar", "unrelated")}
    assert len(cases) == 40 and all(n == 10 for n in counts.values()), f"expected 4 x 10 cases, got {counts}"
    return seeds, cases


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HERE / "cache_cases.yaml"))
    ap.add_argument("--miss-cost", type=float, default=MISS_COST)
    ap.add_argument("--false-hit-cost", type=float, default=FALSE_HIT_COST)
    ap.add_argument("--fresh", action="store_true", help="ignore saved agent runs and re-run the pipeline")
    args = ap.parse_args()

    seeds, cases = load_cases(Path(args.cases))
    runs = AgentRuns(RAW / "part3_agent_runs.json", args.fresh)
    cache = SemanticCache()
    cache.clear()
    version = cache.data_version()
    cache.embed("warm-up")  # load the model before anything is timed

    print(f"=== Seeding cache with {len(seeds)} answers from the HW8 pipeline (data_version={version}) ===")
    seed_by_query = {}
    for s in seeds:
        print(f"  {s['id']}: {s['query']}")
        r = runs.get(s["query"])
        cache.store(s["query"], cache.embed(s["query"]), r["answer"], version, seed_id=s["id"])
        seed_by_query[s["query"]] = s
    seed_answer = {s["id"]: runs.get(s["query"])["answer"] for s in seeds}

    print(f"\n=== Looking up {len(cases)} labeled cases ===")
    top = max(THRESHOLDS)
    for c in cases:
        t = time.perf_counter()
        vec = cache.embed(c["query"])
        entry, sim = cache.search(vec, version)
        c["lookup_ms"] = ms(t)
        c["similarity"] = round(sim, 4) if sim is not None else 0.0
        c["matched_seed"] = seed_by_query[entry["query"]]["id"] if entry else None
        c["matched_query"] = entry["query"] if entry else None
        print(f"  {c['id']} {c['category']:<10} expected={c['expected']:<4} best={c['matched_seed']} "
              f"sim={c['similarity']:.4f} lookup={c['lookup_ms']:.1f}ms | {c['query']}")
        if c["expected"] == "miss" or c["similarity"] < top:
            r = runs.get(c["query"])
            c["agent_ms"], c["own_answer"] = r["agent_ms"], r["answer"]

    # ---- sweep -----------------------------------------------------------------------------
    rows, false_hits = [], {}
    for th in THRESHOLDS:
        hits = fh = missed = 0
        lat, fh_cases = [], []
        for c in cases:
            hit = c["similarity"] >= th
            correct = hit and c["expected"] == "hit" and c["matched_seed"] == c.get("seed")
            if hit:
                hits += 1
                lat.append(c["lookup_ms"])
                if not correct:
                    fh += 1
                    fh_cases.append(c)
            else:
                missed += c["expected"] == "hit"
                lat.append(c["lookup_ms"] + c["agent_ms"])
        misses = len(cases) - hits
        cost = misses * args.miss_cost + fh * args.false_hit_cost
        rows.append({"threshold": th, "hits": hits, "hit_rate_pct": round(100 * hits / len(cases), 1),
                     "false_hits": fh, "false_hit_rate_pct": round(100 * fh / hits, 1) if hits else 0.0,
                     "false_hits_per_query_pct": round(100 * fh / len(cases), 1),
                     "missed_should_hit": missed, "misses": misses,
                     "mean_latency_ms": round(statistics.mean(lat), 1),
                     "miss_cost": round(misses * args.miss_cost, 2),
                     "false_hit_cost": round(fh * args.false_hit_cost, 2), "total_cost": round(cost, 2)})
        false_hits[th] = [c["id"] for c in fh_cases]

    best = min(rows, key=lambda r: (r["total_cost"], -r["threshold"]))  # tie -> stricter threshold

    print(f"\n=== Threshold sweep (40 cases; miss=${args.miss_cost:.2f}, false hit=${args.false_hit_cost:.2f}) ===")
    hdr = "| Threshold | Hit rate | False-hit rate | Mean latency (ms) | Total cost |"
    lines = [hdr, "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['threshold']:.2f} | {r['hit_rate_pct']}% ({r['hits']}/40) | "
                     f"{r['false_hit_rate_pct']}% ({r['false_hits']}/{r['hits']} hits) | {r['mean_latency_ms']:,.1f} | "
                     f"${r['total_cost']:.2f} ({r['misses']} misses ${r['miss_cost']:.2f} + "
                     f"{r['false_hits']} false hits ${r['false_hit_cost']:.2f}) |")
    table = "\n".join(lines)
    print(table)
    for r in rows:
        print(f"  {r['threshold']:.2f}: false hits={false_hits[r['threshold']] or '-'}  "
              f"should-hit cases missed={r['missed_should_hit']}")
    print(f"\nLowest total cost: threshold {best['threshold']:.2f} (${best['total_cost']:.2f})")

    # ---- 3.3 false-hit details ------------------------------------------------------------
    by_id = {c["id"]: c for c in cases}
    fh_ids = sorted({i for ids in false_hits.values() for i in ids}, key=lambda i: -by_id[i]["similarity"])
    md = ["# Part 3.3 - false hits (all thresholds)\n"]
    for i in fh_ids:
        c = by_id[i]
        at = [f"{t:.2f}" for t in THRESHOLDS if i in false_hits[t]]
        md += [f"## {c['id']} ({c['category']}, similarity {c['similarity']:.4f}) - false hit at {', '.join(at)}\n",
               f"- **Incoming query:** {c['query']}",
               f"- **Cached query matched ({c['matched_seed']}):** {c['matched_query']}",
               f"- **Similarity:** {c['similarity']:.4f}",
               f"- **Cached answer returned:** {seed_answer[c['matched_seed']]}",
               f"- **Correct answer (HW8 pipeline run on the incoming query):** {c.get('own_answer', '(not run)')}",
               f"- **Why the answers differ (label):** {c.get('why_different', 'unrelated question')}\n"]
    if not fh_ids:
        md.append("No false hits at any threshold.\n")

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "part3_false_hits.md").write_text("\n".join(md), encoding="utf-8")
    (RAW / "part3_threshold_table.md").write_text(table + "\n", encoding="utf-8")
    with (RAW / "part3_sweep.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (RAW / "part3_sweep.json").write_text(json.dumps({
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_version": version,
        "embed_model": cache.embedder.model_name, "miss_cost": args.miss_cost, "false_hit_cost": args.false_hit_cost,
        "rows": rows, "false_hits": {f"{k:.2f}": v for k, v in false_hits.items()},
        "lowest_cost_threshold": best["threshold"],
        "cases": [{k: c.get(k) for k in ("id", "category", "expected", "seed", "query", "matched_seed",
                                         "matched_query", "similarity", "lookup_ms", "agent_ms")} for c in cases],
    }, indent=2, ensure_ascii=False))
    print(f"\nsaved {RAW / 'part3_sweep.json'}, part3_sweep.csv, part3_threshold_table.md, part3_false_hits.md")


if __name__ == "__main__":
    main()
