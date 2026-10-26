"""HW7 Part 4 - tools, cost engine and LangGraph agent tests (scripted fake model, local pricing fixture)."""

import json
from pathlib import Path

import pytest

from bikeshare import costs
from bikeshare.agent import DECISIONS, run_bikeshare_agent
from bikeshare.tools import RunContext, calculator, csv_sql, policy_retriever

HEADER = ("ride_id,rideable_type,started_at,ended_at,start_station_name,start_station_id,end_station_name,"
          "end_station_id,start_lat,start_lng,end_lat,end_lng,member_casual\n")
# TEST FIXTURE ONLY - prices taken from Bay Wheels help-center articles, not the real pricing-page snapshot.
PRICING_HTML = """<html><head><script>var x=1;</script></head><body>
<div>Compare plans</div><div>Single ride</div><div>Month pass</div><div>$3.99</div><div>$29/month</div>
<div>Single ride</div><div>$3.99</div>
<div>Classic bike prices</div><div>$3.99 for 30 min, then $0.30/min</div><div>45 min free, then $0.17/min</div>
<div>Ebike prices</div><div>$1.00 unlock + $0.49/min</div><div>Free unlocks + $0.17/min</div>
<div>Month pass</div><div>$29/month</div>
<p>Members get unlimited 45-minute rides on classic bikes, reduced ebike prices and free unlocks.</p></body></html>"""
PRICING = {"membership_monthly_fee": 29, "member_included_minutes": 45, "member_overage_per_min": 0.17,
           "member_ebike_per_min": 0.17, "single_ride_price": 3.99, "single_ride_included_minutes": 30,
           "nonmember_extra_per_min": 0.30, "nonmember_ebike_unlock": 1, "nonmember_ebike_per_min": 0.49}


def make_csv(rides: list[tuple[str, str, int]]) -> str:
    """rides = [(rideable_type, start 'YYYY-MM-DD HH:MM:SS', minutes)]"""
    from datetime import datetime, timedelta
    out = HEADER
    for i, (kind, start, mins) in enumerate(rides):
        s = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        e = s + timedelta(minutes=mins, seconds=-20)
        out += f"R{i},{kind},{s},{e},A,1,B,2,37.7,-122.4,37.8,-122.4,casual\n"
    return out


@pytest.fixture()
def ctx(tmp_path: Path) -> RunContext:
    rides = [("classic_bike", "2025-09-01 08:00:00", 12), ("classic_bike", "2025-09-02 08:00:00", 50),
             ("electric_bike", "2025-09-08 09:00:00", 10)]
    return RunContext(csv_text=make_csv(rides), snapshot_dir=tmp_path / "snap")


def test_csv_sql_select_and_derived_columns(ctx: RunContext) -> None:
    out = csv_sql(ctx, "SELECT COUNT(*) AS n, SUM(is_ebike) AS e, MAX(billed_min) AS mx, COUNT(DISTINCT week_start) AS w FROM trips")
    row = out["data"]["rows"][0]
    assert out["success"] and out["data"]["source"] == "uploaded.csv" and out["data"]["row_count"] == 1
    assert row == {"n": 3, "e": 1, "mx": 50, "w": 2}


@pytest.mark.parametrize("sql", ["DELETE FROM trips", "SELECT 1; DROP TABLE trips", "UPDATE trips SET is_ebike=1",
                                 "PRAGMA table_info(trips)", "ATTACH DATABASE 'x.db' AS x",
                                 "WITH t AS (SELECT 1) INSERT INTO trips(ride_id) SELECT 1"])
def test_csv_sql_is_read_only(ctx: RunContext, sql: str) -> None:
    assert csv_sql(ctx, sql)["success"] is False
    assert csv_sql(ctx, "SELECT COUNT(*) AS n FROM trips")["data"]["rows"][0]["n"] == 3  # table intact


def test_calculator_whitelist() -> None:
    assert calculator("(3.99*2 + 0.3*5)/2", "USD")["data"] == {"value": 4.74, "units": "USD"}
    for bad in ("__import__('os')", "2**10", "abs(-1)", "1e9", "x+1"):
        assert calculator(bad)["success"] is False
    assert calculator("1/0")["error"] == "division by zero"


