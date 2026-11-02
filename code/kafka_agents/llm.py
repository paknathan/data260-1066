"""Thin wrapper over the HW1 model adapter (src/model_client.py, Ollama qwen3:8b)."""

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_client = None


def _get():
    global _client
    if _client is None:
        spec = importlib.util.spec_from_file_location("hw1_model_client", _REPO / "src" / "model_client.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _client = mod.ModelClient()
    return _client


def ask_json(system: str, user: str) -> dict[str, Any]:
    """One model call that must return a JSON object (adapter's format=json)."""
    out = _get().complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                          temperature=0.0, response_format="json")
    return {k: v for k, v in out.items() if k != "_usage"}


def ask_text(system: str, user: str) -> str:
    out = _get().complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                          temperature=0.0, response_format=None)
    return re.sub(r"<think>.*?</think>", "", out.get("content", ""), flags=re.S).strip()


def model_name() -> str:
    try:
        return _get().model
    except Exception:
        return "unavailable"


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)
