"""Part 4 - file-based memory (AGENT.md + MEMORY.md), consolidation and commands.

MEMORY.md fact line format:   - [YYYY-MM-DD] key: value
Timestamp comment:            <!-- last_consolidated: 2026-10-19T13:00:00+00:00 -->
"""
import json
import os
import re
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
AGENT_PATH = Path(os.getenv("AGENT_MD", ROOT / "AGENT.md"))
MEMORY_PATH = Path(os.getenv("MEMORY_MD", ROOT / "MEMORY.md"))

MAX_LINES = 40
MAX_AGE = timedelta(hours=24)
TS_RE = re.compile(r"<!--\s*last_consolidated:\s*(\S+)\s*-->")
FACT_RE = re.compile(r"^\s*-\s*\[(\d{4}-\d{2}-\d{2})\]\s*([A-Za-z0-9_.\-]+)\s*:\s*(.+?)\s*$")
CONFIRMED_RE = re.compile(r"\(confirmed\)", re.I)
UNCONFIRMED_RE = re.compile(r"\((unconfirmed|guess|maybe)\)", re.I)


# ------------------------------------------------------------------------------
# Loading + prompt construction
# ------------------------------------------------------------------------------
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_memory_files() -> Tuple[str, str]:
    """Return (AGENT.md text, MEMORY.md text); missing files load as empty strings."""
    return _read(AGENT_PATH), _read(MEMORY_PATH)


def build_system_prompt(base_primer: str) -> str:
    """Append AGENT.md (instructions) and MEMORY.md (durable facts) to the system primer."""
    agent, memory = load_memory_files()
    parts = [base_primer]
    if agent.strip():
        parts.append("# Agent instructions (AGENT.md)\n" + _strip_comments(agent).strip())
    if memory.strip():
        parts.append("# Durable memory (MEMORY.md)\n" + _strip_comments(memory).strip())
    return "\n\n".join(parts)


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


# ------------------------------------------------------------------------------
# Consolidation checks
# ------------------------------------------------------------------------------
def count_content_lines(text: str) -> int:
    """Non-empty, non-comment lines."""
    return sum(1 for ln in _strip_comments(text).splitlines() if ln.strip())


def read_last_consolidated(text: str) -> Optional[datetime]:
    m = TS_RE.search(text)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def needs_consolidation(text: str, now: Optional[datetime] = None) -> Tuple[bool, List[str]]:
    now = now or datetime.now(timezone.utc)
    reasons = []
    n = count_content_lines(text)
    if n > MAX_LINES:
        reasons.append(f"{n} content lines > {MAX_LINES}")
    ts = read_last_consolidated(text)
    if ts is None:
        reasons.append("no last_consolidated timestamp recorded")
    elif now - ts > MAX_AGE:
        reasons.append(f"last consolidated {ts.isoformat()} is more than 24h old")
    return bool(reasons), reasons


# ------------------------------------------------------------------------------
# Consolidation
# ------------------------------------------------------------------------------
def _norm(value: str) -> str:
    v = CONFIRMED_RE.sub("", UNCONFIRMED_RE.sub("", value)).lower()
    return re.sub(r"[^a-z0-9]+", " ", v).strip()


def parse_facts(text: str) -> List[Dict]:
    facts = []
    for i, line in enumerate(text.splitlines()):
        m = FACT_RE.match(line)
        if m:
            facts.append({"line_no": i + 1, "date": m.group(1), "key": m.group(2).lower(),
                          "value": m.group(3).strip()})
    return facts


def consolidate(text: str, now: Optional[datetime] = None) -> Tuple[str, Dict]:
    """Merge duplicates, resolve contradictions (newest dated fact wins; ties -> later line),
    and keep every superseded value in an explicit 'Resolved contradictions' section.
    A resolution is flagged for review when an '(unconfirmed)' value beat a '(confirmed)' one."""
    now = now or datetime.now(timezone.utc)
    facts = parse_facts(text)
    groups: "OrderedDict[str, List[Dict]]" = OrderedDict()
    for f in facts:
        groups.setdefault(f["key"], []).append(f)

    kept, duplicates, contradictions = [], [], []
    for key, items in groups.items():
        distinct: "OrderedDict[str, List[Dict]]" = OrderedDict()
        for f in items:
            distinct.setdefault(_norm(f["value"]), []).append(f)
        # duplicates: same key + same normalised value -> keep the newest copy
        for norm, copies in distinct.items():
            if len(copies) > 1:
                duplicates.append({"key": key, "value": copies[-1]["value"], "copies": len(copies),
                                   "lines": [c["line_no"] for c in copies]})
        # one variant per distinct value: original wording of the first copy, date of the newest copy
        variants = []
        for copies in distinct.values():
            newest = max(copies, key=lambda f: (f["date"], f["line_no"]))
            variants.append({**newest, "value": copies[0]["value"]})
        winner = max(variants, key=lambda f: (f["date"], f["line_no"]))
        kept.append(winner)
        if len(variants) > 1:
            losers = [v for v in variants if v is not winner]
            suspicious = bool(UNCONFIRMED_RE.search(winner["value"])) and any(
                CONFIRMED_RE.search(l["value"]) for l in losers)
            contradictions.append({
                "key": key,
                "kept": {"value": winner["value"], "date": winner["date"], "line": winner["line_no"]},
                "superseded": [{"value": l["value"], "date": l["date"], "line": l["line_no"]} for l in losers],
                "rule": "newest dated fact wins",
                "possibly_incorrect": suspicious,
                "review_note": ("Newer value is unconfirmed while the older one was confirmed - "
                                "'newest wins' is probably wrong here; verify manually.") if suspicious else "",
            })

    out = ["# MEMORY.md - durable facts (consolidated)",
           f"<!-- last_consolidated: {now.replace(microsecond=0).isoformat()} -->",
           f"<!-- source: {len(facts)} fact lines; merged {sum(d['copies'] - 1 for d in duplicates)} duplicate lines; "
           f"resolved {len(contradictions)} contradictions -->",
           "## Facts"]
    out += [f"- [{f['date']}] {f['key']}: {f['value']}" for f in kept]
    if contradictions:
        out.append("## Resolved contradictions (kept for audit - nothing silently deleted)")
        for c in contradictions:
            old = "; ".join(f"\"{s['value']}\" ({s['date']})" for s in c["superseded"])
            flag = "REVIEW - possibly resolved incorrectly: " if c["possibly_incorrect"] else ""
            out.append(f"- {flag}{c['key']}: kept \"{c['kept']['value']}\" ({c['kept']['date']}) over {old}")
    new_text = "\n".join(out) + "\n"

    report = {
        "consolidated_at": now.isoformat(),
        "lines_before": len(text.splitlines()),
        "content_lines_before": count_content_lines(text),
        "facts_before": len(facts),
        "lines_after": len(new_text.splitlines()),
        "content_lines_after": count_content_lines(new_text),
        "facts_after": len(kept),
        "duplicates_merged": duplicates,
        "contradictions_resolved": contradictions,
        "flagged_possibly_incorrect": [c["key"] for c in contradictions if c["possibly_incorrect"]],
    }
    return new_text, report


