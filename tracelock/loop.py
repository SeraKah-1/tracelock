"""Continuous investigation loop — anti-lazy multi-wave OSINT.

Same idea as coding agents (Claude Code / Cursor): one user prompt → many
Reason→Act→Observe cycles until done criteria, not a single tool fire.

Research basis:
  - ReAct (Thought → Action → Observation) until final answer
  - Plan-and-execute + replan at milestones
  - Task checklist as execution contract (prevent partial completion)
  - Hard max iterations (loops don't run forever)
  - Stop when checklist satisfied OR no productive next step
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from osint_cli.state import load_state, save_state

from tracelock.agent import AgentRunResult, run_agent
from tracelock.footprint import FOOTPRINT_CHECKLIST, parse_freeform_clue
from tracelock.qwen_client import QwenConfig


# Minimum waves / max waves for continuous mode
DEFAULT_MAX_WAVES = 5
DEFAULT_MIN_WAVES = 2


@dataclass
class WaveResult:
    wave: int
    ok: bool
    tools_run: list[str]
    open_gaps: list[str]
    next_actions: list[dict[str, str]]
    report_chars: int
    evidence_count: int
    hitl_open: int


@dataclass
class LoopResult:
    ok: bool
    waves: list[WaveResult] = field(default_factory=list)
    case_path: str = ""
    final_report: str = ""
    stop_reason: str = ""
    checklist_coverage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "case_path": self.case_path,
            "stop_reason": self.stop_reason,
            "waves": [
                {
                    "wave": w.wave,
                    "ok": w.ok,
                    "tools_run": w.tools_run,
                    "open_gaps": w.open_gaps,
                    "next_actions": w.next_actions,
                    "report_chars": w.report_chars,
                    "evidence_count": w.evidence_count,
                    "hitl_open": w.hitl_open,
                }
                for w in self.waves
            ],
            "checklist_coverage": self.checklist_coverage,
            "final_report": self.final_report,
            "product": "TraceLock",
            "mode": "continuous_investigate",
        }


def _evidence_types(state: dict[str, Any]) -> set[str]:
    return {
        (e.get("type") or "")
        for e in (state.get("evidence") or [])
        if isinstance(e, dict)
    }


def assess_gaps(state: dict[str, Any]) -> list[str]:
    """Open investigation gaps that force another wave (anti-lazy)."""
    gaps: list[str] = []
    seeds = state.get("seeds") or []
    types = _evidence_types(state)
    has_name = any(s.get("type") == "name" for s in seeds)
    has_user = any(s.get("type") == "username" for s in seeds)
    has_phone = any(s.get("type") == "phone" for s in seeds)
    web_hits = sum(
        1
        for e in (state.get("evidence") or [])
        if isinstance(e, dict) and e.get("type") == "web_hit"
    )
    fp = state.get("digital_footprint") or {}
    hitl_open = [
        g
        for g in (state.get("hitl_gates") or [])
        if isinstance(g, dict) and g.get("status") == "open"
    ]

    if has_name and web_hits < 2:
        gaps.append("name_seed_needs_more_public_serp")
    if has_user and not fp.get("probed"):
        gaps.append("username_enum_not_run")
    if has_user and "username_platform_hit" not in types and "web_hit" not in types:
        gaps.append("no_platform_or_web_signal_for_handle")
    if has_phone and "phone_normalize" not in types and "phone_meta" not in types:
        gaps.append("phone_not_normalized")
    if has_name and "public_record" not in types and web_hits < 1:
        gaps.append("civil_public_sources_thin")
    if not state.get("report_markdown"):
        gaps.append("no_report_yet")
    # HITL open is not a failure — note it as gap for operator, not auto-retry spam
    if hitl_open:
        gaps.append(f"hitl_open_count={len(hitl_open)}")

    dossier = state.get("agent_dossier") or state.get("dossier") or {}
    dims = (dossier.get("dimensions") if isinstance(dossier, dict) else {}) or {}
    dig = dims.get("identity_digital") or {}
    if has_user or has_name:
        if dig.get("status") in (None, "open") and web_hits < 1:
            gaps.append("identity_digital_still_open")

    return gaps


def propose_next_actions(state: dict[str, Any], gaps: list[str]) -> list[dict[str, str]]:
    """Map gaps → concrete next tool/module steps (host agent or continue wave)."""
    actions: list[dict[str, str]] = []
    seeds = state.get("seeds") or []
    has_name = any(s.get("type") == "name" for s in seeds)
    has_user = any(s.get("type") == "username" for s in seeds)

    if "username_enum_not_run" in gaps or "no_platform_or_web_signal_for_handle" in gaps:
        actions.append(
            {
                "tool": "digital_footprint",
                "why": "Cross-platform handle enum still thin",
            }
        )
        actions.append(
            {
                "tool": "collect_public",
                "args": "username_enum,websearch",
                "why": "Live username + SERP",
            }
        )
    if "name_seed_needs_more_public_serp" in gaps or "civil_public_sources_thin" in gaps:
        actions.append(
            {
                "tool": "collect_public",
                "args": "websearch,gov_id,pddikti",
                "why": "More public SERP/gov for name seed",
            }
        )
    if "phone_not_normalized" in gaps:
        actions.append({"tool": "normalize_phone", "why": "Phone seed present"})
        actions.append({"tool": "phone_queries", "why": "Layer-A SERP pack"})
    if any(g.startswith("hitl_open") for g in gaps):
        actions.append(
            {
                "tool": "hitl_operator",
                "why": "Complete open gates in browser, then hitl complete",
            }
        )
    if "no_report_yet" in gaps or "identity_digital_still_open" in gaps:
        actions.append({"tool": "build_dossier", "why": "Refresh dimensions"})
        actions.append({"tool": "report", "why": "Emit latest graded report"})

    if not actions:
        if has_name or has_user:
            actions.append(
                {
                    "tool": "collect_public",
                    "args": "websearch",
                    "why": "Default deepen SERP wave",
                }
            )
        actions.append({"tool": "report", "why": "Always refresh report"})

    # dedupe by tool
    seen: set[str] = set()
    out = []
    for a in actions:
        k = a["tool"] + "|" + a.get("args", "")
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out


def checklist_coverage(state: dict[str, Any]) -> dict[str, Any]:
    """Map FOOTPRINT_CHECKLIST ids to done/partial/open from evidence."""
    types = _evidence_types(state)
    seeds = state.get("seeds") or []
    has_phone = any(s.get("type") == "phone" for s in seeds)
    has_user = any(s.get("type") == "username" for s in seeds)
    web = "web_hit" in types
    fp = bool(state.get("digital_footprint"))
    report = bool(state.get("report_markdown"))
    hitl = any(
        g.get("status") == "open" for g in (state.get("hitl_gates") or []) if isinstance(g, dict)
    )

    status: dict[str, str] = {}
    for item in FOOTPRINT_CHECKLIST:
        i = item["id"]
        if i == "S1_scope":
            status[i] = "done" if seeds else "open"
        elif i == "S2_normalize":
            status[i] = (
                "done"
                if "phone_normalize" in types or "phone_meta" in types or not has_phone
                else "open"
            )
        elif i == "S3_username_enum":
            status[i] = "done" if fp or "username_platform_hit" in types else ("n/a" if not has_user else "open")
        elif i == "S4_profile_pivot":
            status[i] = "partial" if web or "profile" in types else "open"
        elif i == "S5_name_pattern":
            status[i] = "done" if "name_pattern" in types or "name_pattern_enum" in str(types) else "partial"
        elif i == "S6_phone_layer_a":
            status[i] = "done" if "phone_queries" in types or "phone_meta" in types or not has_phone else "open"
        elif i == "S7_phone_layer_b":
            status[i] = "partial" if has_phone else "n/a"
        elif i == "S8_serp":
            status[i] = "done" if web else "open"
        elif i == "S9_archive":
            status[i] = "partial"  # soft always
        elif i == "S10_correlate":
            status[i] = "done" if report else "open"
        elif i == "S11_hitl":
            status[i] = "open" if hitl else "done"
        elif i == "S12_dossier":
            status[i] = "done" if report else "open"
        else:
            status[i] = "open"

    done = sum(1 for v in status.values() if v in ("done", "n/a", "partial"))
    return {
        "items": status,
        "done_or_partial": done,
        "total": len(status),
        "ratio": round(done / max(len(status), 1), 2),
    }


def _run_wave_tools(
    case_path: Path,
    clues: list[str],
    actions: list[dict[str, str]],
    on_event: Optional[Callable[..., None]] = None,
) -> None:
    """Execute a deepen wave using specific tools (not full agent re-init)."""
    from tracelock.tools import run_tool

    # Always ensure seeds
    run_tool("analyze_clues", case_path, clues=clues)
    for a in actions:
        tool = a.get("tool") or ""
        if tool in ("hitl_operator",):
            continue
        args: dict[str, Any] = {}
        if a.get("args"):
            if tool == "collect_public":
                args["modules"] = a["args"]
            else:
                args["modules"] = a["args"]
        if tool == "digital_footprint":
            args["quick"] = True
        if tool in (
            "digital_footprint",
            "collect_public",
            "normalize_phone",
            "phone_queries",
            "phone_checklist",
            "name_pattern_enum",
            "plan_sources",
            "build_dossier",
            "report",
            "open_hitl",
        ):
            run_tool(tool, case_path, clues=clues, args=args)


def investigate_continuous(
    clues_or_phrase: str | list[str],
    case_path: Path | str,
    *,
    cfg: Optional[QwenConfig] = None,
    max_waves: int = DEFAULT_MAX_WAVES,
    min_waves: int = DEFAULT_MIN_WAVES,
    on_event: Optional[Callable[..., None]] = None,
) -> LoopResult:
    """Multi-wave OSINT until gaps close or max_waves.

    Wave 1: full run_agent (plan + tools + report)
    Wave 2..N: replan from gaps → collect_public / footprint deepen → report
    """
    case_path = Path(case_path)
    if isinstance(clues_or_phrase, str):
        clues = parse_freeform_clue(clues_or_phrase)
    else:
        clues = list(clues_or_phrase)
    cfg = cfg or QwenConfig.from_env()

    waves: list[WaveResult] = []
    stop_reason = "max_waves"

    # Wave 1 — full autopilot
    if on_event:
        try:
            on_event("wave_start", "Wave 1 full plan+collect", wave=1)
        except Exception:
            pass
    r1: AgentRunResult = run_agent(clues, case_path, cfg=cfg, on_event=on_event)
    state = load_state(case_path) if case_path.is_file() else {}
    gaps = assess_gaps(state)
    nxt = propose_next_actions(state, gaps)
    waves.append(
        WaveResult(
            wave=1,
            ok=r1.ok,
            tools_run=[t.tool for t in r1.tool_traces],
            open_gaps=gaps,
            next_actions=nxt,
            report_chars=len(r1.report_markdown or ""),
            evidence_count=len(state.get("evidence") or []),
            hitl_open=sum(
                1
                for g in (state.get("hitl_gates") or [])
                if isinstance(g, dict) and g.get("status") == "open"
            ),
        )
    )
    state["investigation_loop"] = {
        "wave": 1,
        "gaps": gaps,
        "next_actions": nxt,
        "max_waves": max_waves,
    }
    save_state(state, case_path)

    # Productive gaps exclude pure HITL (operator must act; looping won't solve captcha)
    def productive(gs: list[str]) -> list[str]:
        return [g for g in gs if not g.startswith("hitl_open")]

    for wave in range(2, max_waves + 1):
        state = load_state(case_path)
        gaps = assess_gaps(state)
        prod = productive(gaps)
        if wave > min_waves and not prod:
            stop_reason = "no_productive_gaps"
            break
        if wave > min_waves and checklist_coverage(state)["ratio"] >= 0.85 and not prod:
            stop_reason = "checklist_coverage_ok"
            break

        nxt = propose_next_actions(state, gaps)
        if on_event:
            try:
                on_event(
                    "wave_start",
                    f"Wave {wave} deepen",
                    wave=wave,
                    gaps=gaps,
                    actions=nxt,
                )
            except Exception:
                pass

        _run_wave_tools(case_path, clues, nxt, on_event=on_event)
        # always refresh report
        from tracelock.tools import run_tool

        run_tool("build_dossier", case_path, clues=clues)
        rep = run_tool("report", case_path, clues=clues)

        state = load_state(case_path)
        gaps2 = assess_gaps(state)
        nxt2 = propose_next_actions(state, gaps2)
        tools_this = [a.get("tool") or "" for a in nxt]
        waves.append(
            WaveResult(
                wave=wave,
                ok=bool(rep.get("ok")),
                tools_run=tools_this,
                open_gaps=gaps2,
                next_actions=nxt2,
                report_chars=len(state.get("report_markdown") or ""),
                evidence_count=len(state.get("evidence") or []),
                hitl_open=sum(
                    1
                    for g in (state.get("hitl_gates") or [])
                    if isinstance(g, dict) and g.get("status") == "open"
                ),
            )
        )
        state["investigation_loop"] = {
            "wave": wave,
            "gaps": gaps2,
            "next_actions": nxt2,
            "max_waves": max_waves,
        }
        save_state(state, case_path)

        if not productive(gaps2) and wave >= min_waves:
            stop_reason = "gaps_closed_or_hitl_only"
            break

    state = load_state(case_path) if case_path.is_file() else {}
    cov = checklist_coverage(state)
    final = state.get("report_markdown") or r1.report_markdown or ""
    # Append loop summary to report
    loop_md = [
        "",
        "## Continuous investigation loop",
        f"- Waves run: {len(waves)}",
        f"- Stop: {stop_reason}",
        f"- Checklist coverage: {cov['done_or_partial']}/{cov['total']} ({cov['ratio']})",
        "",
        "### Per-wave",
    ]
    for w in waves:
        loop_md.append(
            f"- Wave {w.wave}: tools={w.tools_run} evidence={w.evidence_count} "
            f"gaps={w.open_gaps} hitl_open={w.hitl_open}"
        )
    final = (final or "") + "\n".join(loop_md)
    state["report_markdown"] = final
    save_state(state, case_path)

    return LoopResult(
        ok=any(w.ok for w in waves),
        waves=waves,
        case_path=str(case_path),
        final_report=final,
        stop_reason=stop_reason,
        checklist_coverage=cov,
    )


def continue_case(
    case_path: Path | str,
    *,
    max_extra_waves: int = 2,
    on_event: Optional[Callable[..., None]] = None,
) -> LoopResult:
    """Resume an existing case: more deepen waves from current gaps."""
    case_path = Path(case_path)
    state = load_state(case_path)
    clues = []
    for s in state.get("seeds") or []:
        t, v = s.get("type"), s.get("normalized") or s.get("value")
        if t and v:
            clues.append(f"{t}:{v}")
    if not clues:
        clues = ["other:continue existing case"]
    # min_waves=1 so we can stop early if no gaps
    return investigate_continuous(
        clues,
        case_path,
        max_waves=max_extra_waves + 1,
        min_waves=1,
        on_event=on_event,
    )
