"""Clue → questions → source plan (needle-in-haystack reasoning).

Implements OSINT_CLUE_REASONING_FRAMEWORK.md §2–7:
- Classify seeds (hard_id / soft_context / org_event)
- Generate prioritized investigation questions
- Route to sources (PDDIKTI, primary page, tags/bio, student email, …)
- Explicit do_not list (no generic institution essay, no blind enum, image non-default)
"""

from __future__ import annotations

import re
from typing import Any

from .state import next_id, utc_now


# --- institution / Indonesia helpers -----------------------------------------

_INSTITUTION_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (
        re.compile(r"\bfk\s*unri\b|\bfakultas\s+kedokteran\s+universitas\s+riau\b", re.I),
        {
            "label": "Fakultas Kedokteran Universitas Riau",
            "pt_short": "UNRI",
            "student_email_domain": "student.unri.ac.id",
            "campus_hosts": "unri.ac.id,fk.unri.ac.id",
        },
    ),
    (
        re.compile(r"\bunri\b|universitas\s+riau", re.I),
        {
            "label": "Universitas Riau",
            "pt_short": "UNRI",
            "student_email_domain": "student.unri.ac.id",
            "campus_hosts": "unri.ac.id",
        },
    ),
    (
        re.compile(r"\bfk\b|fakultas\s+kedokteran|kedokteran", re.I),
        {
            "label": "Fakultas Kedokteran (generic)",
            "pt_short": "",
            "student_email_domain": "",
            "campus_hosts": "",
        },
    ),
]

_ORG_PATTERNS = re.compile(
    r"\bcimsa\b|\bbem\b|\bhmj\b|\bukm\b|\bscora\b|\bscope\b|\bscoph\b|best\s*member|mahasiswa",
    re.I,
)

_GEO_PATTERNS = re.compile(
    r"simalungun|perdagangan|sumatera\s*utara|\bsumut\b|medan|pekanbaru|bandar\b",
    re.I,
)

_YEAR_PATTERNS = re.compile(
    r"\b(20\d{2})\b|angkatan|maba|mahasiswa\s+baru|masuk\s+tahun|cohort",
    re.I,
)

_DO_NOT = [
    "generic_institution_news_as_person_fact",
    "geo_admin_essay_as_investigation_goal",
    "blind_username_enum_before_handle_candidate",
    "reverse_image_as_default_gate",
    "restate_same_caption_as_new_depth",
    "confirm_soft_geo_year_before_identity_lock",
    "ask_operator_for_legal_name",  # P0 fatal: OSINT must derive name patterns, not request the unknown
    "give_up_after_single_blank_path",  # blank PDDIKTI/pattern → pivot EPT/cohort/comments
    "treat_socmed_nick_as_legal_given_name",  # nick is hypothesis family only
    "phone_breach_bot_nik_address",  # no dark/leak bots for NIK/home
    "phone_ewallet_name_as_civil_lock",  # wallet preview = candidate only
    "phone_prefix_as_domicile",  # carrier prefix ≠ alamat
]


def _role_for_seed(seed: dict[str, Any]) -> str:
    t = (seed.get("type") or "").lower()
    v = seed.get("normalized") or seed.get("value") or ""
    if t in ("email", "phone"):
        return "hard_id"
    if t == "username":
        return "hard_id"
    if t == "url":
        return "org_event" if _ORG_PATTERNS.search(v) else "soft_context"
    if t == "name":
        return "soft_context"
    if _ORG_PATTERNS.search(v):
        return "org_event"
    if t in ("other", "name") and _INSTITUTION_PATTERNS[0][0].search(v):
        return "soft_context"
    return "soft_context"


