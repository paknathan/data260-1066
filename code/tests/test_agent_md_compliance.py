"""Part 4.4 - verify the generated helper follows AGENT.md (conventions + behaviour)."""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transit_utils import classify_delay  # noqa: E402

SOURCE = (ROOT / "transit_utils.py").read_text()
TREE = ast.parse(SOURCE)
FUNCS = [n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef)]


# --- AGENT.md rule 5: snake_case, type hints, docstring -------------------------
def test_functions_are_snake_case():
    assert FUNCS and all(f.name == f.name.lower() for f in FUNCS)


def test_every_function_has_type_hints():
    for f in FUNCS:
        assert f.returns is not None, f"{f.name} missing return type"
        assert all(a.annotation is not None for a in f.args.args), f"{f.name} missing param types"


def test_every_function_has_docstring():
    assert all(ast.get_docstring(f) for f in FUNCS)


# --- AGENT.md rule 7 + 10: no print, no secrets/hosted APIs ----------------------
def test_no_print_or_hosted_api_calls():
    calls = {n.func.id for n in ast.walk(TREE) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "print" not in calls
    assert "openai" not in SOURCE.lower() and "api_key" not in SOURCE.lower()


# --- AGENT.md rule 8: normal, boundary and invalid cases --------------------------
@pytest.mark.parametrize("minutes,expected", [(0, "on_time"), (4, "on_time"), (5, "minor"),
                                              (14, "minor"), (15, "moderate"), (30, "severe"), (90, "severe")])
def test_classify_delay_bands(minutes, expected):
    assert classify_delay(minutes) == expected


@pytest.mark.parametrize("bad", [-1, 2.5, "10", None, True])
def test_classify_delay_rejects_invalid(bad):  # AGENT.md rule 6: explicit ValueError
    with pytest.raises(ValueError):
        classify_delay(bad)
