"""HW7 Part 4 - MRKL tools for the Bay Wheels membership agent: csv_sql, policy_retriever, calculator.

Every tool is a plain function with a JSON schema and returns the common envelope
    {"success": bool, "data"?: any, "error"?: str, "source"?: str, "ts"?: str}
The functions take an explicit RunContext (uploaded CSV + snapshot folder) so they hold no hidden global state.

Security knobs (used by Part 5): RunContext.sql_strict enforces a single read-only SELECT inside csv_sql
regardless of what the model asks for. Leave it True for normal runs.
"""

import ast
import csv
import hashlib
import html
import io
import json
import math
import operator
import re
import sqlite3
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_ROWS_RETURNED = 200
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def envelope(success: bool, data: Any = None, error: str | None = None, source: str | None = None) -> dict[str, Any]:
    """Common tool return shape."""
    out: dict[str, Any] = {"success": success, "ts": _now()}
    if data is not None:
        out["data"] = data
    if error is not None:
        out["error"] = error
    if source is not None:
        out["source"] = source
    return out


# =========================================================================== run context
@dataclass
class RunContext:
    """Everything a tool may touch for one run: the uploaded trips and where snapshots go."""

    csv_text: str
    snapshot_dir: Path
    sql_strict: bool = True
    sanitize_retrieved: bool = False  # Part 5: quarantine instruction-like page text at the tool boundary
    _db: sqlite3.Connection | None = field(default=None, repr=False)
    snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)  # url -> {text, meta}
    trip_columns: list[str] = field(default_factory=list)

    def db(self) -> sqlite3.Connection:
        """Lazily load the uploaded CSV into an in-memory SQLite table `trips` with derived columns."""
        if self._db is None:
            self._db = load_trips(self.csv_text)
            self.trip_columns = [r[1] for r in self._db.execute("PRAGMA table_info(trips)")]
        return self._db