def _refine_clue_type(seed: dict[str, Any]) -> str:
    """Map seed to analyzer types: name|email|phone|username|org|institution|geo|year_cohort|event|url|other."""
    t = (seed.get("type") or "other").lower()
    v = seed.get("normalized") or seed.get("value") or ""
    if t in ("email", "phone", "username", "url", "name"):
        return t
    if _YEAR_PATTERNS.search(v) and (
        re.search(r"20\d{2}|angkatan|maba|masuk", v, re.I)
    ):
        # year alone or with masuk
        if re.search(r"20\d{2}", v) or re.search(r"angkatan|maba|masuk", v, re.I):
            if not _GEO_PATTERNS.search(v) or re.search(r"20\d{2}|angkatan|maba|masuk", v, re.I):
                if re.search(r"20\d{2}|angkatan|maba|masuk", v, re.I) and not (
                    _GEO_PATTERNS.search(v) and not re.search(r"20\d{2}|angkatan|maba|masuk", v, re.I)
                ):
                    pass
        if re.search(r"\b(20\d{2}|angkatan|maba|mahasiswa\s+baru|masuk)\b", v, re.I):
            # prefer year if that's the main signal
            if re.search(r"masuk|angkatan|maba|20\d{2}", v, re.I) and not _ORG_PATTERNS.search(v):
                if not re.search(r"universitas|fakultas|fk\s|unri", v, re.I) or re.search(
                    r"masuk|angkatan|maba", v, re.I
                ):
                    if re.search(r"^\s*(masuk\s+)?20\d{2}\s*$", v, re.I) or re.search(
                        r"masuk\s+20\d{2}|angkatan|maba", v, re.I
                    ):
                        return "year_cohort"
    if _GEO_PATTERNS.search(v) and not re.search(r"universitas|fakultas|fk\s|cimsa", v, re.I):
        return "geo"
    if re.search(r"universitas|fakultas|\bfk\b|\bunri\b|kedokteran", v, re.I):
        return "institution"
    if _ORG_PATTERNS.search(v):
        return "org" if not re.search(r"best\s*member|event|lomba", v, re.I) else "event"
    if re.search(r"best\s*member|lomba|juara|open\s*recruit", v, re.I):
        return "event"
    if re.search(r"\b(20\d{2}|angkatan|maba|masuk)\b", v, re.I):
        return "year_cohort"
    if _GEO_PATTERNS.search(v):
        return "geo"
    return t if t != "other" else "other"


