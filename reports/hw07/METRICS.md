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
