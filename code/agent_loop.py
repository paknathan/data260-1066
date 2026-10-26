"""HW7 Part 2 - hand-written tool-calling agent loop (no framework).

run_agent(user_input) asks the HW1 model adapter for a step, executes any tool calls against the
three HW5 domain tools, appends each result as a role="tool" message, and repeats until the model
gives a final text answer or a hard ceiling is hit. Bad calls (unknown tool, malformed/invalid
arguments, or plain text when a tool was required) get one specific repair reprompt each, with a
bounded total number of repairs.
"""

import importlib.util
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from agent_tools import TOOL_SCHEMAS, execute_tool, parse_tool_call

REPO_ROOT = Path(__file__).resolve().parents[1]

MAX_ITERATIONS = 8   # hard ceiling on model calls per run
MAX_TOOL_CALLS = 10  # hard ceiling on executed tool calls per run
MAX_REPAIRS = 2      # bounded number of repair reprompts per run

SYSTEM_PROMPT = """You are the Municipal Transit Incident assistant for DATA-260 (s1066).
You can ONLY learn facts by calling these tools: search_incidents, get_incident_detail, aggregate_route_stats.
Rules:
- Always call a tool before answering. Never invent incident IDs, routes or numbers.
- Incident IDs look like 'inc_101'; take them from search_incidents results.
- If a later step depends on an earlier result, call the tools one after another.
- Every specific incident you mention (its ID, delay, type, status...) must come from a tool result
  in this conversation. If the user asks for an example or supporting incident, retrieve it with
  search_incidents or get_incident_detail first - aggregate statistics are not an example.
- Do every step the user asks for before giving the final answer.
- When you have enough information, reply in plain text (no tool call) with a short final answer that
  cites the incident IDs and numbers you used. If a tool reports an error, explain it to the user."""

logger = logging.getLogger("agent")


