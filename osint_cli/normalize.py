"""Seed and evidence normalization."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .state import next_id, utc_now


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\-\s().]{7,}$")
URL_RE = re.compile(r"^https?://", re.I)


def detect_type(value: str, explicit: str | None = None) -> str:
    if explicit and explicit != "auto":
        return explicit.lower()
    v = value.strip()
    if URL_RE.match(v):
        return "url"
    if EMAIL_RE.match(v):
        return "email"
    if v.startswith("@") and " " not in v[1:]:
        return "username"
    if PHONE_RE.match(v) and sum(c.isdigit() for c in v) >= 7:
        return "phone"
    if " " in v or (v[:1].isupper() and " " in v):
        return "name"
    # bare token → username by default
    if re.match(r"^[\w.\-]{2,64}$", v):
        return "username"
    return "other"


def normalize_value(seed_type: str, value: str) -> str:
    v = value.strip()
    t = seed_type.lower()
    if t == "email":
        return v.lower()
    if t == "username":
        return v.lstrip("@").lower()
    if t == "phone":
        # Prefer E.164 for Indonesian mobiles; see phone_pivot.normalize_phone_record
        try:
            from .phone_pivot import normalize_phone_record

            rec = normalize_phone_record(v)
            if rec.get("ok") and rec.get("normalized"):
                return str(rec["normalized"])
        except Exception:
            pass
        digits = re.sub(r"[^\d+]", "", v)
        if digits.startswith("+"):
            return "+" + re.sub(r"\D", "", digits)
        only = re.sub(r"\D", "", digits)
        return only
    if t == "url":
        return v
    if t == "name":
        return " ".join(v.split())
    return v


def parse_seed_spec(spec: str) -> tuple[str | None, str]:
    """Parse 'type:value' or bare value. type may be email|username|phone|name|url|image|domain|other|auto."""
    if ":" in spec:
        maybe_type, rest = spec.split(":", 1)
        known = {
            "email",
            "username",
            "phone",
            "name",
            "url",
            "image",
            "domain",
            "other",
            "auto",
        }
        if maybe_type.lower() in known and rest:
            # avoid treating http: as type
            if maybe_type.lower() == "url" or maybe_type.lower() not in ("http", "https"):
                if maybe_type.lower() in known:
                    return maybe_type.lower(), rest
    return None, spec


def add_seed(
    state: dict[str, Any],
    raw: str,
    origin: str = "user",
    explicit_type: str | None = None,
) -> dict[str, Any]:
    etype, value = parse_seed_spec(raw) if explicit_type is None else (explicit_type, raw)
    if etype == "auto":
        etype = None
    stype = detect_type(value, etype)
    normalized = normalize_value(stype, value)
    # Phone: also dedupe across 08… / 62… / +62… forms
    phone_keys: set[str] = set()
    if stype == "phone":
        try:
            from .phone_pivot import normalize_phone_record

            rec = normalize_phone_record(value)
            phone_keys = {x for x in (rec.get("variants") or []) if x}
            phone_keys.add(normalized)
        except Exception:
            phone_keys = {normalized}
    for existing in state["seeds"]:
        if existing.get("type") == stype and existing.get("normalized") == normalized:
            return existing
        if stype == "phone" and existing.get("type") == "phone":
            ex_n = existing.get("normalized") or ""
            if ex_n in phone_keys:
                return existing
            # reverse: existing variants contain new
            try:
                from .phone_pivot import normalize_phone_record as _npr

                ex_rec = _npr(existing.get("value") or ex_n)
                if normalized in set(ex_rec.get("variants") or []) or normalized == ex_rec.get(
                    "normalized"
                ):
                    return existing
            except Exception:
                pass
    seed = {
        "id": next_id(state["seeds"], "s"),
        "type": stype,
        "value": value.strip(),
        "normalized": normalized,
        "added_at": utc_now(),
        "origin": origin,
    }
    if stype == "phone":
        try:
            from .phone_pivot import phone_seed_meta

            seed["meta"] = phone_seed_meta(value)
        except Exception:
            seed["meta"] = {}
    state["seeds"].append(seed)
    return seed


def evidence_dedupe_key(ev: dict[str, Any]) -> tuple:
    val = ev.get("value")
    if isinstance(val, dict):
        val_s = json_stable(val)
    else:
        val_s = str(val)
    return (
        ev.get("type"),
        val_s,
        ev.get("source_url") or "",
        ev.get("source_name") or "",
    )


def json_stable(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def add_evidence(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize and append evidence; skip exact duplicates. Returns added item or None if dup."""
    ev = {
        "id": item.get("id") or next_id(state["evidence"], "e"),
        "type": item.get("type") or "other",
        "value": item.get("value"),
        "source_name": item.get("source_name") or "unknown",
        "source_url": item.get("source_url"),
        "collected_at": item.get("collected_at") or utc_now(),
        "confidence": float(item.get("confidence") if item.get("confidence") is not None else 0.5),
        "tags": list(item.get("tags") or []),
        "raw_ref": item.get("raw_ref"),
        "seed_ids": list(item.get("seed_ids") or []),
        "platform": item.get("platform"),
        "identifiers": item.get("identifiers") or [],
        "meta": item.get("meta") or {},
    }
    key = evidence_dedupe_key(ev)
    for existing in state["evidence"]:
        if evidence_dedupe_key(existing) == key:
            return None
    state["evidence"].append(ev)
    return ev


def platform_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    host = host.removeprefix("www.")
    # common short names
    mapping = {
        "github.com": "github",
        "twitter.com": "twitter",
        "x.com": "x",
        "instagram.com": "instagram",
        "reddit.com": "reddit",
        "linkedin.com": "linkedin",
        "tiktok.com": "tiktok",
        "facebook.com": "facebook",
        "youtube.com": "youtube",
        "gitlab.com": "gitlab",
        "medium.com": "medium",
        "pinterest.com": "pinterest",
        "twitch.tv": "twitch",
        "keybase.io": "keybase",
        "about.me": "aboutme",
    }
    if host in mapping:
        return mapping[host]
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return host or None
