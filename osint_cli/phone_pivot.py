"""Phone number as OSINT clue/seed (Layer A public + HITL checklist).

Aligns with PHONE_PIVOT_OSINT_PLAYBOOK.md:
- clue ≠ goal; multi-signal lock; graded evidence
- Layer A: normalize, prefix soft-geo, SERP footprint queries
- Layer B: HITL checklist only (no auto e-wallet / contact-sync / breach)
- Layer C forbidden: breach bots, NIK/alamat from leaks, IDOR
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from .normalize import add_evidence
from .state import utc_now

# Indonesian mobile leading digits after country 62 (non-exhaustive, soft only)
_ID_MOBILE_PREFIX: dict[str, dict[str, str]] = {
    "811": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "812": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "813": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "821": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "822": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "823": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "851": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "852": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "853": {"provider_hint": "Telkomsel", "note": "prefix soft; number portability"},
    "814": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "815": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "816": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "855": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "856": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "857": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "858": {"provider_hint": "Indosat", "note": "prefix soft; number portability"},
    "817": {"provider_hint": "XL", "note": "prefix soft; number portability"},
    "818": {"provider_hint": "XL", "note": "prefix soft; number portability"},
    "819": {"provider_hint": "XL", "note": "prefix soft; number portability"},
    "859": {"provider_hint": "XL", "note": "prefix soft; number portability"},
    "877": {"provider_hint": "XL", "note": "prefix soft; number portability"},
    "878": {"provider_hint": "XL", "note": "prefix soft; number portability"},
    "895": {"provider_hint": "Three", "note": "prefix soft; number portability"},
    "896": {"provider_hint": "Three", "note": "prefix soft; number portability"},
    "897": {"provider_hint": "Three", "note": "prefix soft; number portability"},
    "898": {"provider_hint": "Three", "note": "prefix soft; number portability"},
    "899": {"provider_hint": "Three", "note": "prefix soft; number portability"},
    "881": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
    "882": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
    "883": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
    "884": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
    "887": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
    "888": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
    "889": {"provider_hint": "Smartfren", "note": "prefix soft; number portability"},
}

_FORBIDDEN = [
    "breach_bot_nik_address",
    "darkweb_phone_lookup",
    "sim_swap_social_engineer",
    "idor_ewallet_api",
    "spam_otp_enumeration",
    "publish_doxx_home_nik",
]


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_phone_record(value: str, default_region: str = "ID") -> dict[str, Any]:
    """Parse phone into canonical forms for seeds + search variants.

    Indonesian-first defaults (08… / 62… / +62…). Other regions kept as +E.164-ish
    if input already has country code; otherwise national digits only.
    """
    raw = (value or "").strip()
    d = digits_only(raw)
    if not d:
        return {
            "ok": False,
            "error": "no_digits",
            "raw": raw,
            "e164": None,
            "normalized": "",
            "variants": [],
        }

    e164: str | None = None
    national: str | None = None
    region = default_region.upper()

    # Explicit + already stripped of non-digits in d; detect 62 / 08
    if raw.strip().startswith("+") and len(d) >= 10:
        e164 = f"+{d}"
        if d.startswith("62") and len(d) >= 11:
            national = "0" + d[2:]
            region = "ID"
        else:
            national = d
    elif d.startswith("62") and len(d) >= 11:
        e164 = f"+{d}"
        national = "0" + d[2:]
        region = "ID"
    elif d.startswith("0") and len(d) >= 10 and region == "ID":
        national = d
        e164 = "+62" + d[1:]
    elif len(d) >= 10 and region == "ID" and d[0] in "8789":
        # bare mobile without leading 0 (e.g. 81160600613)
        national = "0" + d
        e164 = "+62" + d
    elif len(d) >= 10:
        # unknown: store as digits; do not invent country
        national = d
        e164 = f"+{d}" if len(d) >= 11 else None
        region = "ZZ"
    else:
        return {
            "ok": False,
            "error": "too_short",
            "raw": raw,
            "digits": d,
            "e164": None,
            "normalized": d,
            "variants": [d],
        }

    # Canonical seed normalized: prefer E.164 for ID
    normalized = e164 or national or d

    variants = _search_variants(e164=e164, national=national, digits=d)
    prefix_meta = _prefix_meta(national or d, region=region)

    return {
        "ok": True,
        "raw": raw,
        "digits": d,
        "e164": e164,
        "national": national,
        "normalized": normalized,
        "region_hint": region,
        "variants": variants,
        "prefix": prefix_meta,
        "layer": "A",
        "grade_prefix": "soft_geo",
        "policy": {
            "clue_not_goal": True,
            "forbidden": list(_FORBIDDEN),
            "hitl_layer_b": True,
        },
    }


def _search_variants(*, e164: str | None, national: str | None, digits: str) -> list[str]:
    """Distinct strings useful for SERP exact-match (quote these)."""
    out: list[str] = []

    def add(x: str | None) -> None:
        if not x:
            return
        x = x.strip()
        if x and x not in out:
            out.append(x)

    add(e164)
    add(national)
    add(digits)
    if e164 and e164.startswith("+62"):
        add(e164[1:])  # 628…
        add("0" + e164[3:])  # 08…
        # spaced groups common in ads
        n = e164[3:]  # without +62
        if len(n) >= 9:
            add(f"0{n[:3]}-{n[3:7]}-{n[7:]}")
            add(f"0{n[:3]} {n[3:7]} {n[7:]}")
            add(f"+62 {n[:3]}-{n[3:7]}-{n[7:]}")
            add(f"+62{n[:3]}{n[3:]}")
    if national and national.startswith("0") and len(national) >= 10:
        n = national[1:]
        add(f"{national[:4]}-{national[4:8]}-{national[8:]}")
        add(f"{national[:4]} {national[4:8]} {national[8:]}")
    return out


def _prefix_meta(national_or_digits: str, region: str = "ID") -> dict[str, Any]:
    d = digits_only(national_or_digits)
    if region != "ID":
        return {
            "prefix3": d[:3] if len(d) >= 3 else d,
            "provider_hint": None,
            "note": "non-ID or unknown; prefix not mapped",
        }
    if d.startswith("0"):
        body = d[1:]
    elif d.startswith("62"):
        body = d[2:]
    else:
        body = d
    p3 = body[:3] if len(body) >= 3 else body
    info = _ID_MOBILE_PREFIX.get(p3, {})
    return {
        "prefix3": p3,
        "provider_hint": info.get("provider_hint"),
        "note": info.get("note")
        or ("unknown prefix — do not treat as domicile" if p3 else "empty"),
        "confidence": 0.25 if info else 0.1,
    }


def build_footprint_queries(record: dict[str, Any], extra_terms: str | None = None) -> list[str]:
    """Directed SERP queries for Layer A phone footprint."""
    if not record.get("ok"):
        return []
    variants = list(record.get("variants") or [])
    queries: list[str] = []
    for v in variants[:8]:
        queries.append(f'"{v}"')
    # high-signal combos
    primary = record.get("e164") or record.get("national") or record.get("normalized")
    if primary:
        for term in (
            "WhatsApp",
            "wa.me",
            "Telegram",
            "Instagram",
            "dokter",
            "klinik",
            "contact",
            "hubungi",
        ):
            queries.append(f'"{primary}" {term}')
    if extra_terms:
        q0 = record.get("national") or record.get("e164") or ""
        if q0:
            queries.append(f'"{q0}" {extra_terms}')
    # wa.me deep link (public)
    e164 = record.get("e164") or ""
    if e164.startswith("+"):
        wa = "https://wa.me/" + e164[1:]
        queries.append(f'"{wa}"')
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out[:24]


def hitl_phone_checklist(record: dict[str, Any] | None = None) -> dict[str, Any]:
    """Layer B operator checklist — never auto-executed by the tool."""
    phone = (record or {}).get("e164") or (record or {}).get("normalized") or "<phone>"
    return {
        "layer": "B",
        "phone": phone,
        "policy": "lab_device_only · ToS-sensitive · name = candidate not civil lock",
        "steps": [
            {
                "id": "B1_wallet_name_preview",
                "title": "E-wallet / m-banking transfer name preview",
                "do": (
                    "Only with legitimate transfer purpose or self-check. "
                    "Enter number on GoPay/OVO/DANA/ShopeePay/bank app transfer screen; "
                    "record displayed name/initials BEFORE any PIN if shown."
                ),
                "evidence_grade": "app_ui_snippet",
                "output": "name_candidate (confidence low–medium)",
                "dont": "Loop mass numbers; treat display name as KTP; violate app ToS for stalking",
            },
            {
                "id": "B2_contact_sync",
                "title": "Socmed contact sync (burner lab account)",
                "do": (
                    "Save number on lab phone under neutral label. "
                    "IG/TikTok/X → Follow and invite → Sync contacts. "
                    "Note suggested handles."
                ),
                "evidence_grade": "operator_observed",
                "output": "handle_candidates[]",
                "dont": "Use personal account; ignore 'added via phone' notification risk",
            },
            {
                "id": "B3_whatsapp_meta",
                "title": "WhatsApp profile metadata",
                "do": "Save number; observe DP (reverse-image if public), About, business profile, last-seen if visible.",
                "evidence_grade": "operator_observed",
                "output": "photo_url, about_text, business_fields",
                "dont": "24/7 last-seen stalking as default method",
            },
            {
                "id": "B4_telegram_find",
                "title": "Telegram find-by-phone",
                "do": "If privacy allows, capture @username and bio.",
                "evidence_grade": "operator_observed",
                "output": "telegram_username",
                "dont": "Assume registration if privacy hides user",
            },
            {
                "id": "B5_crowd_tags",
                "title": "Truecaller / GetContact tags",
                "do": "Record crowd tags; grade as crowd_tag only.",
                "evidence_grade": "crowd_tag",
                "output": "tags[], display_name soft",
                "dont": "Lock 'penipu' / family nicknames without multi-source",
            },
        ],
        "forbidden": list(_FORBIDDEN),
        "after_hitl": [
            "evidence add --type phone_pivot --grade app_ui_snippet|operator_observed "
            '--value \'{"name_candidate":"…","technique":"B1"}\' '
            f"--identifier phone:{phone}",
            "seed add name:…  # only if multi-signal justifies",
            "plan / next",
        ],
    }


def phone_seed_meta(value: str) -> dict[str, Any]:
    """Compact meta to attach on seed add."""
    rec = normalize_phone_record(value)
    if not rec.get("ok"):
        return {"phone_parse": rec}
    return {
        "phone_parse": {
            "e164": rec.get("e164"),
            "national": rec.get("national"),
            "region_hint": rec.get("region_hint"),
            "prefix": rec.get("prefix"),
            "variants": rec.get("variants"),
        }
    }


def collect_phone_footprint(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """Layer A collector: normalize + prefix soft + SERP queries (via websearch engines)."""
    if seed.get("type") != "phone":
        return []
    raw = seed.get("value") or seed.get("normalized") or ""
    rec = normalize_phone_record(raw)
    out: list[dict[str, Any]] = []

    # Always emit structured phone analysis evidence
    out.append(
        {
            "type": "phone_meta",
            "value": {
                "observation_grade": "portal_metadata",
                "technique": "normalize_prefix",
                "record": rec,
                "layer": "A",
            },
            "source_name": "phone_footprint",
            "source_url": None,
            "collected_at": utc_now(),
            "confidence": 0.7 if rec.get("ok") else 0.2,
            "tags": ["phone_footprint", "layer_a", "normalize"],
            "seed_ids": [seed["id"]],
            "identifiers": [
                {
                    "type": "phone",
                    "value": rec.get("normalized") or seed.get("normalized"),
                }
            ],
            "meta": {"observation_grade": "portal_metadata"},
        }
    )

    if not rec.get("ok"):
        return out

    queries = build_footprint_queries(rec, extra_terms=goal)
    # offline fixture: synthetic hits
    if offline:
        for q in queries[:3]:
            out.append(
                {
                    "type": "web_hit",
                    "value": {
                        "title": f"Fixture phone hit for {rec.get('national')}",
                        "snippet": f"Offline fixture for query {q}",
                        "query": q,
                        "technique": "phone_footprint",
                        "observation_grade": "search_snippet",
                    },
                    "source_name": "phone_footprint",
                    "source_url": "https://example.invalid/phone-fixture",
                    "collected_at": utc_now(),
                    "confidence": 0.3,
                    "tags": ["phone_footprint", "fixture", "layer_a", "grade:search_snippet"],
                    "seed_ids": [seed["id"]],
                    "identifiers": [{"type": "phone", "value": rec.get("normalized")}],
                    "meta": {"query": q, "observation_grade": "search_snippet"},
                }
            )
        out.append(
            {
                "type": "phone_hitl_plan",
                "value": hitl_phone_checklist(rec),
                "source_name": "phone_footprint",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.5,
                "tags": ["phone_footprint", "hitl_checklist", "layer_b"],
                "seed_ids": [seed["id"]],
                "identifiers": [{"type": "phone", "value": rec.get("normalized")}],
            }
        )
        return out

    # Live: reuse multi-engine websearch parsers from collect
    try:
        from .collect import (
            _http_get,
            _parse_bing_html,
            _parse_ddg_html,
            _parse_mojeek_html,
        )
    except Exception:
        out.append(
            {
                "type": "other",
                "value": {"error": "websearch_parsers_unavailable", "queries": queries[:5]},
                "source_name": "phone_footprint",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["phone_footprint", "error"],
                "seed_ids": [seed["id"]],
            }
        )
        return out

    engines: list[tuple[str, Any, Any]] = [
        (
            "duckduckgo",
            lambda q: "https://html.duckduckgo.com/html/?"
            + urllib.parse.urlencode({"q": q}),
            _parse_ddg_html,
        ),
        (
            "bing",
            lambda q: "https://www.bing.com/search?" + urllib.parse.urlencode({"q": q}),
            _parse_bing_html,
        ),
        (
            "mojeek",
            lambda q: "https://www.mojeek.com/search?"
            + urllib.parse.urlencode({"q": q}),
            _parse_mojeek_html,
        ),
    ]

    # Cap live queries to control rate
    for q in queries[:6]:
        hits: list[dict[str, str]] = []
        engine_used = None
        for eng_name, url_fn, parser in engines:
            try:
                status, body, final = _http_get(url_fn(q), timeout=12.0)
                if status != 200 or not body:
                    continue
                parsed = parser(body) or []
                if parsed:
                    hits = parsed
                    engine_used = eng_name
                    break
            except Exception:
                continue
        for h in hits[:5]:
            title = h.get("title") or ""
            snippet = h.get("snippet") or h.get("body") or ""
            url = h.get("url") or h.get("href") or ""
            out.append(
                {
                    "type": "web_hit",
                    "value": {
                        "title": title,
                        "snippet": snippet,
                        "query": q,
                        "engine": engine_used,
                        "technique": "phone_footprint",
                        "observation_grade": "search_snippet",
                    },
                    "source_name": "phone_footprint",
                    "source_url": url or None,
                    "collected_at": utc_now(),
                    "confidence": 0.45,
                    "tags": [
                        "phone_footprint",
                        "layer_a",
                        "websearch",
                        f"engine:{engine_used or 'none'}",
                        "grade:search_snippet",
                    ],
                    "seed_ids": [seed["id"]],
                    "identifiers": [{"type": "phone", "value": rec.get("normalized")}],
                    "meta": {
                        "query": q,
                        "engine": engine_used,
                        "observation_grade": "search_snippet",
                    },
                }
            )

    # Public wa.me probe (existence not guaranteed by HTTP)
    e164 = rec.get("e164") or ""
    if e164.startswith("+"):
        wa = "https://wa.me/" + e164[1:]
        out.append(
            {
                "type": "phone_link",
                "value": {
                    "service": "whatsapp_wa_me",
                    "url": wa,
                    "note": "Public deep link; profile still needs HITL save-contact",
                    "observation_grade": "portal_metadata",
                },
                "source_name": "phone_footprint",
                "source_url": wa,
                "collected_at": utc_now(),
                "confidence": 0.4,
                "tags": ["phone_footprint", "whatsapp", "layer_a"],
                "seed_ids": [seed["id"]],
                "identifiers": [{"type": "phone", "value": rec.get("normalized")}],
            }
        )

    out.append(
        {
            "type": "phone_hitl_plan",
            "value": hitl_phone_checklist(rec),
            "source_name": "phone_footprint",
            "source_url": None,
            "collected_at": utc_now(),
            "confidence": 0.5,
            "tags": ["phone_footprint", "hitl_checklist", "layer_b"],
            "seed_ids": [seed["id"]],
            "identifiers": [{"type": "phone", "value": rec.get("normalized")}],
        }
    )
    return out


def phone_plan_questions(seed: dict[str, Any]) -> list[dict[str, Any]]:
    """Question templates for clue_analyze when phone seed present."""
    rec = normalize_phone_record(seed.get("value") or seed.get("normalized") or "")
    phone = rec.get("normalized") or seed.get("normalized") or ""
    sid = seed.get("id") or ""
    queries = build_footprint_queries(rec) if rec.get("ok") else [f'"{phone}"']
    return [
        {
            "text": (
                f"Phone clue {phone}: jejak publik (SERP exact variants, wa.me, iklan, PDF) "
                "— bukan breach/NIK?"
            ),
            "priority": 0,
            "dimension": "digital",
            "from_clue_ids": [sid],
            "suggested_sources": ["phone_footprint", "websearch"],
            "suggested_queries": queries[:10],
            "suggested_modules": ["phone_footprint", "websearch"],
            "status": "open",
        },
        {
            "text": (
                f"Phone {phone}: HITL Layer B (wallet name preview / WA meta / contact sync lab) "
                "hanya jika investigasi sah — catat grade app_ui_snippet|operator_observed"
            ),
            "priority": 0,
            "dimension": "identity",
            "from_clue_ids": [sid],
            "suggested_sources": ["hitl", "phone_hitl"],
            "suggested_queries": [],
            "suggested_modules": ["phone_footprint"],
            "status": "open",
        },
        {
            "text": (
                f"Name/handle candidates dari phone {phone}: multi-signal lock ke subjek "
                "(kerja/org/geo) — satu nama e-wallet ≠ civil lock"
            ),
            "priority": 1,
            "dimension": "identity",
            "from_clue_ids": [sid],
            "suggested_sources": ["websearch", "primary_page"],
            "suggested_queries": [],
            "suggested_modules": ["websearch"],
            "status": "open",
        },
        {
            "text": (
                f"Collision/recycled SIM: apakah {phone} muncul di iklan massal / multi-nama?"
            ),
            "priority": 1,
            "dimension": "identity",
            "from_clue_ids": [sid],
            "suggested_sources": ["websearch"],
            "suggested_queries": [f'"{phone}" (jual OR sewa OR WhatsApp OR OLX)'],
            "suggested_modules": ["websearch"],
            "status": "open",
        },
    ]
