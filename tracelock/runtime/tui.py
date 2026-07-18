"""TraceLock interactive console — full TUI + simple fallback + setup wizard.

Launch:
  tracelock            # opens TUI when stdout is a TTY
  tracelock chat
  tracelock tui
  tracelock chat -c    # continue last session
  TRACELOCK_SIMPLE_TUI=1  # force classic line mode
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from tracelock.runtime.config import load_config, save_config
from tracelock.runtime.llm import list_models
from tracelock.runtime.react_agent import ReactAgent
from tracelock.runtime.session import SessionStore
from tracelock.runtime.slash import dispatch_slash


BANNER = r"""
╔══════════════════════════════════════════════════════════════════╗
║  TraceLock  ·  Detective OSINT Console                           ║
║  find @handle  ·  /models  ·  /pivot  ·  Tab complete  ·  /help  ║
╚══════════════════════════════════════════════════════════════════╝
"""

COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "magenta": "\033[35m",
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
    key = input("API key (Enter=keep): ").strip()
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
        print(_c("yellow", "No API key — local tool fallback still works."))
    tg = input("Telegram bot token (optional, Enter=skip): ").strip()
    if tg:
        cfg.telegram_bot_token = tg
    save_config(cfg)
    print(_c("green", f"\nSaved → {cfg.public_status()}\n"))
    print(_c("dim", "Start console:  tracelock chat\n"))


def run_simple_tui(*, session_id: str = "tui_local") -> int:
    """Classic readline-style loop (CI / dumb terminals)."""
    cfg = load_config()
    print(BANNER)
    print(
        _c(
            "dim",
            f"model={cfg.model}  llm={'yes' if cfg.has_llm else 'local'}  "
            f"(simple mode — full TUI: tracelock tui on a real terminal)\n",
        )
    )
    store = SessionStore()
    session = store.get_or_create(
        platform="tui", external_id=session_id, case_dir=cfg.cases_dir
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
                cfg = load_config()
                agent = ReactAgent(cfg, on_progress=on_progress)
                continue
        print(_c("magenta", "… working"))
        result = agent.chat(
            text, platform="tui", external_id=session_id, session=session
        )
        session = store.get(session.id) or session
        print()
        print(_c("green", "── reply ──"))
        print(result.reply)
        if result.tool_trace:
            tools = ", ".join(t.get("tool", "?") for t in result.tool_trace)
            print(
                _c(
                    "dim",
                    f"── tools: {tools}  turns={result.turns} mode={result.mode} ──",
                )
            )
        print()
    return 0


def run_tui(
    *,
    session_id: str = "tui_local",
    resume: bool = False,
    resume_id: str = "",
    simple: Optional[bool] = None,
) -> int:
    """Prefer full-screen curses TUI; fall back when not a TTY."""
    force_simple = (
        simple
        if simple is not None
        else os.environ.get("TRACELOCK_SIMPLE_TUI", "").lower() in ("1", "true", "yes")
    )
    if force_simple or not sys.stdout.isatty() or not sys.stdin.isatty():
        return run_simple_tui(session_id=session_id)

    try:
        from tracelock.runtime.tui_app import run_curses_tui

        return run_curses_tui(
            session_id=session_id, resume=resume, resume_id=resume_id
        )
    except Exception as e:
        print(_c("yellow", f"Full TUI failed ({e}); simple mode."))
        return run_simple_tui(session_id=session_id)
