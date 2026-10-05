import json
import logging
import sys
from typing import Any, Dict, List, Optional
import urllib.request

# Ensure logs go to stderr to preserve standard JSON outputs
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("agent_part5")

# Mock Dataset for Municipal Transit Incidents
MOCK_DATASET = [
    {
        "id": "inc_101",
        "route_id": "Route 22",
        "mode": "Bus",
        "type": "Mechanical Delay",
        "severity": "Medium",
        "delay_minutes": 18,
        "status": "Resolved",
    },
    {
        "id": "inc_102",
        "route_id": "Blue Line",
        "mode": "Light Rail",
        "type": "Signal Failure",
        "severity": "High",
        "delay_minutes": 42,
        "status": "Active",
    },
    {
        "id": "inc_103",
        "route_id": "Route 22",
        "mode": "Bus",
        "type": "Traffic Congestion",
        "severity": "Low",
        "delay_minutes": 10,
        "status": "Resolved",
    },
    {
        "id": "inc_104",
        "route_id": "Express 500",
        "mode": "Express Bus",
        "type": "Medical Emergency",
        "severity": "High",
        "delay_minutes": 30,
        "status": "Resolved",
    },
    {
        "id": "inc_105",
        "route_id": "Green Line",
        "mode": "Light Rail",
        "type": "Track Maintenance",
        "severity": "Medium",
        "delay_minutes": 25,
        "status": "Active",
    },
]


def envelope(
    ok: bool, data: Optional[Any] = None, error: Optional[str] = None
) -> Dict[str, Any]:
    return {"ok": ok, "data": data, "error": error}


# Domain Tools
def search_incidents(query: str, dataset=MOCK_DATASET) -> Dict[str, Any]:
    q = str(query).strip().lower()
    if not q:
        return envelope(ok=False, data=None, error="Search query cannot be empty.")
    results = [
        inc
        for inc in dataset
        if q in inc["route_id"].lower()
        or q in inc["type"].lower()
        or q in inc["mode"].lower()
    ]
    return envelope(ok=True, data=results, error=None)


def get_incident_detail(incident_id: str, dataset=MOCK_DATASET) -> Dict[str, Any]:
    cid = str(incident_id).strip()
    incident = next((inc for inc in dataset if inc["id"] == cid), None)
    if not incident:
        return envelope(
            ok=False, data=None, error=f"Incident with ID '{cid}' was not found."
        )
    return envelope(ok=True, data=incident, error=None)


def aggregate_route_stats(route_id: str, dataset=MOCK_DATASET) -> Dict[str, Any]:
    croute = str(route_id).strip()
    route_incidents = [
        inc for inc in dataset if inc["route_id"].lower() == croute.lower()
    ]
    if not route_incidents:
        return envelope(
            ok=False, data=None, error=f"No incident logs found for route '{croute}'."
        )
    total_incidents = len(route_incidents)
    total_delay = sum(inc["delay_minutes"] for inc in route_incidents)
    return envelope(
        ok=True,
        data={
            "route_id": route_incidents[0]["route_id"],
            "total_incidents": total_incidents,
            "avg_delay_minutes": round(total_delay / total_incidents, 1),
        },
        error=None,
    )


TOOL_ROUTER = {
    "search_incidents": search_incidents,
    "get_incident_detail": get_incident_detail,
    "aggregate_route_stats": aggregate_route_stats,
}


# =====================================================================
# I. Safety Rule Implementation inside execute_tool
# =====================================================================
def execute_tool(
    name: str, inputs: Dict[str, Any], dataset=MOCK_DATASET
) -> str:
    """Executes domain tools safely with business-logic safety enforcement."""
    try:
        if name not in TOOL_ROUTER:
            return json.dumps(
                envelope(
                    ok=False, data=None, error=f"Unknown tool '{name}'."
                )
            )

        # -------------------------------------------------------------
        # DOMAIN SAFETY RULE:
        # Block queries targeting classified/restricted routes or internal maintenance tags
        # -------------------------------------------------------------
        query_val = str(inputs.get("query", "") or inputs.get("route_id", "")).lower()
        if "restricted" in query_val or "classified" in query_val or "secure_line" in query_val:
            logger.warning(f"Safety Violation: Blocked query access for '{query_val}'")
            return json.dumps(
                envelope(
                    ok=False,
                    data=None,
                    error="Access Denied: Query target violates municipal transit privacy/safety rules.",
                )
            )

        tool_func = TOOL_ROUTER[name]
        res = tool_func(dataset=dataset, **inputs)
        return json.dumps(res)

    except Exception as e:
        return json.dumps(
            envelope(
                ok=False,
                data=None,
                error=f"Execution error on tool '{name}': {str(e)}",
            )
        )


