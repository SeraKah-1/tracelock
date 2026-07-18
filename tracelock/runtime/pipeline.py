"""Unified inbound pipeline: platform message → slash → agent → reply text.

This is the single path used by TUI, Telegram, webhook, cron delivery triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from tracelock.runtime.config import RuntimeConfig, load_config
from tracelock.runtime.react_agent import AgentTurnResult, ReactAgent
from tracelock.runtime.session import SessionStore
from tracelock.runtime.slash import dispatch_slash


ProgressCb = Callable[[str, str], None]


@dataclass
class PipelineResult:
    reply: str
    session_id: str = ""
    agent: Optional[AgentTurnResult] = None
    slash: bool = False
    meta: dict[str, Any] | None = None


def handle_message(
    text: str,
    *,
    platform: str = "cli",
    external_id: str = "default",
    cfg: Optional[RuntimeConfig] = None,
    on_progress: Optional[ProgressCb] = None,
) -> PipelineResult:
    """Process one inbound user message from any platform."""
    cfg = (cfg or load_config()).apply_env_overrides()
    store = SessionStore()
    session = store.get_or_create(
        platform=platform,
        external_id=str(external_id),
        case_dir=cfg.cases_dir,
    )

    raw = (text or "").strip()
    if raw.startswith("/"):
        sr = dispatch_slash(raw, cfg=cfg, session=session, platform=platform)
        if sr.reset_session:
            session = store.reset(session.id)
            return PipelineResult(reply=sr.reply, session_id=session.id, slash=True)
        if sr.passthrough:
            raw = sr.passthrough
        elif sr.handled:
            return PipelineResult(reply=sr.reply, session_id=session.id, slash=True)

    agent = ReactAgent(cfg, on_progress=on_progress)
    result = agent.chat(
        raw,
        platform=platform,
        external_id=str(external_id),
        session=session,
    )
    return PipelineResult(
        reply=result.reply,
        session_id=result.session_id or session.id,
        agent=result,
        slash=False,
        meta={"mode": result.mode, "turns": result.turns, "tools": len(result.tool_trace)},
    )