def _detect_institutions(seeds: list[dict[str, Any]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in seeds:
        v = s.get("normalized") or s.get("value") or ""
        for pat, meta in _INSTITUTION_PATTERNS:
            if pat.search(v):
                key = meta.get("pt_short") or meta.get("label") or v
                if key not in seen and meta.get("label"):
                    # skip pure generic kedokteran if we already have UNRI
                    if meta["label"].startswith("Fakultas Kedokteran (generic)") and any(
                        x.get("pt_short") == "UNRI" for x in found
                    ):
                        continue
                    seen.add(key)
                    found.append(dict(meta))
    return found


def _name_seeds(seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in seeds if (s.get("type") or "").lower() == "name" or _refine_clue_type(s) == "name"]


def _q(
    text: str,
    *,
    priority: int,
    dimension: str | None,
    from_clue_ids: list[str],
    sources: list[str],
    queries: list[str],
    modules: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "priority": priority,
        "dimension": dimension,
        "from_clue_ids": from_clue_ids,
        "suggested_sources": sources,
        "suggested_queries": queries,
        "suggested_modules": modules or [],
        "status": "open",
    }


def analyze_clues(state: dict[str, Any]) -> dict[str, Any]:
    """Pure analysis from current seeds (does not mutate state)."""
    seeds = list(state.get("seeds") or [])
    clues_out: list[dict[str, Any]] = []
    for s in seeds:
        refined = _refine_clue_type(s)
        clues_out.append(
            {
                "id": s.get("id"),
                "type": s.get("type"),
                "refined_type": refined,
                "normalized": s.get("normalized") or s.get("value"),
                "role": _role_for_seed(s),
                "value": s.get("value"),
            }
        )

    institutions = _detect_institutions(seeds)
    names = _name_seeds(seeds)
    name_ids = [n["id"] for n in names]
    name_strs = [n.get("normalized") or n.get("value") or "" for n in names]
    primary_name = name_strs[0] if name_strs else None

    has_org = any(c["refined_type"] in ("org", "event") or c["role"] == "org_event" for c in clues_out)
    has_geo = any(c["refined_type"] == "geo" for c in clues_out)
    has_year = any(c["refined_type"] == "year_cohort" for c in clues_out)
    has_institution = bool(institutions) or any(c["refined_type"] == "institution" for c in clues_out)
    has_hard = any(c["role"] == "hard_id" for c in clues_out)
    has_username = any(c["refined_type"] == "username" or c["type"] == "username" for c in clues_out)
    has_email = any(c["type"] == "email" for c in clues_out)
    has_phone = any(c["type"] == "phone" or c["refined_type"] == "phone" for c in clues_out)
    has_url = any(c["type"] == "url" or c["refined_type"] == "url" for c in clues_out)

    org_ids = [c["id"] for c in clues_out if c["refined_type"] in ("org", "event") or c["role"] == "org_event"]
    inst_ids = [c["id"] for c in clues_out if c["refined_type"] == "institution"]
    geo_ids = [c["id"] for c in clues_out if c["refined_type"] == "geo"]
    year_ids = [c["id"] for c in clues_out if c["refined_type"] == "year_cohort"]

    questions: list[dict[str, Any]] = []

    # --- P0: academic / PDDIKTI when name + Indonesia campus signal ---
    if primary_name and (has_institution or has_org):
        pt = institutions[0]["pt_short"] if institutions else ""
        pt_label = institutions[0]["label"] if institutions else "perguruan tinggi terkait"
        questions.append(
            _q(
                f"Apakah '{primary_name}' muncul di PDDIKTI / indeks mahasiswa publik"
                + (f" terkait {pt_label}?" if pt_label else "?"),
                priority=0,
                dimension="education",
                from_clue_ids=name_ids + inst_ids,
                sources=["pddikti", "academic_search"],
                queries=[
                    f'{primary_name} site:pddikti.kemdikbud.go.id',
                    f'{primary_name} PDDIKTI' + (f" {pt}" if pt else ""),
                    f'{primary_name}' + (f" {pt_label}" if pt_label else ""),
                ],
                modules=["pddikti", "websearch"],
            )
        )
        questions.append(
            _q(
                f"Ada jejak nama di situs kampus/FK (bukan berita generik penerimaan maba)?",
                priority=0,
                dimension="education",
                from_clue_ids=name_ids + inst_ids,
                sources=["campus_web", "websearch"],
                queries=[
                    f'"{primary_name}"' + (
                        f' site:{institutions[0]["campus_hosts"].split(",")[0]}'
                        if institutions and institutions[0].get("campus_hosts")
                        else " site:unri.ac.id"
                    ),
                    f'"{primary_name}" filetype:pdf' + (f" {pt}" if pt else " kedokteran"),
                ],
                modules=["websearch"],
            )
        )

    if primary_name and institutions and institutions[0].get("student_email_domain"):
        domain = institutions[0]["student_email_domain"]
        local_guesses = _email_local_guesses(primary_name)
        questions.append(
            _q(
                f"Ada email kampus publik @{domain} atau pattern nama untuk {primary_name}?",
                priority=0,
                dimension="digital",
                from_clue_ids=name_ids + inst_ids,
                sources=["student_email_dork", "websearch", "email_reg"],
                queries=[f'"{g}@{domain}"' for g in local_guesses[:4]]
                + [f'"{primary_name}" "@{domain}"'],
                modules=["websearch", "email_reg"],
            )
        )

    # --- P0: org / event primary page + tags ---
    if has_org or any("cimsa" in (c.get("normalized") or "").lower() for c in clues_out):
        org_label = next(
            (
                c["normalized"]
                for c in clues_out
                if c["refined_type"] in ("org", "event") or "cimsa" in (c.get("normalized") or "").lower()
            ),
            "org mahasiswa",
        )
        questions.append(
            _q(
                f"Primary source untuk {org_label} + nama: caption penuh, URL, dan **tags/mentions** (bukan SERP saja)?",
                priority=0,
                dimension="org_activity",
                from_clue_ids=org_ids + name_ids,
                sources=["primary_page", "social_tags", "websearch"],
                queries=[
                    f'"{primary_name}" {org_label}' if primary_name else org_label,
                    f'"{primary_name}" CIMSA' if primary_name else "CIMSA",
                ],
                modules=["websearch", "primary_page"],
            )
        )
        questions.append(
            _q(
                "Siapa yang di-tag/mention bersama subjek di post org? (peer pivot tanpa reverse-image)",
                priority=0,
                dimension="network",
                from_clue_ids=org_ids + name_ids,
                sources=["social_tags", "primary_page"],
                queries=[],
                modules=["primary_page"],
            )
        )

    if has_url:
        for c in clues_out:
            if c["refined_type"] == "url" or c.get("type") == "url":
                questions.append(
                    _q(
                        f"Parse primary page on-page signals: {c['normalized']}",
                        priority=0,
                        dimension="identity",
                        from_clue_ids=[c["id"]],
                        sources=["primary_page"],
                        queries=[c["normalized"]],
                        modules=["primary_page"],
                    )
                )

    # --- P0: collision ---
    if primary_name:
        questions.append(
            _q(
                f"Collision map: profil publik lain bernama mirip '{primary_name}' yang harus di-reject?",
                priority=0,
                dimension="identity",
                from_clue_ids=name_ids,
                sources=["websearch"],
                queries=[
                    f'"{primary_name}" LinkedIn',
                    f'"{primary_name}" -CIMSA' if has_org else f'"{primary_name}"',
                ],
                modules=["websearch"],
            )
        )

    # --- hard ids present ---
    if has_username:
        questions.append(
            _q(
                "Username yang sudah ada: enum lintas platform + parse bio/link (bukan spekulasi nama)?",
                priority=0,
                dimension="digital",
                from_clue_ids=[c["id"] for c in clues_out if c["type"] == "username"],
                sources=["username_enum", "primary_page"],
                queries=[],
                modules=["username_enum", "primary_page"],
            )
        )
        # Unknown legal name: morphology → pattern matrix BEFORE any "ask operator for name"
        if not primary_name:
            try:
                from .name_pattern import patterns_from_state

                matrix = patterns_from_state({"seeds": seeds, "evidence": []})
                hyps = [g["token"] for g in matrix.get("given_name_hypotheses") or []]
                q_queries = list(matrix.get("sample_queries") or [])[:12]
            except Exception:
                hyps = []
                q_queries = []
            user_ids = [c["id"] for c in clues_out if c["type"] == "username"]
            questions.append(
                _q(
                    "Legal name blank: jalankan name_pattern_enum dari username/display "
                    f"(hipotesis: {', '.join(hyps[:8]) or 'morphology'}) — "
                    "bukan minta nama ke operator; score vs PDDIKTI/EPT/campus PDF",
                    priority=0,
                    dimension="identity",
                    from_clue_ids=user_ids,
                    sources=["name_pattern_enum", "pddikti", "campus_web", "websearch"],
                    queries=q_queries
                    or [
                        f'"{h}" UNRI' for h in hyps[:4]
                    ],
                    modules=["name_pattern_enum", "websearch", "pddikti"],
                )
            )
            if has_institution or has_year:
                questions.append(
                    _q(
                        "Pivot cohort: daftar EPT/distribusi maba/kelas prodi (NIM map) — "
                        "grep Cel*/Cec* dan reverse peer×list; jangan tutup kasus karena pattern blank",
                        priority=0,
                        dimension="education",
                        from_clue_ids=user_ids + inst_ids + year_ids,
                        sources=["campus_web", "websearch"],
                        queries=[
                            "Jadwal Pretest EPT TOEFL Prediction Mahasiswa Baru Angkatan UNRI",
                            "Daftar Distribusi Mahasiswa Baru UNRI Ilmu Komunikasi",
                            "pembagian kelas angkatan Komunikasi UNRI",
                        ],
                        modules=["websearch"],
                    )
                )
                questions.append(
                    _q(
                        "Comment/network dig: video/post viral subject — scrape komentar publik "
                        "untuk peer bernama → match EPT (bukan face default)",
                        priority=1,
                        dimension="network",
                        from_clue_ids=user_ids,
                        sources=["primary_page", "social_tags", "websearch"],
                        queries=[],
                        modules=["primary_page", "websearch"],
                    )
                )
    if has_email:
        questions.append(
            _q(
                "Email seed: registrasi layanan publik + breach index legal?",
                priority=0,
                dimension="digital",
                from_clue_ids=[c["id"] for c in clues_out if c["type"] == "email"],
                sources=["email_reg", "websearch"],
                queries=[],
                modules=["email_reg", "websearch"],
            )
        )

    # --- P0: phone as hard pivot clue (Layer A public + HITL checklist) ---
    if has_phone:
        phone_seeds = [s for s in seeds if (s.get("type") or "").lower() == "phone"]
        try:
            from .phone_pivot import phone_plan_questions

            for ps in phone_seeds:
                for pq in phone_plan_questions(ps):
                    questions.append(
                        _q(
                            pq["text"],
                            priority=int(pq.get("priority") or 0),
                            dimension=pq.get("dimension"),
                            from_clue_ids=list(pq.get("from_clue_ids") or []),
                            sources=list(pq.get("suggested_sources") or []),
                            queries=list(pq.get("suggested_queries") or []),
                            modules=list(pq.get("suggested_modules") or []),
                        )
                    )
        except Exception:
            phone_ids = [c["id"] for c in clues_out if c["type"] == "phone"]
            questions.append(
                _q(
                    "Phone seed: footprint publik (SERP variants, wa.me) — no breach/NIK",
                    priority=0,
                    dimension="digital",
                    from_clue_ids=phone_ids,
                    sources=["phone_footprint", "websearch"],
                    queries=[],
                    modules=["phone_footprint", "websearch"],
                )
            )

    # --- P1: multi-event, bio lock ---
    if primary_name and (has_org or has_institution):
        questions.append(
            _q(
                "Apakah ada multi-event aktivitas (timeline), bukan satu caption award saja?",
                priority=1,
                dimension="org_activity",
                from_clue_ids=name_ids + org_ids,
                sources=["websearch", "primary_page"],
                queries=[f'"{primary_name}" (CIMSA OR BEM OR panitia OR angkatan)']
                if primary_name
                else [],
                modules=["websearch"],
            )
        )
        questions.append(
            _q(
                "Identity multi-signal tanpa reverse-image: bio kampus, link-in-bio, co-tag berulang?",
                priority=1,
                dimension="identity",
                from_clue_ids=name_ids,
                sources=["primary_page", "social_graph_light"],
                queries=[],
                modules=["primary_page"],
            )
        )

    # --- P2 soft hypotheses (still generate questions; execution deferred by next/lock) ---
    if has_year and primary_name:
        questions.append(
            _q(
                "Hipotesis tahun/angkatan dari clue: terbukti di record/public list, atau blank setelah method?",
                priority=2,
                dimension="education",
                from_clue_ids=year_ids + name_ids,
                sources=["pddikti", "websearch"],
                queries=[f'"{primary_name}" (angkatan OR MABA OR 2025 OR 2024 OR 2026)']
                if primary_name
                else [],
                modules=["pddikti", "websearch"],
            )
        )
    if has_geo and primary_name:
        questions.append(
            _q(
                "Hipotesis asal geo dari clue: ada tautan orang↔tempat (bio/alumni/lomba), bukan admin-map?",
                priority=3,
                dimension="geo",
                from_clue_ids=geo_ids + name_ids,
                sources=["websearch"],
                queries=[
                    f'"{primary_name}" (Simalungun OR Perdagangan OR Bandar OR Sumut)'
                ]
                if primary_name
                else [],
                modules=["websearch"],
            )
        )

    # dedupe by text
    seen_t: set[str] = set()
    uniq_q: list[dict[str, Any]] = []
    for q in questions:
        key = q["text"].strip().lower()
        if key in seen_t:
            continue
        seen_t.add(key)
        uniq_q.append(q)
    questions = sorted(uniq_q, key=lambda x: (x["priority"], x["text"]))

    # source plan
    source_plan: list[dict[str, Any]] = []
    source_order = [
        ("pddikti", "Academic public index for Indonesian students"),
        ("pddikti_api", "Optional Parse.bot wrapper if PARSE_API_KEY set (third-party)"),
        ("hitl", "Real-browser complete when Cloudflare/captcha blocks automation"),
        ("gov_id", "Passive ID gov pack: MA putusan, AHU, LPSE, KPU dorks — no IDOR"),
        ("campus_web", "Campus/faculty pages and PDFs — not generic admissions news"),
        ("primary_page", "On-page caption, outbound links, mention/tag patterns"),
        ("social_tags", "Peer pivots from tags/mentions — prefer over reverse-image"),
        ("student_email_dork", "Public campus email patterns"),
        ("username_enum", "Only after handle candidate exists"),
        ("name_pattern_enum", "When legal name blank: morph usernames → given-name hypotheses for PDDIKTI/list score"),
        ("email_reg", "Only when email candidate exists"),
        ("phone_footprint", "Phone clue Layer A: E.164 normalize, prefix soft, SERP variants, wa.me — no breach"),
        ("phone_hitl", "Layer B checklist only: wallet preview / WA / contact-sync lab"),
        ("websearch", "Directed queries from question pack — not blind name loops"),
        ("browser_cdp", "Cyborg attach to operator Chrome after human unlock"),
    ]
    needed = set()
    for q in questions:
        needed.update(q.get("suggested_sources") or [])
    if primary_name and has_institution:
        needed.update(["pddikti", "hitl", "pddikti_api"])
    if primary_name:
        needed.add("gov_id")
    if has_username and not primary_name:
        needed.add("name_pattern_enum")
    if has_phone:
        needed.update(["phone_footprint", "phone_hitl", "websearch"])
    for src, why in source_order:
        if src in needed or (src == "pddikti" and primary_name and has_institution):
            source_plan.append(
                {
                    "source": src,
                    "why": why,
                    "priority": 0
                    if src
                    in (
                        "pddikti",
                        "pddikti_api",
                        "hitl",
                        "primary_page",
                        "campus_web",
                        "social_tags",
                        "student_email_dork",
                        "phone_footprint",
                    )
                    else 1,
                }
            )

    # Attach gov catalog slice for agents (ID only by default)
    try:
        from .gov_sources import GOV_POLICY, catalog_for_plan

        gov_catalog = catalog_for_plan(include_global=False)
    except Exception:
        gov_catalog = []
        GOV_POLICY = {"mode": "passive_public"}

    handle_candidates = [
        c["normalized"]
        for c in clues_out
        if c.get("type") == "username" or c.get("refined_type") == "username"
    ]

    return {
        "schema": "clue_analysis_v1",
        "analyzed_at": utc_now(),
        "clues": clues_out,
        "institutions_detected": institutions,
        "handle_candidates": handle_candidates,
        "questions": questions,
        "source_plan": source_plan,
        "gov_catalog": gov_catalog,
        "gov_policy": GOV_POLICY,
        "do_not": list(_DO_NOT)
        + [
            "IDOR / sequential ID brute-force on .go.id profile URLs",
            "Captcha solving services or headless captcha farms",
            "admin.ahu or other undocumented grey-area government APIs",
            "Mass NIK harvesting as an investigation product goal",
        ],
        "policy": {
            "reverse_image_default": False,
            "prefer_bio_tags_connections": True,
            "require_identity_lock_before_soft_geo_year_confirm": True,
            "blind_username_enum_ok": bool(handle_candidates),
            "gov_sources_passive_only": True,
            "hitl_on_challenge_wall": True,
            "ban_ask_operator_for_legal_name": True,
            "name_pattern_before_pddikti_when_name_blank": bool(has_username and not primary_name),
            "anti_give_up_pivot_cohort_lists": True,
        },
        "summary": {
            "clue_count": len(clues_out),
            "question_count": len(questions),
            "p0_questions": sum(1 for q in questions if q["priority"] == 0),
            "has_academic_route": any(
                "pddikti" in (q.get("suggested_sources") or []) for q in questions
            ),
            "has_primary_org_route": any(
                "primary_page" in (q.get("suggested_sources") or [])
                or "social_tags" in (q.get("suggested_sources") or [])
                for q in questions
            ),
            "has_gov_route": bool(primary_name),
            "legal_name_blank": not bool(primary_name),
            "has_name_pattern_route": any(
                "name_pattern" in (q.get("suggested_sources") or [])
                or "name_pattern_enum" in (q.get("suggested_modules") or [])
                for q in questions
            ),
            "has_phone_route": bool(has_phone),
        },
        "policy_phone": {
            "layer_a_default": "phone_footprint",
            "layer_b_hitl_only": True,
            "forbid_breach_nik": True,
            "ewallet_name_is_candidate_only": True,
        },
    }


def _email_local_guesses(full_name: str) -> list[str]:
    parts = re.findall(r"[a-z0-9]+", full_name.lower())
    if not parts:
        return []
    guesses = []
    if len(parts) >= 2:
        guesses += [
            f"{parts[0]}.{parts[-1]}",
            f"{parts[0]}{parts[-1]}",
            f"{parts[0]}_{parts[-1]}",
            f"{parts[0][0]}{parts[-1]}",
        ]
    guesses.append(parts[0])
    # unique
    out: list[str] = []
    for g in guesses:
        if g not in out:
            out.append(g)
    return out


def apply_analysis_to_state(
    state: dict[str, Any],
    analysis: dict[str, Any] | None = None,
    *,
    merge_questions: bool = True,
) -> dict[str, Any]:
    """Persist analysis on state; optionally merge generated questions into state.questions."""
    from .dossier import ensure_dossier, add_question

    ensure_dossier(state)
    analysis = analysis or analyze_clues(state)
    state["clue_analysis"] = analysis

    if merge_questions:
        existing_texts = {
            (q.get("text") or "").strip().lower() for q in state.get("questions") or []
        }
        added = []
        for q in analysis.get("questions") or []:
            text = (q.get("text") or "").strip()
            if not text or text.lower() in existing_texts:
                continue
            row = add_question(
                state,
                text,
                dimension=q.get("dimension"),
                priority=int(q.get("priority", 2)),
                origin="clue_analyze",
            )
            # attach routing metadata
            row["suggested_sources"] = q.get("suggested_sources") or []
            row["suggested_queries"] = q.get("suggested_queries") or []
            row["suggested_modules"] = q.get("suggested_modules") or []
            row["from_clue_ids"] = q.get("from_clue_ids") or []
            existing_texts.add(text.lower())
            added.append(row["id"])
        analysis["questions_merged_ids"] = added

    return analysis


def collect_hints_from_plan(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten open P0/P1 planned questions into collect action hints for `next`."""
    analysis = state.get("clue_analysis") or analyze_clues(state)
    hints = []
    for q in analysis.get("questions") or []:
        if q.get("status") not in (None, "open"):
            continue
        mods = q.get("suggested_modules") or ["websearch"]
        queries = q.get("suggested_queries") or []
        goal = q["text"]
        if queries:
            goal = f"{q['text']} | queries: {'; '.join(queries[:3])}"
        hints.append(
            {
                "priority": q.get("priority", 2),
                "action": "execute_planned_question",
                "dimension": q.get("dimension"),
                "reason": q["text"],
                "command_hint": (
                    f'collect --goal "{goal[:180]}" --modules {",".join(mods)}'
                ),
                "suggested_modules": mods,
                "suggested_queries": queries,
                "suggested_sources": q.get("suggested_sources") or [],
            }
        )
    hints.sort(key=lambda x: (x.get("priority", 9), x.get("reason", "")))
    return hints
