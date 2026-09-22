#summarize_results.py
import pandas as pd
from pathlib import Path

# Paths Setup
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
raw_csv = script_dir.parent / "reports" / "hw03" / "raw" / "retrieval_results.csv"

if not raw_csv.exists():
    raise FileNotFoundError(f"Raw data file non-existent at {raw_csv}. Run chunking_comparison.py first.")

# Load Raw Data
df = pd.read_csv(raw_csv)

print("=" * 80)
print("RECOMPUTED SUMMARY TABLES FROM RAW DATA")
print("=" * 80)

# Summary 1: Metric Averages by Technique
summary_stats = df.groupby("technique").agg(
    avg_cosine_sim=("cosine_sim", "mean"),
    avg_store_score=("store_score", "mean"),
    avg_chunk_len=("chunk_len", "mean"),
    min_chunk_len=("chunk_len", "min"),
    max_chunk_len=("chunk_len", "max"),
    total_retrieved=("rank", "count")
).reset_index()

print("\n--- Summary 1: Aggregate Metrics by Technique ---")
print(summary_stats.to_string(index=False))

# Summary 2: Top Rank Comparison (Rank 1 Results)
top_rank_df = df[df["rank"] == 1][["technique", "store_score", "cosine_sim", "chunk_len", "preview"]]

print("\n--- Summary 2: Top-1 Rank Retrieval Comparison ---")
print(top_rank_df.to_string(index=False))