def consolidate_file(path: Path = None, report_path: Optional[Path] = None) -> Dict:
    path = Path(path or MEMORY_PATH)
    new_text, report = consolidate(_read(path))
    path.write_text(new_text, encoding="utf-8")
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2))
    return report


def append_facts(facts: List[str], path: Path = None) -> List[str]:
    """Append new facts as '- [date] note.<slug>: fact', skipping ones already present."""
    path = Path(path or MEMORY_PATH)
    text = _read(path) or "# MEMORY.md - durable facts\n## Facts\n"
    existing = {_norm(f["value"]) for f in parse_facts(text)}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added = []
    for fact in facts:
        fact = fact.strip().rstrip(".")
        if not fact or _norm(fact) in existing:
            continue
        slug = "_".join(re.findall(r"[a-z0-9]+", fact.lower())[:4]) or "fact"
        line = f"- [{today}] note.{slug}: {fact}"
        text = text.rstrip("\n") + "\n" + line + "\n"
        existing.add(_norm(fact))
        added.append(line)
    path.write_text(text, encoding="utf-8")
    return added


# ------------------------------------------------------------------------------
# Commands: /memory /compact /dream /help
# ------------------------------------------------------------------------------
HELP_TEXT = """Available commands:
/memory  - show the current file-based memory (AGENT.md + MEMORY.md) and whether consolidation is due
/compact - consolidate MEMORY.md (merge duplicates, resolve contradictions) and report counts before/after
/dream   - pull durable facts from the recent conversation and append them to MEMORY.md
/help    - show this help"""


def handle_command(command: str, recent_messages: Optional[List[Dict[str, str]]] = None,
                   extractor=None) -> Dict:
    cmd = command.strip().split()[0].lower()
    if cmd == "/help":
        return {"command": "/help", "reply": HELP_TEXT}

    if cmd == "/memory":
        agent, memory = load_memory_files()
        due, reasons = needs_consolidation(memory)
        return {"command": "/memory",
                "reply": f"--- AGENT.md ---\n{agent}\n--- MEMORY.md ---\n{memory}",
                "memory_content_lines": count_content_lines(memory),
                "last_consolidated": str(read_last_consolidated(memory)),
                "consolidation_due": due, "reasons": reasons}

    if cmd == "/compact":
        report = consolidate_file(MEMORY_PATH, ROOT / "reports" / "hw06" / "raw" / "compact_report.json")
        reply = (f"/compact: MEMORY.md {report['lines_before']} lines -> {report['lines_after']} lines "
                 f"({report['content_lines_before']} -> {report['content_lines_after']} non-comment lines; "
                 f"{report['facts_before']} -> {report['facts_after']} facts). "
                 f"Merged {len(report['duplicates_merged'])} duplicated facts, resolved "
                 f"{len(report['contradictions_resolved'])} contradictions, flagged for review: "
                 f"{report['flagged_possibly_incorrect'] or 'none'}.")
        return {"command": "/compact", "reply": reply, "report": report}

    if cmd == "/dream":
        msgs = [m for m in (recent_messages or []) if m["role"] == "user"]
        facts: List[str] = []
        for m in msgs[-10:]:
            found = extractor(m["content"]) if extractor else []
            facts += [f["fact"] for f in found if f.get("importance", 0) >= 0.5]
        added = append_facts(facts)
        return {"command": "/dream", "reply": f"/dream: scanned {len(msgs[-10:])} recent user messages, "
                                              f"added {len(added)} new facts to MEMORY.md.", "added": added}

    return {"command": cmd, "reply": f"Unknown command {cmd}.\n\n{HELP_TEXT}"}
