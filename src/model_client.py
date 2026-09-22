import json
import sys
import requests
from typing import Any, Dict, List, Optional

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 240


class ModelClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries

    def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        response_format: Optional[str] = "json",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature},
        }

        if response_format:
            payload["format"] = response_format

        if tools:
            payload["tools"] = tools

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    self.base_url, json=payload, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()

                message = data.get("message", {})

                # Extract token usage from Ollama's standard response fields
                input_tokens = data.get("prompt_eval_count", 0)
                output_tokens = data.get("eval_count", 0)

                if "tool_calls" in message:
                    res = {"tool_calls": message["tool_calls"]}
                else:
                    content = message.get("content", "")
                    if response_format == "json":
                        res = json.loads(content)
                    else:
                        res = {"content": content}

                res["_usage"] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
                return res

            except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                print(
                    f"  [retry {attempt}/{self.max_retries}] model call failed: {exc}",
                    file=sys.stderr,
                )

        raise RuntimeError(
            f"Model call failed after {self.max_retries} attempts: {last_error}"
        )


_default_client = ModelClient()


def complete(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 0.0,
    response_format: Optional[str] = "json",
) -> Dict[str, Any]:
    return _default_client.complete(
        messages=messages,
        tools=tools,
        temperature=temperature,
        response_format=response_format,
    )
