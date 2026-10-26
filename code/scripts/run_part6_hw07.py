"""HW7 Part 6 - one combined test run: (a) glob -> search -> read integration test in a temporary
course sandbox, (b) the 10-command safety-gate test (5 pass / 5 blocked), including the false allow
found with the first deny-list and the fix.

From code/:  python scripts/run_part6_hw07.py
Writes reports/hw07/raw/part6_safety_gate.json and appends the output to reports/hw07/RUN_LOG.txt.
"""

import json
import logging
import re
import sys
import tempfile
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(CODE_DIR / "scripts"))

from run_agent_hw07 import setup_logging  # noqa: E402

from file_tools import (  # noqa: E402
    SAFE_PREFIXES,
    bash,
    confirm_bash,
    edit_file,
    glob_files,
    is_destructive,
    read_file,
    search_in_files,
    write_file,
)

RAW = CODE_DIR.parent / "reports" / "hw07" / "raw"
log = logging.getLogger("hw07.part6")

# First version of the deny-list (kept to show the false allow it produced): it only looked at the
# command name, so a SAFE_PREFIXES command that redirects into a system path slipped through.
V1_DENY = re.compile(r"\brm\s+-[a-z]*r|\bsudo\b|\bchmod\b|\bchown\b|\bdd\b.*of=/dev/|\bmkfs")

COMMANDS = [  # (command, expected)
    ("ls -la", "allow"),
    ("pwd", "allow"),
    ("cat app.py", "allow"),
    ("grep -n DEBUG utils.py", "allow"),
    ("python3 --version", "allow"),
    ("rm -rf ./build", "block"),
    ("sudo cat /etc/shadow", "block"),
    ("chmod -R 777 .", "block"),
    ("dd if=/dev/zero of=/dev/disk2 bs=1m", "block"),
    ("echo 'pwned' > /etc/hosts", "block"),
]


def v1_confirm(command: str) -> str:
    """The original gate: v1 deny-list, then SAFE_PREFIXES."""
    if V1_DENY.search(command):
        return "block"
    return "allow" if any(command == p or command.startswith(p + " ") for p in SAFE_PREFIXES) else "block"


def main() -> None:
    setup_logging()
    log.info("=" * 78)
    log.info("Nathan Pak (s1066) | HW7 Part 6 | file tools + safety gate (pure Python, no model)")
    out: dict = {}
    with tempfile.TemporaryDirectory(prefix="data260_hw07_sandbox_") as sandbox:
        log.info("sandbox: %s", sandbox)
        # ---------------- (a) integration test
        files = {"app.py": "def main():\n    print('hello')\n",
                 "utils.py": "DEBUG = True\n\ndef helper(x):\n    if DEBUG:\n        print('debug', x)\n    return x * 2\n",
                 "models.py": "class Incident:\n    pass\n"}
        for name, text in files.items():
            write_file(name, text, root=sandbox)
        instruction = "Find the Python file that contains DEBUG and show its contents."
        log.info("(a) INSTRUCTION: %s", instruction)
        g = glob_files("*.py", root=sandbox)
        log.info("  1. glob_files('*.py') -> %s", g["files"])
        s = search_in_files("DEBUG", root=sandbox, file_pattern="*.py")
        hits = sorted({m["file"] for m in s["matches"]})
        log.info("  2. search_in_files('DEBUG', file_pattern='*.py') -> %d match(es) in %s: %s", s["count"], hits,
                 [f"{m['file']}:{m['line']}" for m in s["matches"]])
        r = read_file(hits[0], root=sandbox, max_lines=20)
        log.info("  3. read_file('%s', max_lines=20) -> %d lines:\n%s", hits[0], r["total_lines"],
                 "\n".join("       " + ln for ln in r["content"].splitlines()))
        e = edit_file("utils.py", "DEBUG = True", "DEBUG = False", root=sandbox)
        log.info("  edit_file('utils.py', 'DEBUG = True' -> 'DEBUG = False') diff:\n%s",
                 "\n".join("       " + ln for ln in e["diff"].splitlines()))
        b = bash("ls", root=sandbox)
        log.info("  bash('ls') -> ran=%s stdout=%s", b["ran"], b["stdout"].split())
        escape = read_file("../../etc/passwd", root=sandbox)
        log.info("  read_file('../../etc/passwd') -> %s", escape["error"])
        out["integration"] = {"glob": g["files"], "search_hits": s["matches"], "read": r["content"],
                              "found": hits, "edit_diff": e["diff"], "sandbox_escape_blocked": not escape["ok"]}
        ok_a = hits == ["utils.py"] and "DEBUG = True" in r["content"]
        log.info("  RESULT (a): %s", "PASS - found utils.py" if ok_a else "FAIL")

        # ---------------- (b) safety-gate test
        log.info("(b) SAFETY GATE - first deny-list (v1):")
        false_allows = []
        for cmd, expected in COMMANDS:
            got = v1_confirm(cmd)
            flag = "" if got == expected else "   <-- FALSE ALLOW" if got == "allow" else "   <-- FALSE BLOCK"
            if got == "allow" and expected == "block":
                false_allows.append(cmd)
            log.info("    %-38s expected=%-5s v1=%s%s", cmd, expected, got, flag)
        log.info("  v1 false allows: %s -> fix: add an independent 'redirection to root path' deny rule "
                 "(>/>> or tee into /...), checked before SAFE_PREFIXES, and refuse chained commands as 'safe'",
                 false_allows)
        log.info("(b) SAFETY GATE - final confirm_bash(command, auto_approve=False):")
        rows, passed = [], 0
        for cmd, expected in COMMANDS:
            res = confirm_bash(cmd)
            ok = res["decision"] == expected
            passed += ok
            rows.append({"command": cmd, "expected": expected, "is_destructive": is_destructive(cmd), **res,
                         "correct": ok, "v1_decision": v1_confirm(cmd)})
            log.info("    %-38s is_destructive=%-5s -> %-5s %s | %s", cmd, is_destructive(cmd), res["decision"].upper(),
                     "OK" if ok else "WRONG", res["reason"])
        confirmed = confirm_bash("rm -rf ./build", auto_approve=True)
        log.info("  explicit confirmation: confirm_bash('rm -rf ./build', auto_approve=True) -> %s (%s)",
                 confirmed["decision"], confirmed["reason"])
        allowed = sum(r["decision"] == "allow" for r in rows)
        log.info("  RESULT (b): %d/10 correct | %d allowed, %d blocked | false allows: 0 (v1 had %d: %s)",
                 passed, allowed, len(rows) - allowed, len(false_allows), false_allows)
        out["safety_gate"] = {"safe_prefixes": SAFE_PREFIXES, "results": rows, "v1_false_allows": false_allows,
                              "confirmed_example": confirmed, "correct": passed}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "part6_safety_gate.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("saved raw/part6_safety_gate.json")


if __name__ == "__main__":
    main()
