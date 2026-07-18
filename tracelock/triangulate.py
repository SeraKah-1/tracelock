"""Non-linear OSINT triangulation — detective-style lead pivots.

Logic (public sources only; no breach corpora):
  1. Seed (handle / phone / name / url)
  2. Expand surface: platforms, bio-linked handles, name morphs
  3. Harvest leads from every hit (second accounts, friends, schools, docs)
  4. Promote high-signal leads to new seeds (anchors)
  5. Cross-validate anchors against independent public sources (PDDIKTI-style packs, SERP)
  6. Graph keeps parent→child edges so report shows *why* a lead exists

This is the anti-linear engine: each finding opens new directions, like a
human investigator — not a single SERP pass.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from osint_cli.name_pattern import morph_username
from osint_cli.normalize import add_evidence, add_seed


# Platforms we extract handles from public URLs
_HANDLE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:instagram\.com|tiktok\.com|threads\.net|x\.com|twitter\.com|"
    r"github\.com|t\.me|telegram\.me|reddit\.com/user|linkedin\.com/in|"
    r"facebook\.com|fb\.com|youtube\.com/@)"
    r"/@?([A-Za-z0-9._-]{2,40})",
    re.I,
)
_BARE_HANDLE_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9._]{2,40})\b")
_NAME_CAND_RE = re.compile(
    r"\b([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,3})\b"
)
_SCHOOL_RE = re.compile(
    r"\b(universitas|university|institut|politeknik|sma|smk|smp|sekolah|"
    r"kampus|fakultas|jurusan|prodi)\b[^\n,.]{0,60}",
    re.I,
)
_DOMISILI_RE = re.compile(
    r"\b(jakarta|bandung|surabaya|yogyakarta|yogya|depok|tangerang|bekasi|"
    r"semarang|malang|medan|makassar|bali|denpasar|bogor|solo|surakarta|"
    r"padang|palembang|balikpapan|manado|pontianak)\b",
    re.I,
)
_DOC_HINT_RE = re.compile(
    r"\b(scribd|slideshare|academia\.edu|researchgate|skripsi|tugas\s*akhir|"
    r"daftar\s*mahasiswa|nim\b|pddikti|forlap)\b",
    re.I,
)


def _norm_handle(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


def _seen_handles(state: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for s in state.get("seeds") or []:
        if s.get("type") == "username":
            out.add(_norm_handle(s.get("normalized") or s.get("value") or ""))
    for e in state.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        if e.get("type") in ("username", "username_platform_hit", "lead_handle"):
            v = e.get("value")
            if isinstance(v, dict):
                out.add(_norm_handle(str(v.get("handle") or v.get("username") or "")))
            else:
                out.add(_norm_handle(str(v or "")))
    g = state.get("lead_graph") or {}
    for n in g.get("nodes") or []:
        if isinstance(n, dict) and n.get("kind") == "handle":
            out.add(_norm_handle(str(n.get("value") or "")))
    return {x for x in out if x}


def extract_leads_from_text(text: str, *, source: str = "") -> list[dict[str, Any]]:
    """Pull pivot candidates from free text / SERP snippet / bio."""
    leads: list[dict[str, Any]] = []
    if not text:
        return leads
    for m in _HANDLE_URL_RE.finditer(text):
        h = _norm_handle(m.group(1))
        if h and h not in ("www", "http", "https", "user", "in"):
            leads.append(
                {
                    "kind": "handle",
                    "value": h,
                    "why": "handle_in_url_or_profile",
                    "source": source,
                    "priority": 0.85,
                }
            )
    for m in _BARE_HANDLE_RE.finditer(text):
        h = _norm_handle(m.group(1))
        if h:
            leads.append(
                {
                    "kind": "handle",
                    "value": h,
                    "why": "at_handle_in_text",
                    "source": source,
                    "priority": 0.7,
                }
            )
    for m in _SCHOOL_RE.finditer(text):
        frag = m.group(0).strip()[:80]
        leads.append(
            {
                "kind": "institution",
                "value": frag,
                "why": "school_or_campus_mention",
                "source": source,
                "priority": 0.75,
            }
        )
    for m in _DOMISILI_RE.finditer(text):
        leads.append(
            {
                "kind": "place",
                "value": m.group(1).title(),
                "why": "geo_mention",
                "source": source,
                "priority": 0.55,
            }
        )
    if _DOC_HINT_RE.search(text):
        leads.append(
            {
                "kind": "doc_anchor",
                "value": "public_document_hint",
                "why": "institutional_or_scribd_style_doc",
                "source": source,
                "priority": 0.8,
                "note": text[:160],
            }
        )
    # light name candidates only if multi-token Capitalized
    for m in _NAME_CAND_RE.finditer(text[:500]):
        name = m.group(1).strip()
        if name.lower() in ("the", "and", "for", "with"):
            continue
        leads.append(
            {
                "kind": "name",
                "value": name,
                "why": "capitalized_name_phrase",
                "source": source,
                "priority": 0.45,
            }
        )
    return leads


def extract_leads_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan all evidence + footprint for new directions."""
    leads: list[dict[str, Any]] = []
    for e in state.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        et = e.get("type") or ""
        val = e.get("value")
        src = e.get("source_name") or et
        blob = ""
        if isinstance(val, str):
            blob = val
        elif isinstance(val, dict):
            blob = " ".join(str(v) for v in val.values() if isinstance(v, (str, int)))
            # structured handle
            for k in ("handle", "username", "user", "login"):
                if val.get(k):
                    leads.append(
                        {
                            "kind": "handle",
                            "value": _norm_handle(str(val[k])),
                            "why": f"structured_{et}",
                            "source": src,
                            "priority": 0.8,
                        }
                    )
            if val.get("url"):
                blob += " " + str(val["url"])
            if val.get("title"):
                blob += " " + str(val["title"])
            if val.get("snippet"):
                blob += " " + str(val["snippet"])
        leads.extend(extract_leads_from_text(blob, source=str(src)))

        # friend/network style keys
        if isinstance(val, dict):
            for k in ("following", "followers", "friends", "mentions", "related"):
                rel = val.get(k)
                if isinstance(rel, list):
                    for item in rel[:20]:
                        h = _norm_handle(str(item))
                        if h:
                            leads.append(
                                {
                                    "kind": "handle",
                                    "value": h,
                                    "why": f"network_{k}",
                                    "source": src,
                                    "priority": 0.65,
                                }
                            )

    fp = state.get("digital_footprint") or {}
    for h in fp.get("handles") or []:
        leads.append(
            {
                "kind": "handle",
                "value": _norm_handle(str(h)),
                "why": "footprint_handle",
                "source": "digital_footprint",
                "priority": 0.9,
            }
        )
    for row in fp.get("probe_results") or fp.get("platforms") or []:
        if isinstance(row, dict) and row.get("handle"):
            leads.append(
                {
                    "kind": "handle",
                    "value": _norm_handle(str(row["handle"])),
                    "why": "platform_probe",
                    "source": str(row.get("platform") or "probe"),
                    "priority": 0.75,
                }
            )

    # name morphs from existing usernames → second-account hypotheses
    for s in state.get("seeds") or []:
        if s.get("type") == "username":
            u = _norm_handle(s.get("normalized") or s.get("value") or "")
            if not u:
                continue
            for m in morph_username(u)[:12]:
                leads.append(
                    {
                        "kind": "handle",
                        "value": _norm_handle(m),
                        "why": "name_pattern_morph",
                        "source": u,
                        "priority": 0.6,
                    }
                )

    return _dedupe_leads(leads)


