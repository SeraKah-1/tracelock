"""Non-interactive CLI — JSON on stdout for AI agent tool calls.

Workflow (person background check, not clue checklist):
  init → seed (clues) → question/hypothesis (goals) → collect → differentiate
  → select strongest → identity-lock → fill dimensions → next → report
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from . import __version__
from .collect import run_collect
from .differentiate import differentiate, select_candidates
from .dossier import (
    DIMENSIONS,
    add_hypothesis,
    add_question,
    add_timeline_event,
    auto_tag_evidence_to_dimensions,
    build_dossier_report,
    ensure_dossier,
    next_actions,
    reject_candidate,
    render_dossier_markdown,
    resolve_hypothesis,
    set_dimension,
    set_identity_lock,
    strongest_candidates,
    update_question,
)
from .clue_analyze import analyze_clues, apply_analysis_to_state
from .escalate import escalate
from .hitl import (
    cancel_gate,
    complete_gate,
    import_file as hitl_import_file,
    list_gates,
    open_gate,
    open_gates_summary,
)
from .normalize import add_evidence, add_seed
from .state import (
    append_run_log,
    load_state,
    new_investigation,
    record_iteration,
    save_state,
    utc_now,
)


def emit(obj: Any, exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")
    return exit_code


def emit_error(message: str, **extra: Any) -> int:
    payload = {"ok": False, "error": message, **extra}
    return emit(payload, exit_code=1)


def default_case_path() -> Path:
    return Path.cwd() / "investigation.json"


def resolve_case(args: argparse.Namespace) -> Path:
    if getattr(args, "case", None):
        return Path(args.case)
    return default_case_path()


def _require_state(args: argparse.Namespace) -> dict[str, Any]:
    path = resolve_case(args)
    if not path.exists():
        raise FileNotFoundError(f"case not found: {path}; run init first")
    return load_state(path)


def cmd_init(args: argparse.Namespace) -> int:
    path = resolve_case(args)
    if path.exists() and not args.force:
        return emit_error(
            f"case already exists: {path}",
            hint="pass --force to overwrite",
            case=str(path),
        )
    state = new_investigation(path, purpose=args.purpose, max_depth=args.max_depth)
    save_state(state, path)
    return emit(
        {
            "ok": True,
            "action": "init",
            "case": str(path.resolve()),
            "investigation_id": state["investigation_id"],
            "schema_version": state["schema_version"],
            "scope": state["scope"],
            "questions_seeded": len(state.get("questions") or []),
            "dimensions": [d["id"] for d in DIMENSIONS],
            "hint": "Seeds are clues only. Use `next` for person-dossier actions; `report` for background check.",
        }
    )


def cmd_status(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    ensure_dossier(state)
    dims = state["dossier"]["dimensions"]
    dim_summary = {k: v.get("status") for k, v in dims.items()}
    return emit(
        {
            "ok": True,
            "action": "status",
            "case": state.get("case_path"),
            "investigation_id": state["investigation_id"],
            "schema_version": state.get("schema_version"),
            "updated_at": state.get("updated_at"),
            "depth": state.get("depth"),
            "identity_lock": state.get("identity_lock"),
            "seed_count": len(state.get("seeds") or []),
            "evidence_count": len(state.get("evidence") or []),
            "candidate_count": len(state.get("candidates") or []),
            "selected_branches": state.get("selected_branches") or [],
            "rejected_count": len(state.get("rejected_candidates") or []),
            "open_questions": sum(
                1 for q in state.get("questions") or [] if q.get("status") == "open"
            ),
            "dimension_status": dim_summary,
            "strongest": strongest_candidates(state, limit=3),
            "iteration_count": len(state.get("iterations") or []),
            "termination": state.get("termination"),
            "workflow": (state.get("scope") or {}).get("workflow"),
            "open_hitl_gates": open_gates_summary(state),
            "seeds": [
                {
                    "id": s["id"],
                    "type": s["type"],
                    "normalized": s["normalized"],
                    "origin": s.get("origin"),
                }
                for s in state.get("seeds") or []
            ],
            "candidates": [
                {
                    "id": c["id"],
                    "label": c.get("label"),
                    "score": c.get("score"),
                    "status": c.get("status"),
                    "evidence_ids": c.get("evidence_ids"),
                }
                for c in state.get("candidates") or []
            ],
        }
    )


def cmd_phone(args: argparse.Namespace) -> int:
    """Phone as clue: normalize / footprint / HITL checklist (Layer A+B; no breach)."""
    from .phone_pivot import (
        build_footprint_queries,
        hitl_phone_checklist,
        normalize_phone_record,
    )

    action = args.phone_action
    if action == "normalize":
        rec = normalize_phone_record(args.spec)
        return emit({"ok": bool(rec.get("ok")), "action": "phone_normalize", "record": rec})

    if action == "checklist":
        rec = normalize_phone_record(args.spec) if args.spec else {}
        return emit(
            {
                "ok": True,
                "action": "phone_checklist",
                "checklist": hitl_phone_checklist(rec if rec.get("ok") else None),
                "record": rec if rec.get("ok") else None,
            }
        )

    if action == "queries":
        rec = normalize_phone_record(args.spec)
        if not rec.get("ok"):
            return emit_error("invalid phone", record=rec)
        return emit(
            {
                "ok": True,
                "action": "phone_queries",
                "record": rec,
                "queries": build_footprint_queries(rec, extra_terms=args.goal),
            }
        )

    # footprint: requires case; adds seed + runs collect module
    if action == "footprint":
        try:
            state = _require_state(args)
        except FileNotFoundError as e:
            return emit_error(str(e))
        seed = add_seed(state, f"phone:{args.spec}", origin="user")
        from .collect import run_collect

        result = run_collect(
            state,
            goal=args.goal,
            modules=["phone_footprint"],
            offline=bool(args.offline),
            seed_ids=[seed["id"]],
        )
        auto = auto_tag_evidence_to_dimensions(state)
        analysis = apply_analysis_to_state(state, merge_questions=True)
        record_iteration(
            state,
            phase="phone_footprint",
            commands_or_goals=[f"phone footprint {args.spec}"],
            modules_run=result.get("modules_run"),
            evidence_ids_added=result.get("evidence_ids_added"),
        )
        append_run_log(state, "phone_footprint", result)
        save_state(state)
        return emit(
            {
                "ok": True,
                "action": "phone_footprint",
                "seed": seed,
                **result,
                "auto_tag": auto,
                "plan_summary": analysis.get("summary"),
                "p0_questions": [
                    q["text"]
                    for q in (analysis.get("questions") or [])
                    if q.get("priority") == 0
                ][:8],
                "hint": (
                    "Phone is a clue pivot. Use `phone checklist` for Layer B HITL. "
                    "Do not treat e-wallet name as civil lock; no breach/NIK modules."
                ),
            }
        )

    return emit_error(f"unknown phone action: {action}")


def cmd_seed(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if args.seed_action == "add":
        specs = list(args.specs or [])
        if not specs:
            return emit_error("seed add requires at least one SPEC (type:value or bare)")
        added = []
        for spec in specs:
            s = add_seed(state, spec, origin="user")
            added.append(s)
            # optional: register clue-derived soft hypotheses for geo-like free text
            if s["type"] in ("other", "name") and any(
                k in s["normalized"].lower()
                for k in ("simalungun", "perdagangan", "sumatera", "angkatan", "2025", "maba")
            ):
                dim = "geo" if any(
                    k in s["normalized"].lower()
                    for k in ("simalungun", "perdagangan", "sumatera", "medan", "pekanbaru")
                ) else "education"
                add_hypothesis(
                    state,
                    f"Clue seed may imply: {s['normalized']}",
                    dimension=dim,
                    from_clue=True,
                )
        record_iteration(
            state,
            phase="seed",
            commands_or_goals=[f"seed add {sp}" for sp in specs],
        )
        # Auto-refresh clue analysis after new seeds
        analysis = apply_analysis_to_state(state, merge_questions=True)
        append_run_log(state, "seed_add", [s["id"] for s in added])
        save_state(state)
        return emit(
            {
                "ok": True,
                "action": "seed_add",
                "seeds_added": added,
                "seed_count": len(state["seeds"]),
                "note": "Seeds are clues only. Analysis refreshed — use `plan`/`next`. Not completion criteria.",
                "hypotheses": state.get("hypotheses") or [],
                "plan_summary": analysis.get("summary"),
                "p0_questions": [
                    q["text"]
                    for q in (analysis.get("questions") or [])
                    if q.get("priority") == 0
                ][:8],
            }
        )
    if args.seed_action == "list":
        return emit({"ok": True, "action": "seed_list", "seeds": state.get("seeds") or []})
    return emit_error(f"unknown seed action: {args.seed_action}")


def cmd_collect(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if not state.get("seeds"):
        return emit_error("no seeds; add seeds before collect")
    modules = None
    if args.modules:
        modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    goal = args.goal
    if args.dimension:
        goal = (
            f"background-check dimension:{args.dimension} for selected/locked subject only; "
            f"primary sources and multi-event timeline; do not restate generic institution news. "
            f"{goal or ''}"
        ).strip()
    started = utc_now()
    result = run_collect(
        state,
        goal=goal,
        modules=modules,
        offline=bool(args.offline),
        seed_ids=args.seed_ids.split(",") if args.seed_ids else None,
    )
    auto = auto_tag_evidence_to_dimensions(state)
    if args.dimension and args.method_note:
        set_dimension(state, args.dimension, method=args.method_note)
    record_iteration(
        state,
        phase="collect",
        commands_or_goals=[goal] if goal else ["collect"],
        modules_run=result["modules_run"],
        evidence_ids_added=result["evidence_ids_added"],
        started_at=started,
        ended_at=utc_now(),
        extra={"dimension": args.dimension, "auto_tag": auto},
    )
    append_run_log(state, "collect", result)
    save_state(state)
    planner = next_actions(state, limit=5)
    return emit(
        {
            "ok": True,
            "action": "collect",
            **result,
            "evidence_count": len(state["evidence"]),
            "auto_tag": auto,
            "open_hitl_gates": open_gates_summary(state),
            "next_actions": planner.get("actions"),
        }
    )


def cmd_hitl(args: argparse.Namespace) -> int:
    """Human-in-the-loop gates: open / list / complete / import-file / cancel."""
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))

    action = args.hitl_action
    if action == "open":
        fields = None
        if args.fields:
            fields = [f.strip() for f in args.fields.split(",") if f.strip()]
        hints = list(args.query_hint or [])
        gate = open_gate(
            state,
            source=args.source,
            url=args.url,
            why=args.why or "",
            expected_fields=fields,
            seed_ids=[s.strip() for s in (args.seed_ids or "").split(",") if s.strip()],
            query_hints=hints,
        )
        record_iteration(
            state,
            phase="hitl_open",
            commands_or_goals=[f"hitl open {gate['id']} {args.source}"],
        )
        append_run_log(state, "hitl_open", gate["id"])
        save_state(state)
        return emit(
            {
                "ok": True,
                "action": "hitl_open",
                "gate": gate,
                "operator": {
                    "do": gate.get("operator_checklist"),
                    "after": [
                        f'hitl complete --gate {gate["id"]} --grade full_page --value \'{{"nama":"…"}}\'',
                        f"hitl import-file --gate {gate['id']} --path ./page.html",
                        "collect --modules browser_cdp  # Chrome --remote-debugging-port=9222",
                    ],
                },
            }
        )

    if action == "list":
        gates = list_gates(state, status=args.status)
        return emit(
            {
                "ok": True,
                "action": "hitl_list",
                "gates": gates,
                "open": open_gates_summary(state),
            }
        )

    if action == "complete":
        try:
            result = complete_gate(
                state,
                args.gate,
                value=args.value,
                grade=args.grade,
                url=args.url,
                notes=args.notes or "",
                confidence=args.confidence,
            )
        except ValueError as e:
            return emit_error(str(e))
        ev_ids = []
        if result.get("evidence") and result["evidence"].get("id"):
            ev_ids = [result["evidence"]["id"]]
        record_iteration(
            state,
            phase="hitl_complete",
            commands_or_goals=[f"hitl complete {args.gate}"],
            evidence_ids_added=ev_ids,
        )
        append_run_log(state, "hitl_complete", args.gate)
        save_state(state)
        return emit({"ok": True, "action": "hitl_complete", **result})

    if action == "import-file":
        try:
            result = hitl_import_file(
                state,
                args.path,
                gate_id=args.gate,
                source=args.source,
                grade=args.grade,
                url=args.url,
            )
        except (ValueError, FileNotFoundError) as e:
            return emit_error(str(e))
        ev_ids = []
        if result.get("evidence") and result["evidence"].get("id"):
            ev_ids = [result["evidence"]["id"]]
        record_iteration(
            state,
            phase="hitl_import",
            commands_or_goals=[f"hitl import-file {args.path}"],
            evidence_ids_added=ev_ids,
        )
        append_run_log(state, "hitl_import", str(args.path))
        save_state(state)
        return emit({"ok": True, "action": "hitl_import_file", **result})

    if action == "cancel":
        try:
            gate = cancel_gate(state, args.gate, notes=args.notes or "")
        except ValueError as e:
            return emit_error(str(e))
        save_state(state)
        return emit({"ok": True, "action": "hitl_cancel", "gate": gate})

    return emit_error(f"unknown hitl action: {action}")


def cmd_differentiate(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    started = utc_now()
    result = differentiate(state)
    auto_tag_evidence_to_dimensions(state)
    record_iteration(
        state,
        phase="differentiate",
        commands_or_goals=["differentiate"],
        started_at=started,
        ended_at=utc_now(),
        extra={"candidate_count": result["candidate_count"]},
    )
    append_run_log(state, "differentiate", result)
    save_state(state)
    return emit(
        {
            "ok": True,
            "action": "differentiate",
            **result,
            "strongest": strongest_candidates(state, limit=5),
            "hint": "Select strongest non-collision node; do not re-chase every clue field.",
        }
    )


def cmd_select(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    ids = list(args.candidate_ids or [])
    if not ids:
        return emit_error("select requires candidate id(s), e.g. select c1")
    try:
        result = select_candidates(state, ids)
    except ValueError as e:
        return emit_error(str(e))
    record_iteration(
        state,
        phase="select",
        commands_or_goals=[f"select {' '.join(ids)}"],
        selected_candidate_ids=ids,
    )
    append_run_log(state, "select", ids)
    save_state(state)
    return emit(
        {
            "ok": True,
            "action": "select",
            **result,
            "next": "Pursue identity-lock (photo/handle/network) before geo/year clue hypotheses.",
        }
    )


def cmd_escalate(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    started = utc_now()
    try:
        result = escalate(state, goal=args.goal, candidate_ids=args.candidate_ids)
    except ValueError as e:
        return emit_error(str(e))
    record_iteration(
        state,
        phase="escalate",
        commands_or_goals=[args.goal] if args.goal else ["escalate"],
        selected_candidate_ids=result.get("selected") or state.get("selected_branches"),
        started_at=started,
        ended_at=utc_now(),
        extra={"seeds_added": result.get("seeds_added")},
    )
    append_run_log(state, "escalate", result)
    save_state(state)
    return emit({"ok": True, "action": "escalate", **result})


def cmd_export(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    out = Path(args.out) if args.out else Path(state["case_path"]).with_name(
        Path(state["case_path"]).stem + ".export.json"
    )
    if args.terminate:
        state["termination"] = {
            "reason": args.terminate,
            "final_candidate_ids": list(state.get("selected_branches") or []),
            "summary": args.summary,
        }
        record_iteration(
            state,
            phase="terminate",
            commands_or_goals=[f"terminate:{args.terminate}"],
        )
        save_state(state)
    package = {k: v for k, v in state.items() if k != "run_log" or args.include_log}
    if not args.include_log:
        package.pop("run_log", None)
    # always embed dossier snapshot
    package["dossier_report"] = build_dossier_report(state)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(package, f, indent=2, ensure_ascii=False)
        f.write("\n")
    record_iteration(state, phase="export", commands_or_goals=[f"export {out}"])
    save_state(state)
    return emit(
        {
            "ok": True,
            "action": "export",
            "path": str(out.resolve()),
            "investigation_id": state["investigation_id"],
            "seed_count": len(state.get("seeds") or []),
            "evidence_count": len(state.get("evidence") or []),
            "candidate_count": len(state.get("candidates") or []),
            "selected_branches": state.get("selected_branches") or [],
            "identity_lock": state.get("identity_lock"),
            "iteration_count": len(state.get("iterations") or []),
        }
    )


def cmd_candidates(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    return emit(
        {
            "ok": True,
            "action": "candidates",
            "candidates": state.get("candidates") or [],
            "selected_branches": state.get("selected_branches") or [],
            "rejected_candidates": state.get("rejected_candidates") or [],
            "strongest": strongest_candidates(state, limit=5),
        }
    )


def cmd_evidence(args: argparse.Namespace) -> int:
    """Record a public observation with explicit provenance grade (shipped path)."""
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if args.evidence_action != "add":
        return emit_error(f"unknown evidence action: {args.evidence_action}")

    grade = args.grade
    conf_map = {
        "full_page": 0.85,
        "search_snippet": 0.55,
        "portal_metadata": 0.4,
        "operator_clue": 0.35,
    }
    conf = args.confidence if args.confidence is not None else conf_map.get(grade, 0.5)

    value: Any
    try:
        value = json.loads(args.value)
    except json.JSONDecodeError:
        value = {"text": args.value}

    if isinstance(value, dict):
        value = dict(value)
        value["observation_grade"] = grade
        value["observed_via"] = "cli_evidence_add"

    idents = []
    if args.identifier:
        for raw in args.identifier:
            # type:value or type@platform:value for username
            if raw.count(":") >= 1:
                t, rest = raw.split(":", 1)
                if t == "username" and "@" in rest and ":" not in rest:
                    # username:handle (platform via --platform)
                    idents.append(
                        {
                            "type": "username",
                            "value": rest,
                            "platform": args.platform or "web",
                        }
                    )
                elif t == "username" and rest.count("@") >= 1:
                    # username:handle@platform style wrong; use username:handle + --platform
                    idents.append(
                        {
                            "type": "username",
                            "value": rest.split("@")[0],
                            "platform": rest.split("@")[-1] if "@" in rest else (args.platform or "web"),
                        }
                    )
                else:
                    idents.append({"type": t, "value": rest})
            else:
                idents.append({"type": "other", "value": raw})

    item = {
        "type": args.type,
        "value": value,
        "source_name": "evidence_add",
        "source_url": args.url,
        "confidence": float(conf),
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()]
        + ["evidence_add", f"grade:{grade}"],
        "seed_ids": [s.strip() for s in (args.seed_ids or "").split(",") if s.strip()],
        "platform": args.platform,
        "identifiers": idents,
        "meta": {"observation_grade": grade},
    }
    ev = add_evidence(state, item)
    if not ev:
        return emit({"ok": True, "action": "evidence_add", "added": False, "note": "duplicate skipped"})
    record_iteration(
        state,
        phase="evidence_add",
        commands_or_goals=[f"evidence add grade={grade} {args.url or ''}"],
        evidence_ids_added=[ev["id"]],
    )
    append_run_log(state, "evidence_add", {"id": ev["id"], "grade": grade})
    save_state(state)
    return emit({"ok": True, "action": "evidence_add", "added": True, "evidence": ev})



def cmd_next(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if not state.get("clue_analysis") and state.get("seeds"):
        apply_analysis_to_state(state, merge_questions=True)
    plan = next_actions(state, limit=args.limit)
    save_state(state)
    return emit({"ok": True, "action": "next", **plan})


def cmd_plan(args: argparse.Namespace) -> int:
    """Clue analyze: questions + source routing (core reasoning upgrade)."""
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if not state.get("seeds"):
        return emit_error("no seeds; add clues first: seed add name:…")
    analysis = apply_analysis_to_state(
        state,
        analyze_clues(state),
        merge_questions=not args.no_merge_questions,
    )
    record_iteration(
        state,
        phase="plan",
        commands_or_goals=["plan / clue-analyze"],
        extra={"summary": analysis.get("summary")},
    )
    save_state(state)
    return emit(
        {
            "ok": True,
            "action": "plan",
            "analysis": analysis,
            "hint": (
                "Execute P0 via collect --modules pddikti,websearch,primary_page "
                "(+ gov_id / pddikti_api). On challenge wall: hitl complete or browser_cdp. "
                "Do not start with reverse-image, IDOR, or captcha farms."
            ),
            "open_hitl_gates": open_gates_summary(state),
        }
    )


def cmd_question(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if args.question_action == "add":
        q = add_question(
            state,
            args.text,
            dimension=args.dimension,
            priority=args.priority,
            origin="user",
        )
        record_iteration(state, phase="question", commands_or_goals=[f"question add {q['id']}"])
        save_state(state)
        return emit({"ok": True, "action": "question_add", "question": q})
    if args.question_action == "list":
        return emit({"ok": True, "action": "question_list", "questions": state.get("questions") or []})
    if args.question_action == "set":
        try:
            q = update_question(
                state,
                args.question_id,
                status=args.status,
                answer=args.answer,
            )
        except ValueError as e:
            return emit_error(str(e))
        record_iteration(
            state,
            phase="question",
            commands_or_goals=[f"question set {args.question_id} {args.status}"],
        )
        save_state(state)
        return emit({"ok": True, "action": "question_set", "question": q})
    return emit_error(f"unknown question action: {args.question_action}")


def cmd_dimension(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    try:
        dim = set_dimension(
            state,
            args.dimension,
            status=args.status,
            fact=args.fact,
            inference=(
                {"text": args.inference, "confidence": args.confidence}
                if args.inference
                else None
            ),
            evidence_ids=args.evidence_ids.split(",") if args.evidence_ids else None,
            method=args.method,
            not_found=args.not_found,
        )
    except ValueError as e:
        return emit_error(str(e))
    record_iteration(
        state,
        phase="dimension",
        commands_or_goals=[f"dimension {args.dimension}"],
    )
    save_state(state)
    return emit({"ok": True, "action": "dimension_set", "dimension": dim})


def cmd_timeline(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    ev = add_timeline_event(
        state,
        date=args.date,
        summary=args.summary,
        dimension=args.dimension,
        evidence_ids=args.evidence_ids.split(",") if args.evidence_ids else None,
        confidence=args.confidence,
    )
    record_iteration(state, phase="timeline", commands_or_goals=[f"timeline {ev['id']}"])
    save_state(state)
    return emit({"ok": True, "action": "timeline_add", "event": ev})


def cmd_identity_lock(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    try:
        lock = set_identity_lock(
            state,
            locked=not args.unlock,
            candidate_id=None if args.unlock else args.candidate,
            signals=list(args.signal or []) if not args.unlock else None,
            notes=args.notes or "",
            kind=getattr(args, "kind", None) or "digital",
        )
    except ValueError as e:
        return emit_error(str(e))
    record_iteration(
        state,
        phase="identity_lock",
        commands_or_goals=["identity-lock" if not args.unlock else "identity-unlock"],
    )
    save_state(state)
    return emit({"ok": True, "action": "identity_lock", "identity_lock": lock})


def cmd_reject(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    try:
        entry = reject_candidate(state, args.candidate_id, args.reason)
    except ValueError as e:
        return emit_error(str(e))
    record_iteration(
        state,
        phase="reject",
        commands_or_goals=[f"reject {args.candidate_id}"],
    )
    save_state(state)
    return emit({"ok": True, "action": "reject", "rejected": entry})


def cmd_hypothesis(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    if args.hypothesis_action == "add":
        h = add_hypothesis(
            state,
            args.text,
            dimension=args.dimension,
            from_clue=bool(args.from_clue),
        )
        save_state(state)
        return emit({"ok": True, "action": "hypothesis_add", "hypothesis": h})
    if args.hypothesis_action == "list":
        return emit(
            {"ok": True, "action": "hypothesis_list", "hypotheses": state.get("hypotheses") or []}
        )
    if args.hypothesis_action == "resolve":
        try:
            h = resolve_hypothesis(
                state,
                args.hypothesis_id,
                status=args.status,
                method=args.method,
                notes=args.notes,
            )
        except ValueError as e:
            return emit_error(str(e))
        record_iteration(
            state,
            phase="hypothesis",
            commands_or_goals=[f"hypothesis resolve {args.hypothesis_id} {args.status}"],
        )
        save_state(state)
        return emit({"ok": True, "action": "hypothesis_resolve", "hypothesis": h})
    return emit_error(f"unknown hypothesis action: {args.hypothesis_action}")


def cmd_report(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    dossier = build_dossier_report(state)
    md = render_dossier_markdown(state)
    out_json = None
    out_md = None
    if args.out:
        out_json = Path(args.out)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(dossier, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        out_md = Path(args.markdown)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md, encoding="utf-8")
    record_iteration(state, phase="report", commands_or_goals=["report"])
    save_state(state)
    return emit(
        {
            "ok": True,
            "action": "report",
            "dossier": dossier,
            "markdown_path": str(out_md.resolve()) if out_md else None,
            "json_path": str(out_json.resolve()) if out_json else None,
            "markdown_preview": md if args.include_markdown else None,
        }
    )


def cmd_platform_probe(args: argparse.Namespace) -> int:
    from .platform_probe import probe_browser_capability

    probe = probe_browser_capability()
    return emit({"ok": True, "action": "platform_probe", **probe})


def cmd_campus_list(args: argparse.Namespace) -> int:
    """Ingest campus list file into investigation evidence."""
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    from pathlib import Path as P

    from .campus_list import grep_name_family, ingest_summary, parse_campus_list_text
    from .normalize import add_evidence
    from .state import utc_now

    path = P(args.file)
    if not path.is_file():
        return emit_error(f"file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = parse_campus_list_text(text, source_label=str(path))
    greps = grep_name_family(rows, pattern=args.pattern)
    summary = ingest_summary(rows, greps)
    summary["source_label"] = str(path.resolve())
    summary["text_chars"] = len(text)
    seed0 = (state.get("seeds") or [{"id": "s0"}])[0]
    ev = add_evidence(
        state,
        {
            "type": "document",
            "value": summary,
            "source_name": "campus_list_ingest",
            "source_url": None,
            "collected_at": utc_now(),
            "confidence": 0.65 if rows else 0.25,
            "tags": ["campus_list", "cohort", "document", "cli_ingest"],
            "seed_ids": [seed0.get("id")],
            "meta": {"observation_grade": "full_page" if rows else "blank_after_methods"},
        },
    )
    record_iteration(state, phase="campus_list", commands_or_goals=[f"campus-list {path}"])
    save_state(state)
    return emit(
        {
            "ok": True,
            "action": "campus_list",
            "row_count": summary["row_count"],
            "cel_family_hits": greps,
            "evidence_id": (ev or {}).get("id"),
            "ilkom_heuristic_count": summary.get("ilkom_heuristic_count"),
        }
    )


def cmd_dossier(args: argparse.Namespace) -> int:
    try:
        state = _require_state(args)
    except FileNotFoundError as e:
        return emit_error(str(e))
    ensure_dossier(state)
    if args.summary is not None:
        state["dossier"]["subject_summary"] = args.summary
        save_state(state)
    return emit(
        {
            "ok": True,
            "action": "dossier",
            "identity_lock": state.get("identity_lock"),
            "dimensions": state["dossier"]["dimensions"],
            "timeline": state["dossier"]["timeline"],
            "subject_summary": state["dossier"].get("subject_summary"),
            "rejected_candidates": state.get("rejected_candidates") or [],
            "hypotheses": state.get("hypotheses") or [],
            "questions": state.get("questions") or [],
        }
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="osint-cli",
        description=(
            "AI-callable terminal OSINT — person background-check dossier "
            "(clues≠goals; expand strongest node; identity-lock before soft geo/year)."
        ),
    )
    p.add_argument("--version", action="version", version=f"osint-cli {__version__}")
    p.add_argument(
        "--case",
        "-c",
        help="Path to investigation JSON state (default: ./investigation.json)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="Create a new investigation case file")
    sp.add_argument("--purpose", default="research")
    sp.add_argument("--max-depth", type=int, default=5)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("status", help="Case summary + dimension status + strongest nodes")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("seed", help="Seed/clue intake (not completion criteria)")
    ssp = sp.add_subparsers(dest="seed_action", required=True)
    addp = ssp.add_parser("add", help="Add seed(s): type:value or bare value")
    addp.add_argument("specs", nargs="+", help="e.g. email:a@b.com username:alice")
    addp.set_defaults(func=cmd_seed)
    listp = ssp.add_parser("list", help="List seeds")
    listp.set_defaults(func=cmd_seed)

    sp = sub.add_parser(
        "phone",
        help="Phone as clue: normalize / SERP footprint / HITL checklist (no breach/NIK)",
    )
    psub = sp.add_subparsers(dest="phone_action", required=True)
    pn = psub.add_parser("normalize", help="E.164 + variants + prefix soft (no network)")
    pn.add_argument("spec", help="Phone e.g. 0811-60600-613 or +62811…")
    pn.set_defaults(func=cmd_phone)
    pq = psub.add_parser("queries", help="Build Layer A SERP queries")
    pq.add_argument("spec", help="Phone number")
    pq.add_argument("--goal", "-g", default=None)
    pq.set_defaults(func=cmd_phone)
    pc = psub.add_parser("checklist", help="Layer B HITL checklist (operator only)")
    pc.add_argument("spec", nargs="?", default=None, help="Optional phone for context")
    pc.set_defaults(func=cmd_phone)
    pf = psub.add_parser(
        "footprint",
        help="Add phone seed + run phone_footprint module on case",
    )
    pf.add_argument("spec", help="Phone number")
    pf.add_argument("--goal", "-g", default=None)
    pf.add_argument("--offline", action="store_true")
    pf.set_defaults(func=cmd_phone)

    sp = sub.add_parser("collect", help="Run collection modules")
    sp.add_argument("--goal", "-g", help="Free-text goal (prefer dimension-focused goals)")
    sp.add_argument(
        "--dimension",
        choices=[d["id"] for d in DIMENSIONS],
        help="Tag collect as filling a life dimension",
    )
    sp.add_argument("--method-note", help="Record method tried on dimension")
    sp.add_argument(
        "--modules",
        "-m",
        help=(
            "Comma list: websearch,username_enum,email_reg,fixture,pddikti,pddikti_api,"
            "primary_page,gov_id,browser_cdp,phone_footprint"
        ),
    )
    sp.add_argument("--offline", action="store_true")
    sp.add_argument("--seed-ids", help="Comma seed ids to limit collection")
    sp.set_defaults(func=cmd_collect)

    sp = sub.add_parser(
        "hitl",
        help="Human-in-the-loop: open/complete browser gates (CAPTCHA walls) — no captcha farms",
    )
    hsub = sp.add_subparsers(dest="hitl_action", required=True)
    ho = hsub.add_parser("open", help="Open a gate for operator real-browser work")
    ho.add_argument(
        "--source",
        default="generic",
        choices=["pddikti", "putusan_ma", "ahu", "lpse", "kpu", "generic"],
    )
    ho.add_argument("--url", default=None)
    ho.add_argument("--why", default="")
    ho.add_argument("--fields", help="Comma expected field names")
    ho.add_argument("--seed-ids", default="")
    ho.add_argument("--query-hint", action="append", default=[])
    ho.set_defaults(func=cmd_hitl)
    hl = hsub.add_parser("list", help="List HITL gates")
    hl.add_argument("--status", choices=["open", "completed", "cancelled"], default=None)
    hl.set_defaults(func=cmd_hitl)
    hc = hsub.add_parser("complete", help="Complete gate with operator-captured fields")
    hc.add_argument("--gate", required=True, help="Gate id e.g. g1")
    hc.add_argument("--value", required=True, help="JSON object or plain text")
    hc.add_argument(
        "--grade",
        default="full_page",
        choices=["full_page", "search_snippet", "portal_metadata", "operator_clue"],
    )
    hc.add_argument("--url", default=None)
    hc.add_argument("--notes", default="")
    hc.add_argument("--confidence", type=float, default=None)
    hc.set_defaults(func=cmd_hitl)
    hi = hsub.add_parser("import-file", help="Import HTML/JSON/text saved by operator")
    hi.add_argument("--path", required=True)
    hi.add_argument("--gate", default=None)
    hi.add_argument("--source", default="generic")
    hi.add_argument(
        "--grade",
        default="full_page",
        choices=["full_page", "search_snippet", "portal_metadata", "operator_clue"],
    )
    hi.add_argument("--url", default=None)
    hi.set_defaults(func=cmd_hitl)
    hx = hsub.add_parser("cancel", help="Cancel an open gate")
    hx.add_argument("--gate", required=True)
    hx.add_argument("--notes", default="")
    hx.set_defaults(func=cmd_hitl)

    sp = sub.add_parser("differentiate", help="Cluster evidence into candidate persons")
    sp.set_defaults(func=cmd_differentiate)

    sp = sub.add_parser("candidates", help="List candidates + strongest expand scores")
    sp.set_defaults(func=cmd_candidates)

    sp = sub.add_parser(
        "evidence",
        help="Record public observation with provenance grade (full_page|search_snippet|…)",
    )
    esub = sp.add_subparsers(dest="evidence_action", required=True)
    ea = esub.add_parser("add", help="Add one evidence item observed outside automated modules")
    ea.add_argument("--type", default="web_hit", help="profile|web_hit|public_record|other|…")
    ea.add_argument("--url", default=None, help="Source URL")
    ea.add_argument(
        "--grade",
        required=True,
        choices=["full_page", "search_snippet", "portal_metadata", "operator_clue"],
        help="How the observation was obtained (honesty for verification)",
    )
    ea.add_argument("--value", required=True, help="JSON object or plain text")
    ea.add_argument("--tags", default="", help="Comma tags")
    ea.add_argument("--seed-ids", default="", help="Comma seed ids")
    ea.add_argument("--platform", default=None)
    ea.add_argument(
        "--identifier",
        action="append",
        default=[],
        help="Repeatable type:value e.g. name:X username:handle",
    )
    ea.add_argument("--confidence", type=float, default=None)
    ea.set_defaults(func=cmd_evidence)

    sp = sub.add_parser("select", help="Select candidate branch(es) to deepen")
    sp.add_argument("candidate_ids", nargs="+", help="e.g. c1 c2")
    sp.set_defaults(func=cmd_select)

    sp = sub.add_parser("reject", help="Reject a collision candidate with reason")
    sp.add_argument("candidate_id")
    sp.add_argument("--reason", required=True)
    sp.set_defaults(func=cmd_reject)

    sp = sub.add_parser("escalate", help="Derive new seeds from selected candidates only")
    sp.add_argument("--goal", "-g")
    sp.add_argument("--candidate-ids", nargs="*", default=None)
    sp.set_defaults(func=cmd_escalate)

    sp = sub.add_parser("next", help="Planner: next person-dossier actions (not clue checklist)")
    sp.add_argument("--limit", type=int, default=8)
    sp.set_defaults(func=cmd_next)

    sp = sub.add_parser(
        "plan",
        help="Clue→questions→sources analysis (PDDIKTI, primary page, tags; image non-default)",
        aliases=["clue-analyze", "analyze"],
    )
    sp.add_argument(
        "--no-merge-questions",
        action="store_true",
        help="Do not merge generated questions into state.questions",
    )
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("question", help="Investigation questions (true goals)")
    qsub = sp.add_subparsers(dest="question_action", required=True)
    qa = qsub.add_parser("add")
    qa.add_argument("text")
    qa.add_argument("--dimension", choices=[d["id"] for d in DIMENSIONS])
    qa.add_argument("--priority", type=int, default=2)
    qa.set_defaults(func=cmd_question)
    ql = qsub.add_parser("list")
    ql.set_defaults(func=cmd_question)
    qs = qsub.add_parser("set")
    qs.add_argument("question_id")
    qs.add_argument("--status", choices=["open", "answered", "blank", "blocked"])
    qs.add_argument("--answer")
    qs.set_defaults(func=cmd_question)

    sp = sub.add_parser("dimension", help="Record fact/inference/blank on a life dimension")
    sp.add_argument("dimension", choices=[d["id"] for d in DIMENSIONS])
    sp.add_argument("--status", choices=["empty", "partial", "filled", "blank_after_methods", "blocked_need_identity_lock"])
    sp.add_argument("--fact")
    sp.add_argument("--inference")
    sp.add_argument("--confidence", type=float, default=0.5)
    sp.add_argument("--evidence-ids")
    sp.add_argument("--method")
    sp.add_argument("--not-found", dest="not_found")
    sp.set_defaults(func=cmd_dimension)

    sp = sub.add_parser("timeline", help="Add a dated life-event")
    sp.add_argument("--date", help="ISO date or free date string")
    sp.add_argument("--summary", required=True)
    sp.add_argument("--dimension", choices=[d["id"] for d in DIMENSIONS])
    sp.add_argument("--evidence-ids")
    sp.add_argument("--confidence", type=float, default=0.5)
    sp.set_defaults(func=cmd_timeline)

    sp = sub.add_parser(
        "identity-lock",
        help="Lock identity: --kind digital (handles) or civil (name+NIM). Digital ≠ civil.",
    )
    sp.add_argument("--candidate", help="Candidate id to lock")
    sp.add_argument(
        "--kind",
        choices=["digital", "civil", "both"],
        default="digital",
        help="digital=handles/bio/peers; civil=legal name+NIM; both=rare",
    )
    sp.add_argument(
        "--signal",
        action="append",
        default=[],
        help="Repeatable: bio_match, dual_handle_pointer, peer_coappearance, nim_match, …",
    )
    sp.add_argument("--notes", default="")
    sp.add_argument("--unlock", action="store_true", help="Clear lock for --kind")
    sp.set_defaults(func=cmd_identity_lock)

    sp = sub.add_parser("hypothesis", help="Clue-derived hypotheses (test later; not auto-facts)")
    hsub = sp.add_subparsers(dest="hypothesis_action", required=True)
    ha = hsub.add_parser("add")
    ha.add_argument("text")
    ha.add_argument("--dimension", choices=[d["id"] for d in DIMENSIONS])
    ha.add_argument(
        "--from-clue",
        dest="from_clue",
        action="store_true",
        default=True,
        help="Mark as clue-derived (default true)",
    )
    ha.add_argument(
        "--not-from-clue",
        dest="from_clue",
        action="store_false",
        help="Mark as investigator-generated hypothesis",
    )
    ha.set_defaults(func=cmd_hypothesis)
    hl = hsub.add_parser("list")
    hl.set_defaults(func=cmd_hypothesis)
    hr = hsub.add_parser("resolve")
    hr.add_argument("hypothesis_id")
    hr.add_argument("--status", required=True, choices=["untested", "testing", "confirmed", "blank", "rejected"])
    hr.add_argument("--method")
    hr.add_argument("--notes")
    hr.set_defaults(func=cmd_hypothesis)

    sp = sub.add_parser("dossier", help="Show dossier dimensions/timeline/collisions")
    sp.add_argument("--summary", help="Set subject summary string")
    sp.set_defaults(func=cmd_dossier)

    sp = sub.add_parser("report", help="Person background-check report (JSON + optional markdown)")
    sp.add_argument("--out", "-o", help="Write dossier JSON path")
    sp.add_argument("--markdown", help="Write markdown dossier path")
    sp.add_argument("--include-markdown", action="store_true", help="Embed markdown in JSON stdout")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser(
        "platform-probe",
        help="Detect if CDP/Chrome works here (arm64/Android → prefer HITL)",
    )
    sp.set_defaults(func=cmd_platform_probe)

    sp = sub.add_parser(
        "campus-list",
        help="Ingest EPT/distribusi text file into case evidence + Cel-family grep",
    )
    sp.add_argument("--file", "-f", required=True, help="Path to extracted list text")
    sp.add_argument("--pattern", help="Optional regex for name grep (default Cel/Cec family)")
    sp.set_defaults(func=cmd_campus_list)

    sp = sub.add_parser("export", help="Write full investigation JSON package (+ dossier_report)")
    sp.add_argument("--out", "-o")
    sp.add_argument(
        "--terminate",
        choices=[
            "stable_identity",
            "exhausted_public_sources",
            "max_depth",
            "user_stop",
            "ambiguous_unresolvable",
        ],
    )
    sp.add_argument("--summary")
    sp.add_argument("--include-log", action="store_true")
    sp.set_defaults(func=cmd_export)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0
    except Exception as e:
        return emit_error(str(e), traceback=traceback.format_exc())


if __name__ == "__main__":
    raise SystemExit(main())
