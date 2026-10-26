# AI_USE.md - HW7 (Nathan Pak, SID4 1066)

## 1. What I used an AI assistant for, and what I did myself

I used Claude (an AI assistant) heavily on this homework. It drafted most of the new code:

- Part 1: the JWT auth module, role checks, MySQL users migration, and the Ruff/pre-commit config.
- Part 2: the hand-written agent loop and the tool schemas.
- Part 3: the deterministic verifier and the Reflexion loop.
- Part 4: the LangGraph ReAct agent, the three MRKL tools, the cost engine, and the UI.
- Part 5: the attack runner and defenses.
- Part 6: the file tools and safety gate.

It also drafted the pytest files, the run scripts, and first drafts of the report sections.

What I did myself:

- Ran every experiment on my own machine (local Ollama qwen3:8b, my MySQL database, live Bay Wheels pricing page and trip data) and took all the screenshots.
- Did the Ruff/pre-commit lint demo, git commits, and tagging.
- Chose the city (Bay Wheels) and the scenarios.
- Reviewed the outputs and reported each failure back so it could be fixed.
- Decided how to report negative results honestly. Task B failed 5/7 in Part 2. In Part 5, the live model ignored two of the injections, and one attack got past my first defense.

All numbers in the report come from my own runs (RUN_LOG.txt and reports/hw07/raw/), not from the assistant.

## 2. One AI-produced output that was wrong or unsuitable

The first version of the Part 4 policy_retriever was wrong. It converted the Lyft pricing page to text line by line, which split the plan comparison table ("$29/month", "45 min free, then $0.17/min", ...) into fragments that were too short to keep. The agent therefore never saw the real prices. qwen3:8b invented them from marketing text ("less than a dollar a day"), produced "$30/month" and "$0.19 overage", and in the pay-per-use scenario its totals implied the wrong plan.

Other AI mistakes I hit:

- main.py crashed when started with `python main.py`, because the module was imported twice.
- The first test setup failed with plain `pytest` (no conftest.py).
- A verifier heuristic wrongly rejected comparisons like "longer by 17 minutes".
- The agent accepted a decision that contradicted its own computed totals.

## 3. How I detected the problem

The UI shows the agent's own calculator totals next to an independent deterministic "engine check" that applies the cited prices to every trip. In my first runs the two columns disagreed badly: $833 vs $4,769 pay-per-use. The engine even said membership was cheaper in the scenario where the agent said pay-per-use.

I opened the saved pricing snapshot (reports/hw07/raw/part4/.../pricing_snapshot.txt) and compared it with what policy_retriever had returned. The real prices were in the snapshot, but not in any retrieved passage. That showed the bug was in retrieval, not in the model.

## 4. What I changed, and why it works now

1. The retriever now rebuilds the flattened pricing table into one quotable snippet per plan, using only the page's own cell text, for example "Month pass ($29/month) - Classic bike prices: 45 min free, then $0.17/min; Ebike prices: Free unlocks + $0.17/min". It drops the leftover fragments that mixed different plans' prices.
2. The agent may not finish until three things hold:
   - it has used the calculator
   - every price appears in the snippet for the right plan
   - its totals match the cited prices applied to the trips, and its decision matches its totals

   Otherwise it gets a specific repair message, such as an exact calculator expression.
3. The final answer is produced with Ollama structured output (a JSON schema), so the decision can only be one of the two allowed values.

It works now because the agent receives correct, citable prices, and any arithmetic or reasoning error is caught by code rather than trusted. After the fix both scenarios were correct and matched the engine check exactly:

| Scenario | Membership | Pay-per-use | Decision |
|---|---|---|---|
| Membership scenario | $1,698.57 | $5,767.90 | membership |
| Pay-per-use scenario | $3,016.00 | $1,435.23 | pay-per-use |

The final runs are in raw/part4/scenario_*/result.json, with the same snapshot SHA-256 for both. tests/test_bikeshare.py now includes a test that replays this exact failure.
