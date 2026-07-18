"""True agentic loop: system + history → LLM → tool_calls → observe → repeat.

When no API key is configured, falls back to local multi-wave investigate
skill so the product still works offline for demos/CI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from tracelock.runtime.config import RuntimeConfig, load_config
from tracelock.runtime.llm import LLMResponse, chat_completions
from tracelock.runtime.memory import MemoryStore
from tracelock.runtime.session import Session, SessionStore
from tracelock.runtime.tool_schema import execute_tool_call, openai_tools


ProgressCb = Callable[[str, str], None]  # (kind, message)


SYSTEM_BASE = """You are TraceLock, an ethical public-source OSINT investigation agent
that works like a detective — non-linear triangulation, not a single Google pass.

IDENTITY
- Public sources only (SERP, public profiles, public campus/docs packs).
- Digital identity (handles/phones) ≠ civil identity (legal name + institutional ID).
- Never invent identities. Prefer tools over speculation.

DETECTIVE LOOP (mandatory multi-hop)
1) Seed: analyze_clues on the operator clue.
2) Surface: digital_footprint + collect_public (username_enum, websearch).
3) Pivot: ALWAYS call triangulate after new evidence — second accounts, @mentions,
   schools, places, public-doc anchors become new seeds.
4) Expand: name_pattern_enum on handles; re-collect_public with modules from triangulate.
5) Anchor validate: for name/institution leads use collect_public modules gov_id,pddikti
   (public packs only — never claim private breach data).
6) Place expand: if domisili appears, SERP name+city+school style queries via websearch.
7) Network: friend/related handles are LEADS to check, not automatic same-person.
8) Cross-check: high claims need ≥2 independent public signals before strong language.
9) HITL: captcha / e-wallet Layer-B / civil lock → open_hitl or phone_checklist only.
10) report + explain lead graph pivots in plain language.

TOOLS ORDER (typical)
analyze_clues → digital_footprint → collect_public → triangulate →
name_pattern_enum / phone tools → collect_public (again on new seeds) →
triangulate → build_dossier → report
Do NOT stop after one tool. Each finding is a door to another room.