def _load_hw1_adapter() -> Any:
    """Import src/model_client.py (the HW1 adapter) by path so no other model_client.py can shadow it."""
    path = REPO_ROOT / "src" / "model_client.py"
    spec = importlib.util.spec_from_file_location("hw1_model_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_client(model: str | None = None) -> Any:
    """Return a HW1 ModelClient (default model comes from the adapter)."""
    mc = _load_hw1_adapter()
    return mc.ModelClient(model=model) if model else mc.ModelClient()


def _clean_text(text: str) -> str:
    """Strip any <think>...</think> block a reasoning model may still emit."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def run_agent(
    user_input: str,
    client: Any = None,
    temperature: float = 0.0,
    max_iterations: int = MAX_ITERATIONS,
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_repairs: int = MAX_REPAIRS,
    extra_context: list[str] | None = None,
) -> dict[str, Any]:
    """Run the tool loop for one user request and return the answer plus a full trace."""
    client = client or make_client()
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for note in extra_context or []:  # used by Part 3 (reflections); always passed as data, never as system text
        messages.append({"role": "user", "content": note})
    messages.append({"role": "user", "content": user_input})

    tool_calls: list[dict[str, Any]] = []  # executed, well-formed calls
    problems: list[dict[str, Any]] = []    # every bad proposal + whether a later step repaired it
    proposals = 0                          # tool-call opportunities the model was given (calls + text-when-required)
    repairs_used = 0
    tokens = 0
    final_answer = ""
    stop_reason = "max_iterations"
    started = time.perf_counter()
    iteration = 0

    def _problem(kind: str, detail: str, name: Any = None, args: Any = None) -> None:
        problems.append({"type": kind, "detail": detail, "tool": name, "args": args,
                         "iteration": iteration, "executed_before": len(tool_calls)})
        logger.info("  [invalid] %s: %s", kind, detail)

    for iteration in range(1, max_iterations + 1):
        try:
            resp = client.complete(messages, tools=TOOL_SCHEMAS, temperature=temperature, response_format=None)
        except Exception as exc:  # adapter already retried; stop cleanly instead of crashing
            stop_reason = "model_error"
            final_answer = f"Model call failed: {exc}"
            break
        tokens += int(resp.get("_usage", {}).get("total_tokens", 0))
        raw_calls = resp.get("tool_calls") or []

        # ---- no tool call: either a final answer or "text when a tool was required"
        if not raw_calls:
            text = _clean_text(resp.get("content", ""))
            if tool_calls:
                final_answer, stop_reason = text, "final_answer"
                break
            proposals += 1
            _problem("text_when_tool_required", "the model answered in text before calling any tool")
            if repairs_used >= max_repairs:
                final_answer, stop_reason = text, "repair_limit"
                break
            repairs_used += 1
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": (
                "REPAIR: You answered without calling a tool, but this request needs tool data. "
                "Call the appropriate tool now (search_incidents, get_incident_detail or aggregate_route_stats).")})
            continue

        # ---- echo the assistant turn (sanitised so the server can always re-parse it)
        echoed = []
        for c in raw_calls:
            fn = c.get("function", {}) if isinstance(c, dict) else {}
            args = fn.get("arguments")
            echoed.append({"function": {"name": str(fn.get("name")), "arguments": args if isinstance(args, dict) else {}}})
        messages.append({"role": "assistant", "content": "", "tool_calls": echoed})

        bad_this_turn = False
        budget_hit = False
        for call in raw_calls:
            proposals += 1
            name, args, problem, kind = parse_tool_call(call)
            if problem:
                bad_this_turn = True
                _problem(kind, problem, name, args)
                messages.append({"role": "tool", "tool_name": str(name), "content": json.dumps(
                    {"ok": False, "data": None, "error": f"REPAIR: {problem}. Fix this call and try again."})})
                continue
            if len(tool_calls) >= max_tool_calls:
                budget_hit = True
                break
            n = len(tool_calls) + 1
            logger.info("  [tool %d] %s %s", n, name, json.dumps(args))
            t0 = time.perf_counter()
            result = execute_tool(name, args)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            summary = (f"ok, {len(result['data'])} result(s)" if result.get("ok") and isinstance(result.get("data"), list)
                       else "ok" if result.get("ok") else f"error: {result.get('error')}")
            logger.info("           -> %s", summary)
            tool_calls.append({"n": n, "iteration": iteration, "name": name, "args": args,
                               "ok": bool(result.get("ok")), "result": result, "ms": ms})
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)})

        if budget_hit:
            stop_reason = "tool_budget"
            final_answer = "Stopped: tool-call budget exhausted before a final answer."
            break
        if bad_this_turn:
            if repairs_used >= max_repairs:
                stop_reason = "repair_limit"
                final_answer = "Stopped: the model kept producing invalid tool calls after the allowed repairs."
                break
            repairs_used += 1

    for p in problems:  # repaired = a well-formed call was executed after the bad one
        p["repaired"] = len(tool_calls) > p.pop("executed_before")

    return {
        "user_input": user_input,
        "final_answer": final_answer,
        "stop_reason": stop_reason,
        "iterations": iteration,
        "total_tool_calls": len(tool_calls),
        "tool_calls": tool_calls,
        "proposals": proposals,
        "problems": problems,
        "repairs_used": repairs_used,
        "tokens": tokens,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "messages": messages,
    }


def check_chain(case: dict[str, Any], result: dict[str, Any]) -> bool:
    """Deterministic multi-step check: executed tools contain the case's `steps` in order (plus distinct IDs)."""
    names = [c["name"] for c in result["tool_calls"] if c["ok"]]
    i = 0
    for allowed in case["steps"]:
        while i < len(names) and names[i] not in allowed:
            i += 1
        if i == len(names):
            return False
        i += 1
    need = case.get("distinct_detail_ids", 0)
    ids = {c["args"].get("incident_id") for c in result["tool_calls"] if c["name"] == "get_incident_detail" and c["ok"]}
    return len(ids) >= need and result["stop_reason"] == "final_answer"
