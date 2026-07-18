"""Telegram Bot API adapter (stdlib urllib — no extra deps).

Env:
  TRACELOCK_TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN
  TRACELOCK_TELEGRAM_ALLOWLIST  comma-separated user ids (empty = allow all with caution)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


API = "https://api.telegram.org"


def bot_token() -> str:
    return (
        os.environ.get("TRACELOCK_TELEGRAM_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()


def allowlist() -> set[str]:
    raw = os.environ.get("TRACELOCK_TELEGRAM_ALLOWLIST") or os.environ.get(
        "TELEGRAM_ALLOWLIST", ""
    )
    return {x.strip() for x in raw.split(",") if x.strip()}


def _api(method: str, payload: Optional[dict[str, Any]] = None, timeout: float = 35.0) -> dict[str, Any]:
    token = bot_token()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    url = f"{API}/bot{token}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}", "detail": err[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(chat_id: str | int, text: str, **kwargs: Any) -> dict[str, Any]:
    # Telegram hard limit ~4096
    chunks = []
    t = text or ""
    while t:
        chunks.append(t[:4000])
        t = t[4000:]
    if not chunks:
        chunks = [""]
    last: dict[str, Any] = {}
    for c in chunks:
        last = _api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": c,
                "disable_web_page_preview": True,
                **kwargs,
            },
        )
        if not last.get("ok"):
            return last
    return last


def get_updates(offset: Optional[int] = None, timeout: int = 25) -> dict[str, Any]:
    payload: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    return _api("getUpdates", payload, timeout=float(timeout + 10))


def authorized(user_id: str | int) -> bool:
    al = allowlist()
    if not al:
        # no allowlist → allow (document risk); set allowlist in prod
        return True
    return str(user_id) in al


def parse_update(upd: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Normalize Telegram update → {chat_id, user_id, text, update_id}."""
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return None
    text = (msg.get("text") or msg.get("caption") or "").strip()
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    return {
        "update_id": upd.get("update_id"),
        "chat_id": chat.get("id"),
        "user_id": user.get("id"),
        "username": user.get("username") or "",
        "text": text,
        "raw": upd,
    }