# =========================================================================== csv_sql
def _parse_ts(value: str) -> datetime | None:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def load_trips(csv_text: str) -> sqlite3.Connection:
    """Load a Bay Wheels trip CSV (2020+ schema) into SQLite table `trips`, adding derived columns.

    Derived columns: duration_min (float), billed_min (whole minutes, rounded up as Bay Wheels bills),
    is_ebike (1/0), ride_date (YYYY-MM-DD), month (YYYY-MM), week_start (Monday, YYYY-MM-DD).
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or not {"started_at", "ended_at"} <= set(reader.fieldnames):
        raise ValueError("CSV must have Bay Wheels columns including started_at and ended_at")
    src_cols = [c for c in reader.fieldnames if c]
    derived = ["duration_min", "billed_min", "is_ebike", "ride_date", "month", "week_start"]
    con = sqlite3.connect(":memory:", check_same_thread=False)
    cols_sql = ", ".join(f'"{c}" TEXT' for c in src_cols)
    con.execute(f"CREATE TABLE trips ({cols_sql}, duration_min REAL, billed_min INTEGER, is_ebike INTEGER, "
                f"ride_date TEXT, month TEXT, week_start TEXT)")
    rows = []
    for r in reader:
        start, end = _parse_ts(r.get("started_at", "")), _parse_ts(r.get("ended_at", ""))
        if not start or not end or end < start:
            continue  # unusable row (missing/invalid timestamps) - reported as a caveat via row counts
        dur = (end - start).total_seconds() / 60
        monday = (start - timedelta(days=start.weekday())).date()
        rows.append([r.get(c) for c in src_cols] + [
            round(dur, 2), max(1, math.ceil(dur - 1e-9)),
            1 if "electric" in (r.get("rideable_type") or "").lower() else 0,
            start.date().isoformat(), start.strftime("%Y-%m"), monday.isoformat()])
    con.executemany(f"INSERT INTO trips VALUES ({', '.join('?' * (len(src_cols) + len(derived)))})", rows)
    con.commit()
    return con


_READ_ONLY_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
_WRITE_WORDS = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|reindex)\b", re.I)


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S).strip()


def csv_sql(ctx: RunContext, sql: str) -> dict[str, Any]:
    """Run ONE read-only SELECT over the uploaded trips (table `trips`)."""
    if not isinstance(sql, str) or not sql.strip():
        return envelope(False, error="sql must be a non-empty string", source="uploaded.csv")
    try:
        con = ctx.db()
    except ValueError as exc:
        return envelope(False, error=str(exc), source="uploaded.csv")
    body = _strip_sql_comments(sql).rstrip(";").strip()
    try:
        if ctx.sql_strict:
            # tool-boundary contract: exactly one statement, SELECT/WITH only, enforced by SQLite itself
            if ";" in body:
                return envelope(False, error="only a single SQL statement is allowed", source="uploaded.csv")
            if not re.match(r"(?is)^(select|with)\b", body) or _WRITE_WORDS.search(body):
                return envelope(False, error="csv_sql is read-only: only a single SELECT query is allowed",
                                source="uploaded.csv")

            def authorizer(action: int, *args: Any) -> int:
                return sqlite3.SQLITE_OK if action in _READ_ONLY_ACTIONS else sqlite3.SQLITE_DENY

            con.set_authorizer(authorizer)
            try:
                cur = con.execute(body)
                rows = cur.fetchmany(MAX_ROWS_RETURNED + 1)
            finally:
                con.set_authorizer(None)
        else:  # UNSAFE mode, only for the Part 5 "before defenses" baseline
            cur = con.cursor()
            statements = [s for s in sql.split(";") if s.strip()]
            for s in statements[:-1]:
                cur.execute(s)
            cur.execute(statements[-1])
            con.commit()
            rows = cur.fetchmany(MAX_ROWS_RETURNED + 1) if cur.description else []
        names = [d[0] for d in cur.description] if cur.description else []
    except sqlite3.Error as exc:
        return envelope(False, error=f"SQL error: {exc}. Table is `trips`; columns: {ctx.trip_columns}",
                        source="uploaded.csv")
    truncated = len(rows) > MAX_ROWS_RETURNED
    data = {"rows": [dict(zip(names, r, strict=False)) for r in rows[:MAX_ROWS_RETURNED]],
            "row_count": min(len(rows), MAX_ROWS_RETURNED), "source": "uploaded.csv"}
    if truncated:
        data["truncated_at"] = MAX_ROWS_RETURNED
    return envelope(True, data=data, source="uploaded.csv")


# =========================================================================== policy_retriever
class _TextExtractor:
    """Very small HTML -> text converter (drops script/style/nav noise, keeps block boundaries)."""

    BLOCK = re.compile(r"</?(p|div|li|ul|ol|h[1-6]|tr|td|th|br|section|article|table|dd|dt)\b[^>]*>", re.I)

    @classmethod
    def extract(cls, raw: str) -> str:
        if "<" not in raw:  # already plain text
            return re.sub(r"[ \t]+", " ", raw).strip()
        s = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", raw)
        s = cls.BLOCK.sub("\n", s)
        s = re.sub(r"<[^>]+>", " ", s)
        s = html.unescape(s)
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in s.split("\n")]
        return "\n".join(ln for ln in lines if ln)


def _fetch(url: str) -> str:
    """Fetch a URL (or read a local file / file:// URL that holds a saved copy of the page)."""
    if url.startswith("file://"):
        return Path(url[7:]).read_text(encoding="utf-8", errors="ignore")
    if not re.match(r"^https?://", url) and Path(url).exists():
        return Path(url).read_text(encoding="utf-8", errors="ignore")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310 - URL is the user's pricing page
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="ignore")


