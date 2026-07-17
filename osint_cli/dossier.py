"""Person-centric background-check dossier: dimensions, questions, next actions, report.

Design rules from postmortem:
- Clues/seeds open doors; goals are investigation questions and life dimensions.
- Do not circle known lead context (generic SNBP news, admin geography alone).
- Identity lock before soft geo/year hypotheses as profile facts.
- Report = subject dossier, not methodology essay.
"""

from __future__ import annotations

import re
from typing import Any

from .state import next_id, utc_now


# Life dimensions for a background-check style OSINT product
DIMENSIONS: list[dict[str, str]] = [
    {"id": "identity", "label": "Identity lock", "desc": "Stable person: photo, handles, multi-signal"},
    {"id": "education", "label": "Education timeline", "desc": "Schools, university, cohort/year, programs"},
    {"id": "org_activity", "label": "Org / campus activity", "desc": "Student orgs, roles, events over time"},
    {"id": "work", "label": "Work / internship", "desc": "Jobs, internships, professional profiles"},
    {"id": "digital", "label": "Digital footprint", "desc": "Verified social/web accounts only"},
    {"id": "family", "label": "Family (public only)", "desc": "Public family links if any; never invent"},
    {"id": "geo", "label": "Places / origin", "desc": "Tied to person, not bare place existence"},
    {"id": "notable", "label": "Notable / public record", "desc": "Awards, news, publications, contests"},
    {"id": "risk", "label": "Risk / adverse", "desc": "Public adverse mentions if any"},
    {"id": "network", "label": "Network / peers", "desc": "Named co-appearing people with edges"},
]

# Priority order after a strong lead exists
EXPAND_PRIORITY = [
    "identity",
    "org_activity",
    "education",
    "digital",
    "network",
    "work",
    "notable",
    "geo",
    "family",
    "risk",
]

DEFAULT_QUESTIONS: list[dict[str, Any]] = [
    {
        "text": "Who is the subject as a stable public identity (photo/handle/multi-signal)?",
        "dimension": "identity",
        "priority": 0,
    },
    {
        "text": "What education timeline is publicly supported?",
        "dimension": "education",
        "priority": 1,
    },
    {
        "text": "What org/campus activity events form a timeline (not a single award)?",
        "dimension": "org_activity",
        "priority": 1,
    },
    {
        "text": "What verified digital accounts belong to this person?",
        "dimension": "digital",
        "priority": 1,
    },
    {
        "text": "Who appears in the same public graph (peers/tags)?",
        "dimension": "network",
        "priority": 2,
    },
    {
        "text": "Any public work/internship footprint?",
        "dimension": "work",
        "priority": 2,
    },
    {
        "text": "Any public notable awards/news beyond the initial lead?",
        "dimension": "notable",
        "priority": 2,
    },
    {
        "text": "Is origin/residence tied to the locked identity (not bare place names)?",
        "dimension": "geo",
        "priority": 3,
    },
    {
        "text": "Any public family links?",
        "dimension": "family",
        "priority": 3,
    },
    {
        "text": "Any public adverse/risk mentions?",
        "dimension": "risk",
        "priority": 3,
    },
]


def empty_dimension(dim_id: str) -> dict[str, Any]:
    meta = next(d for d in DIMENSIONS if d["id"] == dim_id)
    return {
        "id": dim_id,
        "label": meta["label"],
        "status": "empty",  # empty | partial | filled | blank_after_methods | blocked_need_identity_lock
        "facts": [],
        "inferences": [],
        "evidence_ids": [],
        "methods_tried": [],
        "not_found_notes": [],
        "updated_at": None,
    }


