"""Model adapter for the local Ollama model (same role as the HW1 adapter).

Env vars:
  OLLAMA_URL    default http://localhost:11434
  OLLAMA_MODEL  default llama3.2:3b   (set to whatever model you used in HW1)
  EMBED_MODEL   default nomic-embed-text  (falls back to a hashing embedding if missing)
"""
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from typing import Dict, List

from database import SEED

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))

_embed_backend = {"name": None}


class LLMError(RuntimeError):
    pass


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LLMError(f"Ollama request to {path} failed: {exc}") from exc


def approx_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) used for per-component accounting."""
    return 0 if not text else max(1, math.ceil(len(text) / 4))


def chat(messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 400,
         json_mode: bool = False) -> Dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "seed": SEED, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"
    t0 = time.perf_counter()
    data = _post("/api/chat", payload)
    latency_ms = (time.perf_counter() - t0) * 1000
    text = data.get("message", {}).get("content", "").strip()
    prompt_text = "\n".join(m["content"] for m in messages)
    return {
        "text": text,
        "prompt_tokens": data.get("prompt_eval_count") or approx_tokens(prompt_text),
        "completion_tokens": data.get("eval_count") or approx_tokens(text),
        "latency_ms": round(latency_ms, 1),
        "model": MODEL,
    }


def _hash_embed(text: str, dim: int = 256) -> List[float]:
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> List[float]:
    """Embed with Ollama; fall back to a deterministic hashing embedding."""
    if _embed_backend["name"] != "hash":
        try:
            try:
                data = _post("/api/embed", {"model": EMBED_MODEL, "input": text})
                vec = data["embeddings"][0]
            except (LLMError, KeyError):
                data = _post("/api/embeddings", {"model": EMBED_MODEL, "prompt": text})
                vec = data["embedding"]
            if vec:
                _embed_backend["name"] = f"ollama:{EMBED_MODEL}"
                return [float(v) for v in vec]
        except (LLMError, KeyError, IndexError):
            pass
        _embed_backend["name"] = "hash"
    return _hash_embed(text)


def embed_backend() -> str:
    return _embed_backend["name"] or "unknown"


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
