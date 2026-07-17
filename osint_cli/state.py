"""Investigation state load/save and schema helpers."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.2"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_investigation(
    case_path: str | Path,
    purpose: str = "research",
    max_depth: int = 5,
) -> dict[str, Any]:
    now = utc_now()
    # Lazy import to avoid circular deps at module load for simple state ops
    from .dossier import ensure_dossier

    state = {
        "schema_version": SCHEMA_VERSION,
        "investigation_id": str(uuid.uuid4()),
        "case_path": str(Path(case_path).resolve()),
        "created_at": now,
        "updated_at": now,
        "depth": 0,
        "scope": {
            "purpose": purpose,
            "jurisdiction_notes": "",
            "max_depth": max_depth,
            "allowed_modules": [
                "websearch",
                "username_enum",
                "name_pattern_enum",
                "tiktok_embed",
                "tiktok_comments",
                "campus_list_ingest",
                "email_reg",
                "fixture",
                "pddikti",
                "pddikti_api",
                "primary_page",
                "gov_id",
                "browser_cdp",
            ],
            "workflow": {
                "clue_is_not_goal": True,
                "require_identity_lock_before_soft_geo_year": True,
                "report_is_person_dossier": True,
                "expand_from_strongest_node": True,
                "forbid_generic_institution_as_person_fact": True,
                "hitl_on_challenge_wall": True,
                "gov_sources_passive_only": True,
                "forbid_idor_and_captcha_farms": True,
                "ban_ask_operator_for_legal_name": True,
                "anti_give_up_cohort_pivot": True,
                "split_digital_vs_civil_lock": True,
            },
        },
        "seeds": [],
        "iterations": [],
        "evidence": [],
        "candidates": [],
        "links": [],
        "selected_branches": [],
        "hitl_gates": [],
        "termination": {
            "reason": None,
            "final_candidate_ids": [],
            "summary": None,
        },
        "export_meta": {
            "tool": "ai-osint-terminal",
            "format": "investigation_graph_v1",
            "dossier_format": "background_check_dossier_v1",
        },
        "run_log": [],
    }
    ensure_dossier(state)
    return state


def save_state(state: dict[str, Any], path: str | Path | None = None) -> Path:
    p = Path(path or state["case_path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    state = deepcopy(state)
    state["updated_at"] = utc_now()
    state["case_path"] = str(p.resolve())
    with p.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return p


def load_state(path: str | Path) -> dict[str, Any]:
    from .dossier import ensure_dossier

    p = Path(path)
    with p.open(encoding="utf-8") as f:
        state = json.load(f)
    state["case_path"] = str(p.resolve())
    ensure_dossier(state)  # migrate 1.0 → 1.1 structures
    return state


def next_id(items: list[dict[str, Any]], prefix: str) -> str:
    n = 1
    existing = {i.get("id") for i in items}
    while f"{prefix}{n}" in existing:
        n += 1
    return f"{prefix}{n}"


def record_iteration(
    state: dict[str, Any],
    phase: str,
    commands_or_goals: list[str] | None = None,
    modules_run: list[str] | None = None,
    evidence_ids_added: list[str] | None = None,
    selected_candidate_ids: list[str] | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    it = {
        "iteration": len(state["iterations"]) + 1,
        "phase": phase,
        "selected_candidate_ids": list(
            selected_candidate_ids
            if selected_candidate_ids is not None
            else state.get("selected_branches") or []
        ),
        "commands_or_goals": commands_or_goals or [],
        "modules_run": modules_run or [],
        "started_at": started_at or utc_now(),
        "ended_at": ended_at or utc_now(),
        "evidence_ids_added": evidence_ids_added or [],
    }
    if extra:
        it.update(extra)
    state["iterations"].append(it)
    return it


def append_run_log(state: dict[str, Any], event: str, detail: Any = None) -> None:
    state.setdefault("run_log", []).append(
        {"at": utc_now(), "event": event, "detail": detail}
    )
