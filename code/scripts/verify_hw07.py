"""HW7 self-check (smoke test) -> reports/hw07/verification.json.

Starts each part of the system and checks basic behavior objectively (status codes, tool results, row counts),
never exact wording. Uses temporary SQLite / sandbox folders only; it does not modify application code.

From code/:   python scripts/verify_hw07.py          (uses Ollama for the live agent check if it is running)
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
REPO = CODE_DIR.parent
OUT = REPO / "reports" / "hw07" / "verification.json"
TMP = Path(tempfile.mkdtemp(prefix="verify_hw07_"))

# isolated config for the smoke test (temporary SQLite DB, throwaway JWT secret)
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'verify.db'}"
os.environ["JWT_SECRET"] = "verify-hw07-temporary-secret-0123456789abcdef"
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(CODE_DIR / "scripts"))

SID4, SEED, VERIFY_SEED, PORT_BASE = 1066, 1066, 261066, 8166
checks: list[dict] = []


def check(name: str):
    """Decorator: run a check, record pass/fail + detail, never crash the script."""
    def wrap(fn):
        try:
            ok, detail = fn()
        except Exception as exc:  # a crash is a failed check
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return fn
    return wrap


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


# ----------------------------------------------------------------------------- Part 1: JWT + roles
@check("part1_auth_and_roles")
def _():
    from fastapi.testclient import TestClient

    import main
    from security import hash_password
    from sql_db import Role, SessionLocal, UserModel
    db = SessionLocal()
    for u, r in (("v_reader", Role.reader), ("v_writer", Role.writer), ("v_mod", Role.moderator)):
        db.add(UserModel(username=u, password_hash=hash_password("pw-verify"), role=r))
    db.add(main.CongestionIndexModel(id=1, level_name="Low", index_code="CONG-V-1"))
    db.commit()
    db.close()
    c = TestClient(main.app)

    def tok(u: str) -> dict:
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"username": u, "password": "pw-verify"}).json()["access_token"]}
    R, W, M = tok("v_reader"), tok("v_writer"), tok("v_mod")
    body = {"title": "verify", "incident_code": "INC-2026-9999", "delay_minutes": 5, "congestion_index_id": 1}
    got = {
        "login_valid": c.post("/auth/login", json={"username": "v_reader", "password": "pw-verify"}).status_code,
        "login_invalid": c.post("/auth/login", json={"username": "v_reader", "password": "bad"}).status_code,
        "me_no_token": c.get("/auth/me").status_code,
        "me_bad_token": c.get("/auth/me", headers={"Authorization": "Bearer x.y.z"}).status_code,
        "create_reader": c.post("/incidents", json=body, headers=R).status_code,
    }
    created = c.post("/incidents", json=body, headers=W)
    got["create_writer"] = created.status_code
    iid = created.json().get("id")
    got["list_reader"] = c.get("/incidents", headers=R).status_code
    got["delete_writer"] = c.delete(f"/incidents/{iid}", headers=W).status_code
    got["delete_moderator"] = c.delete(f"/incidents/{iid}", headers=M).status_code
    want = {"login_valid": 200, "login_invalid": 401, "me_no_token": 401, "me_bad_token": 401, "create_reader": 403,
            "create_writer": 201, "list_reader": 200, "delete_writer": 403, "delete_moderator": 204}
    return got == want, got


# ----------------------------------------------------------------------------- Part 2: agent loop
def _ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


LIVE = _ollama_up()


@check("part2_agent_loop_task_A" + ("_live" if LIVE else "_scripted"))
def _():
    from agent_loop import check_chain, make_client, run_agent
    case = json.loads((REPO / "reports/hw07/cases/part2_tasks.json").read_text())["cases"][0]
    if LIVE:
        client = make_client()
    else:
        class Scripted:
            model = "scripted"
            steps = [{"tool_calls": [{"function": {"name": "search_incidents", "arguments": {"query": "Route 22"}}}]},
                     {"tool_calls": [{"function": {"name": "get_incident_detail", "arguments": {"incident_id": "inc_101"}}}]},
                     {"content": "inc_101: Mechanical Delay, 18 minutes."}]

            def complete(self, *a, **k):
                return {**self.steps.pop(0), "_usage": {"total_tokens": 0}}
        client = Scripted()
    r = run_agent(case["prompt"], client=client, temperature=0.0)
    ok = r["stop_reason"] == "final_answer" and check_chain(case, r) and r["total_tool_calls"] >= 2
    return ok, {"tools": [c["name"] for c in r["tool_calls"]], "stop_reason": r["stop_reason"], "model": client.model}


@check("part2_error_recovery_nonexistent_id")
def _():
    from agent_tools import execute_tool
    out = execute_tool("get_incident_detail", {"incident_id": "inc_999"})
    return out["ok"] is False and "not found" in out["error"], out["error"]


# ----------------------------------------------------------------------------- Part 3: verifier
@check("part3_verifier_rejects_unsupported_and_accepts_grounded")
def _():
    from agent_tools import execute_tool
    from verifier import verify
    case = json.loads((REPO / "reports/hw07/cases/part2_tasks.json").read_text())["cases"][1]

    def res(calls, ans):
        return {"tool_calls": [{"name": n, "args": a, "ok": True, "result": execute_tool(n, a)} for n, a in calls],
                "final_answer": ans, "stop_reason": "final_answer"}
    agg = ("aggregate_route_stats", {"route_id": "Route 22"})
    bad = verify(case, res([agg], "Average 14.0 minutes; inc_101 had 14 minutes."))["passed"]
    good = verify(case, res([agg, ("search_incidents", {"query": "Route 22"})],
                            "Average 14.0 minutes; inc_101 had a delay of 18 minutes."))["passed"]
    return (not bad) and good, {"invented_example_rejected": not bad, "grounded_answer_accepted": good}


# ----------------------------------------------------------------------------- Part 4: MRKL tools + costs
@check("part4_tools_and_cost_engine")
def _():
    from bikeshare.costs import compute
    from bikeshare.tools import RunContext, calculator, csv_sql, load_trips, policy_retriever
    snap = REPO / "reports/hw07/raw/part4/scenario_membership/pricing_snapshot.txt"
    ctx = RunContext(csv_text=(REPO / "reports/hw07/cases/part4/scenario_membership.csv").read_text(), snapshot_dir=TMP / "s")
    passages = policy_retriever(ctx, str(snap), "monthly membership pricing", 3)["data"]["passages"]
    p = {"membership_monthly_fee": 29, "member_included_minutes": 45, "member_overage_per_min": 0.17,
         "member_ebike_per_min": 0.17, "single_ride_price": 1.0, "single_ride_included_minutes": 0,
         "nonmember_extra_per_min": 0.19, "nonmember_ebike_unlock": 1.0, "nonmember_ebike_per_min": 0.49}
    winners = {n: compute(load_trips((REPO / f"reports/hw07/cases/part4/{n}.csv").read_text()), p)["cheaper"]
               for n in ("scenario_membership", "scenario_paygo")}
    got = {"retriever_finds_month_pass": any("$29/month" in x["text"] for x in passages),
           "csv_sql_select_ok": csv_sql(ctx, "SELECT COUNT(*) AS n FROM trips")["data"]["rows"][0]["n"] == 600,
           "csv_sql_rejects_delete": csv_sql(ctx, "DELETE FROM trips")["success"] is False,
           "calculator": calculator("2*(3+4)")["data"]["value"] == 14,
           "calculator_rejects_code": calculator("__import__('os')")["success"] is False,
           "winners": winners}
    ok = all(v for k, v in got.items() if k != "winners") and winners == {
        "scenario_membership": "Buy Monthly Membership", "scenario_paygo": "Pay Per Ride/Minute"}
    return ok, got


# ----------------------------------------------------------------------------- Part 5: injection defenses
@check("part5_tool_boundary_blocks_compromised_model")
def _():
    from run_attacks_hw07 import CONFIGS, CompromisedModel, build_fixtures

    from bikeshare.agent import run_bikeshare_agent
    fixtures = build_fixtures()
    csv_text = (REPO / "reports/hw07/cases/part4/scenario_membership.csv").read_text()
    out = {}
    for attack in ("sql", "exfil", "override"):
        r = run_bikeshare_agent(csv_text, str(fixtures[attack]), TMP / f"p5_{attack}",
                                client=CompromisedModel(attack, str(fixtures[attack])), **CONFIGS["full"])
        out[attack] = {"rows_after": r["data_integrity"]["rows_after"], "decision": r["decision"]}
    ok = out["sql"]["rows_after"] == 600 and out["exfil"]["decision"] is None and out["override"]["decision"] is None
    return ok, out


# ----------------------------------------------------------------------------- Part 6: file tools + gate
@check("part6_glob_search_read_and_safety_gate")
def _():
    from file_tools import confirm_bash, glob_files, read_file, search_in_files, write_file
    box = TMP / "sandbox"
    box.mkdir()
    for n, t in (("a.py", "x = 1\n"), ("b.py", "DEBUG = True\n"), ("c.py", "y = 2\n")):
        write_file(n, t, root=box)
    found = sorted({m["file"] for m in search_in_files("DEBUG", root=box, file_pattern="*.py")["matches"]})
    integ = len(glob_files("*.py", root=box)["files"]) == 3 and found == ["b.py"] and "DEBUG" in read_file("b.py", box)["content"]
    allow = ["ls -la", "pwd", "cat a.py", "grep -n DEBUG b.py", "python3 --version"]
    block = ["rm -rf ./build", "sudo cat /etc/shadow", "chmod -R 777 .", "dd if=/dev/zero of=/dev/disk2", "echo x > /etc/hosts"]
    gate = sum(confirm_bash(c)["decision"] == "allow" for c in allow) + sum(confirm_bash(c)["decision"] == "block" for c in block)
    return integ and gate == 10, {"debug_file": found, "gate_correct": f"{gate}/10"}


# ----------------------------------------------------------------------------- unit tests
@check("unit_tests_offline")
def _():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_auth_jwt.py", "tests/test_agent_loop.py",
                        "tests/test_reflexion.py", "tests/test_bikeshare.py", "tests/test_attacks.py",
                        "tests/test_file_tools.py"], cwd=CODE_DIR, capture_output=True, text=True)
    last = (p.stdout.strip().splitlines() or ["no output"])[-1]
    return p.returncode == 0, last


commit = git("rev-parse", "HEAD")
result = {
    "homework": 7,
    "sid4": SID4,
    "commit": commit,
    "commit_tags": git("tag", "--points-at", "HEAD").split(),
    "working_tree_clean": git("status", "--porcelain", "--", "code") == "",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "model": {"name": "qwen3:8b (Ollama, local)", "live_agent_check": LIVE, "temperature": 0.0},
    "config": {"PORT_BASE": PORT_BASE, "PREFIX": f"s{SID4}", "DOMAIN_ID": SID4 % 8},
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "checks": checks,
    "summary": {"passed": sum(c["passed"] for c in checks), "total": len(checks),
                "all_passed": all(c["passed"] for c in checks)},
}
OUT.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
print(f"\n{result['summary']['passed']}/{result['summary']['total']} checks passed -> {OUT}")
