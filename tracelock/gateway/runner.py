"""Gateway — long-lived process: Telegram + HTTP + cron.

Inbound path (all platforms):
  adapter event → pipeline.handle_message → slash | ReactAgent tool loop → deliver
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from tracelock.cron.runner import tick_once
from tracelock.runtime.config import load_config
from tracelock.runtime.pipeline import handle_message


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
        rt = load_config()
        return cls(
            host=os.environ.get("TRACELOCK_GATEWAY_HOST", rt.gateway_host),
            port=int(os.environ.get("TRACELOCK_GATEWAY_PORT") or rt.gateway_port),
            enable_telegram=os.environ.get("TRACELOCK_GATEWAY_TELEGRAM", "1")
            not in ("0", "false"),
            enable_http=os.environ.get("TRACELOCK_GATEWAY_HTTP", "1")
            not in ("0", "false"),
            enable_cron=os.environ.get("TRACELOCK_GATEWAY_CRON", "1")
            not in ("0", "false"),
            cron_interval_sec=float(os.environ.get("TRACELOCK_CRON_INTERVAL") or "60"),
            cases_dir=os.environ.get("TRACELOCK_CASES_DIR") or rt.cases_dir,
            no_network=os.environ.get("TRACELOCK_NO_NETWORK", "")
            in ("1", "true", "yes"),
            max_waves=int(os.environ.get("TRACELOCK_GATEWAY_MAX_WAVES") or "3"),
            telegram_poll=os.environ.get("TRACELOCK_TELEGRAM_POLL", "1")
            not in ("0", "false"),
        )


def process_inbound(
    text: str,
    *,
    platform: str,
    external_id: str,
    no_network: bool = False,
) -> str:
    if no_network:
        os.environ["TRACELOCK_NO_NETWORK"] = "1"
    result = handle_message(
        text,
        platform=platform,
        external_id=str(external_id),
    )
    return result.reply


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
            return

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
                rt = load_config()
                self._json(
                    200,
                    {
                        "ok": True,
                        "product": "TraceLock",
                        "uptime_sec": int(time.time() - state.started),
                        "requests": state.requests,
                        "model": rt.model,
                        "has_llm": rt.has_llm,
                        "pipeline": "slash→react_agent→tools",
                    },
                )
                return
            if u.path == "/help":
                self._text(
                    200,
                    process_inbound("/help", platform="http", external_id="help"),
                )
                return
            qs = parse_qs(u.query or "")
            if u.path == "/osint" and qs.get("q"):
                msg = process_inbound(
                    qs["q"][0],
                    platform="http",
                    external_id="get",
                    no_network=state.cfg.no_network,
                )
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

            if u.path in ("/telegram", "/webhook/telegram"):
                from tracelock.gateway.adapters.telegram import (
                    authorized,
                    parse_update,
                    send_message,
                )

                parsed = parse_update(
                    data if ("message" in data or "edited_message" in data) else data
                )
                if parsed:
                    text = parsed["text"]
                    chat_id = parsed["chat_id"]
                    user_id = parsed["user_id"]
                else:
                    text = data.get("text") or data.get("message", {}).get("text") or ""
                    chat_id = data.get("chat_id") or data.get("message", {}).get("chat", {}).get("id")
                    user_id = data.get("user_id") or data.get("message", {}).get("from", {}).get("id")
                if user_id is not None and not authorized(user_id):
                    self._json(403, {"ok": False, "error": "not authorized"})
                    return
                reply = process_inbound(
                    text,
                    platform="telegram",
                    external_id=str(chat_id),
                    no_network=state.cfg.no_network,
                )
                if chat_id is not None:
                    send_message(chat_id, reply)
                self._json(200, {"ok": True})
                return

            if u.path in ("/osint", "/message", "/webhook", "/whatsapp"):
                text = data.get("text") or data.get("q") or data.get("message") or ""
                # WhatsApp Cloud API sometimes nests
                if not text and isinstance(data.get("entry"), list):
                    try:
                        text = (
                            data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
                        )
                    except Exception:
                        text = ""
                session = str(
                    data.get("session_id")
                    or data.get("from")
                    or data.get("wa_id")
                    or "http"
                )
                platform = "whatsapp" if "whatsapp" in u.path else "webhook"
                reply = process_inbound(
                    text,
                    platform=platform,
                    external_id=session,
                    no_network=state.cfg.no_network,
                )
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
        # load from runtime config
        rt = load_config()
        if rt.telegram_bot_token:
            os.environ["TRACELOCK_TELEGRAM_BOT_TOKEN"] = rt.telegram_bot_token
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
                # typing-ish: send nothing, just process
                reply = process_inbound(
                    parsed["text"],
                    platform="telegram",
                    external_id=str(parsed.get("chat_id")),
                    no_network=state.cfg.no_network,
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
    # sync config tokens
    rt = load_config()
    if rt.telegram_bot_token:
        os.environ.setdefault("TRACELOCK_TELEGRAM_BOT_TOKEN", rt.telegram_bot_token)
    if rt.telegram_allowlist:
        os.environ.setdefault("TRACELOCK_TELEGRAM_ALLOWLIST", rt.telegram_allowlist)

    state = _GatewayState(cfg)
    if cfg.enable_cron:
        threading.Thread(target=_cron_loop, args=(state,), daemon=True, name="cron").start()
    if cfg.enable_telegram and cfg.telegram_poll:
        threading.Thread(
            target=_telegram_poll_loop, args=(state,), daemon=True, name="telegram"
        ).start()

    if cfg.enable_http:
        handler = _make_handler(state)
        httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)
        print(
            json.dumps(
                {
                    "event": "gateway_start",
                    "host": cfg.host,
                    "port": cfg.port,
                    "pipeline": "platform → slash → react_agent (tool calls) → reply",
                    "telegram": cfg.enable_telegram,
                    "cron": cfg.enable_cron,
                    "model": rt.model,
                    "has_llm": rt.has_llm,
                    "endpoints": [
                        f"http://{cfg.host}:{cfg.port}/health",
                        "POST /message {\"text\":\"…\"}",
                        "POST /telegram  (Telegram webhook)",
                        "POST /whatsapp  (Cloud API / generic)",
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
            threading.Thread(target=httpd.serve_forever, daemon=True, name="http").start()
    elif block:
        print(json.dumps({"event": "gateway_start", "http": False}))
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            state.stop.set()
    return cfg
