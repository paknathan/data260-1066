import json
import traceback
from typing import Any, Dict, Optional

# =====================================================================
# Fixture / Dependency Injection Strategy (Item 24)
# Offline mock dataset replacing any network or database dependencies
# =====================================================================
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
]


def envelope(ok: bool, data: Optional[Any] = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Standard envelope formatting helper."""
    return {"ok": ok, "data": data, "error": error}


# =====================================================================
# Domain Tools Implementation (Dependency Injected for Offline Testing)
# =====================================================================
def search_incidents(query: str, dataset=MOCK_DATASET) -> Dict[str, Any]:
    cleaned_query = str(query).strip().strip('"').strip("'")
    if not cleaned_query:
        return envelope(ok=False, data=None, error="Search query cannot be empty.")

    q = cleaned_query.lower()
    results = [
        inc
        for inc in dataset
        if q in inc["route_id"].lower()
        or q in inc["type"].lower()
        or q in inc["mode"].lower()
    ]
    return envelope(ok=True, data=results, error=None)


def get_incident_detail(incident_id: str, dataset=MOCK_DATASET) -> Dict[str, Any]:
    cid = str(incident_id).strip().strip('"').strip("'")
    if not cid:
        return envelope(ok=False, data=None, error="incident_id parameter is required.")

    incident = next((inc for inc in dataset if inc["id"] == cid), None)
    if not incident:
        return envelope(ok=False, data=None, error=f"Incident with ID '{cid}' was not found.")

    return envelope(ok=True, data=incident, error=None)


def aggregate_route_stats(route_id: str, dataset=MOCK_DATASET) -> Dict[str, Any]:
    croute = str(route_id).strip().strip('"').strip("'")
    if not croute:
        return envelope(ok=False, data=None, error="route_id parameter is required.")

    route_incidents = [inc for inc in dataset if inc["route_id"].lower() == croute.lower()]
    if not route_incidents:
        valid_routes = sorted(list({inc["route_id"] for inc in dataset}))
        return envelope(
            ok=False,
            data=None,
            error=f"No incident logs found for route '{croute}'. Valid routes: {valid_routes}",
        )

    total_incidents = len(route_incidents)
    total_delay = sum(inc["delay_minutes"] for inc in route_incidents)
    avg_delay = total_delay / total_incidents
    active_count = sum(1 for inc in route_incidents if inc["status"] == "Active")

    stats = {
        "route_id": route_incidents[0]["route_id"],
        "total_incidents": total_incidents,
        "active_incidents": active_count,
        "avg_delay_minutes": round(avg_delay, 1),
        "total_delay_minutes": total_delay,
    }
    return envelope(ok=True, data=stats, error=None)


# Map tool names to internal functions
TOOL_ROUTER = {
    "search_incidents": search_incidents,
    "get_incident_detail": get_incident_detail,
    "aggregate_route_stats": aggregate_route_stats,
}


# =====================================================================
# Item 22: Safe Entry Point
# =====================================================================
def execute_tool(name: str, inputs: Dict[str, Any]) -> str:
    """Single entry point for agent tool calls.
    
    Executes domain tools safely without crashing, returning a JSON string envelope.
    """
    try:
        if name not in TOOL_ROUTER:
            res = envelope(
                ok=False,
                data=None,
                error=f"Unknown tool '{name}'. Available tools: {list(TOOL_ROUTER.keys())}",
            )
            return json.dumps(res)

        tool_func = TOOL_ROUTER[name]
        res = tool_func(**inputs)
        return json.dumps(res)

    except TypeError as te:
        # Handles missing or unexpected parameters gracefully
        res = envelope(ok=False, data=None, error=f"Invalid arguments for tool '{name}': {str(te)}")
        return json.dumps(res)

    except Exception as e:
        # Catch-all safety guard to prevent server crashes
        res = envelope(
            ok=False,
            data=None,
            error=f"Unhandled internal error during tool execution: {str(e)}",
        )
        return json.dumps(res)


# =====================================================================
# Item 23 & 24: Offline Test Runner using `assert`
# =====================================================================
def run_tests():
    tests = []

    # --- Test 1: search_incidents (Valid Input) ---
    def test_search_valid():
        raw_res = execute_tool("search_incidents", {"query": "Route 22"})
        res = json.loads(raw_res)
        assert res["ok"] is True, f"Expected ok=True, got {res}"
        assert res["error"] is None, f"Expected error=None, got {res['error']}"
        assert len(res["data"]) == 2, f"Expected 2 matches, got {len(res['data'])}"

    tests.append(("search_incidents - Valid input ('Route 22')", test_search_valid))

    # --- Test 2: search_incidents (Invalid Input - Part 3 Empty Query) ---
    def test_search_invalid():
        raw_res = execute_tool("search_incidents", {"query": ""})
        res = json.loads(raw_res)
        assert res["ok"] is False, f"Expected ok=False, got {res}"
        assert res["data"] is None, "Expected data to be None"
        assert "Search query cannot be empty" in res["error"], f"Unexpected error: {res['error']}"

    tests.append(("search_incidents - Invalid input (empty string)", test_search_invalid))

    # --- Test 3: get_incident_detail (Valid Input) ---
    def test_detail_valid():
        raw_res = execute_tool("get_incident_detail", {"incident_id": "inc_101"})
        res = json.loads(raw_res)
        assert res["ok"] is True, f"Expected ok=True, got {res}"
        assert res["data"]["id"] == "inc_101", "Returned incorrect incident ID"
        assert res["error"] is None

    tests.append(("get_incident_detail - Valid input ('inc_101')", test_detail_valid))

    # --- Test 4: get_incident_detail (Invalid Input - Part 3 Not Found) ---
    def test_detail_invalid():
        raw_res = execute_tool("get_incident_detail", {"incident_id": "inc_999"})
        res = json.loads(raw_res)
        assert res["ok"] is False, f"Expected ok=False, got {res}"
        assert res["data"] is None
        assert "Incident with ID 'inc_999' was not found" in res["error"]

    tests.append(("get_incident_detail - Invalid input ('inc_999')", test_detail_invalid))

    # --- Test 5: aggregate_route_stats (Valid Input) ---
    def test_aggregate_valid():
        raw_res = execute_tool("aggregate_route_stats", {"route_id": "Route 22"})
        res = json.loads(raw_res)
        assert res["ok"] is True, f"Expected ok=True, got {res}"
        assert res["data"]["total_incidents"] == 2
        assert res["data"]["avg_delay_minutes"] == 14.0

    tests.append(("aggregate_route_stats - Valid input ('Route 22')", test_aggregate_valid))

    # --- Test 6: aggregate_route_stats (Invalid Input - Part 3 Non-existent Route) ---
    def test_aggregate_invalid():
        raw_res = execute_tool("aggregate_route_stats", {"route_id": "Purple Line"})
        res = json.loads(raw_res)
        assert res["ok"] is False, f"Expected ok=False, got {res}"
        assert res["data"] is None
        assert "No incident logs found for route 'Purple Line'" in res["error"]

    tests.append(("aggregate_route_stats - Invalid input ('Purple Line')", test_aggregate_invalid))

    # --- Execute All Tests & Log Summary ---
    passed = 0
    total = len(tests)

    print("=========================================================")
    print("           PART 4: OFFLINE TEST RUNNER RESULTS          ")
    print("=========================================================\n")

    for idx, (name, test_func) in enumerate(tests, 1):
        try:
            test_func()
            print(f"Test {idx}/{total}: [PASS] - {name}")
            passed += 1
        except AssertionError as ae:
            print(f"Test {idx}/{total}: [FAIL] - {name}")
            print(f"   Reason: {ae}")
        except Exception as e:
            print(f"Test {idx}/{total}: [FAIL] - {name} (Unhandled exception)")
            print(f"   Reason: {e}")

    print("\n---------------------------------------------------------")
    print(f"SUMMARY: {passed}/{total} tests passed.")
    print("---------------------------------------------------------")


if __name__ == "__main__":
    run_tests()