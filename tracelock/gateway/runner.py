"""Gateway runner — long-lived process: Telegram + HTTP + cron tick.

Flow:
  Platform event → authorize → session → OSINT skill → deliver

TraceLock scope:
  Message → investigate skill → brief report back
  Background: cron tick every N seconds for proactive jobs
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from tracelock.cron.runner import tick_once
from tracelock.skills.osint_skill import skill_manifest, run_osint_skill


@dataclass
class GatewayConfig:
    host: str = "0.0.0.0"
    port: int = 8787
    enable_telegram: bool = True
    enable_http: bool = True
    enable_cron: bool = True
    cron_interval_sec: float = 60.0
    cases_dir: str = ""
    no_network: bool = False
    max_waves: int = 3
    telegram_poll: bool = True

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        return cls(
            host=os.environ.get("TRACELOCK_GATEWAY_HOST", "0.0.0.0"),
            port=int(os.environ.get("TRACELOCK_GATEWAY_PORT") or "8787"),
            enable_telegram=os.environ.get("TRACELOCK_GATEWAY_TELEGRAM", "1")
            not in ("0", "false"),
            enable_http=os.environ.get("TRACELOCK_GATEWAY_HTTP", "1")
            not in ("0", "false"),
            enable_cron=os.environ.get("TRACELOCK_GATEWAY_CRON", "1")
            not in ("0", "false"),
            cron_interval_sec=float(os.environ.get("TRACELOCK_CRON_INTERVAL") or "60"),
            cases_dir=os.environ.get("TRACELOCK_CASES_DIR")
            or str(Path.home() / ".tracelock" / "cases"),
            no_network=os.environ.get("TRACELOCK_NO_NETWORK", "")
            in ("1", "true", "yes"),
            max_waves=int(os.environ.get("TRACELOCK_GATEWAY_MAX_WAVES") or "3"),
            telegram_poll=os.environ.get("TRACELOCK_TELEGRAM_POLL", "1")
            not in ("0", "false"),
        )


HELP_TEXT = """TraceLock OSINT gateway

Commands:
  /help              this text
  /osint <clue>      investigate (handle, phone, name)
  /investigate …    alias for /osint
  /continue <case>   continue open case path
  /status            gateway status
  /skills            list skills

Examples:
  /osint @demo_subject_ig
  /osint phone:081255500100
  /osint name:Example Public Figure

