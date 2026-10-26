# HW7 Metrics - Nathan Pak (SID4 1066)

Configuration: PORT_BASE 8166 · PREFIX s1066 · SEED 1066 · VERIFY_SEED 261066 · DOMAIN_ID 2 · model qwen3:8b (Ollama, local)

## Part 2 - Agent loop reliability

Fixed cases: `reports/hw07/cases/part2_tasks.json` (A, B, C). Raw per-attempt data: `raw/part2_reliability.csv`
(one row per attempt) and `raw/part2_reliability.jsonl` (full traces). Run: 2026-10-25 20:35-20:37,
21 attempts round-robin A/B/C, identical settings (temperature 0.7; limits 8 model calls / 10 tool calls / 2 repairs).


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

**Notes**
- A *call opportunity* is a turn where the model had to produce a tool call (every proposed call, plus any
  turn where it answered in text before calling a tool). *Before repair* = well-formed on the first try;
  *after repair* = well-formed or fixed by the one-shot repair reprompt.
- All 44 calls qwen3:8b emitted through Ollama's native tool-calling were well-formed (correct tool names, valid
  JSON, schema-valid arguments), so the repair path was never triggered in this run; its behaviour is covered
  by `code/tests/test_agent_loop.py` (unknown tool, malformed/invalid arguments, text-when-tool-required,
  repair limit).
- Every failure was a **lost multi-step chain**, all on case B: in 5/7 attempts the model called
  `aggregate_route_stats` and then answered without retrieving a supporting incident, inventing the example
  (e.g. "inc_101 ... a delay of 14 minutes"; the real value is 18). The call-level repair path cannot catch
  this, because each call was valid - it is a task-level failure, which the Part 3 verifier + Reflexion retry targets.

## Part 3 - Original loop vs Reflexion loop

Run 2026-10-25 22:41-22:47; qwen3:8b, temperature 0.7, 7 trials x 3 fixed tasks per loop (interleaved, same settings).
Reflexion bounds: <=2 retries, <=12 tool calls and <=20,000 tokens per task (reflection calls included).
Success = deterministic verifier pass (`code/verifier.py`). Raw data: `raw/part3_comparison.csv` (one row per run),
`raw/part3_runs.jsonl` (traces + per-attempt verdicts), `raw/part3_reflections.jsonl` (4 stored reflections + evidence),
`raw/part3_false_rejections.jsonl` (empty - none observed).

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

**Notes**
- Unsupported claims = answer statements no tool observation supports (an incident ID never returned by a tool, or a
  per-incident delay that contradicts the tool data). All 3 in the original loop were the same Task B failure:
  "inc_101 ... has a delay of 14 minutes" after only `aggregate_route_stats` (true delay: 18).
- Reflexion fixed all 4 failing Task B attempts with exactly one retry each (stop reason `success` for 21/21; no
  `budget_exhausted` or `human_review` was needed). Cost: +0.33 tool calls, +512 tokens and +1.8 s per task on average,
  concentrated in the 4 retried runs (~4,250 tokens each vs ~2,240 for a first-try pass).
- Verifier false rejections: 0. An independent answer-only oracle agreed with the verifier on all 46 judged attempts
  (7 rejections were all genuinely wrong answers; no verifier pass was judged wrong by the oracle either).

