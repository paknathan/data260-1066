"""HW7 Part 2 - JSON schemas, argument validation and execute_tool() for the three HW5 domain tools."""

import json
import sys
import types
from collections.abc import Callable
from typing import Any

# domain_server.py (HW5) imports the MCP SDK only for its @mcp.tool() decorator, which returns the
# plain function. If the SDK isn't installed in this Python, stand in a no-op decorator so we can
# call the same three functions directly (no MCP transport needed for a hand-written loop).
try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401
except ImportError:  # pragma: no cover - depends on the local environment

    class _FastMCPShim:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
            return lambda fn: fn

        def run(self) -> None:
            raise RuntimeError("MCP SDK not installed; run `pip install mcp` to serve over MCP.")

    _fastmcp = types.ModuleType("mcp.server.fastmcp")
    _fastmcp.FastMCP = _FastMCPShim
    sys.modules.setdefault("mcp", types.ModuleType("mcp"))
    sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
    sys.modules["mcp.server.fastmcp"] = _fastmcp

from domain_server import aggregate_route_stats, get_incident_detail, search_incidents  # noqa: E402

TOOL_FUNCS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_incidents": search_incidents,
    "get_incident_detail": get_incident_detail,
    "aggregate_route_stats": aggregate_route_stats,
}


def _schema(name: str, description: str, prop: str, prop_desc: str) -> dict[str, Any]:
    """Build an Ollama/OpenAI-style function schema with one required string argument."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {prop: {"type": "string", "description": prop_desc}},
                "required": [prop],
                "additionalProperties": False,
            },
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema(
        "search_incidents",
        "Search transit incidents by route ID, incident type, or transit mode. Returns a list of incidents with IDs.",
        "query",
        "A route (e.g. 'Route 22'), incident type (e.g. 'Signal Failure') or mode (e.g. 'Light Rail').",
    ),
    _schema(
        "get_incident_detail",
        "Retrieve the full incident report for one incident ID.",
        "incident_id",
        "An incident ID exactly as returned by search_incidents, e.g. 'inc_101'.",
    ),
    _schema(
        "aggregate_route_stats",
        "Aggregate statistics (incident count, active count, average and total delay) for one route.",
        "route_id",
        "An exact route name, e.g. 'Route 22' or 'Blue Line'.",
    ),
]
_SCHEMA_BY_NAME = {s["function"]["name"]: s["function"]["parameters"] for s in TOOL_SCHEMAS}
_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}


def validate_args(name: str, args: Any) -> str | None:
    """Return a specific problem description if `args` violates the tool's schema, else None."""
    schema = _SCHEMA_BY_NAME[name]
    if not isinstance(args, dict):
        return f"arguments for {name} must be a JSON object, got {type(args).__name__}"
    props = schema["properties"]
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        return f"{name} is missing required argument(s) {missing}; expected {sorted(props)}"
    extra = sorted(set(args) - set(props))
    if extra and not schema.get("additionalProperties", True):
        return f"{name} got unexpected argument(s) {extra}; allowed: {sorted(props)}"
    for key, spec in props.items():
        if key in args:
            expected = _JSON_TYPES[spec["type"]]
            if not isinstance(args[key], expected) or isinstance(args[key], bool) and spec["type"] != "boolean":
                return f"{name}.{key} must be a {spec['type']}, got {type(args[key]).__name__}"
            if spec["type"] == "string" and not args[key].strip():
                return f"{name}.{key} must be a non-empty string"
    return None


def parse_tool_call(call: Any) -> tuple[str | None, Any, str | None, str | None]:
    """Extract (name, args, problem, problem_type) from one raw model tool call."""
    fn = call.get("function", {}) if isinstance(call, dict) else {}
    name = fn.get("name")
    raw_args = fn.get("arguments", {})
    if not name or name not in TOOL_FUNCS:
        return name, raw_args, f"unknown tool '{name}'. Available tools: {sorted(TOOL_FUNCS)}", "unknown_tool"
    args = raw_args
    if isinstance(raw_args, str):  # some models send arguments as a JSON string
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError as exc:
            return name, raw_args, f"arguments for {name} are not valid JSON ({exc.msg})", "malformed_arguments"
    problem = validate_args(name, args)
    if problem:
        return name, args, problem, "malformed_arguments"
    return name, args, None, None


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one domain tool and always return the {ok, data, error} envelope - never raise."""
    if name not in TOOL_FUNCS:
        return {"ok": False, "data": None, "error": f"Unknown tool '{name}'. Available: {sorted(TOOL_FUNCS)}"}
    problem = validate_args(name, args)
    if problem:
        return {"ok": False, "data": None, "error": f"Invalid arguments: {problem}"}
    try:
        result = TOOL_FUNCS[name](**args)
    except Exception as exc:  # a tool bug must not crash the agent
        return {"ok": False, "data": None, "error": f"{name} raised {type(exc).__name__}: {exc}"}
    if name == "get_incident_detail" and not result.get("ok"):
        result = {**result, "hint": "Use search_incidents to find valid incident IDs (format 'inc_###')."}
    return result
