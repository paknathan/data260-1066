### Part 3 - original vs Reflexion (7 trials x 3 tasks, model qwen3:8b, temperature 0.7)

| Metric | Original loop | Reflexion loop |
|---|---|---|
| Task success | 18/21 (86%) | 21/21 (100%) |
| Unsupported claims | 3 in 3/21 final answers | 0 in 0/21 final answers |
| Retry rate | 0/21 (0%); 0 retries total | 4/21 (19%); 4 retries total |
| Tool calls | 2.19 avg (46 total) | 2.52 avg (53 total) |
| Tokens | 2,471 avg | 2,983 avg |
| Latency (ms) | 8,689 avg | 10,535 avg |
| Verifier false rejections | 0 of 3 rejections | 0 of 4 rejections |

| Task | Original success | Reflexion success | Reflexion stop reasons |
|---|---|---|---|
| A | 7/7 | 7/7 | success 7 |
| B | 4/7 | 7/7 | success 7 |
| C | 7/7 | 7/7 | success 7 |