def test_policy_retriever_snapshot_and_snippets(ctx: RunContext, tmp_path: Path) -> None:
    page = tmp_path / "pricing.html"
    page.write_text(PRICING_HTML)
    out = policy_retriever(ctx, str(page), "monthly membership price included minutes", k=2)
    assert out["success"] and len(out["data"]["passages"]) == 2
    texts = [p["text"] for p in out["data"]["passages"]]
    assert any("$29" in t for t in texts)
    assert all(p["source"] == str(page) and p["score"] > 0 for p in out["data"]["passages"])
    meta = json.loads((ctx.snapshot_dir / "pricing_snapshot_meta.json").read_text())
    assert len(meta["sha256"]) == 64 and "var x" not in (ctx.snapshot_dir / "pricing_snapshot.txt").read_text()
    assert policy_retriever(ctx, "https://invalid.invalid/x", "fee")["success"] is False


def test_cost_engine(ctx: RunContext) -> None:
    res = costs.compute(ctx.db(), PRICING)
    # ppu: 3.99 + (3.99+20*0.30) + (1+10*0.49) = 3.99+9.99+5.90 = 19.88 ; member: 29 + 5*0.17 + 10*0.17 = 31.55
    assert res["pay_per_use_total"] == 19.88 and res["membership_total"] == 31.55
    assert res["cheaper"] == "Pay Per Ride/Minute" and res["months"] == 1 and len(res["weekly"]) == 2
    assert costs.compute(ctx.db(), {})["missing_pricing"]


class FakeClient:
    model = "fake"

    def __init__(self, script: list[dict]) -> None:
        self.script = script
        self.formats: list = []

    def complete(self, messages, tools=None, temperature=0.0, response_format=None) -> dict:
        self.formats.append(response_format)
        step = self.script.pop(0)
        return {**step, "_usage": {"total_tokens": 100}}


def tc(name: str, **args) -> dict:
    return {"tool_calls": [{"function": {"name": name, "arguments": args}}]}


def test_langgraph_agent_end_to_end(tmp_path: Path) -> None:
    page = tmp_path / "pricing.html"
    page.write_text(PRICING_HTML)
    csv_text = make_csv([("electric_bike", f"2025-09-{d:02d} 08:00:00", 25) for d in range(1, 29)])
    final = {"decision": "Buy Monthly Membership", "justification": "Membership is $29 [1] ...",
             "pricing": PRICING, "costs": {"pay_per_use_total": 371.0, "membership_total": 148.0},
             "citations": [{"id": 1, "text": "Monthly Membership: $29/month."}], "assumptions": ["none"]}
    fake = FakeClient([
        tc("policy_retriever", url=str(page), query="monthly membership price"),
        tc("csv_sql", sql="SELECT COUNT(*) AS rides FROM trips"),
        tc("calculator", expression="28*(1+25*0.49)"),
        {"content": "```json\n" + json.dumps(final) + "\n```"},
    ])
    r = run_bikeshare_agent(csv_text, str(page), snapshot_dir=tmp_path / "run", client=fake)
    assert r["decision"] == "Buy Monthly Membership" and r["metrics"]["stop_reason"] == "final_answer"
    assert r["metrics"]["steps"] == 3 and [t["tool"] for t in r["timeline"] if t["type"] == "tool"] == [
        "policy_retriever", "csv_sql", "calculator"]
    assert r["engine_check"]["pay_per_use_total"] == 371.0 and r["engine_check"]["cheaper"] == "Buy Monthly Membership"
    assert r["pricing_snapshots"][0]["sha256"] and (tmp_path / "run" / "pricing_snapshot.txt").exists()


def test_agent_invalid_final_stops_cleanly(tmp_path: Path) -> None:
    fake = FakeClient([{"content": "I think membership."}, {"content": "still not json"}] * 4)
    r = run_bikeshare_agent(make_csv([("classic_bike", "2025-09-01 08:00:00", 5)]), "x", tmp_path, client=fake)
    assert r["metrics"]["stop_reason"] == "invalid_final" and r["decision"] is None


def test_table_rebuilt_from_flattened_pricing_page(tmp_path: Path) -> None:
    lines = ["Compare your options", "Single ride", "Month pass", "$1.00", "$29/month", "Single ride", "$1.00",
             "Classic bike prices", "$1.00 to unlock, then $0.19/min", "45 min free, then $0.17/min",
             "Ebike prices", "$1.00 unlock + $0.49/min", "Free unlocks + $0.17/min", "Month pass", "$29/month",
             "Classic bike prices", "$1.00 to unlock, then $0.19/min", "45 min free, then $0.17/min"]
    page = tmp_path / "flat.txt"
    page.write_text("\n".join(lines) + "\n" + "Lyft Bike offers day passes and single rides so you can ride casually. " * 3)
    ctx = RunContext(csv_text=make_csv([("classic_bike", "2025-09-01 08:00:00", 5)]), snapshot_dir=tmp_path / "s")
    texts = [p["text"] for p in policy_retriever(ctx, str(page), "monthly membership price", k=8)["data"]["passages"]]
    assert ("Month pass ($29/month) - Classic bike prices: 45 min free, then $0.17/min; "
            "Ebike prices: Free unlocks + $0.17/min") in texts
    assert not any("month pass" in t.lower() and "$0.19" in t for t in texts)  # no mixed-column fragments