Policy: public sources only · HITL for captcha / Layer-B · no breach tools
"""


def _extract_clue(text: str) -> str:
    t = (text or "").strip()
    for prefix in ("/osint", "/investigate", "/cari", "/lacak"):
        if t.lower().startswith(prefix):
            return t[len(prefix) :].strip()
    return t


def handle_inbound_text(
    text: str,
    *,
    cfg: GatewayConfig,
    session_id: str = "default",
) -> str:
    raw = (text or "").strip()
    if not raw:
        return "Send a clue or /help"
    low = raw.lower()
    if low in ("/help", "help", "/start"):
        return HELP_TEXT
    if low in ("/status", "status"):
        return json.dumps(
            {
                "product": "TraceLock",
                "gateway": True,
                "skill": skill_manifest()["name"],
                "cases_dir": cfg.cases_dir,
                "cron": cfg.enable_cron,
            },
            indent=2,
        )
    if low in ("/skills", "skills"):
        return json.dumps(skill_manifest(), indent=2)

    if low.startswith("/continue"):
        rest = raw.split(maxsplit=1)
        if len(rest) < 2:
            return "Usage: /continue /path/to/case.json"
        case = Path(rest[1].strip())
        res = run_osint_skill(
            "continue",
            case_path=case,
            max_waves=cfg.max_waves,
            no_network=cfg.no_network,
            continue_existing=True,
        )
        return res.to_message()

    if low.startswith("/") and not any(
        low.startswith(p) for p in ("/osint", "/investigate", "/cari", "/lacak")
    ):
        return f"Unknown command. {HELP_TEXT}"

    clue = _extract_clue(raw)
    if not clue:
        return "Usage: /osint <handle|phone|name>"

    cases = Path(cfg.cases_dir)
    cases.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.@+-]+", "_", clue)[:40]
    case_path = cases / f"{session_id}_{int(time.time())}_{safe}.json"

    res = run_osint_skill(
        clue,
        case_path=case_path,
        max_waves=cfg.max_waves,
        min_waves=1,
        no_network=cfg.no_network,
    )
    return res.to_message()


class _GatewayState:
    def __init__(self, cfg: GatewayConfig) -> None:
        self.cfg = cfg
        self.started = time.time()
        self.requests = 0
        self.last_error = ""
        self.stop = threading.Event()


def _make_handler(state: _GatewayState):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return  # quiet

        def _json(self, code: int, obj: Any) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _text(self, code: int, text: str) -> None:
            body = (text or "").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            state.requests += 1
            u = urlparse(self.path)
            if u.path in ("/", "/health", "/status"):
                self._json(
                    200,
                    {
                        "ok": True,
                        "product": "TraceLock",
                        "uptime_sec": int(time.time() - state.started),
                        "requests": state.requests,
                        "skill": skill_manifest()["name"],
                    },
                )
                return
            if u.path == "/help":
                self._text(200, HELP_TEXT)
                return
            qs = parse_qs(u.query or "")
            if u.path == "/osint" and qs.get("q"):
                msg = handle_inbound_text(qs["q"][0], cfg=state.cfg, session_id="http")
                self._text(200, msg)
                return
            self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            state.requests += 1
            u = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                data = {"text": raw.decode("utf-8", errors="replace")}

            # Telegram webhook style
            if u.path in ("/telegram", "/webhook/telegram"):
                from tracelock.gateway.adapters.telegram import (
                    authorized,
                    parse_update,
                    send_message,
                )

                parsed = parse_update(data if "message" in data or "edited_message" in data else data)
                if not parsed:
                    # maybe already flat
                    text = data.get("text") or data.get("message", {}).get("text") or ""
                    chat_id = data.get("chat_id") or data.get("message", {}).get("chat", {}).get("id")
                    user_id = data.get("user_id") or data.get("message", {}).get("from", {}).get("id")
                else:
                    text = parsed["text"]
                    chat_id = parsed["chat_id"]
                    user_id = parsed["user_id"]
                if user_id is not None and not authorized(user_id):
                    self._json(403, {"ok": False, "error": "not authorized"})
                    return
                reply = handle_inbound_text(
                    text, cfg=state.cfg, session_id=f"tg_{chat_id}"
                )
                if chat_id is not None:
                    send_message(chat_id, reply)
                self._json(200, {"ok": True})
                return

            if u.path in ("/osint", "/message", "/webhook"):
                text = data.get("text") or data.get("q") or data.get("message") or ""
                session = str(data.get("session_id") or data.get("from") or "http")
                reply = handle_inbound_text(text, cfg=state.cfg, session_id=session)
                # WhatsApp Cloud API style response field
                self._json(200, {"ok": True, "reply": reply, "text": reply})
                return

            self._json(404, {"ok": False, "error": "not found"})

    return H


def _telegram_poll_loop(state: _GatewayState) -> None:
    from tracelock.gateway.adapters.telegram import (
        authorized,
        bot_token,
        get_updates,
        parse_update,
        send_message,
    )

    if not bot_token():
        return
    offset: Optional[int] = None
    while not state.stop.is_set():
        try:
            upd = get_updates(offset=offset, timeout=25)
            if not upd.get("ok"):
                state.last_error = str(upd.get("error") or upd)[:200]
                time.sleep(5)
                continue
            for item in upd.get("result") or []:
                offset = int(item.get("update_id", 0)) + 1
                parsed = parse_update(item)
                if not parsed or not parsed.get("text"):
                    continue
                if not authorized(parsed.get("user_id") or ""):
                    continue
                reply = handle_inbound_text(
                    parsed["text"],
                    cfg=state.cfg,
                    session_id=f"tg_{parsed.get('chat_id')}",
                )
                send_message(parsed["chat_id"], reply)
        except Exception as e:
            state.last_error = str(e)[:200]
            time.sleep(3)


def _cron_loop(state: _GatewayState) -> None:
    while not state.stop.is_set():
        try:
            tick_once(no_network=state.cfg.no_network)
        except Exception as e:
            state.last_error = f"cron: {e}"[:200]
        state.stop.wait(state.cfg.cron_interval_sec)


def run_gateway(cfg: Optional[GatewayConfig] = None, *, block: bool = True) -> GatewayConfig:
    cfg = cfg or GatewayConfig.from_env()
    Path(cfg.cases_dir).mkdir(parents=True, exist_ok=True)
    state = _GatewayState(cfg)
    threads: list[threading.Thread] = []

    if cfg.enable_cron:
        t = threading.Thread(target=_cron_loop, args=(state,), daemon=True, name="cron")
        t.start()
        threads.append(t)

    if cfg.enable_telegram and cfg.telegram_poll:
        t = threading.Thread(
            target=_telegram_poll_loop, args=(state,), daemon=True, name="telegram"
        )
        t.start()
        threads.append(t)

    httpd = None
    if cfg.enable_http:
        handler = _make_handler(state)
        httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)
        print(
            json.dumps(
                {
                    "event": "gateway_start",
                    "host": cfg.host,
                    "port": cfg.port,
                    "telegram": cfg.enable_telegram,
                    "cron": cfg.enable_cron,
                    "cases_dir": cfg.cases_dir,
                    "endpoints": [
                        f"http://{cfg.host}:{cfg.port}/health",
                        f"http://{cfg.host}:{cfg.port}/osint?q=@handle",
                        f"POST /osint {{\"text\":\"…\"}}",
                        f"POST /telegram  (Telegram webhook)",
                        f"POST /webhook   (WhatsApp/generic)",
                    ],
                },
                indent=2,
            )
        )
        if block:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                state.stop.set()
                httpd.shutdown()
        else:
            t = threading.Thread(target=httpd.serve_forever, daemon=True, name="http")
            t.start()
            threads.append(t)
    elif block:
        print(json.dumps({"event": "gateway_start", "http": False, "telegram_poll": True}))
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            state.stop.set()

    return cfg
