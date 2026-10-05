import os
import json
import time
import random
import numpy as np
import pandas as pd

VERIFY_SEED = 42
RATES = [0.0, 0.2, 0.5]
CALLS_PER_RATE = 50
OS_DIR = "reports/hw05/raw"

os.makedirs(OS_DIR, exist_ok=True)

def simulated_api_call(failure_rate: float, rng: random.Random):
    """Simulates API latency + injected failures."""
    base_latency = rng.uniform(0.02, 0.05) # 20-50ms nominal
    time.sleep(base_latency)
    
    if rng.random() < failure_rate:
        raise ConnectionError("Injected failure")
    return {"ok": True, "data": "success", "error": None}

def run_experiment(failure_rate: float):
    rng = random.Random(VERIFY_SEED)
    records = []
    
    for call_id in range(1, CALLS_PER_RATE + 1):
        start_t = time.time()
        success = False
        attempts = 0
        max_retries = 3
        delay = 0.05
        
        while attempts < max_retries:
            attempts += 1
            try:
                res = simulated_api_call(failure_rate, rng)
                success = True
                break
            except Exception:
                if attempts < max_retries:
                    time.sleep(delay)
                    delay *= 2.0
                    
        total_latency = (time.time() - start_t) * 1000.0  # ms
        records.append({
            "call_id": call_id,
            "failure_rate": failure_rate,
            "success": success,
            "attempts": attempts,
            "latency_ms": total_latency
        })
        
    df = pd.DataFrame(records)
    df.to_csv(f"{OS_DIR}/calls_rate_{int(failure_rate*100)}.csv", index=False)
    
    return {
        "failure_rate": f"{int(failure_rate*100)}%",
        "success_rate": f"{(df['success'].mean() * 100):.1f}%",
        "mean_latency": round(df["latency_ms"].mean(), 2),
        "p99_latency": round(np.percentile(df["latency_ms"], 99), 2)
    }

results = [run_experiment(r) for r in RATES]