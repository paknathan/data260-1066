### Part 2 reliability (21 attempts, model qwen3:8b, temperature 0.7)

| Metric | Value |
|---|---|
| Attempts (A/B/C round-robin) | 21 |
| Tool-call opportunities | 44 |
| Well-formed call rate - before repair | 44/44 = 100.0% |
| Well-formed call rate - after repair | 44/44 = 100.0% |
| Attempts fully correct on first try | 16/21 |
| Attempts with correct multi-step chain (after repair) | 16/21 |

| Failure type | Count |
|---|---|
| malformed arguments | 0 |
| unknown tool | 0 |
| text when tool required | 0 |
| lost multi step chain | 5 |

| Case | Attempts | Chain OK | Avg tool calls | Avg tokens | Avg latency (ms) |
|---|---|---|---|---|---|
| A | 7 | 7/7 | 2.0 | 2282 | 7348 |
| B | 7 | 2/7 | 1.3 | 1602 | 5847 |
| C | 7 | 7/7 | 3.0 | 3278 | 10165 |
