"""Name-pattern enumeration from usernames / display strings.

Used when legal name is blank: artificial handles (llaauurraa, zzfandomxx) still
yield given-name *hypotheses* for PDDIKTI / campus-list scoring — never treated
as confirmed legal identity.
"""

from __future__ import annotations

import re
from typing import Any


# Common Gen-Z handle padding: doubled letters, leading/trailing fluff
_STRIP_EDGE = re.compile(r"^[._\-]+|[._\-]+$")
_MULTI_CHAR = re.compile(r"(.)\1{1,}")


def collapse_doubles(s: str) -> str:
    """llaauurraa → cecilia (collapse runs of identical letters to one)."""
    if not s:
        return s
    out: list[str] = []
    prev = None
    for ch in s.lower():
        if ch == prev:
            continue
        out.append(ch)
        prev = ch
    return "".join(out)


def morph_username(username: str) -> list[str]:
    """Derive given-name-like tokens from a bare username."""
    u = (username or "").strip().lstrip("@").lower()
    u = _STRIP_EDGE.sub("", u)
    if not u or len(u) < 3:
        return []
    candidates: list[str] = []
    seen: set[str] = set()

    def add(x: str, why: str) -> None:
        x = re.sub(r"[^a-z]", "", x.lower())
        if len(x) < 3 or x in seen:
            return
        # skip pure fandom tokens without name-like vowels
        if x in ("hoshii", "hoshi", "toki", "cosplay", "user"):
            return
        seen.add(x)
        candidates.append(x)

    add(u, "raw")
    collapsed = collapse_doubles(u)
    add(collapsed, "collapse_doubles")
    # drop trailing digits / year
    add(re.sub(r"\d+$", "", collapsed), "strip_digits")
    # take prefix before first digit/underscore
    m = re.match(r"([a-z]+)", collapsed)
    if m:
        add(m.group(1), "alpha_prefix")

    # Cecilia family from cec* handles
    if collapsed.startswith("cec") or u.startswith("cec"):
        for g in ("cecilia", "celia", "ceci", "cece", "cecylia", "cecillia"):
            add(g, "cec_family")
    if collapsed.startswith("cel") or "celia" in collapsed or collapsed in ("cell", "cella"):
        for g in ("celia", "cecilia", "cell"):
            add(g, "cel_family")
    # Alicia / similar from alic*
    if "alic" in collapsed:
        add("alicia", "alic")
    # Indonesian diminutives from doubled-letter cores
    if collapsed.endswith("ia") and len(collapsed) >= 4:
        add(collapsed, "ia_suffix")

    # Keep only plausible given-name length
    return [c for c in candidates if 3 <= len(c) <= 14]


def morph_display(display: str) -> list[str]:
    """Tokens from display names like cell!-, celia, feith."""
    if not display:
        return []
    raw = re.sub(r"[^A-Za-z\s\-]", " ", display)
    parts = [p for p in re.split(r"[\s\-]+", raw) if len(p) >= 3]
    out: list[str] = []
    for p in parts:
        out.extend(morph_username(p))
        out.append(p.lower())
    # dedupe preserve order
    seen: set[str] = set()
    final: list[str] = []
    for x in out:
        x = re.sub(r"[^a-z]", "", x.lower())
        if x and x not in seen and 3 <= len(x) <= 14:
            seen.add(x)
            final.append(x)
    return final


def patterns_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Aggregate name-pattern matrix from seeds + evidence display names."""
    given: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_given(token: str, source: str) -> None:
        t = token.lower().strip()
        if not t or t in seen:
            return
        seen.add(t)
        given.append({"token": t, "source": source})

    for s in state.get("seeds") or []:
        if s.get("type") == "username":
            u = s.get("normalized") or s.get("value") or ""
            for t in morph_username(u):
                add_given(t, f"username:{u}")
        if s.get("type") == "name":
            n = s.get("normalized") or s.get("value") or ""
            for part in n.split():
                add_given(part.lower(), "seed_name")

    for e in state.get("evidence") or []:
        val = e.get("value")
        if isinstance(val, dict):
            for key in ("display_name", "nickname", "nickName", "author_name", "title"):
                d = val.get(key)
                if isinstance(d, str) and d.strip():
                    for t in morph_display(d):
                        add_given(t, f"evidence:{key}")
        # signature lines like "20\nig: llaauurraa" already covered via username seeds

    # queries for public hunt (not mass brute)
    queries: list[str] = []
    for g in given[:12]:
        t = g["token"]
        queries.append(f'"{t}" "ilmu komunikasi" UNRI')
        queries.append(f'"{t}" PDDIKTI UNRI')
        queries.append(f'"{t.capitalize()}" "Universitas Riau"')

    return {
        "legal_name_present": any(
            (s.get("type") == "name" and (s.get("normalized") or s.get("value") or "").strip())
            for s in (state.get("seeds") or [])
        ),
        "given_name_hypotheses": given,
        "sample_queries": queries[:18],
        "policy": {
            "hypotheses_not_identity": True,
            "ban_ask_operator_for_legal_name": True,
            "next_after_patterns": [
                "score_against_campus_lists_ept_distribusi",
                "pddikti_or_pddikti_api_per_candidate",
                "reject_wrong_prodi_wrong_year",
                "peer_graph_comment_scrape",
            ],
        },
    }


def as_evidence_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Payload suitable for evidence type=other tags=name_pattern."""
    matrix = patterns_from_state(state)
    return {
        "kind": "name_pattern_matrix",
        **matrix,
    }