def _page(tmp_path: Path) -> str:
    page = tmp_path / "pricing.html"
    page.write_text(PRICING_HTML)
    return str(page)


def test_agent_must_use_calculator_before_final(tmp_path: Path) -> None:
    final = {"decision": "Pay Per Ride/Minute", "justification": "x", "pricing": PRICING,
             "costs": {"pay_per_use_total": 3.99, "membership_total": 29}, "citations": []}
    fake = FakeClient([tc("policy_retriever", url=_page(tmp_path), query="single ride and month pass prices", k=5),
                       {"content": json.dumps(final)}, tc("calculator", expression="5*2.77"), {"content": json.dumps(final)}])
    r = run_bikeshare_agent(make_csv([("classic_bike", "2025-09-01 08:00:00", 5)]), "x", tmp_path, client=fake)
    assert r["metrics"]["stop_reason"] == "final_answer"
    repairs = [t for t in r["timeline"] if t["type"] == "repair"]
    assert len(repairs) == 1 and "calculator" in repairs[0]["text"]


def test_text_answer_is_finalized_with_structured_output(tmp_path: Path) -> None:
    final = {"decision": "pay per ride/minute", "justification": "x", "pricing": PRICING,
             "costs": {"pay_per_use_total": 3.99, "membership_total": 29}, "citations": []}
    fake = FakeClient([tc("policy_retriever", url=_page(tmp_path), query="single ride and month pass prices", k=5),
                       tc("calculator", expression="5*2.77"),
                       {"content": "Pay-per-use is cheaper for this rider."},  # prose, not JSON
                       {"content": json.dumps(final)}])                         # schema-constrained finalize
    r = run_bikeshare_agent(make_csv([("classic_bike", "2025-09-01 08:00:00", 5)]), "x", tmp_path, client=fake)
    assert r["metrics"]["stop_reason"] == "final_answer" and r["decision"] == "Pay Per Ride/Minute"
    schema = fake.formats[-1]
    assert isinstance(schema, dict) and schema["properties"]["decision"]["enum"] == list(DECISIONS)


def test_decision_must_match_totals_and_totals_must_match_trips(tmp_path: Path) -> None:
    csv_text = make_csv([("classic_bike", "2025-09-01 08:00:00", 5)])  # engine: pay-per-use 3.99, membership 29
    wrong_total = {"decision": "Pay Per Ride/Minute", "justification": "x", "pricing": PRICING,
                   "costs": {"pay_per_use_total": 1.0, "membership_total": 29}, "citations": []}
    wrong_decision = {**wrong_total, "decision": "Buy Monthly Membership",
                      "costs": {"pay_per_use_total": 3.99, "membership_total": 29}}
    good = {**wrong_total, "costs": {"pay_per_use_total": 3.99, "membership_total": 29}}
    mislabeled = {**good, "pricing": {**PRICING, "nonmember_extra_per_min": 0.17}}  # member rate in a non-member field
    fake = FakeClient([tc("policy_retriever", url=_page(tmp_path), query="single ride and month pass prices", k=5),
                       tc("calculator", expression="3.99"), {"content": json.dumps(mislabeled)},
                       {"content": json.dumps(wrong_total)}, {"content": json.dumps(wrong_decision)},
                       {"content": json.dumps(good)}])
    r = run_bikeshare_agent(csv_text, "x", tmp_path, client=fake)
    repairs = [t["text"] for t in r["timeline"] if t["type"] == "repair"]
    assert "nonmember_extra_per_min = 0.17 does not appear in the single ride snippet" in repairs[0]
    assert "Call calculator with exactly: 1*3.99 + 0*0.3 + 0*1 + 0*0.49" in repairs[1]
    assert "contradicts your own totals" in repairs[2]
    assert r["metrics"]["stop_reason"] == "final_answer" and r["decision"] == "Pay Per Ride/Minute"
