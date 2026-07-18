"""OSINT skill — reusable procedure wrapping TraceLock continuous loop.

Short clue → multi-wave investigate → human report. Callable from CLI,
messaging gateway, and scheduled jobs.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from tracelock.loop import LoopResult, continue_case, investigate_continuous
from tracelock.report_human import build_human_report


OSINT_SKILL = {
    "name": "osint-investigate",
    "description": (
        "Run continuous public-source OSINT on a handle, phone, or free-text clue. "
        "Multi-wave ReAct until checklist gaps close or HITL is required. "
        "Returns graded human-readable report. Never uses --offline for real work."
    ),
    "triggers": [
        "osint",
        "investigate",
        "doxx",  # informal operator slang — still ethical public-only
        "footprint",
        "cari",
        "lacak",
        "siapa",
    ],
    "toolset": "osint_full",
    "default_max_waves": 4,
    "default_min_waves": 2,
}


@dataclass
class SkillResult:
    ok: bool
    skill: str
    case_path: str
    report_brief: str = ""
    report_markdown: str = ""
    stop_reason: str = ""
    waves: int = 0
    hitl_open: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_message(self, max_chars: int = 3500) -> str:
        """Compact text for Telegram / WhatsApp / email delivery."""
        head = (
            f"TraceLock · {self.skill}\n"
            f"ok={self.ok} waves={self.waves} stop={self.stop_reason}\n"
            f"case={self.case_path}\n"
        )
        if self.hitl_open:
            head += f"HITL open gates: {self.hitl_open} (operator action needed)\n"
        body = (self.report_brief or self.report_markdown or "").strip()
        if len(body) > max_chars:
            body = body[: max_chars - 40] + "\n…(truncated — see case JSON)"
        return head + "\n" + body


def skill_manifest() -> dict[str, Any]:
    return dict(OSINT_SKILL)


def run_osint_skill(
    text: str,
    *,
    case_path: Optional[Path] = None,
    max_waves: int = 4,
    min_waves: int = 2,
    no_network: bool = False,
    continue_existing: bool = False,
) -> SkillResult:
    """Execute the OSINT skill (continuous investigate)."""
    text = (text or "").strip()
    if not text:
        return SkillResult(
            ok=False,
            skill=OSINT_SKILL["name"],
            case_path="",
            report_brief="Empty clue — send a handle, phone, or name.",
            stop_reason="empty_input",
        )

    if no_network:
        os.environ["TRACELOCK_NO_NETWORK"] = "1"
        os.environ["TRACELOCK_OFFLINE"] = "1"
    else:
        os.environ.pop("TRACELOCK_NO_NETWORK", None)
        os.environ.pop("TRACELOCK_OFFLINE", None)

    if case_path is None:
        case_path = Path(tempfile.mkdtemp(prefix="tracelock-skill-")) / "case.json"
    else:
        case_path = Path(case_path)

    loop: LoopResult
    if continue_existing and case_path.is_file():
        loop = continue_case(case_path, max_extra_waves=max_waves)
    else:
        loop = investigate_continuous(
            text,
            case_path,
            max_waves=max_waves,
            min_waves=min_waves,
        )

    brief = ""
    md = loop.final_report or ""
    hitl_open = 0
    try:
        from osint_cli.state import load_state

        st = load_state(case_path)
        hitl_open = sum(
            1
            for g in (st.get("hitl_gates") or [])
            if isinstance(g, dict) and g.get("status") == "open"
        )
        # Prefer stored human brief
        paths = st.get("report_paths") or {}
        if paths.get("brief") and Path(paths["brief"]).is_file():
            brief = Path(paths["brief"]).read_text(encoding="utf-8")
        else:
            pack = build_human_report(st)
            brief = pack.get("brief") or pack.get("markdown") or ""
            md = pack.get("markdown") or md
    except Exception:
        brief = md[:2000] if md else ""

    return SkillResult(
        ok=loop.ok,
        skill=OSINT_SKILL["name"],
        case_path=str(loop.case_path or case_path),
        report_brief=brief,
        report_markdown=md,
        stop_reason=loop.stop_reason,
        waves=len(loop.waves),
        hitl_open=hitl_open,
        raw=loop.to_dict(),
    )
