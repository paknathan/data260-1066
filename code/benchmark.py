# benchmark.py
import requests
import time
import numpy as np
import os

BASE_URL = "http://localhost:8166"

# Login to get session cookie
session = requests.Session()
login_res = session.post(f"{BASE_URL}/login", json={"email": "admin@transit.org", "password": "password123"})
if login_res.status_code != 200:
    print("Login failed. Make sure user exists.")
    exit()

page_sizes = [10, 50, 200]
versions = ["naive", "fixed"]

print("| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |")
print("|-----------|---------|---------------|----------|----------|----------|")

for size in page_sizes:
    for version in versions:
        latencies = []
        endpoint = f"{BASE_URL}/incidents-{version}?limit={size}"
        
        # Determine SQL statements per request
        # Naive: 1 query for main list + N queries for related rows = 1 + size
        # Fixed: 1 JOIN query total = 1
        sql_stmts = (size + 1) if version == "naive" else 1

        for _ in range(30):
            start = time.perf_counter()
            res = session.get(endpoint)
            end = time.perf_counter()
            if res.status_code == 200:
                latencies.append((end - start) * 1000) # Convert to ms

        p50 = np.percentile(latencies, 50)
        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)

        print(f"| {size:<9} | {version:<7} | {sql_stmts:<13} | {p50:<8.2f} | {p95:<8.2f} | {p99:<8.2f} |")