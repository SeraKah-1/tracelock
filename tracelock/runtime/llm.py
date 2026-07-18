"""OpenAI-compatible LLM client (stdlib urllib — no openai package required).

Supports:
  GET  {base}/models
  POST {base}/chat/completions   (with tools / tool_choice)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def has_tools(self) -> bool:
        return bool(self.tool_calls)


def _headers(api_key: str) -> dict[str, str]:
    h = {
        "Content-Type": "application/json",
        "User-Agent": "TraceLock-Agent/2.1",
    }
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _request(
    method: str,
    url: str,
    *,
    api_key: str = "",
    body: Optional[dict[str, Any]] = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=_headers(api_key),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e
    except Exception as e:
        raise RuntimeError(f"{method} {url}: {e}") from e


def normalize_base(api_base: str) -> str:
    b = (api_base or "").strip().rstrip("/")
    # accept base with or without /v1
    return b


def list_models(api_base: str, api_key: str, timeout: float = 30.0) -> dict[str, Any]:
    """GET {base}/models — OpenAI-compatible model catalog."""
    base = normalize_base(api_base)
    url = f"{base}/models"
    try:
        data = _request("GET", url, api_key=api_key, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": str(e), "models": []}
    models: list[dict[str, Any]] = []
    for m in data.get("data") or []:
        if isinstance(m, dict):
            models.append(
                {
                    "id": m.get("id") or m.get("model") or "",
                    "owned_by": m.get("owned_by") or "",
                    "object": m.get("object") or "model",
                }
            )
        elif isinstance(m, str):
            models.append({"id": m, "owned_by": "", "object": "model"})
    # some providers return {models: [...]}
    if not models and isinstance(data.get("models"), list):
        for m in data["models"]:
            if isinstance(m, dict):
                models.append({"id": m.get("id") or m.get("name") or "", "owned_by": "", "object": "model"})
            else:
                models.append({"id": str(m), "owned_by": "", "object": "model"})
    models = [m for m in models if m.get("id")]
    return {"ok": True, "models": models, "count": len(models), "raw_keys": list(data.keys())[:12]}


def chat_completions(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    tool_choice: str = "auto",
    timeout: float = 180.0,
) -> LLMResponse:
    """POST chat/completions with optional tools (function calling)."""
    base = normalize_base(api_base)
    url = f"{base}/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice
    try:
        data = _request("POST", url, api_key=api_key, body=body, timeout=timeout)
    except Exception as e:
        return LLMResponse(error=str(e))

    choices = data.get("choices") or []
    if not choices:
        return LLMResponse(error="empty choices", raw=data)
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if isinstance(content, list):
        # multimodal content parts
        content = "".join(
            (p.get("text") or "") for p in content if isinstance(p, dict)
        )
    raw_tools = msg.get("tool_calls") or []
    tool_calls: list[dict[str, Any]] = []
    for tc in raw_tools:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        args_raw = fn.get("arguments") or "{}"
        if isinstance(args_raw, dict):
            args = args_raw
        else:
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
        tool_calls.append(
            {
                "id": tc.get("id") or f"call_{len(tool_calls)}",
                "type": "function",
                "function": {
                    "name": fn.get("name") or "",
                    "arguments": args if isinstance(args, dict) else {"value": args},
                    "arguments_raw": args_raw if isinstance(args_raw, str) else json.dumps(args_raw),
                },
            }
        )
    return LLMResponse(
        content=str(content or ""),
        tool_calls=tool_calls,
        finish_reason=str(choices[0].get("finish_reason") or ""),
        raw=data,
    )