# =====================================================================
# II. Agent Loop & Logging
# =====================================================================
def call_ollama(
    messages: List[Dict[str, str]], model: str = "llama3.2"
) -> str:
    """Sends requests to local Ollama API."""
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode("utf-8"))
        return res["message"]["content"]


SYSTEM_PROMPT = """You are a Municipal Transit AI Assistant.
To call a tool, output JSON in this exact structure:
{
  "action": "tool_call",
  "tool_name": "<search_incidents|get_incident_detail|aggregate_route_stats>",
  "inputs": { ... }
}

When you have sufficient information to answer the user, output:
{
  "action": "final_answer",
  "response": "<your detailed response>"
}
"""


def run_agent(
    user_input: str,
    max_steps: int = 5,
    model_func=call_ollama,
    log_file: str = "agent_runs.jsonl",
) -> Dict[str, Any]:
    """Runs the agent step loop, enforcing turn counts and logging runs."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    step_count = 0
    tool_call_count = 0
    stop_reason = "completed"
    final_response = ""

    while step_count < max_steps:
        step_count += 1
        logger.info(f"--- Step {step_count}/{max_steps} ---")

        try:
            model_out = model_func(messages)
            parsed = json.loads(model_out)
        except Exception as e:
            logger.error(f"Failed to parse LLM JSON: {e}")
            parsed = {
                "action": "final_answer",
                "response": f"Error parsing model output: {str(e)}",
            }

        action = parsed.get("action")

        if action == "tool_call":
            tool_call_count += 1
            t_name = parsed.get("tool_name")
            t_inputs = parsed.get("inputs", {})

            # Execute Tool safely
            tool_result_json = execute_tool(t_name, t_inputs)

            # Log step to file
            log_entry = {
                "step": step_count,
                "user_input": user_input,
                "action": "tool_call",
                "tool_name": t_name,
                "inputs": t_inputs,
                "result": json.loads(tool_result_json),
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

            # Append interaction to chat history
            messages.append({"role": "assistant", "content": model_out})
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool output: {tool_result_json}. Proceed or provide final answer.",
                }
            )

        elif action == "final_answer":
            final_response = parsed.get("response", "")
            stop_reason = "completed"

            # Log final response
            log_entry = {
                "step": step_count,
                "user_input": user_input,
                "action": "final_answer",
                "response": final_response,
                "stop_reason": stop_reason,
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            break

    if step_count >= max_steps and not final_response:
        stop_reason = "max_steps_exceeded"
        final_response = "Agent stopped: Reached maximum allowed execution steps."
        log_entry = {
            "step": step_count,
            "user_input": user_input,
            "stop_reason": stop_reason,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    return {
        "final_response": final_response,
        "step_count": step_count,
        "tool_call_count": tool_call_count,
        "stop_reason": stop_reason,
    }


# =====================================================================
# III. Offline Tests (Mock Model & Safety Assertions)
# =====================================================================
def run_part5_offline_tests():
    print("=========================================================")
    print("         PART 5: OFFLINE TESTS (SAFETY & MOCK AGENT)    ")
    print("=========================================================\n")

    # Test 1: execute_tool blocks call violating safety rule
    blocked_res = json.loads(
        execute_tool("search_incidents", {"query": "secure_line_data"})
    )
    assert blocked_res["ok"] is False, "Expected safety rule block"
    assert "Access Denied" in blocked_res["error"], "Safety error string missing"
    print("Test 1: [PASS] - execute_tool successfully blocks safety-violating call.")

    # Test 2: run_agent stops after reaching max_steps using MockModel
    def mock_infinite_loop_model(messages):
        return json.dumps(
            {
                "action": "tool_call",
                "tool_name": "search_incidents",
                "inputs": {"query": "Route 22"},
            }
        )

    res = run_agent(
        user_input="Loop continuously",
        max_steps=3,
        model_func=mock_infinite_loop_model,
        log_file="test_runs.jsonl",
    )

    assert res["step_count"] == 3, f"Expected 3 steps, got {res['step_count']}"
    assert res["stop_reason"] == "max_steps_exceeded", f"Got {res['stop_reason']}"
    print("Test 2: [PASS] - run_agent correctly terminates on max_steps limit.")

    print("\n---------------------------------------------------------")
    print("SUMMARY: 2/2 Part 5 offline tests passed.")
    print("---------------------------------------------------------\n")


if __name__ == "__main__":
    run_part5_offline_tests()