"""Slash command registry — works in TUI and messaging platforms."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from tracelock.runtime.config import RuntimeConfig, load_config, save_config, update_config
from tracelock.runtime.llm import list_models
from tracelock.runtime.memory import MemoryStore
from tracelock.runtime.session import Session, SessionStore


@dataclass
class SlashContext:
    cfg: RuntimeConfig
    session: Session
    platform: str = "cli"
    raw: str = ""


@dataclass
class SlashResult:
    handled: bool
    reply: str = ""
    reset_session: bool = False
    # if set, remaining text should be sent to agent as normal chat
    passthrough: str = ""


Handler = Callable[[SlashContext, str], SlashResult]


def _help(_: SlashContext, __: str) -> SlashResult:
    text = """TraceLock — short commands

  find / who / hunt <clue>   full detective OSINT (alias: /f /w /h)
  /go <clue>                 same as find
  /pivot                     force triangulate on current case
  /new                       clear session
  /status  /case             where you are
  /model  /models  /key      LLM setup
  /endpoint <url>            API base …/v1
  /mem                       memory notes
  /help

Or just type a clue:  @handle   phone:08…   name:Someone
Agent multi-hops: surface → pivot → anchors → report.
"""
    return SlashResult(True, text)


def _status(ctx: SlashContext, _: str) -> SlashResult:
    st = ctx.cfg.public_status()
    st["session_id"] = ctx.session.id
    st["platform"] = ctx.platform
    st["messages"] = len(ctx.session.messages)
    st["case_path"] = ctx.session.case_path
    st["has_llm"] = ctx.cfg.has_llm
    return SlashResult(True, json.dumps(st, indent=2))


def _new(ctx: SlashContext, _: str) -> SlashResult:
    return SlashResult(True, "Session reset. Send a clue or question.", reset_session=True)


def _model(ctx: SlashContext, args: str) -> SlashResult:
    args = args.strip()
    if not args:
        return SlashResult(
            True,
            f"Current model: {ctx.cfg.model}\nAPI base: {ctx.cfg.api_base}\nUse /model <id> or /models",
        )
    update_config(model=args)
    ctx.cfg.model = args
    return SlashResult(True, f"Model set to `{args}`")


def _models(ctx: SlashContext, _: str) -> SlashResult:
    if not ctx.cfg.api_key:
        return SlashResult(True, "No API key. Set with /key <secret> then /models")
    r = list_models(ctx.cfg.api_base, ctx.cfg.api_key)
    if not r.get("ok"):
        return SlashResult(True, f"Failed to list models: {r.get('error')}")
    lines = [f"Models from {ctx.cfg.api_base}/models ({r.get('count')}):"]
    for m in (r.get("models") or [])[:40]:
        lines.append(f"  • {m.get('id')}")
    if (r.get("count") or 0) > 40:
        lines.append(f"  … +{r['count']-40} more")
    lines.append("Set with /model <id>")
    return SlashResult(True, "\n".join(lines))


def _endpoint(ctx: SlashContext, args: str) -> SlashResult:
    url = args.strip().rstrip("/")
    if not url:
        return SlashResult(True, f"API base: {ctx.cfg.api_base}")
    if not url.startswith("http"):
        return SlashResult(True, "Endpoint must start with http:// or https://")
    update_config(api_base=url)
    ctx.cfg.api_base = url
    return SlashResult(True, f"API base set to {url}\nTry /models")


def _key(ctx: SlashContext, args: str) -> SlashResult:
    secret = args.strip()
    if not secret:
        return SlashResult(True, f"API key: {ctx.cfg.public_status()['api_key']}")
    update_config(api_key=secret)
    ctx.cfg.api_key = secret
    return SlashResult(True, "API key saved to ~/.tracelock/config.json")


def _memory(ctx: SlashContext, args: str) -> SlashResult:
    store = MemoryStore.from_config(ctx.cfg)
    if not args or args.strip() in ("list", "show"):
        block = store.prompt_block()
        return SlashResult(True, block or "(empty memory)")
    return SlashResult(True, "Usage: /memory  or  /memory list")


def _personality(ctx: SlashContext, args: str) -> SlashResult:
    args = args.strip().lower()
    if not args:
        return SlashResult(True, f"personality={ctx.cfg.personality}")
    if args not in ("operator", "brief", "forensic"):
        return SlashResult(True, "Choose: operator | brief | forensic")
    update_config(personality=args)
    ctx.cfg.personality = args
    return SlashResult(True, f"personality={args}")


def _osint(ctx: SlashContext, args: str) -> SlashResult:
    clue = args.strip()
    if not clue:
        return SlashResult(
            True,
            "Usage: find @handle · who name:… · hunt phone:08…\n"
            "Short: /f /w /h /go",
        )
    prompt = (
        f"DETECTIVE OSINT (non-linear triangulation) on: {clue}\n"
        "Run analyze → digital_footprint → collect_public → triangulate → "
        "expand new seeds with collect_public again → triangulate → "
        "build_dossier → report. "
        "Treat every handle/school/place/doc hit as a new door. "
        "Cross-validate anchors with public packs. Human brief + lead pivots."
    )
    return SlashResult(True, "", passthrough=prompt)


def _pivot(ctx: SlashContext, args: str) -> SlashResult:
    """Force triangulate path via agent or skill."""
    extra = args.strip()
    prompt = (
        "Run tool triangulate on the active case, then collect_public on next_modules, "
        "then triangulate again, then report. Focus on second accounts and anchors."
    )
    if extra:
        prompt = f"Clue/context: {extra}\n" + prompt
    return SlashResult(True, "", passthrough=prompt)


def _case(ctx: SlashContext, _: str) -> SlashResult:
    return SlashResult(
        True,
        f"session={ctx.session.id}\ncase={ctx.session.case_path or '(none yet)'}\nclues={ctx.session.clues}",
    )


def _undo(ctx: SlashContext, _: str) -> SlashResult:
    msgs = ctx.session.messages
    # pop last assistant then user if present
    removed = 0
    if msgs and msgs[-1].get("role") == "assistant":
        msgs.pop()
        removed += 1
    if msgs and msgs[-1].get("role") == "user":
        msgs.pop()
        removed += 1
    SessionStore().save(ctx.session)
    return SlashResult(True, f"Removed {removed} message(s).")


def _setup(ctx: SlashContext, _: str) -> SlashResult:
    return SlashResult(
        True,
        "Run interactive setup in terminal:\n"
        "  python3 -m tracelock setup\n"
        "Or set now:\n"
        "  /endpoint https://dashscope-intl.aliyuncs.com/compatible-mode/v1\n"
        "  /key sk-...\n"
        "  /models\n"
        "  /model qwen-plus",
    )


def _stop(_: SlashContext, __: str) -> SlashResult:
    return SlashResult(True, "Stop acknowledged. Send a new message to continue.")


COMMANDS: dict[str, Handler] = {
    "help": _help,
    "start": _help,
    "?": _help,
    "status": _status,
    "st": _status,
    "new": _new,
    "reset": _new,
    "model": _model,
    "models": _models,
    "endpoint": _endpoint,
    "key": _key,
    "apikey": _key,
    "memory": _memory,
    "mem": _memory,
    "personality": _personality,
    # human short verbs
    "osint": _osint,
    "investigate": _osint,
    "find": _osint,
    "who": _osint,
    "hunt": _osint,
    "go": _osint,
    "f": _osint,
    "w": _osint,
    "h": _osint,
    "cari": _osint,
    "lacak": _osint,
    "siapa": _osint,
    "pivot": _pivot,
    "tri": _pivot,
    "case": _case,
    "undo": _undo,
    "setup": _setup,
    "stop": _stop,
}


def dispatch_slash(
    text: str,
    *,
    cfg: Optional[RuntimeConfig] = None,
    session: Optional[Session] = None,
    platform: str = "cli",
) -> SlashResult:
    """If text starts with /, handle it. Else not handled."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return SlashResult(False, "")
    cfg = cfg or load_config()
    if session is None:
        session = SessionStore().get_or_create(platform=platform, external_id="default")
    # parse
    body = raw[1:]
    if " " in body:
        cmd, args = body.split(" ", 1)
    else:
        cmd, args = body, ""
    cmd = cmd.lower().strip().lstrip("/")
    handler = COMMANDS.get(cmd)
    if not handler:
        return SlashResult(
            True,
            f"Unknown command /{cmd}. Try /help",
        )
    ctx = SlashContext(cfg=cfg, session=session, platform=platform, raw=raw)
    return handler(ctx, args)
