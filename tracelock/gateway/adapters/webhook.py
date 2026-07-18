"""Outbound webhook + inbound JSON handler helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def post_json(url: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "TraceLock-Gateway/2.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {"raw": body[:500]}
            return {"ok": True, "status": resp.status, "body": parsed}
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "error": f"HTTP {e.code}",
            "detail": e.read().decode("utf-8", errors="replace")[:400],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
