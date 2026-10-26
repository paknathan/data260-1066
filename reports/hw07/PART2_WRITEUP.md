# Part 2 - Write the Agent Loop

## Implementation

`code/agent_loop.py` implements `run_agent(user_input)` as a hand-written loop (no framework) over the HW1 model adapter (`src/model_client.py`, Ollama `qwen3:8b`) and the three HW5 domain tools (`search_incidents`, `get_incident_detail`, `aggregate_route_stats`). On every iteration the model receives the conversation and the tools' JSON schemas. Each tool call it returns is validated, executed through `execute_tool()`, and appended as a `role: "tool"` message, and the loop continues until the model replies with plain text (`final_answer`) or a hard ceiling is reached: 8 model calls, 10 tool calls, or 2 repair reprompts.

Invalid output gets one specific repair reprompt per bad call:

- an unknown tool name
- arguments that are not valid JSON
- arguments that fail the schema (missing or extra keys, wrong type, empty string)
- a text answer before any tool was called

For example: `REPAIR: unknown tool 'find_incident'. Available tools: [...]`. Once the repair budget is used up, the run stops cleanly with `stop_reason = repair_limit`. Model or network errors stop with `model_error` instead of crashing. Every invocation is logged as `[tool n] name {args}` with its result, and each run ends with a line giving total tool calls, stop reason, iterations, repairs, tokens and latency.

```python
for iteration in range(1, max_iterations + 1):
    try:
        resp = client.complete(messages, tools=TOOL_SCHEMAS, temperature=temperature, response_format=None)
    except Exception as exc:                                  # adapter already retried 3x
        stop_reason, final_answer = "model_error", f"Model call failed: {exc}"
        break
    raw_calls = resp.get("tool_calls") or []
    if not raw_calls:                                         # plain text
        text = _clean_text(resp.get("content", ""))
        if tool_calls:                                        # at least one tool used -> final answer
            final_answer, stop_reason = text, "final_answer"
            break
        _problem("text_when_tool_required", "the model answered in text before calling any tool")
        if repairs_used >= max_repairs:
            final_answer, stop_reason = text, "repair_limit"
            break
        repairs_used += 1
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "REPAIR: You answered without calling a tool ..."}]
        continue
    messages.append({"role": "assistant", "content": "", "tool_calls": echoed})
    for call in raw_calls:
        name, args, problem, kind = parse_tool_call(call)     # unknown tool / bad JSON / schema check
        if problem:
            bad_this_turn = True
            _problem(kind, problem, name, args)
            messages.append({"role": "tool", "tool_name": str(name),
                             "content": json.dumps({"ok": False, "error": f"REPAIR: {problem}. Fix this call and try again."})})
            continue
        logger.info("  [tool %d] %s %s", len(tool_calls) + 1, name, json.dumps(args))
        result = execute_tool(name, args)                     # never raises; returns {ok, data, error}
        tool_calls.append({"name": name, "args": args, "ok": bool(result.get("ok")), "result": result})
        messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)})
    if bad_this_turn:
        if repairs_used >= max_repairs:
            stop_reason = "repair_limit"
            break
        repairs_used += 1
```

## I. Verification tasks - tool-invocation log excerpts

All runs use `qwen3:8b` at temperature 0.0. The full logs are in `reports/hw07/RUN_LOG.txt`, and the fixed cases are in `reports/hw07/cases/part2_tasks.json`. Each task completed from a single prompt with no follow-up prompting.

**Task A - search, then detail-lookup the first result**
```
20:34:05   [tool 1] search_incidents {"query": "Route 22"}            -> ok, 2 result(s)
20:34:07   [tool 2] get_incident_detail {"incident_id": "inc_101"}    -> ok
20:34:11 FINAL ANSWER: The incident with ID inc_101 on Route 22 is a Mechanical Delay with Medium
         severity. It caused an 18-minute delay and has a Resolved status.
20:34:11 total tool calls: 2 | stop_reason: final_answer | iterations: 3 | repairs: 0 | tokens: 2281
         multi-step chain check: PASS
```

**Task B - aggregate question, then one supporting example**
```
20:34:13   [tool 1] aggregate_route_stats {"route_id": "Route 22"}    -> ok
20:34:16   [tool 2] search_incidents {"query": "Route 22"}            -> ok, 2 result(s)
20:34:19 FINAL ANSWER: The average delay on Route 22 is 14.0 minutes. A specific incident that
         supports this answer is inc_101 with a delay of 18 minutes.
20:34:19 total tool calls: 2 | stop_reason: final_answer | iterations: 3 | repairs: 0 | tokens: 2243
         multi-step chain check: PASS
```

