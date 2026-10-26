"""HW7 Part 2 - agent loop tests with a scripted fake model (no Ollama needed)."""

import json
from typing import Any

from agent_loop import check_chain, run_agent
from agent_tools import execute_tool, parse_tool_call, validate_args


def call(name: str, args: Any) -> dict:
    return {"function": {"name": name, "arguments": args}}


class FakeClient:
    """Returns scripted responses in order; records the messages it was sent."""

    model = "fake"

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools=None, temperature=0.0, response_format=None) -> dict:
        self.seen.append(json.loads(json.dumps(messages)))
        step = self.script.pop(0) if self.script else {"content": "done"}
        if isinstance(step, Exception):
            raise step
        return {**step, "_usage": {"total_tokens": 10}}


CASE_A = {"steps": [["search_incidents"], ["get_incident_detail"]]}
CASE_C = {"steps": [["search_incidents"], ["get_incident_detail"], ["get_incident_detail"]], "distinct_detail_ids": 2}


def test_happy_path_two_step_chain() -> None:
    fake = FakeClient([
        {"tool_calls": [call("search_incidents", {"query": "Route 22"})]},
        {"tool_calls": [call("get_incident_detail", {"incident_id": "inc_101"})]},
        {"content": "inc_101 is a Mechanical Delay of 18 minutes."},
    ])
    r = run_agent("A", client=fake)
    assert r["stop_reason"] == "final_answer" and r["total_tool_calls"] == 2
    assert [c["name"] for c in r["tool_calls"]] == ["search_incidents", "get_incident_detail"]
    assert r["problems"] == [] and check_chain(CASE_A, r)
    tool_msgs = [m for m in fake.seen[-1] if m["role"] == "tool"]  # results appended as tool-role messages
    assert len(tool_msgs) == 2 and json.loads(tool_msgs[1]["content"])["data"]["id"] == "inc_101"


def test_unknown_tool_is_repaired_once() -> None:
    fake = FakeClient([
        {"tool_calls": [call("find_incident", {"q": "x"})]},
        {"tool_calls": [call("search_incidents", {"query": "Blue Line"})]},
        {"content": "ok"},
    ])
    r = run_agent("x", client=fake)
    assert r["problems"][0]["type"] == "unknown_tool" and r["problems"][0]["repaired"]
    assert r["repairs_used"] == 1 and r["stop_reason"] == "final_answer"
    repair_msg = fake.seen[1][-1]
    assert repair_msg["role"] == "tool" and "unknown tool 'find_incident'" in repair_msg["content"]


def test_malformed_and_schema_invalid_arguments() -> None:
    assert parse_tool_call(call("search_incidents", "{bad json"))[3] == "malformed_arguments"
    assert "missing required" in validate_args("get_incident_detail", {"id": "inc_101"})
    assert "must be a string" in validate_args("search_incidents", {"query": 5})
    assert "unexpected" in validate_args("search_incidents", {"query": "a", "limit": 3})
    assert parse_tool_call(call("search_incidents", '{"query": "Bus"}'))[2] is None  # JSON string is fine


def test_text_when_tool_required_gets_reprompted() -> None:
    fake = FakeClient([
        {"content": "The average delay is probably 20 minutes."},
        {"tool_calls": [call("aggregate_route_stats", {"route_id": "Route 22"})]},
        {"content": "14.0 minutes"},
    ])
    r = run_agent("avg?", client=fake)
    assert r["problems"][0]["type"] == "text_when_tool_required" and r["problems"][0]["repaired"]
    assert "REPAIR" in fake.seen[1][-1]["content"]


def test_repair_limit_stops_cleanly() -> None:
    fake = FakeClient([{"tool_calls": [call("nope", {})]}] * 10)
    r = run_agent("x", client=fake, max_repairs=2)
    assert r["stop_reason"] == "repair_limit" and r["total_tool_calls"] == 0
    assert len(r["problems"]) == 3 and not any(p["repaired"] for p in r["problems"])


def test_nonexistent_id_returns_useful_message() -> None:
    out = execute_tool("get_incident_detail", {"incident_id": "inc_999"})
    assert out["ok"] is False and "not found" in out["error"] and "search_incidents" in out["hint"]
    fake = FakeClient([
        {"tool_calls": [call("get_incident_detail", {"incident_id": "inc_999"})]},
        {"content": "Incident inc_999 does not exist."},
    ])
    r = run_agent("details for inc_999", client=fake)
    assert r["stop_reason"] == "final_answer" and r["tool_calls"][0]["ok"] is False


def test_hard_iteration_ceiling_and_model_error() -> None:
    loop = FakeClient([{"tool_calls": [call("search_incidents", {"query": "Bus"})]}] * 20)
    r = run_agent("x", client=loop, max_iterations=4)
    assert r["stop_reason"] == "max_iterations" and r["total_tool_calls"] == 4
    r = run_agent("x", client=FakeClient([RuntimeError("ollama down")]))
    assert r["stop_reason"] == "model_error" and "ollama down" in r["final_answer"]


def test_chain_check_requires_two_distinct_details() -> None:
    fake = FakeClient([
        {"tool_calls": [call("search_incidents", {"query": "Light Rail"})]},
        {"tool_calls": [call("get_incident_detail", {"incident_id": "inc_102"}),
                        call("get_incident_detail", {"incident_id": "inc_102"})]},
        {"content": "same one twice"},
    ])
    assert not check_chain(CASE_C, run_agent("C", client=fake))
