"""TraceLock interactive TUI — slash commands + agent chat.

Design: dark operator console (ANSI), multiline not required (single-line readline).
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from tracelock.runtime.config import load_config, save_config, update_config
from tracelock.runtime.llm import list_models
from tracelock.runtime.react_agent import ReactAgent
from tracelock.runtime.session import SessionStore
from tracelock.runtime.slash import dispatch_slash


BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║  TraceLock  ·  Agentic OSINT Console                     ║
║  /help  /setup  /models  /osint @handle                  ║
╚══════════════════════════════════════════════════════════╝
"""

COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "reset": "\033[0m",
}


def _c(name: str, text: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"{COLORS.get(name, '')}{text}{COLORS['reset']}"


def run_setup_wizard() -> None:
    """Interactive endpoint + API key + model selection."""
    cfg = load_config()
    print(_c("bold", "\nTraceLock setup\n"))
    print(f"Current API base: {cfg.api_base}")
    base = input("API base URL [/v1 compatible] (Enter=keep): ").strip()
    if base:
        cfg.api_base = base.rstrip("/")
    print(f"Current key: {cfg.public_status()['api_key']}")
    key = input("API key (Enter=keep, spaces stripped): ").strip()
    if key:
        cfg.api_key = key
    save_config(cfg)
    cfg = load_config()
    if cfg.api_key:
        print(_c("dim", f"Fetching {cfg.api_base}/models …"))
        r = list_models(cfg.api_base, cfg.api_key)
        if r.get("ok"):
            models = r.get("models") or []
            for i, m in enumerate(models[:30], 1):
                print(f"  {i:2d}. {m.get('id')}")
            pick = input(f"Model id or number (Enter=keep {cfg.model}): ").strip()
            if pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < min(30, len(models)):
                    cfg.model = models[idx]["id"]
            elif pick:
                cfg.model = pick
        else:
            print(_c("yellow", f"Could not list models: {r.get('error')}"))
            m = input(f"Model id (Enter=keep {cfg.model}): ").strip()
            if m:
                cfg.model = m
    else:
        print(_c("yellow", "No API key — agent will use local tool skill fallback."))
    tg = input("Telegram bot token (optional, Enter=skip): ").strip()
    if tg:
        cfg.telegram_bot_token = tg
    save_config(cfg)
    print(_c("green", f"\nSaved → {cfg.public_status()}\n"))


def run_tui(*, session_id: str = "tui_local") -> int:
    cfg = load_config()
    print(BANNER)
    print(_c("dim", f"model={cfg.model}  base={cfg.api_base}  llm={'yes' if cfg.has_llm else 'local-fallback'}"))
    print(_c("dim", "Type /help · /setup · or a natural language OSINT request\n"))

    store = SessionStore()
    session = store.get_or_create(
        platform="tui",
        external_id=session_id,
        case_dir=cfg.cases_dir,
    )

    def on_progress(kind: str, msg: str) -> None:
        print(_c("dim", f"  ▸ {msg}"))

    agent = ReactAgent(cfg, on_progress=on_progress)

    while True:
        try:
            line = input(_c("cyan", "tracelock› "))
        except (EOFError, KeyboardInterrupt):
            print("\n" + _c("dim", "bye"))
            return 0
        text = (line or "").strip()
        if not text:
            continue
        if text in ("exit", "quit", ":q"):
            return 0

        if text.startswith("/"):
            sr = dispatch_slash(text, cfg=cfg, session=session, platform="tui")
            if sr.reset_session:
                session = store.reset(session.id)
                print(_c("yellow", sr.reply))
                continue
            if sr.passthrough:
                text = sr.passthrough
            elif sr.handled:
                print(sr.reply)
                # reload config after /key /endpoint /model
                cfg = load_config()
                agent = ReactAgent(cfg, on_progress=on_progress)
                continue

        print(_c("dim", "… agent working"))
        result = agent.chat(text, platform="tui", external_id=session_id, session=session)
        session = store.get(session.id) or session
        print()
        print(_c("green", "── reply ──"))
        print(result.reply)
        if result.tool_trace:
            tools = ", ".join(t.get("tool", "?") for t in result.tool_trace)
            print(_c("dim", f"── tools: {tools}  turns={result.turns} mode={result.mode} ──"))
        print()
    return 0