def ensure_dossier(state: dict[str, Any]) -> dict[str, Any]:
    """Migrate/ensure dossier + questions + identity_lock structures on state."""
    if "dossier" not in state or not isinstance(state["dossier"], dict):
        state["dossier"] = {
            "dimensions": {d["id"]: empty_dimension(d["id"]) for d in DIMENSIONS},
            "timeline": [],
            "subject_summary": None,
        }
    else:
        dims = state["dossier"].setdefault("dimensions", {})
        for d in DIMENSIONS:
            if d["id"] not in dims:
                dims[d["id"]] = empty_dimension(d["id"])
        state["dossier"].setdefault("timeline", [])
        state["dossier"].setdefault("subject_summary", None)

    if "questions" not in state or not isinstance(state["questions"], list):
        state["questions"] = []
        for q in DEFAULT_QUESTIONS:
            add_question(state, q["text"], dimension=q["dimension"], priority=q["priority"])

    if "identity_lock" not in state:
        state["identity_lock"] = _empty_identity_lock()
    else:
        # migrate legacy single-lock → digital/civil split
        lock = state["identity_lock"]
        if "digital" not in lock or "civil" not in lock:
            legacy_locked = bool(lock.get("locked"))
            state["identity_lock"] = {
                "locked": legacy_locked,  # backward-compat: any lock
                "candidate_id": lock.get("candidate_id"),
                "signals": list(lock.get("signals") or []),
                "locked_at": lock.get("locked_at"),
                "notes": lock.get("notes") or "",
                "digital": {
                    "locked": legacy_locked,
                    "signals": list(lock.get("signals") or []),
                    "locked_at": lock.get("locked_at"),
                    "notes": "migrated from legacy identity_lock",
                },
                "civil": {
                    "locked": False,
                    "signals": [],
                    "locked_at": None,
                    "notes": "civil (name+NIM multi-signal) not set; do not infer from digital",
                },
            }

    if "rejected_candidates" not in state:
        state["rejected_candidates"] = []

    if "hypotheses" not in state:
        state["hypotheses"] = []

    # policy flags for agents
    scope = state.setdefault("scope", {})
    scope.setdefault(
        "workflow",
        {
            "clue_is_not_goal": True,
            "require_identity_lock_before_soft_geo_year": True,
            "report_is_person_dossier": True,
            "expand_from_strongest_node": True,
            "forbid_generic_institution_as_person_fact": True,
        },
    )
    return state


