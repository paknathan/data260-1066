"""HW6 smoke test -> reports/hw06/verification.json   (run: make verify-hw06)

Uses the running server on PORT_BASE if there is one; otherwise starts uvicorn itself
(DATABASE_URL must be exported, same as for normal runs) and stops it afterwards.
Only temporary data is created (one test document, a verify-<VERIFY_SEED> chat user);
application code is never modified.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SID4 = 1066
PORT_BASE = 8000 + SID4 % 900
SEED, VERIFY_SEED = SID4, 260000 + SID4
BASE = f"http://127.0.0.1:{PORT_BASE}"
OUT = ROOT / "reports" / "hw06" / "verification.json"


def call(method, path, body=None, timeout=240):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def server_up():
    try:
        return call("GET", "/openapi.json", timeout=3)[0] == 200
    except Exception:
        return False


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def main():
    checks = []

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as exc:  # a crashing check is a failed check
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} - {detail}")

    proc = None
    if not server_up():
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT_BASE)],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        for _ in range(40):
            if server_up():
                break
            time.sleep(0.5)

    try:
        check(f"backend responds on PORT_BASE {PORT_BASE}", lambda: (server_up(), f"GET {BASE}/openapi.json"))

        state = {}

        def crud():
            body = {"title": f"verify {VERIFY_SEED}", "description": "smoke test", "category": "bus",
                    "event_time": "2026-10-19T08:00:00"}
            s, doc = call("POST", "/api/items", body)
            if s != 201:
                return False, f"create -> {s} {doc}"
            iid = doc["_id"]
            steps = [("get", call("GET", f"/api/items/{iid}")[0], 200),
                     ("list", call("GET", "/api/items")[0], 200),
                     ("put", call("PUT", f"/api/items/{iid}", {**body, "status": "resolved"})[0], 200),
                     ("delete", call("DELETE", f"/api/items/{iid}")[0], 204),
                     ("get-after-delete", call("GET", f"/api/items/{iid}")[0], 404)]
            return all(a == b for _, a, b in steps), "; ".join(f"{n}={a}" for n, a, _ in steps)
        check("Part 1 CRUD on /api/items (201/200/200/204/404)", crud)

        def validation():
            bad = [{"title": "x" * 101, "category": "bus", "event_time": "2026-10-19T08:00:00"},
                   {"title": "ok", "category": "ferry", "event_time": "2026-10-19T08:00:00"},
                   {"title": "ok", "category": "bus"},
                   {"title": "ok", "category": "bus", "event_time": "not-a-date"}]
            codes = [call("POST", "/api/items", b)[0] for b in bad]
            return all(c == 422 for c in codes), f"invalid payload status codes {codes}"
        check("Part 1 validation errors return 422", validation)
        check("Part 1 bad ObjectId returns 400", lambda: (call("GET", "/api/items/123")[0] == 400, "GET /api/items/123"))

        uid = f"verify-{VERIFY_SEED}"

        def chat():
            s, r = call("POST", "/api/chat", {"user_id": uid, "message": "Hi, my name is Verify and I ride the bus."})
            if s != 200:
                return False, f"status {s}: {r}"
            state["session"] = r["session_id"]
            ok = bool(r.get("reply")) and {"short_term_count", "episodic_facts"} <= set(r["memory_used"])
            return ok, f"reply chars={len(r['reply'])}, prompt_tokens={r['usage']['prompt_tokens']}"
        check("Part 2 POST /api/chat returns a reply + memory_used", chat)

        def memory():
            s, r = call("GET", f"/api/memory/{uid}")
            ok = s == 200 and {"recent_messages", "latest_session_summary", "latest_lifetime_summary",
                                "episodic_facts"} <= set(r)
            return ok, f"status {s}, messages={len(r.get('recent_messages', [])) if isinstance(r, dict) else '?'}"
        check("Part 2 GET /api/memory/{user_id}", memory)

        def aggregate():
            s, r = call("GET", f"/api/aggregate/{uid}")
            return s == 200 and "daily_message_counts" in r, f"status {s}"
        check("Part 2 GET /api/aggregate/{user_id}", aggregate)

        def help_cmd():
            s, r = call("POST", "/api/chat", {"user_id": uid, "message": "/help"})
            return s == 200 and "/compact" in r.get("reply", ""), f"status {s}"
        check("Part 4 /help command via /api/chat", help_cmd)

        def consolidation():
            sys.path.insert(0, str(ROOT / "scripts"))
            import file_memory
            from make_memory_fixture import build
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "MEMORY.md"
                p.write_text(build())
                before = len(p.read_text().splitlines())
                rep = file_memory.consolidate_file(p)
                after = len(p.read_text().splitlines())
            ok = before == 55 and after < 40 and len(rep["contradictions_resolved"]) >= 3
            return ok, f"temp MEMORY.md {before} -> {after} lines, {len(rep['contradictions_resolved'])} contradictions"
        check("Part 4 consolidation (temp copy) 55 -> <40 lines", consolidation)
    finally:
        if proc:
            proc.terminate()

    try:
        import llm_adapter
        model = llm_adapter.MODEL
    except Exception:
        model = os.getenv("OLLAMA_MODEL", "unknown")
    result = {
        "homework": 6, "sid4": SID4, "port_base": PORT_BASE,
        "commit": git("rev-parse", "HEAD"), "tag_hw6_commit": git("rev-list", "-n", "1", "hw6"),
        "model": model, "embed_model": os.getenv("EMBED_MODEL", "nomic-embed-text"),
        "config": {"SHORT_TERM_N": os.getenv("SHORT_TERM_N", "12"),
                   "SUMMARIZE_EVERY_USER_MSGS": os.getenv("SUMMARIZE_EVERY_USER_MSGS", "4"),
                   "MEMORY_POLICY": os.getenv("MEMORY_POLICY", "none")},
        "seed": SEED, "verify_seed": VERIFY_SEED,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "passed": sum(c["passed"] for c in checks), "total": len(checks),
        "all_passed": all(c["passed"] for c in checks),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(f"\n{result['passed']}/{result['total']} checks passed -> {OUT}")
    sys.exit(0 if result["all_passed"] else 1)


if __name__ == "__main__":
    main()