def _dedupe_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for L in leads:
        kind = str(L.get("kind") or "")
        val = str(L.get("value") or "").strip().lower()
        if not kind or not val or len(val) < 2:
            continue
        key = (kind, val)
        prev = best.get(key)
        if not prev or float(L.get("priority") or 0) > float(prev.get("priority") or 0):
            best[key] = L
    out = list(best.values())
    out.sort(key=lambda x: float(x.get("priority") or 0), reverse=True)
    return out


def ensure_graph(state: dict[str, Any]) -> dict[str, Any]:
    g = state.get("lead_graph")
    if not isinstance(g, dict):
        g = {"nodes": [], "edges": [], "version": 1}
        state["lead_graph"] = g
    g.setdefault("nodes", [])
    g.setdefault("edges", [])
    return g


def _node_id(kind: str, value: str) -> str:
    return f"{kind}:{value.strip().lower()}"


def promote_leads(
    state: dict[str, Any],
    *,
    max_new_seeds: int = 8,
    min_priority: float = 0.55,
) -> dict[str, Any]:
    """Add high-priority leads as seeds + graph nodes; return summary."""
    graph = ensure_graph(state)
    existing = _seen_handles(state)
    known_names = {
        (s.get("normalized") or s.get("value") or "").lower()
        for s in (state.get("seeds") or [])
        if s.get("type") == "name"
    }
    leads = extract_leads_from_state(state)
    promoted: list[dict[str, Any]] = []
    skipped = 0

    # seed existing seeds as root nodes
    for s in state.get("seeds") or []:
        st = s.get("type") or "seed"
        sv = str(s.get("normalized") or s.get("value") or "")
        if not sv:
            continue
        nid = _node_id(st if st != "username" else "handle", sv)
        if not any(n.get("id") == nid for n in graph["nodes"]):
            graph["nodes"].append(
                {
                    "id": nid,
                    "kind": "handle" if st == "username" else st,
                    "value": sv,
                    "role": "seed",
                    "priority": 1.0,
                }
            )

    for L in leads:
        if float(L.get("priority") or 0) < min_priority:
            skipped += 1
            continue
        kind = L["kind"]
        val = str(L["value"]).strip()
        if kind == "handle":
            h = _norm_handle(val)
            if not h or h in existing:
                skipped += 1
                continue
            if len(promoted) >= max_new_seeds:
                break
            try:
                add_seed(state, f"username:{h}")
            except Exception:
                continue
            existing.add(h)
            nid = _node_id("handle", h)
            graph["nodes"].append(
                {
                    "id": nid,
                    "kind": "handle",
                    "value": h,
                    "role": "pivot",
                    "why": L.get("why"),
                    "priority": L.get("priority"),
                }
            )
            parent = L.get("source") or "evidence"
            graph["edges"].append(
                {
                    "from": str(parent),
                    "to": nid,
                    "rel": L.get("why") or "pivot",
                }
            )
            promoted.append(L)
            add_evidence(
                state,
                {
                    "type": "lead_handle",
                    "value": {"handle": h, "why": L.get("why"), "from": parent},
                    "source_name": "triangulate",
                    "confidence": float(L.get("priority") or 0.6),
                },
            )
        elif kind == "name":
            low = val.lower()
            if low in known_names or len(val.split()) < 2:
                skipped += 1
                continue
            if len(promoted) >= max_new_seeds:
                break
            try:
                add_seed(state, f"name:{val}")
                known_names.add(low)
            except Exception:
                continue
            nid = _node_id("name", val)
            graph["nodes"].append(
                {
                    "id": nid,
                    "kind": "name",
                    "value": val,
                    "role": "pivot",
                    "why": L.get("why"),
                    "priority": L.get("priority"),
                }
            )
            promoted.append(L)
        elif kind in ("institution", "place", "doc_anchor"):
            nid = _node_id(kind, val)
            if any(n.get("id") == nid for n in graph["nodes"]):
                skipped += 1
                continue
            graph["nodes"].append(
                {
                    "id": nid,
                    "kind": kind,
                    "value": val,
                    "role": "anchor_hint",
                    "why": L.get("why"),
                    "priority": L.get("priority"),
                    "note": L.get("note"),
                }
            )
            graph["edges"].append(
                {
                    "from": str(L.get("source") or "evidence"),
                    "to": nid,
                    "rel": kind,
                }
            )
            add_evidence(
                state,
                {
                    "type": f"lead_{kind}",
                    "value": {"value": val, "why": L.get("why"), "note": L.get("note")},
                    "source_name": "triangulate",
                    "confidence": float(L.get("priority") or 0.5),
                },
            )
            promoted.append(L)

    state["lead_graph"] = graph
    state["triangulation"] = {
        "promoted_count": len(promoted),
        "skipped": skipped,
        "lead_pool": len(leads),
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "promoted": promoted[:20],
        "method": "multi_hop_public_pivot",
    }
    return state["triangulation"]