def add_question(
    state: dict[str, Any],
    text: str,
    dimension: str | None = None,
    priority: int = 2,
    origin: str = "user",
) -> dict[str, Any]:
    ensure_dossier(state)
    q = {
        "id": next_id(state["questions"], "q"),
        "text": text.strip(),
        "dimension": dimension,
        "priority": int(priority),
        "status": "open",  # open | answered | blank | blocked
        "answer": None,
        "evidence_ids": [],
        "origin": origin,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    state["questions"].append(q)
    return q


def update_question(
    state: dict[str, Any],
    question_id: str,
    status: str | None = None,
    answer: str | None = None,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    ensure_dossier(state)
    for q in state["questions"]:
        if q["id"] == question_id:
            if status:
                q["status"] = status
            if answer is not None:
                q["answer"] = answer
            if evidence_ids is not None:
                q["evidence_ids"] = list(evidence_ids)
            q["updated_at"] = utc_now()
            return q
    raise ValueError(f"unknown question id: {question_id}")


def set_dimension(
    state: dict[str, Any],
    dimension: str,
    *,
    status: str | None = None,
    fact: str | None = None,
    inference: dict[str, Any] | None = None,
    evidence_ids: list[str] | None = None,
    method: str | None = None,
    not_found: str | None = None,
) -> dict[str, Any]:
    ensure_dossier(state)
    if dimension not in state["dossier"]["dimensions"]:
        raise ValueError(f"unknown dimension: {dimension}; known={list(state['dossier']['dimensions'])}")
    dim = state["dossier"]["dimensions"][dimension]
    if status:
        dim["status"] = status
    if fact:
        dim["facts"].append({"text": fact, "at": utc_now(), "evidence_ids": list(evidence_ids or [])})
    if inference:
        inf = dict(inference)
        inf.setdefault("at", utc_now())
        dim["inferences"].append(inf)
    if evidence_ids:
        for eid in evidence_ids:
            if eid not in dim["evidence_ids"]:
                dim["evidence_ids"].append(eid)
    if method:
        dim["methods_tried"].append({"method": method, "at": utc_now()})
    if not_found:
        dim["not_found_notes"].append({"text": not_found, "at": utc_now()})
        if dim["status"] in ("empty", "partial") and not dim["facts"]:
            dim["status"] = "blank_after_methods"
    # auto status
    if dim["facts"] and dim["status"] in ("empty", "blank_after_methods"):
        dim["status"] = "partial" if len(dim["facts"]) < 2 else "filled"
    dim["updated_at"] = utc_now()
    return dim


def add_timeline_event(
    state: dict[str, Any],
    date: str | None,
    summary: str,
    dimension: str | None = None,
    evidence_ids: list[str] | None = None,
    confidence: float = 0.5,
) -> dict[str, Any]:
    ensure_dossier(state)
    ev = {
        "id": next_id(state["dossier"]["timeline"], "t"),
        "date": date,
        "summary": summary,
        "dimension": dimension,
        "evidence_ids": list(evidence_ids or []),
        "confidence": confidence,
        "added_at": utc_now(),
    }
    state["dossier"]["timeline"].append(ev)
    # sort: undated last
    state["dossier"]["timeline"].sort(key=lambda x: (x.get("date") is None, x.get("date") or "", x["id"]))
    return ev


def _empty_identity_lock() -> dict[str, Any]:
    return {
        "locked": False,
        "candidate_id": None,
        "signals": [],
        "locked_at": None,
        "notes": "",
        "digital": {"locked": False, "signals": [], "locked_at": None, "notes": ""},
        "civil": {"locked": False, "signals": [], "locked_at": None, "notes": ""},
    }


def set_identity_lock(
    state: dict[str, Any],
    locked: bool,
    candidate_id: str | None = None,
    signals: list[str] | None = None,
    notes: str = "",
    kind: str = "digital",
) -> dict[str, Any]:
    """Lock identity.

    kind:
      - digital: handles / bio pointers / peer co-appearance (NOT civil name)
      - civil: legal name + NIM (or equivalent) multi-signal
      - both: set digital + civil together (rare; needs strong signals)

    ``identity_lock.locked`` remains True if *digital* is locked (compat for
    soft geo/year gates). Civil open is always visible on report.
    """
    ensure_dossier(state)
    kind = (kind or "digital").lower().strip()
    if kind not in ("digital", "civil", "both"):
        raise ValueError("kind must be digital|civil|both")
    if locked and not candidate_id:
        raise ValueError("identity lock requires candidate_id")
    if locked and candidate_id:
        known = {c["id"] for c in state.get("candidates") or []}
        if candidate_id not in known:
            raise ValueError(f"unknown candidate: {candidate_id}")
        for c in state["candidates"]:
            c["status"] = "selected" if c["id"] == candidate_id else (
                "active" if c.get("status") == "selected" else c.get("status", "active")
            )
        state["selected_branches"] = [candidate_id]

    lock = state.setdefault("identity_lock", _empty_identity_lock())
    for sub in ("digital", "civil"):
        lock.setdefault(sub, {"locked": False, "signals": [], "locked_at": None, "notes": ""})

    sigs = list(signals or [])
    now = utc_now() if locked else None
    targets = ["digital", "civil"] if kind == "both" else [kind]
    for t in targets:
        if locked:
            lock[t] = {
                "locked": True,
                "signals": sigs,
                "locked_at": now,
                "notes": notes,
            }
        else:
            lock[t] = {
                "locked": False,
                "signals": [],
                "locked_at": None,
                "notes": notes or "unlocked",
            }

    digital_on = bool(lock.get("digital", {}).get("locked"))
    civil_on = bool(lock.get("civil", {}).get("locked"))
    # Compat: top-level locked follows digital (expand/geo gates)
    lock["locked"] = digital_on
    lock["candidate_id"] = candidate_id if (digital_on or civil_on) else None
    # Merge signals for legacy readers
    merged = []
    for t in ("digital", "civil"):
        for s in lock.get(t, {}).get("signals") or []:
            if s not in merged:
                merged.append(s)
    lock["signals"] = merged
    lock["locked_at"] = now if (digital_on or civil_on) else None
    lock["notes"] = notes
    lock["civil_open"] = not civil_on
    lock["summary"] = {
        "digital_locked": digital_on,
        "civil_locked": civil_on,
        "civil_open": not civil_on,
    }

    if digital_on or civil_on:
        parts = []
        if digital_on:
            parts.append(f"digital=[{', '.join(lock['digital'].get('signals') or [])}]")
        if civil_on:
            parts.append(f"civil=[{', '.join(lock['civil'].get('signals') or [])}]")
        status = "filled" if civil_on and digital_on else "partial"
        kwargs: dict[str, Any] = {
            "status": status,
            "fact": f"Identity on {candidate_id}: {'; '.join(parts)}",
            "method": "identity_lock_command",
        }
        if digital_on and not civil_on:
            kwargs["not_found"] = (
                "civil name+NIM multi-signal still OPEN (digital lock ≠ legal ID)"
            )
        set_dimension(state, "identity", **kwargs)
    return state["identity_lock"]


def reject_candidate(
    state: dict[str, Any],
    candidate_id: str,
    reason: str,
) -> dict[str, Any]:
    ensure_dossier(state)
    cand = None
    for c in state.get("candidates") or []:
        if c["id"] == candidate_id:
            cand = c
            c["status"] = "rejected"
            break
    if not cand:
        raise ValueError(f"unknown candidate: {candidate_id}")
    entry = {
        "candidate_id": candidate_id,
        "label": cand.get("label"),
        "reason": reason,
        "identifiers": cand.get("identifiers") or [],
        "rejected_at": utc_now(),
    }
    # dedupe
    state["rejected_candidates"] = [
        r for r in state["rejected_candidates"] if r.get("candidate_id") != candidate_id
    ]
    state["rejected_candidates"].append(entry)
    if candidate_id in (state.get("selected_branches") or []):
        state["selected_branches"] = [x for x in state["selected_branches"] if x != candidate_id]
    return entry


def add_hypothesis(
    state: dict[str, Any],
    text: str,
    dimension: str | None = None,
    from_clue: bool = True,
) -> dict[str, Any]:
    ensure_dossier(state)
    h = {
        "id": next_id(state["hypotheses"], "h"),
        "text": text.strip(),
        "dimension": dimension,
        "from_clue": from_clue,
        "status": "untested",  # untested | testing | confirmed | blank | rejected
        "methods": [],
        "notes": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    state["hypotheses"].append(h)
    return h


def resolve_hypothesis(
    state: dict[str, Any],
    hypothesis_id: str,
    status: str,
    method: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    ensure_dossier(state)
    if status not in ("untested", "testing", "confirmed", "blank", "rejected"):
        raise ValueError(f"bad hypothesis status: {status}")
    for h in state["hypotheses"]:
        if h["id"] == hypothesis_id:
            # Soft geo/year from clues blocked as confirmed without identity lock
            if (
                status == "confirmed"
                and h.get("from_clue")
                and h.get("dimension") in ("geo", "education")
                and not state.get("identity_lock", {}).get("locked")
            ):
                raise ValueError(
                    "cannot confirm clue-derived geo/education hypothesis before identity_lock; "
                    "record as blank or wait for lock"
                )
            h["status"] = status
            if method:
                h["methods"].append({"method": method, "at": utc_now()})
            if notes is not None:
                h["notes"] = notes
            h["updated_at"] = utc_now()
            # mirror into dimension
            if h.get("dimension") and status in ("blank", "confirmed", "rejected"):
                if status == "blank":
                    set_dimension(
                        state,
                        h["dimension"],
                        method=method or "hypothesis_resolve",
                        not_found=notes or h["text"],
                    )
                elif status == "confirmed":
                    set_dimension(
                        state,
                        h["dimension"],
                        fact=notes or h["text"],
                        method=method or "hypothesis_resolve",
                    )
            return h
    raise ValueError(f"unknown hypothesis: {hypothesis_id}")


def score_candidate_strength(state: dict[str, Any], cand: dict[str, Any]) -> float:
    """Higher = stronger node to expand from (not bare username noise)."""
    score = float(cand.get("score") or 0)
    eids = set(cand.get("evidence_ids") or [])
    tag_bonus = 0.0
    for e in state.get("evidence") or []:
        if e.get("id") not in eids:
            continue
        tags = set(e.get("tags") or [])
        if "collision" in tags or "rejected" in tags:
            tag_bonus -= 0.5
        if "primary_source" in tags or "best_member" in tags:
            tag_bonus += 0.4
        if e.get("type") == "profile" and e.get("source_name") not in ("fixture",):
            tag_bonus += 0.1
        if e.get("type") == "web_hit" and e.get("source_name") in ("websearch",):
            # generic search alone is weak expansion root
            tag_bonus -= 0.05
    # prefer more evidence
    tag_bonus += 0.05 * len(eids)
    return score + tag_bonus


def strongest_candidates(state: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    ensure_dossier(state)
    cands = [c for c in (state.get("candidates") or []) if c.get("status") != "rejected"]
    ranked = sorted(cands, key=lambda c: score_candidate_strength(state, c), reverse=True)
    out = []
    for c in ranked[:limit]:
        out.append(
            {
                "id": c["id"],
                "label": c.get("label"),
                "status": c.get("status"),
                "base_score": c.get("score"),
                "expand_score": round(score_candidate_strength(state, c), 3),
                "evidence_ids": c.get("evidence_ids"),
            }
        )
    return out


def next_actions(state: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    """Agent planner: clue plan P0 → identity → dimensions (not reverse-image first)."""
    ensure_dossier(state)
    actions: list[dict[str, Any]] = []
    lock = state.get("identity_lock") or {}
    selected = state.get("selected_branches") or []
    strong = strongest_candidates(state, limit=3)

    if not state.get("seeds"):
        actions.append(
            {
                "priority": 0,
                "action": "seed_add",
                "reason": "No seeds yet",
                "command_hint": "seed add name:… email:… username:…",
            }
        )
        return {"ok": True, "identity_locked": False, "actions": actions, "strongest": strong}

    # Clue analysis / plan first
    if not state.get("clue_analysis"):
        actions.append(
            {
                "priority": 0,
                "action": "plan",
                "reason": "No clue analysis yet — generate questions + source routing (PDDIKTI, primary page, tags)",
                "command_hint": "plan",
            }
        )

    # Execute planned P0 questions before generic websearch loops
    try:
        from .clue_analyze import collect_hints_from_plan

        for h in collect_hints_from_plan(state)[:5]:
            if h.get("priority", 9) <= 1:
                # rewrite hints: never default reverse-image
                hint = h.get("command_hint") or ""
                if "reverse-image" in hint.lower() or "reverse_image" in hint.lower():
                    hint = hint.replace("reverse-image", "bio/tags/links")
                h = dict(h)
                h["command_hint"] = hint
                actions.append(h)
    except Exception:
        pass

    # Open HITL gates block automation — surface first
    try:
        from .hitl import open_gates_summary

        for g in open_gates_summary(state)[:3]:
            actions.append(
                {
                    "priority": 0,
                    "action": "hitl_complete",
                    "reason": f"Open human-in-loop gate {g.get('id')} ({g.get('source')}): finish in real browser",
                    "command_hint": g.get("command_hint")
                    or f"hitl complete --gate {g.get('id')} --grade full_page --value '{{...}}'",
                    "alternatives": [
                        g.get("import_hint"),
                        g.get("cdp_hint"),
                        "collect --modules pddikti_api  # if PARSE_API_KEY set",
                    ],
                }
            )
    except Exception:
        pass

    if not state.get("evidence"):
        actions.append(
            {
                "priority": 0,
                "action": "collect",
                "dimension": "identity",
                "reason": "No evidence; run planned P0 modules (pddikti/websearch/primary_page) — not blind username enum",
                "command_hint": (
                    'collect --goal "P0: PDDIKTI + campus + primary org sources; bio/tags/links not reverse-image" '
                    "--modules pddikti,websearch"
                ),
            }
        )
        actions.append(
            {
                "priority": 1,
                "action": "collect_gov",
                "dimension": "risk",
                "reason": "Optional passive government pack (MA/AHU/LPSE/KPU dorks + portal probes)",
                "command_hint": 'collect --modules gov_id --goal "sources=putusan_ma,ahu,lpse,pddikti"',
            }
        )

    if state.get("evidence") and not state.get("candidates"):
        actions.append(
            {
                "priority": 0,
                "action": "differentiate",
                "reason": "Evidence exists but no candidates; cluster now",
                "command_hint": "differentiate",
            }
        )

    if state.get("candidates") and not selected and not lock.get("locked"):
        actions.append(
            {
                "priority": 0,
                "action": "select_strongest",
                "reason": "Select strongest non-collision candidate to expand (not every clue field)",
                "command_hint": f"select {strong[0]['id']}" if strong else "select c1",
                "strongest": strong[:1],
            }
        )

    if selected and not lock.get("locked"):
        actions.append(
            {
                "priority": 0,
                "action": "identity_lock_work",
                "dimension": "identity",
                "reason": "Before geo/year clue hypotheses: lock via bio/tags/peers/academic_record (image optional, not default)",
                "command_hint": (
                    'collect --goal "on-page bio, tags, mentions, outbound links, peer co-appearance; no reverse-image required" '
                    f"--modules primary_page,websearch; then identity-lock --candidate {selected[0]} "
                    "--signal bio_match --signal peer_coappearance --signal org_naming"
                ),
            }
        )

    # --- Unknown legal name: pattern hunt + anti-give-up (never ask operator for name) ---
    has_name_seed = any(
        s.get("type") == "name" and (s.get("normalized") or s.get("value") or "").strip()
        for s in (state.get("seeds") or [])
    )
    has_username_seed = any(s.get("type") == "username" for s in (state.get("seeds") or []))
    if has_username_seed and not has_name_seed:
        already_pattern = any(
            "name_pattern" in (e.get("tags") or []) for e in (state.get("evidence") or [])
        )
        if not already_pattern:
            actions.append(
                {
                    "priority": 0,
                    "action": "name_pattern_enum",
                    "dimension": "identity",
                    "reason": (
                        "Legal name blank: morph usernames → given-name hypotheses; "
                        "score via PDDIKTI/campus lists — NEVER ask operator for legal name"
                    ),
                    "command_hint": (
                        'collect --goal "name_pattern matrix from handles; not legal identity" '
                        "--modules name_pattern_enum,websearch"
                    ),
                    "forbidden": ["ask_operator_for_legal_name"],
                }
            )
        else:
            actions.append(
                {
                    "priority": 0,
                    "action": "cohort_list_pivot",
                    "dimension": "education",
                    "reason": (
                        "Pattern evidence exists but name still open: pivot EPT/distribusi/class lists "
                        "+ reverse peer×list + comment dig (anti give-up)"
                    ),
                    "command_hint": (
                        'collect --modules campus_list_ingest,websearch '
                        '--goal "path=/path/to/ept_extract.txt; peer co-tags; '
                        'do not close case; do not ask operator for legal name"'
                    ),
                    "forbidden": ["ask_operator_for_legal_name", "give_up_single_approach"],
                }
            )
            # if any tiktok video URL seed present, comment dig
            has_tt_video = any(
                s.get("type") == "url"
                and "/video/" in (s.get("normalized") or "")
                and "tiktok.com" in (s.get("normalized") or "").lower()
                for s in (state.get("seeds") or [])
            )
            if has_tt_video:
                actions.append(
                    {
                        "priority": 0,
                        "action": "tiktok_comment_dig",
                        "dimension": "network",
                        "reason": "TT video seed present: scrape public comments for named peers",
                        "command_hint": (
                            'collect --modules tiktok_comments --goal "max_pages=5"'
                        ),
                    }
                )

    # Dimension gaps (person dossier)
    dims = state["dossier"]["dimensions"]
    for dim_id in EXPAND_PRIORITY:
        dim = dims[dim_id]
        if dim["status"] in ("filled", "blank_after_methods"):
            continue
        if dim_id in ("geo", "family") and not lock.get("locked"):
            actions.append(
                {
                    "priority": 3,
                    "action": "defer_dimension",
                    "dimension": dim_id,
                    "reason": f"{dim_id} deferred until identity_lock (avoid clue-chasing on unlocked name)",
                    "command_hint": "identity-lock first; do not burn queries on bare place/year clues",
                }
            )
            continue
        if dim["status"] in ("empty", "partial", "blocked_need_identity_lock"):
            actions.append(
                {
                    "priority": 1 if dim_id in ("identity", "org_activity", "education", "digital", "network") else 2,
                    "action": "fill_dimension",
                    "dimension": dim_id,
                    "reason": f"Dimension {dim_id} is {dim['status']}",
                    "command_hint": (
                        f'collect --goal "background-check dimension:{dim_id} for selected subject only; '
                        f'primary sources and multi-event timeline; do not restate generic institution news" '
                        f"--modules websearch"
                    ),
                }
            )

    # Open questions
    for q in sorted(state.get("questions") or [], key=lambda x: (x.get("priority", 9), x["id"])):
        if q.get("status") != "open":
            continue
        actions.append(
            {
                "priority": int(q.get("priority", 2)),
                "action": "answer_question",
                "question_id": q["id"],
                "dimension": q.get("dimension"),
                "reason": q["text"],
                "command_hint": f"question set {q['id']} --status answered|blank --answer '…'",
            }
        )

    # Untested hypotheses — only after lock for soft ones
    for h in state.get("hypotheses") or []:
        if h.get("status") != "untested":
            continue
        if h.get("from_clue") and h.get("dimension") in ("geo", "education") and not lock.get("locked"):
            actions.append(
                {
                    "priority": 4,
                    "action": "defer_hypothesis",
                    "hypothesis_id": h["id"],
                    "reason": f"Clue hypothesis deferred until identity lock: {h['text']}",
                    "command_hint": "identity-lock first",
                }
            )
            continue
        actions.append(
            {
                "priority": 2,
                "action": "test_hypothesis",
                "hypothesis_id": h["id"],
                "dimension": h.get("dimension"),
                "reason": h["text"],
                "command_hint": f"hypothesis resolve {h['id']} --status blank|confirmed|rejected --method '…' --notes '…'",
            }
        )

    # escalate if selected and identity partial
    if selected and lock.get("locked"):
        actions.append(
            {
                "priority": 1,
                "action": "escalate_and_collect",
                "reason": "Expand graph from locked identity only",
                "command_hint": "escalate --goal 'new seeds from locked cluster only'; collect --goal 'peers tags archives multi-event'",
            }
        )

    actions.sort(key=lambda a: (a.get("priority", 9), a.get("action", "")))
    # de-dupe similar dimension fills; strip any "ask legal name" anti-patterns
    _ask_name_re = re.compile(
        r"ask\s+(operator|user|human).{0,40}(legal\s+)?name|"
        r"minta\s+nama\s+(legal|lengkap)|"
        r"operator\s+give\s+(full\s+)?name|"
        r"paste\s+(full\s+)?(legal\s+)?name",
        re.I,
    )
    seen_keys = set()
    deduped = []
    for a in actions:
        blob = f"{a.get('action', '')} {a.get('reason', '')} {a.get('command_hint', '')}"
        if _ask_name_re.search(blob):
            continue  # hard ban: never surface ask-name as next action
        key = (a.get("action"), a.get("dimension"), a.get("question_id"), a.get("hypothesis_id"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(a)
    workflow = dict((state.get("scope") or {}).get("workflow") or {})
    workflow.setdefault("ban_ask_operator_for_legal_name", True)
    workflow.setdefault("anti_give_up_cohort_pivot", True)
    return {
        "ok": True,
        "identity_locked": bool(lock.get("locked")),
        "selected_branches": selected,
        "strongest": strong,
        "actions": deduped[:limit],
        "policy": workflow,
    }


def build_dossier_report(state: dict[str, Any]) -> dict[str, Any]:
    """Machine-readable person dossier (background check), not a methods essay."""
    ensure_dossier(state)
    lock = state.get("identity_lock") or {}
    selected = state.get("selected_branches") or []
    subject = None
    if lock.get("candidate_id"):
        for c in state.get("candidates") or []:
            if c["id"] == lock["candidate_id"]:
                subject = c
                break
    if not subject and selected:
        for c in state.get("candidates") or []:
            if c["id"] == selected[0]:
                subject = c
                break

    dims_out = {}
    for dim_id, dim in state["dossier"]["dimensions"].items():
        dims_out[dim_id] = {
            "label": dim["label"],
            "status": dim["status"],
            "facts": dim.get("facts") or [],
            "inferences": dim.get("inferences") or [],
            "methods_tried": dim.get("methods_tried") or [],
            "not_found": dim.get("not_found_notes") or [],
            "evidence_ids": dim.get("evidence_ids") or [],
        }

    open_q = [q for q in state.get("questions") or [] if q.get("status") == "open"]
    answered_q = [q for q in state.get("questions") or [] if q.get("status") != "open"]

    digital = lock.get("digital") or {}
    civil = lock.get("civil") or {}
    return {
        "schema": "background_check_dossier_v1",
        "investigation_id": state.get("investigation_id"),
        "generated_at": utc_now(),
        "subject": {
            "candidate_id": (subject or {}).get("id"),
            "label": (subject or {}).get("label"),
            "identifiers": (subject or {}).get("identifiers") or [],
            "identity_locked": bool(lock.get("locked")),
            "digital_locked": bool(digital.get("locked")),
            "civil_locked": bool(civil.get("locked")),
            "civil_open": not bool(civil.get("locked")),
            "lock_signals": lock.get("signals") or [],
            "digital_signals": digital.get("signals") or [],
            "civil_signals": civil.get("signals") or [],
            "summary": state["dossier"].get("subject_summary"),
            "lock_note": (
                "digital lock ≠ civil name+NIM; civil_open=true means legal ID still unknown"
                if bool(digital.get("locked")) and not bool(civil.get("locked"))
                else None
            ),
        },
        "dimensions": dims_out,
        "timeline": state["dossier"].get("timeline") or [],
        "collisions_rejected": state.get("rejected_candidates") or [],
        "hypotheses": state.get("hypotheses") or [],
        "questions": {"open": open_q, "closed": answered_q},
        "seeds_note": "Seeds/clues are intake only; they are not completion criteria.",
        "counts": {
            "evidence": len(state.get("evidence") or []),
            "candidates": len(state.get("candidates") or []),
            "timeline_events": len(state["dossier"].get("timeline") or []),
        },
    }


def render_dossier_markdown(state: dict[str, Any]) -> str:
    """Human-readable background-check report focused on the person."""
    d = build_dossier_report(state)
    lines: list[str] = []
    lines.append("# Background check dossier (public OSINT)")
    lines.append("")
    lines.append(f"- Generated: {d['generated_at']}")
    lines.append(f"- Investigation: {d['investigation_id']}")
    sub = d["subject"]
    lines.append("")
    lines.append("## Subject")
    lines.append(f"- Candidate: `{sub.get('candidate_id')}` — {sub.get('label')}")
    lines.append(f"- Identity locked: **{sub.get('identity_locked')}**")
    if sub.get("lock_signals"):
        lines.append(f"- Lock signals: {', '.join(sub['lock_signals'])}")
    if sub.get("identifiers"):
        lines.append("- Identifiers:")
        for i in sub["identifiers"]:
            lines.append(f"  - {i}")
    if sub.get("summary"):
        lines.append(f"- Summary: {sub['summary']}")
    lines.append("")
    lines.append("## Life dimensions")
    for dim_id in EXPAND_PRIORITY:
        dim = d["dimensions"].get(dim_id) or {}
        lines.append(f"### {dim.get('label', dim_id)} (`{dim_id}`) — *{dim.get('status')}*")
        facts = dim.get("facts") or []
        if facts:
            lines.append("**Facts**")
            for f in facts:
                lines.append(f"- {f.get('text')}")
        infs = dim.get("inferences") or []
        if infs:
            lines.append("**Inferences**")
            for inf in infs:
                conf = inf.get("confidence")
                conf_s = f" (confidence {conf})" if conf is not None else ""
                lines.append(f"- {inf.get('text')}{conf_s}")
        nf = dim.get("not_found") or []
        if nf:
            lines.append("**Not found (after methods)**")
            for n in nf:
                lines.append(f"- {n.get('text')}")
        methods = dim.get("methods_tried") or []
        if methods:
            lines.append("**Methods tried**")
            for m in methods:
                lines.append(f"- {m.get('method')}")
        if not facts and not infs and not nf:
            lines.append("- _(empty — use `next` planner; do not pad with generic institution news)_")
        lines.append("")
    lines.append("## Timeline")
    if not d["timeline"]:
        lines.append("- _(no dated events yet)_")
    else:
        for t in d["timeline"]:
            lines.append(f"- `{t.get('date') or 'undated'}` — {t.get('summary')} [{t.get('dimension')}]")
    lines.append("")
    lines.append("## Rejected collisions")
    if not d["collisions_rejected"]:
        lines.append("- _(none recorded)_")
    else:
        for r in d["collisions_rejected"]:
            lines.append(f"- `{r.get('candidate_id')}` {r.get('label')}: {r.get('reason')}")
    lines.append("")
    lines.append("## Hypotheses (clues are not goals)")
    for h in d["hypotheses"]:
        lines.append(f"- `{h.get('id')}` [{h.get('status')}] {h.get('text')}")
    lines.append("")
    lines.append("## Open questions")
    for q in d["questions"]["open"]:
        lines.append(f"- `{q.get('id')}` (p{q.get('priority')}) {q.get('text')}")
    if not d["questions"]["open"]:
        lines.append("- _(none)_")
    lines.append("")
    lines.append("---")
    lines.append(
        "_This report is a person dossier. Process postmortems and tool metrics belong in a separate appendix._"
    )
    lines.append("")
    return "\n".join(lines)


def auto_tag_evidence_to_dimensions(state: dict[str, Any]) -> dict[str, Any]:
    """Lightweight heuristic mapping of evidence into dossier dimensions (suggestions only)."""
    ensure_dossier(state)
    mapped = 0
    for e in state.get("evidence") or []:
        tags = set(e.get("tags") or [])
        et = e.get("type")
        dim = None
        if "collision" in tags or "rejected" in tags:
            continue
        if et == "profile" or "derived_username" in tags:
            dim = "digital"
        elif et in ("phone_meta", "phone_link", "phone_hitl_plan") or "phone_footprint" in tags:
            dim = "digital"
        elif "cimsa" in tags or "best_member" in tags or "org" in tags:
            dim = "org_activity"
        elif et == "registration":
            dim = "digital"
        elif et == "web_hit" and "phone_footprint" in tags:
            dim = "digital"
        elif "geo" in tags:
            dim = "geo"
        elif "institution" in tags or "2025_intake" in tags:
            # generic institution — do NOT promote to education fact
            continue
        elif et == "web_hit":
            val = e.get("value") or {}
            title = (val.get("title") or "").lower() if isinstance(val, dict) else ""
            if any(k in title for k in ("linkedin", "kerja", "pt ", "intern")):
                dim = "work"
            elif any(k in title for k in ("sma", "universitas", "fakultas", "mahasiswa", "angkatan")):
                dim = "education"
            elif any(k in title for k in ("award", "best member", "juara", "lomba")):
                dim = "notable"
        if not dim:
            continue
        eid = e["id"]
        dref = state["dossier"]["dimensions"][dim]
        if eid not in dref["evidence_ids"]:
            dref["evidence_ids"].append(eid)
            if dref["status"] == "empty":
                dref["status"] = "partial"
            dref["updated_at"] = utc_now()
            mapped += 1
    return {"mapped_links": mapped}
