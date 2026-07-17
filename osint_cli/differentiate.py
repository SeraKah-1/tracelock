"""Entity resolution: platform-qualified keys, no bare-username auto-merge."""

from __future__ import annotations

import re
from typing import Any

from .state import next_id


# Tokens that appear in search/fixture boilerplate and must never drive merges.
_BIO_STOPWORDS = frozenset(
    {
        "fixture",
        "offline",
        "result",
        "results",
        "query",
        "search",
        "public",
        "hits",
        "hit",
        "enumerate",
        "enumeration",
        "profile",
        "profiles",
        "about",
        "page",
        "http",
        "https",
        "www",
        "com",
        "from",
        "with",
        "this",
        "that",
        "have",
        "been",
        "will",
        "your",
        "user",
        "username",
        "account",
        "online",
        "website",
        "example",
        "invalid",
        "demo",
        "test",
        "snippet",
        "title",
        "websearch",
        "duckduckgo",
        "google",
    }
)


def _ident_key(ident: dict[str, Any]) -> str | None:
    """Strong identity key. username requires platform."""
    t = (ident.get("type") or "").lower()
    v = ident.get("value")
    if v is None or v == "":
        return None
    v = str(v).strip().lower()
    if t == "email":
        return f"email:{v}"
    if t == "phone":
        return f"phone:{v}"
    if t == "username":
        plat = (ident.get("platform") or "").lower().strip()
        if not plat or plat == "seed":
            # bare / seed-pseudo platform is weak — never a merge key
            return None
        return f"username@{plat}:{v}"
    if t == "url":
        return f"url:{v}"
    if t == "image" or t == "image_phash":
        return f"image:{v}"
    return None


def _weak_username(ident: dict[str, Any]) -> str | None:
    if (ident.get("type") or "").lower() != "username":
        return None
    v = ident.get("value")
    if not v:
        return None
    return str(v).strip().lower()


def _extract_identifiers(ev: dict[str, Any]) -> list[dict[str, Any]]:
    ids: list[dict[str, Any]] = []
    for i in ev.get("identifiers") or []:
        if isinstance(i, dict):
            ids.append(dict(i))
    val = ev.get("value")
    plat = ev.get("platform")
    if isinstance(val, dict):
        if val.get("username"):
            ids.append(
                {
                    "type": "username",
                    "value": val["username"],
                    "platform": val.get("platform") or plat,
                }
            )
        if val.get("public_email"):
            ids.append({"type": "email", "value": val["public_email"]})
        if val.get("preferredUsername") and not val.get("username"):
            ids.append(
                {
                    "type": "username",
                    "value": val["preferredUsername"],
                    "platform": plat or "gravatar",
                }
            )
    return ids


def _photo_signal(ev: dict[str, Any]) -> str | None:
    val = ev.get("value")
    if isinstance(val, dict):
        for k in ("photo_hash", "avatar_hash", "image_phash", "avatar_url"):
            if val.get(k):
                return str(val[k]).lower()
    meta = ev.get("meta") or {}
    if meta.get("photo_hash"):
        return str(meta["photo_hash"]).lower()
    return None


def _bio_tokens(ev: dict[str, Any]) -> set[str]:
    """
    Tokens for soft bio-merge. Only real profile bio/displayName fields.
    Excludes web_hit/search snippets/titles and common boilerplate.
    """
    etype = (ev.get("type") or "").lower()
    # Search hits and errors must not participate in bio clustering
    if etype in ("web_hit", "other", "archive", "breach_index"):
        return set()
    # registration without a bio field: skip
    val = ev.get("value")
    if not isinstance(val, dict):
        return set()
    # Only explicit person-description fields (not title/snippet)
    parts: list[str] = []
    for k in ("bio", "displayName", "display_name", "about", "description"):
        if val.get(k):
            parts.append(str(val[k]))
    if not parts:
        return set()
    text = " ".join(parts).lower()
    raw = re.findall(r"[a-z0-9_]{4,}", text)
    tokens = {t for t in raw if t not in _BIO_STOPWORDS and not t.isdigit()}
    return tokens