def next_collect_modules(state: dict[str, Any]) -> list[str]:
    """Choose collect modules from graph state (non-linear pack)."""
    mods: list[str] = ["websearch"]
    seeds = state.get("seeds") or []
    has_user = any(s.get("type") == "username" for s in seeds)
    has_name = any(s.get("type") == "name" for s in seeds)
    has_phone = any(s.get("type") == "phone" for s in seeds)
    graph = state.get("lead_graph") or {}
    kinds = {n.get("kind") for n in (graph.get("nodes") or []) if isinstance(n, dict)}

    if has_user:
        mods.extend(["username_enum", "name_pattern_enum"])
    if has_name or "institution" in kinds or "doc_anchor" in kinds:
        mods.extend(["gov_id", "pddikti"])
    if has_phone:
        mods.append("phone_footprint")
    if "place" in kinds and has_name:
        mods.append("websearch")  # deepen local school SERP via name+place in queries
    # unique preserve order
    return list(dict.fromkeys(mods))


def graph_summary(state: dict[str, Any]) -> str:
    g = state.get("lead_graph") or {}
    nodes = g.get("nodes") or []
    if not nodes:
        return "(no lead graph yet)"
    lines = ["Lead graph (triangulation):"]
    for n in nodes[:25]:
        if not isinstance(n, dict):
            continue
        lines.append(
            f"  • [{n.get('role') or n.get('kind')}] {n.get('value')} "
            f"— {n.get('why') or ''}"
        )
    edges = g.get("edges") or []
    if edges:
        lines.append(f"  pivots: {len(edges)} edges")
    return "\n".join(lines)


def detective_playbook() -> str:
    """Human-readable methodology for prompts / .md skill."""
    return """# Detective OSINT playbook (TraceLock)

Public sources only. Non-linear triangulation:

1. **Seed** — handle / phone / name / URL from operator.
2. **Surface map** — same handle on major platforms; bio + link-in-bio pivots.
3. **Second-account hunt** — deconstruct handle → morph patterns → enum again.
4. **Content harvest** — public posts/comments/snippets → new @handles, names, schools.
5. **Network pivot** — friend/mention handles become *leads* (not automatic truth).
6. **Anchor** — institutional public docs (campus lists, PDDIKTI-style packs, Scribd-class
   public uploads) used to *validate* a name/NIM hypothesis — never invent IDs.
7. **Place expand** — if domisili appears, search schools/orgs in that area + name.
8. **Cross-check** — every high claim needs ≥2 independent public signals.
9. **HITL** — captcha, e-wallet Layer-B, civil lock confirmation stay human-only.
10. **Report** — digital ≠ civil; show lead graph edges (why each pivot existed).

Anti-patterns: single SERP and stop; invent legal names; treat one friend match as identity.
"""
