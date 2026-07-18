"""Email delivery via maildir-style outbox (works without SMTP credentials).

For production SMTP set:
  TRACELOCK_SMTP_HOST, TRACELOCK_SMTP_PORT, TRACELOCK_SMTP_USER,
  TRACELOCK_SMTP_PASS, TRACELOCK_SMTP_FROM

Without SMTP, messages land in ~/.tracelock/outbox/ as .eml for pickup
or external relay (Mailgun/SES on Alibaba can poll/push later).
"""

from __future__ import annotations

import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def outbox_dir() -> Path:
    base = Path(os.environ.get("TRACELOCK_HOME") or Path.home() / ".tracelock")
    d = base / "outbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def queue_email(to_addr: str, subject: str, body: str) -> dict[str, Any]:
    host = os.environ.get("TRACELOCK_SMTP_HOST") or ""
    if host:
        return _send_smtp(to_addr, subject, body)

    ts = time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() else "_" for c in to_addr)[:40]
    path = outbox_dir() / f"{ts}_{safe}.eml"
    msg = EmailMessage()
    msg["From"] = os.environ.get("TRACELOCK_SMTP_FROM") or "tracelock@localhost"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    path.write_bytes(msg.as_bytes())
    return {
        "ok": True,
        "channel": "email_outbox",
        "path": str(path),
        "note": "Queued to outbox (set TRACELOCK_SMTP_HOST for live SMTP)",
    }


def _send_smtp(to_addr: str, subject: str, body: str) -> dict[str, Any]:
    host = os.environ["TRACELOCK_SMTP_HOST"]
    port = int(os.environ.get("TRACELOCK_SMTP_PORT") or "587")
    user = os.environ.get("TRACELOCK_SMTP_USER") or ""
    password = os.environ.get("TRACELOCK_SMTP_PASS") or ""
    from_addr = os.environ.get("TRACELOCK_SMTP_FROM") or user or "tracelock@localhost"
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            if os.environ.get("TRACELOCK_SMTP_STARTTLS", "1") not in ("0", "false"):
                s.starttls()
                s.ehlo()
            if user:
                s.login(user, password)
            s.send_message(msg)
        return {"ok": True, "channel": "smtp", "to": to_addr}
    except Exception as e:
        path = outbox_dir() / f"failed_{int(time.time())}.eml"
        path.write_bytes(msg.as_bytes())
        return {"ok": False, "error": str(e), "fallback_outbox": str(path)}
