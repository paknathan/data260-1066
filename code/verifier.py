"""HW7 Part 3 - deterministic per-task verifier (no model involved).

verify(case, result) runs four checks on a finished run_agent() result:
  1. chain_order     - the case's required tools were executed in order (plus distinct IDs for C)
  2. grounded_ids    - every incident ID named in the answer was actually returned by a tool
  3. grounded_numbers- every "N minutes" attributed to an incident ID matches that incident's real delay
  4. expected_facts  - the answer states the case's expected facts (ID / delay / average / difference)
Unsupported claims = failures of checks 2 and 3 (things stated that no tool observation supports).

oracle_correct(case, answer) is a separate, answer-only check of the expected facts. When the verifier
rejects but the oracle accepts, the run is flagged as a *candidate verifier false rejection* for review.
"""

import re
from typing import Any

from agent_loop import check_chain

ID_RE = re.compile(r"\binc_\d+\b", re.I)
NUM_MIN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?min(?:ute)?s?\b", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
AFTER_COMPARE_RE = re.compile(r"\s*(longer|shorter|more|less|greater|fewer|than|apart|difference)\b", re.I)
# numbers right after these words describe a comparison or aggregate, not one incident's own delay
NOT_PER_INCIDENT_RE = re.compile(r"\b(by|difference|differ\w*|more|less|longer|shorter|average|avg|mean|total|combined|sum)\b[^.;]{0,20}$", re.I)


def _observations(result: dict[str, Any]) -> tuple[dict[str, dict], list[dict]]:
    """Collect incidents (by ID) and aggregate stats that tools actually returned in this run."""
    incidents: dict[str, dict] = {}
    aggregates: list[dict] = []
    for call in result["tool_calls"]:
        out = call["result"]
        if not out.get("ok"):
            continue
        data = out.get("data")
        if call["name"] == "aggregate_route_stats" and isinstance(data, dict):
            aggregates.append(data)
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and "id" in item:
                incidents[item["id"].lower()] = item
    return incidents, aggregates


def _clean(answer: str) -> str:
    """Drop markdown emphasis/backticks so regexes see plain text."""
    return re.sub(r"[*`]+", "", answer or "")


def unsupported_claims(result: dict[str, Any]) -> list[dict[str, Any]]:
    """List answer statements not backed by a tool observation (unknown IDs, wrong per-incident minutes)."""
    answer = _clean(result["final_answer"])
    incidents, _ = _observations(result)
    claims: list[dict[str, Any]] = []
    for inc_id in sorted({m.group(0).lower() for m in ID_RE.finditer(answer)}):
        if inc_id not in incidents:
            claims.append({"kind": "unretrieved_id", "id": inc_id, "detail": f"{inc_id} was never returned by a tool"})
    for sentence in SENTENCE_RE.split(answer):
        for num in NUM_MIN_RE.finditer(sentence):
            before = list(ID_RE.finditer(sentence[: num.start()]))
            if not before:  # e.g. "the average is 14.0 minutes" / "difference is 17 minutes" - not tied to an ID
                continue
            if NOT_PER_INCIDENT_RE.search(sentence[: num.start()]) or AFTER_COMPARE_RE.match(sentence[num.end():]):
                continue  # "longer by 17 minutes", "average 14 minutes", "17 minutes longer than"
            inc_id = before[-1].group(0).lower()  # attribute the number to the nearest preceding ID
            real = incidents.get(inc_id, {}).get("delay_minutes")
            if real is not None and float(num.group(1)) != float(real):
                claims.append({"kind": "wrong_value", "id": inc_id,
                               "detail": f"answer says {inc_id} = {num.group(1)} min, tool data says {real} min"})
    return claims


def _has_num(text: str, value: float) -> bool:
    """True if `value` appears as a number in text (14 matches '14' or '14.0')."""
    return any(float(n) == float(value) for n in re.findall(r"\d+(?:\.\d+)?", text))


def oracle_correct(case: dict[str, Any], answer: str) -> bool:
    """Answer-only check of the case's expected facts (independent of how the agent got there)."""
    text = _clean(answer).lower()
    exp = case.get("expected", {})
    cid = case["id"]
    if cid == "A":
        return exp["incident_id"] in text and _has_num(text, exp["delay_minutes"])
    if cid == "B":  # average stated + one real example with its true delay (from the fixed dataset)
        real = {"inc_101": 18, "inc_103": 10}
        example_ok = any(i in text and _has_num(text, real[i]) for i in exp["example_ids"])
        return _has_num(text, exp["avg_delay_minutes"]) and example_ok
    if cid == "C":
        return all(i in text for i in exp["ids"]) and _has_num(text, exp["difference_minutes"]) \
            and _has_num(text, 42) and _has_num(text, 25)
    return False


def verify(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Run all deterministic checks; `passed` only if every check passes."""
    claims = unsupported_claims(result)
    text = _clean(result["final_answer"]).lower()
    exp = case.get("expected", {})
    if case["id"] == "A":
        facts_ok = exp["incident_id"] in text and _has_num(text, exp["delay_minutes"])
        facts_detail = f"mentions {exp['incident_id']} and {exp['delay_minutes']} min"
    elif case["id"] == "B":
        facts_ok = _has_num(text, exp["avg_delay_minutes"]) and any(i in text for i in exp["example_ids"])
        facts_detail = f"states average {exp['avg_delay_minutes']} and cites one of {exp['example_ids']}"
    elif case["id"] == "C":
        facts_ok = all(i in text for i in exp["ids"]) and exp["longer"] in text and _has_num(text, exp["difference_minutes"])
        facts_detail = f"names {exp['ids']}, longer {exp['longer']}, difference {exp['difference_minutes']} min"
    else:
        facts_ok, facts_detail = True, "no expected facts"
    chain_ok = check_chain(case, result)
    used = " > ".join(c["name"] for c in result["tool_calls"] if c["ok"]) or "(no tools)"
    checks = [
        {"name": "chain_order", "passed": chain_ok,
         "detail": f"required {case['steps']}; executed {used}; stop_reason={result['stop_reason']}"},
        {"name": "grounded_ids", "passed": not any(c["kind"] == "unretrieved_id" for c in claims),
         "detail": "; ".join(c["detail"] for c in claims if c["kind"] == "unretrieved_id") or "all IDs retrieved"},
        {"name": "grounded_numbers", "passed": not any(c["kind"] == "wrong_value" for c in claims),
         "detail": "; ".join(c["detail"] for c in claims if c["kind"] == "wrong_value") or "per-incident minutes match"},
        {"name": "expected_facts", "passed": facts_ok, "detail": facts_detail},
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "unsupported_claims": claims}