def differentiate(state: dict[str, Any]) -> dict[str, Any]:
    """
    Cluster evidence into candidate persons.

    Rules:
    - Strong keys (email, phone, username@platform, image) seed clusters and merge.
    - Bare username never auto-merges across platforms.
    - Username *seeds* do not create orphan username@seed nodes; only email/phone
      seeds create anchor keys (when present).
    - Bio merge uses profile bio/displayName only (never web_hit title/snippet).
    - Candidates with zero evidence are dropped.
    """
    prev_selected_ids = list(state.get("selected_branches") or [])
    prev_candidate_snapshot = [dict(c) for c in (state.get("candidates") or [])]

    evidence = state.get("evidence") or []
    # Only email/phone seeds create graph anchors (strong, evidence-attachable).
    # Username seeds are weak until platform-qualified evidence appears.
    seed_idents: list[tuple[str, dict[str, Any]]] = []
    for s in state.get("seeds") or []:
        if s.get("type") in ("email", "phone"):
            seed_idents.append(
                (
                    s["id"],
                    {"type": s["type"], "value": s["normalized"], "platform": None},
                )
            )

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    key_to_node: dict[str, str] = {}
    node_meta: dict[str, dict[str, Any]] = {}
    evidence_keys: dict[str, list[str]] = {}
    evidence_weak: dict[str, list[str]] = {}
    evidence_photo: dict[str, str | None] = {}
    evidence_bio: dict[str, set[str]] = {}

    def ensure_key_node(key: str, label: str) -> str:
        if key not in key_to_node:
            nid = f"n:{key}"
            key_to_node[key] = nid
            parent.setdefault(nid, nid)
            node_meta[nid] = {
                "key": key,
                "label": label,
                "evidence_ids": [],
                "idents": [],
            }
        return key_to_node[key]

    # email/phone seed anchors only
    for sid, ident in seed_idents:
        k = _ident_key(ident)
        if k:
            nid = ensure_key_node(k, k)
            node_meta[nid]["idents"].append(ident)

    for ev in evidence:
        eid = ev["id"]
        idents = _extract_identifiers(ev)
        # attach seed emails/phones referenced by seed_ids
        for sid in ev.get("seed_ids") or []:
            for s in state.get("seeds") or []:
                if s["id"] == sid and s["type"] in ("email", "phone"):
                    idents.append({"type": s["type"], "value": s["normalized"]})

        strong: list[str] = []
        weak: list[str] = []
        for ident in idents:
            k = _ident_key(ident)
            if k:
                strong.append(k)
                nid = ensure_key_node(k, k)
                if eid not in node_meta[nid]["evidence_ids"]:
                    node_meta[nid]["evidence_ids"].append(eid)
                node_meta[nid]["idents"].append(ident)
            else:
                w = _weak_username(ident)
                if w:
                    weak.append(w)

        evidence_keys[eid] = strong
        evidence_weak[eid] = weak
        evidence_photo[eid] = _photo_signal(ev)
        evidence_bio[eid] = _bio_tokens(ev)

        if strong:
            base = ensure_key_node(strong[0], strong[0])
            for sk in strong[1:]:
                union(base, ensure_key_node(sk, sk))
            for sk in strong:
                nid = key_to_node[sk]
                if eid not in node_meta[nid]["evidence_ids"]:
                    node_meta[nid]["evidence_ids"].append(eid)

        # evidence with no strong keys: singleton (still has evidence_ids)
        if not strong:
            nid = f"n:ev:{eid}"
            parent.setdefault(nid, nid)
            node_meta[nid] = {
                "key": nid,
                "label": f"evidence:{eid}",
                "evidence_ids": [eid],
                "idents": idents,
                "weak_usernames": weak,
            }

    # Photo-based merges
    photo_map: dict[str, list[str]] = {}
    for eid, ph in evidence_photo.items():
        if ph:
            photo_map.setdefault(ph, []).append(eid)

    def nodes_for_evidence(eid: str) -> list[str]:
        nodes = []
        for nid, meta in node_meta.items():
            if eid in meta.get("evidence_ids", []):
                nodes.append(nid)
        return nodes

    for ph, eids in photo_map.items():
        if len(eids) < 2:
            continue
        roots = []
        for eid in eids:
            ns = nodes_for_evidence(eid)
            if ns:
                roots.append(ns[0])
        for i in range(1, len(roots)):
            union(roots[0], roots[i])

    # Bio overlap: profile bio tokens only (web_hit already excluded in _bio_tokens)
    eids = list(evidence_bio.keys())
    for i in range(len(eids)):
        for j in range(i + 1, len(eids)):
            a, b = eids[i], eids[j]
            ba, bb = evidence_bio[a], evidence_bio[b]
            if not ba or not bb:
                continue
            inter = ba & bb
            union_sz = len(ba | bb) or 1
            jacc = len(inter) / union_sz
            # require real overlap: ≥2 non-stopword tokens and jaccard ≥ 0.5
            if jacc >= 0.5 and len(inter) >= 2:
                na, nb = nodes_for_evidence(a), nodes_for_evidence(b)
                if na and nb:
                    union(na[0], nb[0])

    components: dict[str, list[str]] = {}
    for nid in node_meta:
        r = find(nid)
        components.setdefault(r, []).append(nid)

    candidates: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    state["candidates"] = []
    state["links"] = []

    for root, members in components.items():
        eids_set: set[str] = set()
        idents_acc: list[dict[str, Any]] = []
        keys: list[str] = []
        weak_names: set[str] = set()
        for nid in members:
            meta = node_meta[nid]
            eids_set.update(meta.get("evidence_ids") or [])
            idents_acc.extend(meta.get("idents") or [])
            keys.append(meta.get("key") or nid)
            for w in meta.get("weak_usernames") or []:
                weak_names.add(w)
            for eid in meta.get("evidence_ids") or []:
                for w in evidence_weak.get(eid) or []:
                    weak_names.add(w)

        # Drop orphan anchors (e.g. email seed with no evidence, leftover empty nodes)
        if not eids_set:
            continue

        seen_i: set[str] = set()
        idents_out = []
        for ident in idents_acc:
            k = _ident_key(ident) or (
                f"weak:{ident.get('type')}:{ident.get('value')}:{ident.get('platform')}"
            )
            if k in seen_i:
                continue
            seen_i.add(k)
            idents_out.append(ident)

        strong_count = sum(1 for i in idents_out if _ident_key(i))
        score = min(1.0, 0.2 + 0.15 * strong_count + 0.05 * len(eids_set))
        photos = {evidence_photo[e] for e in eids_set if evidence_photo.get(e)}
        if any(photos):
            score = min(1.0, score + 0.15)

        platforms = sorted(
            {
                (i.get("platform") or "")
                for i in idents_out
                if i.get("type") == "username"
                and i.get("platform")
                and i.get("platform") != "seed"
            }
        )
        label_bits = []
        emails = [i["value"] for i in idents_out if i.get("type") == "email"]
        users = [
            f"{i['value']}@{i.get('platform')}"
            for i in idents_out
            if i.get("type") == "username"
            and i.get("platform")
            and i.get("platform") != "seed"
        ]
        if emails:
            label_bits.append(emails[0])
        if users:
            label_bits.append(users[0])
        if not label_bits and weak_names:
            label_bits.append(f"weak:{next(iter(weak_names))}")
        if not label_bits:
            # Prefer source evidence label over "unknown"
            label_bits.append(f"evidence:{sorted(eids_set)[0]}")

        notes_parts = []
        if len(platforms) > 1:
            notes_parts.append(
                f"platforms={','.join(platforms)}; bare username match alone does not merge clusters"
            )
        if weak_names and not users:
            notes_parts.append(f"weak_usernames={sorted(weak_names)}")

        cid = next_id(candidates, "c")
        cand = {
            "id": cid,
            "label": " / ".join(label_bits)[:120],
            "status": "active",
            "evidence_ids": sorted(eids_set),
            "identifiers": idents_out,
            "signals": {
                "photo_match": sorted(p for p in photos if p) or None,
                "bio_overlap": [],
                "mutual_connections": [],
                "timeline_consistency": None,
                "style_overlap": None,
                "platforms": platforms,
                "strong_key_count": strong_count,
            },
            "score": round(score, 3),
            "notes": "; ".join(notes_parts) if notes_parts else "",
            "keys": keys,
        }
        candidates.append(cand)
        for eid in eids_set:
            links.append(
                {
                    "from": eid,
                    "to": cid,
                    "relation": "supports",
                    "weight": round(score, 3),
                }
            )

    candidates.sort(key=lambda c: (-c["score"], c["id"]))
    for i, c in enumerate(candidates, 1):
        old = c["id"]
        new = f"c{i}"
        c["id"] = new
        for lk in links:
            if lk["to"] == old:
                lk["to"] = new

    prev_cands = {c["id"]: c for c in prev_candidate_snapshot}
    prev_fps: list[set[str]] = []
    for pid in prev_selected_ids:
        pc = prev_cands.get(pid)
        if not pc:
            continue
        fp: set[str] = set()
        for ident in pc.get("identifiers") or []:
            k = _ident_key(ident)
            if k:
                fp.add(k)
        if fp:
            prev_fps.append(fp)

    new_selected: list[str] = []
    for c in candidates:
        c["status"] = "active"
        cfp = set()
        for ident in c.get("identifiers") or []:
            k = _ident_key(ident)
            if k:
                cfp.add(k)
        for pfp in prev_fps:
            if cfp & pfp:
                c["status"] = "selected"
                new_selected.append(c["id"])
                break
    state["selected_branches"] = new_selected
    state["candidates"] = candidates
    state["links"] = links

    return {
        "candidate_count": len(candidates),
        "candidates": [
            {
                "id": c["id"],
                "label": c["label"],
                "score": c["score"],
                "evidence_ids": c["evidence_ids"],
                "identifier_count": len(c["identifiers"]),
                "notes": c["notes"],
                "status": c["status"],
            }
            for c in candidates
        ],
        "note": "Bare username equality does not auto-merge; keys are username@platform, email, phone, image.",
        "selected_branches": new_selected,
        "previous_selection_ids": prev_selected_ids,
    }


def select_candidates(state: dict[str, Any], candidate_ids: list[str]) -> dict[str, Any]:
    ids = list(candidate_ids)
    known = {c["id"] for c in state.get("candidates") or []}
    missing = [i for i in ids if i not in known]
    if missing:
        raise ValueError(f"unknown candidate ids: {missing}; known={sorted(known)}")
    for c in state["candidates"]:
        if c["id"] in ids:
            c["status"] = "selected"
        elif c["status"] == "selected":
            c["status"] = "active"
    state["selected_branches"] = ids
    return {
        "selected_branches": ids,
        "candidates": [
            {
                "id": c["id"],
                "status": c["status"],
                "label": c["label"],
                "score": c["score"],
            }
            for c in state["candidates"]
        ],
    }
