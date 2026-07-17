"""Agent tools wrapping real osint_cli functions (no re-implementation of core logic)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from osint_cli.clue_analyze import analyze_clues, apply_analysis_to_state
from osint_cli.hitl import ensure_hitl, open_gate
from osint_cli.name_pattern import morph_username, patterns_from_state
from osint_cli.normalize import add_evidence, add_seed
from osint_cli.phone_pivot import (
    build_footprint_queries,
    hitl_phone_checklist,
    normalize_phone_record,
)
from osint_cli.state import load_state, new_investigation, save_state

ToolFn = Callable[..., dict[str, Any]]


def _ev(
    state: dict[str, Any],
    *,
    etype: str,
    value: Any,
    source_name: str = "tracelock_agent",
    confidence: float = 0.7,
) -> None:
    add_evidence(
        state,
        {
            "type": etype,
            "value": value,
            "source_name": source_name,
            "confidence": confidence,
        },
    )


def tool_init_case(case_path: Path, **_kwargs: Any) -> dict[str, Any]:
    case_path = Path(case_path)
    case_path.parent.mkdir(parents=True, exist_ok=True)
    state = new_investigation(case_path, purpose="tracelock_autopilot")
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "init_case",
        "case_path": str(case_path),
        "investigation_id": state.get("investigation_id"),
    }


def tool_analyze_clues(
    case_path: Path, clues: list[str] | None = None, **_kwargs: Any
) -> dict[str, Any]:
    state = load_state(case_path)
    for raw in clues or []:
        try:
            add_seed(state, raw)
        except Exception as e:
            _ev(
                state,
                etype="seed_error",
                value={"raw": raw, "error": str(e)},
                confidence=0.2,
            )
    analysis = analyze_clues(state)
    try:
        apply_analysis_to_state(state, analysis)
    except Exception:
        state["clue_analysis"] = analysis
    _ev(
        state,
        etype="clue_analyze",
        value={"summary": "clue analysis complete", "keys": list(analysis.keys())[:12]},
    )
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "analyze_clues",
        "seed_count": len(state.get("seeds") or []),
        "analysis_keys": list(analysis.keys()),
        "analysis": analysis,
    }


def tool_normalize_phone(
    case_path: Path, phone: str = "", **kwargs: Any
) -> dict[str, Any]:
    args = kwargs.get("args") or {}
    phone = phone or args.get("phone") or ""
    if not phone:
        # recover from seeds
        state = load_state(case_path)
        for s in state.get("seeds") or []:
            if s.get("type") == "phone":
                phone = s.get("normalized") or s.get("value") or ""
                break
    rec = normalize_phone_record(phone)
    state = load_state(case_path)
    _ev(state, etype="phone_normalize", value=rec)
    save_state(state, case_path)
    return {"ok": True, "tool": "normalize_phone", "record": rec}


def tool_phone_queries(
    case_path: Path, phone: str = "", **kwargs: Any
) -> dict[str, Any]:
    args = kwargs.get("args") or {}
    phone = phone or args.get("phone") or ""
    state = load_state(case_path)
    if not phone:
        for s in state.get("seeds") or []:
            if s.get("type") == "phone":
                phone = s.get("normalized") or s.get("value") or ""
                break
    rec = normalize_phone_record(phone)
    queries = build_footprint_queries(rec)
    _ev(
        state,
        etype="phone_queries",
        value={"phone": rec.get("e164"), "queries": queries},
    )
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "phone_queries",
        "phone": rec.get("e164"),
        "queries": queries,
        "count": len(queries),
    }


def tool_phone_checklist(
    case_path: Path, phone: str = "", **kwargs: Any
) -> dict[str, Any]:
    args = kwargs.get("args") or {}
    phone = phone or args.get("phone") or ""
    state = load_state(case_path)
    if not phone:
        for s in state.get("seeds") or []:
            if s.get("type") == "phone":
                phone = s.get("normalized") or s.get("value") or ""
                break
    rec = normalize_phone_record(phone) if phone else None
    checklist = hitl_phone_checklist(rec)
    _ev(state, etype="phone_hitl_checklist", value=checklist)
    gate = open_gate(
        state,
        source="phone_layer_b",
        kind="phone_layer_b",
        why="Layer-B e-wallet/contact-sync is operator-only (zero-autonomy)",
        expected_fields=["name_candidate", "technique", "app"],
        query_hints=[(rec or {}).get("e164") or phone or ""],
    )
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "phone_checklist",
        "checklist": checklist,
        "gate": gate,
        "hitl": True,
        "zero_autonomy": True,
    }


def tool_name_pattern_enum(
    case_path: Path, clues: list[str] | None = None, **_kwargs: Any
) -> dict[str, Any]:
    state = load_state(case_path)
    # ensure username seeds present
    for raw in clues or []:
        text = str(raw)
        if "instagram.com/" in text:
            h = text.split("instagram.com/")[-1].strip("/").split("?")[0]
            add_seed(state, f"username:{h}")
        elif text.startswith("@") or text.startswith("username:"):
            add_seed(state, text if ":" in text else f"username:{text.lstrip('@')}")
    patterns = patterns_from_state(state)
    # also morph bare handles for richer matrix
    morphs: dict[str, list[str]] = {}
    for s in state.get("seeds") or []:
        if s.get("type") == "username":
            u = (s.get("normalized") or s.get("value") or "").lstrip("@")
            morphs[u] = morph_username(u)
    payload = {"patterns_from_state": patterns, "morphs": morphs}
    _ev(state, etype="name_pattern_enum", value=payload)
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "name_pattern_enum",
        "patterns": patterns,
        "morphs": morphs,
    }


def tool_plan_sources(case_path: Path, **_kwargs: Any) -> dict[str, Any]:
    state = load_state(case_path)
    sources = [
        {"id": "websearch", "role": "Multi-engine public SERP"},
        {"id": "phone_footprint", "role": "Layer-A phone SERP + wa.me"},
        {"id": "digital_footprint", "role": "Cross-platform username enum + checklist"},
        {"id": "name_pattern_enum", "role": "Unknown-name handle expansion"},
        {"id": "username_enum", "role": "Cross-platform username probe"},
        {"id": "gov_id", "role": "Passive MA/AHU/LPSE/KPU pack"},
        {"id": "hitl_pddikti", "role": "Civil portal only via HITL"},
    ]
    state["agent_plan_sources"] = sources
    _ev(state, etype="plan_sources", value={"sources": sources})
    save_state(state, case_path)
    return {"ok": True, "tool": "plan_sources", "sources": sources}


def tool_digital_footprint(
    case_path: Path,
    clues: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Full digital-trail pack: checklist + cross-platform handle probes + SERP queries."""
    from tracelock.footprint import (
        FOOTPRINT_CHECKLIST,
        enum_handle_platforms,
        footprint_brief,
        handles_from_clues,
        serp_query_pack,
    )

    state = load_state(case_path)
    # Prefer live seeds; fall back to passed clues
    seed_texts: list[str] = []
    for s in state.get("seeds") or []:
        t = s.get("type")
        v = s.get("normalized") or s.get("value") or ""
        if t and v:
            seed_texts.append(f"{t}:{v}")
    for c in clues or []:
        if c not in seed_texts:
            seed_texts.append(c)

    handles = handles_from_clues(seed_texts)
    # also raw username fields
    for s in state.get("seeds") or []:
        if s.get("type") == "username":
            h = (s.get("normalized") or s.get("value") or "").lstrip("@")
            if h and h not in handles:
                handles.append(h)

    args = kwargs.get("args") or {}
    quick = bool(args.get("quick") or kwargs.get("quick"))
    # quick = fewer platforms for CI; full = research set
    platforms = (
        ["instagram", "tiktok", "threads", "github", "x"]
        if quick
        else None
    )
    timeout = float(args.get("timeout") or (4.0 if quick else 6.0))

    enums: list[dict[str, Any]] = []
    for h in handles[:5]:
        enums.append(enum_handle_platforms(h, platforms=platforms, timeout=timeout))

    brief = footprint_brief(seed_texts)
    pack = {
        "checklist": FOOTPRINT_CHECKLIST,
        "handles": handles,
        "platform_enums": enums,
        "serp_queries": serp_query_pack(seed_texts, handles),
        "workflow": brief["workflow"],
        "policy": brief["policy"],
    }
    _ev(state, etype="digital_footprint", value=pack, confidence=0.75)
    # promote hit signals into digital dimension-friendly evidence
    for en in enums:
        for hit in en.get("hits") or []:
            _ev(
                state,
                etype="username_platform_hit",
                value={
                    "handle": en.get("handle"),
                    "platform": hit.get("platform"),
                    "url": hit.get("url"),
                    "http_status": hit.get("http_status"),
                    "title": hit.get("title"),
                },
                confidence=0.55,
            )
    state["digital_footprint"] = {
        "handles": handles,
        "hit_count": sum(e.get("hit_count") or 0 for e in enums),
        "probed": sum(e.get("probed") or 0 for e in enums),
    }
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "digital_footprint",
        "handles": handles,
        "hit_count": state["digital_footprint"]["hit_count"],
        "probed": state["digital_footprint"]["probed"],
        "serp_query_count": len(pack["serp_queries"]),
        "checklist_steps": len(FOOTPRINT_CHECKLIST),
        "enums": enums,
        "serp_queries": pack["serp_queries"],
    }