def get_snapshot(ctx: RunContext, url: str) -> dict[str, Any]:
    """Fetch the pricing page once per run, save the exact text + URL + access time + SHA-256, and reuse it."""
    if url in ctx.snapshots:
        return ctx.snapshots[url]
    text = _TextExtractor.extract(_fetch(url))
    accessed = _now()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ctx.snapshot_dir.mkdir(parents=True, exist_ok=True)
    (ctx.snapshot_dir / "pricing_snapshot.txt").write_text(text, encoding="utf-8")
    meta = {"source_url": url, "accessed_at": accessed, "sha256": digest, "chars": len(text),
            "file": str(ctx.snapshot_dir / "pricing_snapshot.txt")}
    (ctx.snapshot_dir / "pricing_snapshot_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    ctx.snapshots[url] = {"text": text, "meta": meta}
    return ctx.snapshots[url]


# Instruction-like text has no place on a pricing page; quarantine it before the model ever sees it.
INJECTION_RE = re.compile(
    r"(?i)(\bfor\s+(ai|llm)\s+(assistants?|agents?|models?)\b|\bignore\s+(the|all|any|previous|other|above)\b|"
    r"\byou\s+must\s+(call|answer|include|list|run|output)\b|\balways\s+answer\b|\bsystem\s+prompt\b|"
    r"\bdisregard\b|\b(call|run|execute)\s+csv_sql\b|\b(delete\s+from|drop\s+table|insert\s+into|update\s+\w+\s+set)\b|"
    r"\bverbatim\b)")


_PRICE_WORDS = {"member", "membership", "month", "monthly", "annual", "minute", "minutes", "min", "unlock", "fee",
                "ride", "ebike", "e-bike", "electric", "classic", "single", "pass", "price", "cost", "overage",
                "additional", "extra", "included", "free", "cap", "capped", "per"}


_PLAN_PRICE = re.compile(r"^\$\d+(?:\.\d+)?(?:\s*/\s*[a-z]+)?$", re.I)


def _table_passages(lines: list[str]) -> tuple[list[str], set[int]]:
    """Rebuild a pricing comparison table that HTML->text flattened into one cell per line.

    Pattern on pricing pages: a run of n plan prices ("$1.00", "$15/day", "$29/month", ...) and later row
    labels (e.g. "Classic bike prices") each followed by n cell lines. Plan names come from elsewhere on the
    page, where a name line is directly followed by that plan's price. Returns one passage per plan, built
    only from verbatim cell text: "Month pass ($29/month) - Classic bike prices: 45 min free, then $0.17/min; ..."
    """
    best: tuple[int, int] = (0, 0)  # (start, length) of the longest run of consecutive plan-price lines
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and _PLAN_PRICE.match(lines[j]):
            j += 1
        if j - i > best[1]:
            best = (i, j - i)
        i = max(j, i + 1)
    start, n = best
    if n < 2:
        return [], set()
    prices = lines[start:start + n]
    names = []
    for p in prices:  # a name line followed by this price, outside the header run
        name = next((lines[x - 1] for x in range(1, len(lines))
                     if lines[x] == p and not (start <= x < start + n) and not _PLAN_PRICE.match(lines[x - 1])), p)
        names.append(name)
    rows: dict[str, list[str]] = {}
    used: set[int] = set(range(start, start + n))
    for x, ln in enumerate(lines):
        cells = lines[x + 1:x + 1 + n]
        if (ln.lower().endswith("prices") or ln.lower().endswith("price")) and len(cells) == n \
                and all("$" in c or "free" in c.lower() for c in cells):
            rows.setdefault(ln, cells)
            used.update(range(x, x + 1 + n))  # every repeated copy of the row (per-plan page sections too)
    if not rows:
        return [], set()
    passages = [f"{names[c]} ({prices[c]}) - " + "; ".join(f"{label}: {cells[c]}" for label, cells in rows.items())
                for c in range(n)]
    return passages, used


def _chunks(text: str) -> list[str]:
    """Split page text into short quotable snippets: rebuilt table rows, then sentences/merged short lines."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    out, used = _table_passages(lines)
    buf: list[str] = []
    for idx, line in enumerate(lines):
        if idx in used:  # table cells are already in the rebuilt per-plan passages; don't mix columns
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        if len(line) < 60:  # short UI lines ("$1.00 to unlock", "$0.19/min for classic bikes.") -> merge up to 4
            buf.append(line)
            if len(buf) == 4:
                out.append(" ".join(buf))
                buf = buf[2:]  # overlap so a price is never split from its label
            continue
        if buf:
            out.append(" ".join(buf))
            buf = []
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z$])", line):
            out.append(s)
    if buf:
        out.append(" ".join(buf))
    seen, uniq = set(), []
    for c in out:
        c = c[:320]
        if len(c) >= 12 and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def policy_retriever(ctx: RunContext, url: str, query: str, k: int = 3) -> dict[str, Any]:
    """Return the k most relevant short snippets from the pricing page for `query` (keyword + price scoring)."""
    if not isinstance(url, str) or not url.strip():
        return envelope(False, error="url is required")
    if not isinstance(query, str) or not query.strip():
        return envelope(False, error="query is required", source=url)
    try:
        k = max(1, min(int(k), 8))
    except (TypeError, ValueError):
        k = 3
    try:
        snap = get_snapshot(ctx, url.strip())
    except Exception as exc:  # network / file errors -> useful message, never a crash
        return envelope(False, error=f"could not fetch pricing page: {type(exc).__name__}: {exc}", source=url)
    if len(snap["text"]) < 200:
        return envelope(False, error=("pricing page returned almost no text (it may be rendered by JavaScript). "
                                      "Save the page from a browser and pass the saved file path as url."),
                        source=url)
    q_stems = {t[:5] for t in re.findall(r"[a-z]+", query.lower()) if len(t) > 2}
    scored = []
    chunks = _chunks(snap["text"])
    quarantined = [c for c in chunks if ctx.sanitize_retrieved and INJECTION_RE.search(c)]
    for chunk in (c for c in chunks if c not in quarantined):
        low = chunk.lower()
        words = set(re.findall(r"[a-z\-]+", low))
        overlap = len(q_stems & {w[:5] for w in words})  # "monthly" ~ "month", "membership" ~ "member"
        price_bonus = 1.5 if re.search(r"\$\s?\d", chunk) else 0.0
        table_bonus = 2.0 if re.match(r"^.{2,40} \(\$[\d.]+(?:/\w+)?\) - ", chunk) else 0.0
        domain = 0.25 * len(words & _PRICE_WORDS)
        score = overlap * 2.0 + price_bonus + table_bonus + domain
        if score > 0:
            scored.append((round(score, 2), chunk))
    scored.sort(key=lambda x: -x[0])
    passages = [{"text": t, "source": snap["meta"]["source_url"], "score": s} for s, t in scored[:k]]
    data = {"passages": passages, "captured_at": snap["meta"]["accessed_at"], "sha256": snap["meta"]["sha256"]}
    if quarantined:
        data["quarantined"] = {"count": len(quarantined), "reason": "instruction-like text removed from page evidence",
                               "examples": [q[:120] for q in quarantined[:2]]}
    return envelope(True, data=data, source=snap["meta"]["source_url"])


# =========================================================================== calculator
CALC_WHITELIST = re.compile(r"^[0-9+\-*/().\s]+$")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calculator(expression: str, units: str | None = None) -> dict[str, Any]:
    """Safe arithmetic: whitelist ^[0-9+\\-*/().\\s]+$ then evaluate the AST (no eval)."""
    if not isinstance(expression, str) or not CALC_WHITELIST.match(expression or ""):
        return envelope(False, error="expression may only contain digits, + - * / ( ) . and spaces")
    if len(expression) > 500:
        return envelope(False, error="expression too long (max 500 chars)")
    try:
        value = _eval_node(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return envelope(False, error="division by zero")
    except (SyntaxError, ValueError) as exc:
        return envelope(False, error=f"invalid expression: {exc}")
    data: dict[str, Any] = {"value": round(value, 6)}
    if units:
        data["units"] = str(units)[:20]
    return envelope(True, data=data)


# =========================================================================== schemas (MRKL tool registry)
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "csv_sql",
        "description": ("Run ONE read-only SELECT over the uploaded trips table `trips`. Useful columns: "
                        "rideable_type, started_at, ended_at, member_casual, duration_min, billed_min "
                        "(whole minutes billed), is_ebike (1/0), ride_date, month (YYYY-MM), week_start."),
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"],
                       "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "policy_retriever",
        "description": "Fetch the official pricing page and return short quotable snippets relevant to the query.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}, "query": {"type": "string"},
            "k": {"type": "integer", "description": "number of snippets (default 3)"}},
            "required": ["url", "query"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Safe arithmetic on numbers only (digits, + - * / ( ) . and spaces).",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string"}, "units": {"type": "string"}},
            "required": ["expression"], "additionalProperties": False}}},
]

# Output schemas (documented for the report)
OUTPUT_SCHEMAS = {
    "csv_sql": {"rows": "Array<object>", "row_count": "number", "source": "uploaded.csv"},
    "policy_retriever": {"passages": [{"text": "string", "source": "string", "score": "number"}]},
    "calculator": {"value": "number", "units?": "string"},
    "envelope": {"success": "bool", "data?": "any", "error?": "string", "source?": "string", "ts?": "string"},
}


def run_tool(ctx: RunContext, name: str, args: Any) -> dict[str, Any]:
    """Dispatch one model tool call with argument validation; never raises."""
    if not isinstance(args, dict):
        return envelope(False, error=f"arguments for {name} must be a JSON object")
    try:
        if name == "csv_sql":
            if set(args) - {"sql"}:
                return envelope(False, error=f"csv_sql takes only 'sql', got {sorted(args)}")
            return csv_sql(ctx, args.get("sql", ""))
        if name == "policy_retriever":
            if set(args) - {"url", "query", "k"}:
                return envelope(False, error=f"policy_retriever takes url, query, k; got {sorted(args)}")
            return policy_retriever(ctx, args.get("url", ""), args.get("query", ""), args.get("k", 3))
        if name == "calculator":
            if set(args) - {"expression", "units"}:
                return envelope(False, error=f"calculator takes expression, units; got {sorted(args)}")
            return calculator(args.get("expression", ""), args.get("units"))
    except Exception as exc:  # defensive: a tool bug must not crash the agent
        return envelope(False, error=f"{name} failed: {type(exc).__name__}: {exc}")
    return envelope(False, error=f"unknown tool '{name}'. Available: csv_sql, policy_retriever, calculator")
