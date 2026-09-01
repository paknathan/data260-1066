import json
import os
import statistics
import time
from collections import Counter

# Import the pipeline components directly from your existing script
import agents_demo

SAMPLE_TITLE = "Route 22 Bus Breakdown Near Downtown Transit Center"
SAMPLE_CONTENT = (
    "A Route 22 bus experienced a mechanical breakdown near the "
    "Downtown Transit Center during evening rush hour. The engine "
    "stalled at a signal and could not restart, blocking one lane of "
    "traffic. Riders were transferred to the following bus after a "
    "20-minute delay. A maintenance crew towed the disabled vehicle "
    "off-route roughly 45 minutes after the initial report."
)

OUTPUT_DIR = os.path.join("reports", "hw01", "raw")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "per_run_results.json")


def calculate_percentiles(values):
    """Calculates p50, p95, and p99 from a sorted list of values."""
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 0:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def get_percentile(p):
        k = (n - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c < n:
            return sorted_v[f] + (k - f) * (sorted_v[c] - sorted_v[f])
        return sorted_v[f]

    return {
        "p50": round(get_percentile(50), 4),
        "p95": round(get_percentile(95), 4),
        "p99": round(get_percentile(99), 4),
    }


def analyze_temperature_runs(runs_data):
    # 1. Distinct Tag Sets (using frozenset to ignore order differences)
    tag_sets = [frozenset(r["tags"]) for r in runs_data]
    distinct_tag_sets = len(set(tag_sets))

    # 2. Tag frequencies across runs
    all_tags = [tag for r in runs_data for tag in r["tags"]]
    tag_counts = Counter(all_tags)

    tags_in_all = [tag for tag, count in tag_counts.items() if count == 20]
    tags_in_one = [tag for tag, count in tag_counts.items() if count == 1]

    # 3. Latency Metrics
    latencies = [r["latency_seconds"] for r in runs_data]
    percentiles = calculate_percentiles(latencies)

    return {
        "distinct_tag_sets_count": distinct_tag_sets,
        "tags_in_all_20_runs": tags_in_all,
        "tags_in_exactly_one_run": tags_in_one,
        "latency_percentiles": percentiles,
    }


def main():
    temperatures = [0.7, 0.0]
    runs_per_temp = 20
    all_raw_data = []

    print("Starting evaluation runs...")

    for temp in temperatures:
        print(f"\n--- Starting 20 runs at Temperature {temp} ---")
        for run_idx in range(1, runs_per_temp + 1):
            print(f"Run {run_idx}/20 (temp={temp})...")
            start_time = time.perf_counter()

            # Execute the multi-agent pipeline step
            result = agents_demo.run_pipeline(
                SAMPLE_TITLE, SAMPLE_CONTENT, temperature=temp
            )

            latency = time.perf_counter() - start_time

            all_raw_data.append(
                {
                    "run_id": len(all_raw_data) + 1,
                    "temperature": temp,
                    "run_index": run_idx,
                    "tags": result.get("tags", []),
                    "summary": result.get("summary", ""),
                    "latency_seconds": round(latency, 4),
                }
            )

    # Ensure output directory exists and save raw data
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_raw_data, f, indent=2)

    print(f"\nRaw results successfully saved to: {OUTPUT_FILE}\n")

    # Generate and print reports
    print("=" * 60)
    print("EVALUATION METRICS REPORT")
    print("=" * 60)

    for temp in temperatures:
        temp_runs = [r for r in all_raw_data if r["temperature"] == temp]
        metrics = analyze_temperature_runs(temp_runs)

        print(f"\nResults for Temperature {temp}:")
        print(
            f"  • Number of Distinct Tag Sets: {metrics['distinct_tag_sets_count']}"
        )
        print(f"  • Tags in ALL 20 runs: {metrics['tags_in_all_20_runs']}")
        print(
            f"  • Tags in EXACTLY 1 run: {metrics['tags_in_exactly_one_run']}"
        )
        print(
            f"  • Latency p50: {metrics['latency_percentiles']['p50']} seconds"
        )
        print(
            f"  • Latency p95: {metrics['latency_percentiles']['p95']} seconds"
        )
        print(
            f"  • Latency p99: {metrics['latency_percentiles']['p99']} seconds"
        )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()