def tool_open_hitl(
    case_path: Path,
    template: str = "pddikti",
    reason: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    args = kwargs.get("args") or {}
    template = args.get("template") or template
    reason = args.get("reason") or reason or f"HITL required for {template}"
    state = load_state(case_path)
    url = None
    if template == "pddikti":
        url = "https://pddikti.kemdiktisaintek.go.id/"
    gate = open_gate(
        state,
        source=template,
        url=url,
        kind=template,
        why=reason,
        expected_fields=["nama", "nim", "nama_pt"] if template == "pddikti" else None,
    )
    ensure_hitl(state)
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "open_hitl",
        "template": template,
        "reason": reason,
        "gate": gate,
        "zero_autonomy": True,
    }


def tool_build_dossier(case_path: Path, **_kwargs: Any) -> dict[str, Any]:
    state = load_state(case_path)
    evidence = state.get("evidence") or []
    seeds = state.get("seeds") or []
    dims: dict[str, Any] = {
        "identity_digital": {"status": "open", "signals": []},
        "identity_civil": {"status": "open", "signals": []},
        "phone": {"status": "open", "signals": []},
        "education": {"status": "open", "signals": []},
        "risk_notes": {
            "status": "clean_public_demo",
            "signals": ["Offline/demo path: no adverse public material claimed"],
        },
    }
    for s in seeds:
        if s.get("type") == "username":
            dims["identity_digital"]["signals"].append(
                f"handle seed: {s.get('normalized') or s.get('value')}"
            )
            dims["identity_digital"]["status"] = "partial"
        if s.get("type") == "phone":
            dims["phone"]["signals"].append(
                f"phone seed: {s.get('normalized') or s.get('value')}"
            )
            dims["phone"]["status"] = "partial"
        if s.get("type") == "name":
            dims["identity_civil"]["signals"].append(
                f"name seed (unverified until multi-signal): {s.get('value')}"
            )
    for ev in evidence:
        t = (ev.get("type") if isinstance(ev, dict) else "") or ""
        if "phone" in t:
            dims["phone"]["status"] = "partial"
            dims["phone"]["signals"].append(t)
        if "name_pattern" in t or "digital_footprint" in t or "username_platform" in t:
            dims["identity_digital"]["status"] = "partial"
            if "username_platform" in t:
                val = ev.get("value") if isinstance(ev.get("value"), dict) else {}
                dims["identity_digital"]["signals"].append(
                    f"platform hit soft: {val.get('platform')} @{val.get('handle')}"
                )
    fp = state.get("digital_footprint") or {}
    if fp.get("handles"):
        dims["identity_digital"]["status"] = "partial"
        dims["identity_digital"]["signals"].append(
            f"footprint enum: {fp.get('hit_count', 0)}/{fp.get('probed', 0)} soft hits"
        )
    dossier = {
        "product": "TraceLock",
        "version": "1.0.0",
        "investigation_id": state.get("investigation_id"),
        "dimensions": dims,
        "evidence_count": len(evidence),
        "seed_count": len(seeds),
        "hitl_gates": state.get("hitl_gates") or [],
        "policy": {
            "digital_ne_civil": True,
            "public_sources_only": True,
            "no_breach_nik": True,
            "hitl_zero_autonomy": True,
        },
    }
    state["agent_dossier"] = dossier
    _ev(state, etype="dossier", value={"dimensions": list(dims.keys())})
    save_state(state, case_path)
    return {"ok": True, "tool": "build_dossier", "dossier": dossier}