POLICY
- Forbidden: breach dumps, NIK bots, captcha farms, grey admin APIs, malware.
- Allowed: public SERP, username enum, morphs, passive gov packs, HITL gates.
- Memory: save durable operator prefs; session_search for past cases.
"""


def build_system_prompt(cfg: RuntimeConfig, memory: MemoryStore, case_path: str) -> str:
    parts = [SYSTEM_BASE]
    parts.append(f"\nMODEL: {cfg.model}\nCASE_PATH: {case_path}\nPERSONALITY: {cfg.personality}\n")
    if cfg.personality == "brief":
        parts.append("Style: terse operator brief. Bullet points. No fluff.\n")
    elif cfg.personality == "forensic":
        parts.append("Style: forensic chain-of-custody tone. Cite tool outputs.\n")
    else:
        parts.append("Style: clear investigation operator. Indonesian or English matching the user.\n")
    # Weaponize skill .md playbook
    try:
        playbook = Path(__file__).resolve().parent.parent / "skills" / "detective_osint.md"
        if playbook.is_file():
            parts.append("\n" + playbook.read_text(encoding="utf-8")[:4000])
    except Exception:
        pass
    if cfg.memory_enabled:
        parts.append("\n" + memory.prompt_block())
    return "\n".join(parts)


@dataclass
class AgentTurnResult:
    ok: bool
    reply: str
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0
    mode: str = "live"  # live | local_fallback
    case_path: str = ""
    session_id: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reply": self.reply,
            "turns": self.turns,
            "mode": self.mode,
            "case_path": self.case_path,
            "session_id": self.session_id,
            "tool_trace": self.tool_trace,
            "error": self.error,
        }


class ReactAgent:
    def __init__(
        self,
        cfg: Optional[RuntimeConfig] = None,
        *,
        on_progress: Optional[ProgressCb] = None,
    ) -> None:
        self.cfg = (cfg or load_config()).apply_env_overrides()
        self.memory = MemoryStore.from_config(self.cfg)
        self.sessions = SessionStore()
        self.on_progress = on_progress
        self.tools = openai_tools()

    def _progress(self, kind: str, msg: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(kind, msg)
            except Exception:
                pass
        elif self.cfg.show_tool_progress and kind in ("tool", "think", "info"):
            print(f"  · {msg}")

    def _ensure_case(self, session: Session) -> Path:
        if session.case_path:
            p = Path(session.case_path)
        else:
            cdir = Path(self.cfg.cases_dir)
            cdir.mkdir(parents=True, exist_ok=True)
            p = cdir / f"{session.id}.json"
            session.case_path = str(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def chat(
        self,
        user_text: str,
        *,
        platform: str = "cli",
        external_id: str = "local",
        session: Optional[Session] = None,
    ) -> AgentTurnResult:
        user_text = (user_text or "").strip()
        if not user_text:
            return AgentTurnResult(ok=False, reply="Empty message.", error="empty")

        session = session or self.sessions.get_or_create(
            platform=platform,
            external_id=external_id,
            case_dir=self.cfg.cases_dir,
        )
        case_path = self._ensure_case(session)

        # extract clues from free text for tool defaults
        clues = list(session.clues)
        for m in re.finditer(r"(@[\w.]{2,40}|phone:\S+|username:\S+|name:[^\n]+)", user_text, re.I):
            c = m.group(1).strip()
            if c not in clues:
                clues.append(c)
        session.clues = clues

        self.sessions.append_message(session, "user", user_text)

        if not self.cfg.has_llm:
            return self._local_fallback(user_text, session, case_path)

        return self._live_loop(user_text, session, case_path, clues)

    def _local_fallback(
        self, user_text: str, session: Session, case_path: Path
    ) -> AgentTurnResult:
        """No API key → still run real OSINT skill (deterministic tools)."""
        self._progress("info", "No API key — local investigate skill (tools still run)")
        from tracelock.skills.osint_skill import run_osint_skill

        res = run_osint_skill(
            user_text,
            case_path=case_path,
            max_waves=3,
            min_waves=1,
            no_network=False,
            continue_existing=case_path.is_file(),
        )
        reply = res.to_message()
        reply += (
            "\n\n_(Planner: local fallback — set API base + key with "
            "`tracelock setup` or `/model` for full tool-calling agent.)_"
        )
        self.sessions.append_message(session, "assistant", reply)
        return AgentTurnResult(
            ok=res.ok,
            reply=reply,
            turns=res.waves,
            mode="local_fallback",
            case_path=str(case_path),
            session_id=session.id,
            tool_trace=[{"skill": "osint-investigate", "waves": res.waves}],
        )

    def _live_loop(
        self,
        user_text: str,
        session: Session,
        case_path: Path,
        clues: list[str],
    ) -> AgentTurnResult:
        system = build_system_prompt(self.cfg, self.memory, str(case_path))
        # OpenAI messages: system + prior (user/assistant only from store, skip tool noise) + new is already stored
        history: list[dict[str, Any]] = [{"role": "system", "content": system}]
        # rebuild compact history from session (user/assistant text only for stability)
        for m in session.messages[:-1]:  # exclude just-added user; re-add cleanly
            role = m.get("role")
            if role in ("user", "assistant") and m.get("content"):
                history.append({"role": role, "content": str(m["content"])[:8000]})
        history.append({"role": "user", "content": user_text})

        tool_trace: list[dict[str, Any]] = []
        final_text = ""
        turns = 0
        max_turns = max(1, int(self.cfg.max_turns))

        mem_handler = self.memory.handle
        sess_search = self.sessions.search

        while turns < max_turns:
            turns += 1
            self._progress("think", f"model turn {turns}/{max_turns}")
            resp: LLMResponse = chat_completions(
                api_base=self.cfg.api_base,
                api_key=self.cfg.api_key,
                model=self.cfg.model,
                messages=history,
                tools=self.tools,
                temperature=self.cfg.temperature,
            )
            if not resp.ok:
                # one retry without tools for plain answer, then fail
                err = resp.error
                self._progress("info", f"LLM error: {err[:120]}")
                if turns == 1:
                    # try local fallback on hard failure
                    fb = self._local_fallback(user_text, session, case_path)
                    fb.error = err
                    fb.mode = "local_fallback_after_error"
                    return fb
                return AgentTurnResult(
                    ok=False,
                    reply=f"Model error: {err}",
                    tool_trace=tool_trace,
                    turns=turns,
                    mode="live",
                    case_path=str(case_path),
                    session_id=session.id,
                    error=err,
                )

            if resp.has_tools:
                # assistant message with tool_calls
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": resp.content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"].get("arguments_raw")
                                or json.dumps(tc["function"].get("arguments") or {}),
                            },
                        }
                        for tc in resp.tool_calls
                    ],
                }
                history.append(assistant_msg)

                for tc in resp.tool_calls:
                    name = tc["function"]["name"]
                    args = tc["function"].get("arguments") or {}
                    self._progress("tool", f"→ {name}({_brief_args(args)})")
                    result = execute_tool_call(
                        name,
                        args,
                        case_path=case_path,
                        clues=clues,
                        memory_handler=mem_handler,
                        session_search_handler=sess_search,
                    )
                    tool_trace.append(
                        {
                            "turn": turns,
                            "tool": name,
                            "args": args,
                            "ok": bool(result.get("ok", True)),
                            "summary": _tool_summary(result),
                        }
                    )
                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, ensure_ascii=False, default=str)[:8000],
                        }
                    )
                continue

            # final text response
            final_text = (resp.content or "").strip()
            if not final_text:
                final_text = "(no content from model)"
            break
        else:
            final_text = (
                final_text
                or "Reached max agent turns. Partial tool work is saved on the case file."
            )
            if tool_trace:
                final_text += "\n\nTools run: " + ", ".join(
                    t["tool"] for t in tool_trace[-12:]
                )

        self.sessions.append_message(session, "assistant", final_text)
        self.sessions.save(session)
        return AgentTurnResult(
            ok=True,
            reply=final_text,
            tool_trace=tool_trace,
            turns=turns,
            mode="live",
            case_path=str(case_path),
            session_id=session.id,
        )


def _brief_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts = []
    for k, v in list(args.items())[:4]:
        s = str(v)
        if len(s) > 40:
            s = s[:37] + "…"
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _tool_summary(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"error:{result['error']}"[:120]
    bits = []
    for k in ("evidence_count", "web_hit_count", "count", "modules", "action"):
        if k in result:
            bits.append(f"{k}={result[k]}")
    return ", ".join(bits)[:160] or ("ok" if result.get("ok") else "done")