**Task C - compare two entities with search plus two detail lookups**
```
20:34:21   [tool 1] search_incidents {"query": "Light Rail"}          -> ok, 2 result(s)
20:34:24   [tool 2] get_incident_detail {"incident_id": "inc_102"}    -> ok
20:34:25   [tool 3] get_incident_detail {"incident_id": "inc_105"}    -> ok
20:34:29 FINAL ANSWER: The Light Rail incident with the longer delay is inc_102 (Blue Line) with a
         delay of 42 minutes, while inc_105 (Green Line) has a delay of 25 minutes. The difference
         in delay is 17 minutes.
20:34:29 total tool calls: 3 | stop_reason: final_answer | iterations: 4 | repairs: 0 | tokens: 3276
         multi-step chain check: PASS
```

[Screenshots: Task A, Task B, Task C]

**Honest note on Task B.** With the original system prompt, Task B failed at temperature 0 (runs at 20:28 and 20:29). The model called `aggregate_route_stats` once, then answered "inc_101 ... has a delay of 14 minutes" without retrieving any incident. The ID was plausible, but the delay was invented: it reused the route average, and inc_101 actually has 18 minutes. The deterministic chain check reported **FAIL** because no `search_incidents` or `get_incident_detail` call followed the aggregate.

I added one general rule to the system prompt: every incident mentioned must come from a tool result in the conversation, aggregate statistics are not an example, and every requested step must be done before answering. After that, Task B passed at temperature 0 (20:31 and 20:34, shown above). The rule is not specific to Task B, and Tasks A and C were re-run with the same prompt.

## II. Error recovery - nonexistent ID

```
20:34:30 USER: Get the full details for incident inc_999.
20:34:31   [tool 1] get_incident_detail {"incident_id": "inc_999"}
                    -> error: Incident with ID 'inc_999' was not found.
20:34:34 FINAL ANSWER: The incident with ID 'inc_999' was not found. Please use the `search_incidents`
         tool to find valid incident IDs in the format 'inc_###'.
20:34:34 total tool calls: 1 | stop_reason: final_answer | iterations: 2 | repairs: 0 | tokens: 1289
```

`execute_tool()` never raises. It returns the tool's `{ok: false, error}` envelope and adds a hint (`Use search_incidents to find valid incident IDs`). The agent passed that message on to the user and stopped normally with `final_answer`, without crashing. The model-failure path is also safe: during the first run (20:25:33) Ollama was not running, and the agent stopped with `stop_reason: model_error` after the adapter's three retries.

[Screenshot: error-recovery case]

## III. Reliability measurement

There were 21 attempts, run round-robin over the three fixed cases (7 each), with identical settings: `qwen3:8b`, temperature 0.7, and limits of 8 model calls, 10 tool calls and 2 repairs. Temperature 0.7 was used, rather than the 0.0 of the screenshot runs, so that repeated attempts could differ; at 0.0 all seven attempts of a case would produce essentially the same output. The raw per-attempt rows are in `reports/hw07/raw/part2_reliability.csv` and the full traces in `raw/part2_reliability.jsonl`.

| Metric | Value |
|---|---|
| Attempts (A/B/C round-robin) | 21 |
| Tool-call opportunities | 44 |
| Well-formed call rate - before repair | 44/44 = 100.0% |
| Well-formed call rate - after repair | 44/44 = 100.0% |
| Attempts fully correct on first try | 16/21 (76.2%) |
| Attempts with correct multi-step chain (after repair) | 16/21 (76.2%) |

| Failure type | Count |
|---|---|
| Malformed arguments | 0 |
| Unknown tool | 0 |
| Text when a tool was required | 0 |
| Lost multi-step chain | 5 |

| Case | Attempts | Chain OK | Avg tool calls | Avg tokens | Avg latency (ms) |
|---|---|---|---|---|---|
| A | 7 | 7/7 | 2.0 | 2282 | 7348 |
| B | 7 | 2/7 | 1.3 | 1602 | 5847 |
| C | 7 | 7/7 | 3.0 | 3278 | 10165 |

**Analysis.** Every tool call `qwen3:8b` produced through Ollama's native tool-calling interface was well-formed: valid tool names, valid JSON, and arguments that passed the schema. The rate is therefore 100% both before and after the repair path, and the repair path was never triggered during the measurement. Its behaviour is instead verified by `code/tests/test_agent_loop.py`, which uses a scripted model to produce each failure type (unknown tool, malformed and schema-invalid arguments, text when a tool was required, and running out of repairs) and checks the reprompt and the clean stop.

All five failures were **lost multi-step chains**, and all of them were on Task B. In each one the model stopped after `aggregate_route_stats` and answered without retrieving a supporting incident. Even with the stricter system prompt, the model still dropped the second step 5 out of 7 times at temperature 0.7, while A and C were 7/7. The call-level repair path cannot catch this failure, because every call that was made was valid; the problem is a step that was never taken. Catching it needs a task-level check of the final result against what the task required, which is the deterministic verifier and Reflexion retry added in Part 3.
