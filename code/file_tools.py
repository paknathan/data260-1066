"""HW7 Part 6 - sandboxed file tools and a pure-Python bash safety gate (no model needed).

File tools resolve every path inside a sandbox root and refuse anything that escapes it.
bash() runs only what confirm_bash() allows: destructive commands (is_destructive) are blocked unless
explicit confirmation is given, even when they start with a SAFE_PREFIXES entry.
"""

import difflib
import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- safety gate
SAFE_PREFIXES: tuple[str, ...] = (
    "ls", "pwd", "cat", "head", "tail", "wc", "grep", "find", "echo", "python --version", "python3 --version",
    "git status", "git log", "git diff", "date", "whoami", "uname",
)

_DESTRUCTIVE: list[tuple[str, re.Pattern[str]]] = [
    ("recursive deletion", re.compile(
        r"\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*\b|.*\s-[a-zA-Z]*[rR][a-zA-Z]*\b|.*--recursive\b)|\bfind\b.*\s-delete\b"
        r"|\bfind\b.*-exec\s+rm\b")),
    ("privilege escalation", re.compile(r"(^|[;&|(]\s*|\s)(sudo|su|doas|pkexec)(\s|$)")),
    ("permission/ownership change", re.compile(r"(^|[;&|(]\s*|\s)(chmod|chown|chgrp|chattr|setfacl)\s")),
    ("raw-device write", re.compile(r"\bdd\b.*\bof=/dev/|>\s*/dev/(?!null\b|stdout\b|stderr\b)\w|\bshred\b")),
    ("filesystem creation", re.compile(r"\b(mkfs(\.\w+)?|mke2fs|newfs(_\w+)?|mkswap)\b|\bdiskutil\s+(erase|partition)\w*",
                                       re.I)),
    ("redirection to root path", re.compile(r">>?\s*/(?!dev/null\b|tmp/)\S*|\btee\s+(-a\s+)?/(?!dev/null\b|tmp/)")),
]


def is_destructive(command: str) -> bool:
    """True if the command matches any deny-list category (checked independently of SAFE_PREFIXES)."""
    return destructive_reason(command) is not None


def destructive_reason(command: str) -> str | None:
    """Name of the first deny-list category the command matches, else None."""
    cmd = " ".join(str(command or "").split())
    for name, pattern in _DESTRUCTIVE:
        if pattern.search(cmd):
            return name
    return None


def _matches_safe_prefix(command: str) -> bool:
    cmd = " ".join(command.split())
    if re.search(r"[;&|`]|\$\(", cmd):  # chained / substituted commands are never "safe by prefix"
        return False
    return any(cmd == p or cmd.startswith(p + " ") for p in SAFE_PREFIXES)


def confirm_bash(command: str, auto_approve: bool = False) -> dict[str, Any]:
    """Decide whether a shell command may run: {'decision': 'allow'|'block', 'allowed': bool, 'reason': str}."""
    if not isinstance(command, str) or not command.strip():
        return {"decision": "block", "allowed": False, "reason": "empty command"}
    danger = destructive_reason(command)
    if danger:
        if auto_approve:
            return {"decision": "allow", "allowed": True, "reason": f"destructive ({danger}) - explicitly confirmed"}
        return {"decision": "block", "allowed": False,
                "reason": f"destructive: {danger}; requires explicit confirmation (even if it matches SAFE_PREFIXES)"}
    if _matches_safe_prefix(command):
        return {"decision": "allow", "allowed": True, "reason": "matches SAFE_PREFIXES allow-list"}
    if auto_approve:
        return {"decision": "allow", "allowed": True, "reason": "not on allow-list - explicitly confirmed"}
    return {"decision": "block", "allowed": False, "reason": "not on SAFE_PREFIXES allow-list; needs confirmation"}


# --------------------------------------------------------------------------- sandboxed file tools
def _resolve(root: str | Path, path: str | Path) -> Path:
    """Resolve path inside root; raise ValueError if it escapes the sandbox."""
    base = Path(root).resolve()
    target = (base / path).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"path '{path}' is outside the sandbox {base}")
    return target


def read_file(path: str, root: str | Path, max_lines: int | None = None) -> dict[str, Any]:
    """Read a text file; with max_lines, return only the first N lines (and say if truncated)."""
    try:
        p = _resolve(root, path)
        lines = p.read_text(encoding="utf-8").splitlines()
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    shown = lines if max_lines is None else lines[: max(0, int(max_lines))]
    return {"ok": True, "path": str(path), "content": "\n".join(shown), "total_lines": len(lines),
            "truncated": len(shown) < len(lines)}


def write_file(path: str, content: str, root: str | Path) -> dict[str, Any]:
    """Create or overwrite a text file inside the sandbox."""
    try:
        p = _resolve(root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": str(path), "bytes": len(content.encode("utf-8"))}


def edit_file(path: str, old: str, new: str, root: str | Path, max_diff_lines: int = 12) -> dict[str, Any]:
    """Replace exactly one occurrence of `old` with `new`; return a short unified diff."""
    try:
        p = _resolve(root, path)
        before = p.read_text(encoding="utf-8")
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    count = before.count(old)
    if count != 1:
        return {"ok": False, "error": f"old text must occur exactly once (found {count})"}
    after = before.replace(old, new, 1)
    p.write_text(after, encoding="utf-8")
    diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", n=1, lineterm=""))
    return {"ok": True, "path": str(path), "diff": "\n".join(diff[:max_diff_lines])}


def glob_files(pattern: str, root: str | Path) -> dict[str, Any]:
    """List files under the sandbox matching a glob pattern (e.g. '*.py', '**/*.py')."""
    base = Path(root).resolve()
    files = sorted(str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file())
    return {"ok": True, "pattern": pattern, "files": files, "count": len(files)}


def search_in_files(query: str, root: str | Path, file_pattern: str = "*", regex: bool = False) -> dict[str, Any]:
    """Search text in files whose name matches file_pattern; return file, line number and line text."""
    base = Path(root).resolve()
    rx = re.compile(query if regex else re.escape(query))
    matches = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or not fnmatch.fnmatch(p.name, file_pattern):
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line):
                    matches.append({"file": str(p.relative_to(base)), "line": i, "text": line.strip()})
        except (OSError, UnicodeDecodeError):
            continue
    return {"ok": True, "query": query, "file_pattern": file_pattern, "matches": matches, "count": len(matches)}


def bash(command: str, root: str | Path, auto_approve: bool = False, timeout: int = 20) -> dict[str, Any]:
    """Run a shell command in the sandbox only if confirm_bash() allows it."""
    gate = confirm_bash(command, auto_approve=auto_approve)
    if not gate["allowed"]:
        return {"ok": False, "ran": False, "gate": gate}
    try:
        proc = subprocess.run(command, shell=True, cwd=str(Path(root).resolve()), capture_output=True, text=True,
                              timeout=timeout)  # noqa: S602 - only reached after the gate allowed it
    except subprocess.TimeoutExpired:
        return {"ok": False, "ran": True, "gate": gate, "error": f"timed out after {timeout}s"}
    return {"ok": proc.returncode == 0, "ran": True, "gate": gate, "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}


__all__ = ["SAFE_PREFIXES", "bash", "confirm_bash", "destructive_reason", "edit_file", "glob_files",
           "is_destructive", "read_file", "search_in_files", "write_file"]