def tool_report(case_path: Path, **_kwargs: Any) -> dict[str, Any]:
    state = load_state(case_path)
    dossier = state.get("agent_dossier") or {}
    gates = state.get("hitl_gates") or []
    evidence = state.get("evidence") or []
    seeds = state.get("seeds") or []
    lines = [
        "# TraceLock Investigation Report",
        "",
        f"- Investigation: `{state.get('investigation_id')}`",
        f"- Seeds: {len(seeds)}",
        f"- Evidence items: {len(evidence)}",
        f"- HITL gates: {len(gates)}",
        f"- Policy: digital ≠ civil · public sources only · no breach/NIK",
        "",
        "## Seeds",
    ]
    for s in seeds:
        lines.append(
            f"- `{s.get('type')}`: {s.get('normalized') or s.get('value')}"
        )
    lines.append("")
    lines.append("## Dimensions")
    for name, body in (dossier.get("dimensions") or {}).items():
        status = body.get("status") if isinstance(body, dict) else "?"
        sigs = body.get("signals") if isinstance(body, dict) else []
        lines.append(f"### {name} — `{status}`")
        for sig in (sigs or [])[:10]:
            lines.append(f"- {sig}")
        if not sigs:
            lines.append("- (no signals yet)")
        lines.append("")
    lines.append("## HITL / Zero-Autonomy Checkpoints")
    if not gates:
        lines.append("- (none opened)")
    for g in gates:
        if not isinstance(g, dict):
            continue
        lines.append(
            f"- `{g.get('id')}` kind=`{g.get('kind') or g.get('source')}` "
            f"status=`{g.get('status')}` — {g.get('why') or g.get('reason') or ''}"
        )
    lines.append("")
    lines.append("## Evidence trail (last 12)")
    for ev in evidence[-12:]:
        if isinstance(ev, dict):
            lines.append(
                f"- `{ev.get('id')}` type=`{ev.get('type')}` "
                f"src=`{ev.get('source_name')}`"
            )
    md = "\n".join(lines)
    state["report_markdown"] = md
    save_state(state, case_path)
    return {
        "ok": True,
        "tool": "report",
        "markdown": md,
        "dossier": dossier,
        "evidence_count": len(evidence),
        "hitl_gate_count": len(gates),
        "report_class": "dossier",
    }


REGISTRY: dict[str, ToolFn] = {
    "init_case": tool_init_case,
    "analyze_clues": tool_analyze_clues,
    "normalize_phone": tool_normalize_phone,
    "phone_queries": tool_phone_queries,
    "phone_checklist": tool_phone_checklist,
    "name_pattern_enum": tool_name_pattern_enum,
    "digital_footprint": tool_digital_footprint,
    "plan_sources": tool_plan_sources,
    "open_hitl": tool_open_hitl,
    "build_dossier": tool_build_dossier,
    "report": tool_report,
}


def run_tool(
    name: str,
    case_path: Path,
    clues: list[str] | None = None,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fn = REGISTRY.get(name)
    if not fn:
        return {"ok": False, "tool": name, "error": f"unknown tool: {name}"}
    args = dict(args or {})
    try:
        return fn(case_path, clues=clues or [], args=args, **args)
    except TypeError:
        try:
            return fn(case_path, **args)
        except Exception as e:
            return {"ok": False, "tool": name, "error": str(e)}
    except Exception as e:
        return {"ok": False, "tool": name, "error": str(e)}
