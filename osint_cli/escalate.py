"""Escalate: derive new seeds only from selected candidate clusters."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .normalize import add_seed, normalize_value


def _candidate_by_id(state: dict[str, Any], cid: str) -> dict[str, Any] | None:
    for c in state.get("candidates") or []:
        if c["id"] == cid:
            return c
    return None


def _existing_seed_keys(state: dict[str, Any]) -> set[tuple[str, str]]:
    return {(s["type"], s["normalized"]) for s in state.get("seeds") or []}


def escalate(
    state: dict[str, Any],
    goal: str | None = None,
    candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract new seeds from selected (or specified) candidates only.
    Increments depth; refuses if max_depth exceeded.
    """
    max_depth = int(state.get("scope", {}).get("max_depth") or 5)
    depth = int(state.get("depth") or 0)
    if depth >= max_depth:
        return {
            "ok": False,
            "reason": "max_depth",
            "depth": depth,
            "max_depth": max_depth,
            "seeds_added": [],
        }

    selected = candidate_ids or list(state.get("selected_branches") or [])
    if not selected:
        raise ValueError("no candidates selected; run select first")

    existing = _existing_seed_keys(state)
    added: list[dict[str, Any]] = []
    considered: list[str] = []

    for cid in selected:
        cand = _candidate_by_id(state, cid)
        if not cand:
            raise ValueError(f"unknown candidate: {cid}")
        # identifiers on candidate
        for ident in cand.get("identifiers") or []:
            t = (ident.get("type") or "").lower()
            v = ident.get("value")
            if not v:
                continue
            if t == "username":
                nv = normalize_value("username", str(v))
                key = ("username", nv)
                considered.append(f"username:{nv}")
                if key not in existing:
                    seed = add_seed(state, f"username:{nv}", origin=f"escalate:{cid}")
                    existing.add(key)
                    added.append(seed)
            elif t == "email":
                nv = normalize_value("email", str(v))
                key = ("email", nv)
                considered.append(f"email:{nv}")
                if key not in existing:
                    seed = add_seed(state, f"email:{nv}", origin=f"escalate:{cid}")
                    existing.add(key)
                    added.append(seed)
            elif t == "phone":
                nv = normalize_value("phone", str(v))
                key = ("phone", nv)
                considered.append(f"phone:{nv}")
                if key not in existing:
                    seed = add_seed(state, f"phone:{nv}", origin=f"escalate:{cid}")
                    existing.add(key)
                    added.append(seed)
            elif t == "url":
                nv = str(v).strip()
                key = ("url", nv)
                considered.append(f"url:{nv}")
                if key not in existing:
                    seed = add_seed(state, f"url:{nv}", origin=f"escalate:{cid}")
                    existing.add(key)
                    added.append(seed)

        # evidence-linked URLs and profile links for this candidate only
        eids = set(cand.get("evidence_ids") or [])
        for ev in state.get("evidence") or []:
            if ev.get("id") not in eids:
                continue
            url = ev.get("source_url")
            if url and str(url).startswith("http"):
                # derive username from path for known hosts if not already
                _maybe_username_from_url(state, url, existing, added, cid, considered)
            val = ev.get("value")
            if isinstance(val, dict):
                for k in ("profileUrl", "url", "link"):
                    if val.get(k) and str(val[k]).startswith("http"):
                        _maybe_username_from_url(
                            state, str(val[k]), existing, added, cid, considered
                        )
                if val.get("public_email"):
                    nv = normalize_value("email", str(val["public_email"]))
                    key = ("email", nv)
                    considered.append(f"email:{nv}")
                    if key not in existing:
                        seed = add_seed(state, f"email:{nv}", origin=f"escalate:{cid}")
                        existing.add(key)
                        added.append(seed)

    state["depth"] = depth + 1
    return {
        "ok": True,
        "depth": state["depth"],
        "max_depth": max_depth,
        "selected": selected,
        "goal": goal,
        "seeds_added": [
            {"id": s["id"], "type": s["type"], "normalized": s["normalized"], "origin": s["origin"]}
            for s in added
        ],
        "considered": sorted(set(considered)),
        "note": "New seeds derived only from selected candidate clusters",
    }


def _maybe_username_from_url(
    state: dict[str, Any],
    url: str,
    existing: set[tuple[str, str]],
    added: list[dict[str, Any]],
    cid: str,
    considered: list[str],
) -> None:
    try:
        p = urlparse(url)
        host = p.netloc.lower().removeprefix("www.")
        parts = [x for x in p.path.split("/") if x]
        if not parts:
            return
        # github.com/user, reddit.com/user/name, x.com/user, about.me/user
        user = None
        if host in ("github.com", "gitlab.com", "instagram.com", "pinterest.com", "keybase.io", "about.me"):
            user = parts[0]
            if user.startswith("@"):
                user = user[1:]
        elif host in ("reddit.com", "www.reddit.com") and parts[0] == "user" and len(parts) > 1:
            user = parts[1]
        elif host in ("x.com", "twitter.com", "tiktok.com"):
            user = parts[0].lstrip("@")
        elif host == "medium.com" and parts[0].startswith("@"):
            user = parts[0][1:]
        if not user or user in ("login", "join", "explore", "settings"):
            return
        nv = normalize_value("username", user)
        key = ("username", nv)
        considered.append(f"username:{nv}")
        if key not in existing:
            seed = add_seed(state, f"username:{nv}", origin=f"escalate:{cid}")
            existing.add(key)
            added.append(seed)
    except Exception:
        return
