"""Digital footprint tracking — full checklist without a long user prompt.

Research-aligned workflow (SOCMINT / OSINT cycle):
  scope → normalize identifiers → cross-platform username enum →
  profile/bio pivots → phone Layer-A → SERP packs → archive soft →
  correlate/validate (digital ≠ civil) → HITL walls → graded dossier

User may pass a short phrase; we expand to the same quality as a long prompt.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Platforms commonly reused for handle correlation (public surface only)
PLATFORM_TEMPLATES: dict[str, str] = {
    "instagram": "https://www.instagram.com/{h}/",
    "tiktok": "https://www.tiktok.com/@{h}",
    "threads": "https://www.threads.net/@{h}",
    "x": "https://x.com/{h}",
    "github": "https://github.com/{h}",
    "youtube_at": "https://www.youtube.com/@{h}",
    "facebook": "https://www.facebook.com/{h}",
    "telegram": "https://t.me/{h}",
    "reddit": "https://www.reddit.com/user/{h}",
    "linkedin_in": "https://www.linkedin.com/in/{h}",
}

# Full footprint checklist (anti-lazy: always surface, even if some steps HITL)
FOOTPRINT_CHECKLIST: list[dict[str, str]] = [
    {
        "id": "S1_scope",
        "title": "Scope & seed log",
        "do": "Record exact clue strings; do not invent fields",
    },
    {
        "id": "S2_normalize",
        "title": "Normalize identifiers",
        "do": "Phone→E.164; strip @; parse URLs to platform+handle",
    },
    {
        "id": "S3_username_enum",
        "title": "Cross-platform username enum",
        "do": "Probe same handle on major platforms; log hit/miss/blocked",
    },
    {
        "id": "S4_profile_pivot",
        "title": "Primary profile / bio / link-in-bio",
        "do": "Public bio text, linked sites, dual-handle hints (HITL if login wall)",
    },
    {
        "id": "S5_name_pattern",
        "title": "Name-pattern expansion",
        "do": "If legal name blank: morph nick → given-name hypotheses only",
    },
    {
        "id": "S6_phone_layer_a",
        "title": "Phone Layer-A (if phone seed)",
        "do": "SERP variants + wa.me; prefix = soft geo only",
    },
    {
        "id": "S7_phone_layer_b",
        "title": "Phone Layer-B HITL",
        "do": "E-wallet/contact-sync never auto — operator only",
    },
    {
        "id": "S8_serp",
        "title": "Directed web search pack",
        "do": "Quoted name/handle + platform dorks; multi-engine when available",
    },
    {
        "id": "S9_archive",
        "title": "Archive soft (Wayback/CDX)",
        "do": "Historical URLs if any; institutional PDFs often beat IG snapshots",
    },
    {
        "id": "S10_correlate",
        "title": "Correlate & validate",
        "do": "Multi-signal before civil lock; reject name collisions",
    },
    {
        "id": "S11_hitl",
        "title": "Zero-autonomy gates",
        "do": "Captcha/portal/civil lock → human; never captcha farm",
    },
    {
        "id": "S12_dossier",
        "title": "Graded dossier",
        "do": "Digital vs civil dimensions; open gaps explicit; no silent empty success",
    },
]

_PROMPT_STRIP = re.compile(
    r"^(?:lakukan\s+)?(?:osint|socmint|investigasi|investigate|track|cari|cek|background\s*check)"
    r"(?:\s+(?:ke|pada|untuk|on|to|about))?\s*[:=]?\s*",
    re.I,
)
_PHONE_RE = re.compile(
    r"(?:\+?62|0)\s*[\d\-]{8,18}|\bphone\s*:\s*[+\d\-\s]{8,}",
    re.I,
)
_URL_RE = re.compile(r"https?://[^\s]+", re.I)
_AT_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9._]{2,40})")
_HANDLE_BARE = re.compile(
    r"\b(?:ig|instagram|tiktok|tt|threads|github|gh|twitter|x)\s*[:=/]\s*@?([A-Za-z0-9._]{2,40})\b",
    re.I,
)


def strip_osint_boilerplate(text: str) -> str:
    t = (text or "").strip()
    t = _PROMPT_STRIP.sub("", t).strip()
    t = re.sub(r"^['\"]|['\"]$", "", t).strip()
    return t


def parse_freeform_clue(text: str) -> list[str]:
    """Expand a short user phrase into typed seed list (quality without long prompt)."""
    raw = strip_osint_boilerplate(text)
    if not raw:
        return []
    clues: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip()
        if not s or s in seen:
            return
        seen.add(s)
        clues.append(s)

    # URLs first
    for m in _URL_RE.finditer(raw):
        url = m.group(0).rstrip(").,;")
        add(f"url:{url}")
        host = urlparse(url).netloc.lower()
        path = urlparse(url).path.strip("/")
        if "instagram.com" in host and path:
            h = path.split("/")[0]
            if h and h not in ("p", "reel", "stories"):
                add(f"username:{h}")
        if "tiktok.com" in host and "@" in path:
            h = path.split("@")[-1].split("/")[0]
            if h:
                add(f"username:{h}")
        if "threads.net" in host and path.startswith("@"):
            add(f"username:{path[1:].split('/')[0]}")

    # phones
    for m in _PHONE_RE.finditer(raw):
        chunk = m.group(0)
        if chunk.lower().startswith("phone"):
            add(chunk if ":" in chunk else f"phone:{chunk}")
        else:
            add(f"phone:{chunk}")

    # @handles
    for m in _AT_RE.finditer(raw):
        add(f"username:{m.group(1)}")

    # ig:foo / tiktok:bar
    for m in _HANDLE_BARE.finditer(raw):
        add(f"username:{m.group(1)}")

    # typed seeds already present
    for part in re.split(r"[\n,;]+", raw):
        part = part.strip()
        if re.match(
            r"^(name|nama|username|phone|email|url|other|nim)\s*:",
            part,
            re.I,
        ):
            add(part)

    # residual free text as name or other
    residual = raw
    for m in _URL_RE.finditer(raw):
        residual = residual.replace(m.group(0), " ")
    for m in _PHONE_RE.finditer(raw):
        residual = residual.replace(m.group(0), " ")
    residual = _AT_RE.sub(" ", residual)
    residual = re.sub(r"\b(?:ig|instagram|tiktok|tt|threads)\s*[:=/]\s*@?\w+", " ", residual, flags=re.I)
    residual = re.sub(r"\s+", " ", residual).strip(" :,-")
    # drop short noise
    if residual and len(residual) >= 3:
        if re.match(r"^[A-Za-z][A-Za-z\s\.\']{2,60}$", residual):
            add(f"name:{residual}")
        elif residual.lower() not in (
            "ini",
            "orang",
            "akun",
            "user",
            "subject",
            "target",
        ):
            add(f"other:{residual}")

    if not clues:
        add(f"other:{raw}")
    return clues


def handles_from_clues(clues: list[str]) -> list[str]:
    out: list[str] = []
    for c in clues:
        c = c.strip()
        if c.lower().startswith("username:"):
            out.append(c.split(":", 1)[1].strip().lstrip("@"))
        elif c.lower().startswith("url:"):
            u = c.split(":", 1)[1].strip()
            path = urlparse(u).path.strip("/")
            if "tiktok.com" in u and "@" in path:
                out.append(path.split("@")[-1].split("/")[0])
            elif path and path.split("/")[0] not in ("p", "reel", "stories", "user"):
                h = path.split("/")[0].lstrip("@")
                if re.match(r"^[A-Za-z0-9._]{2,40}$", h):
                    out.append(h)
        elif c.startswith("@"):
            out.append(c[1:])
    # unique preserve order
    seen: set[str] = set()
    uniq = []
    for h in out:
        hl = h.lower()
        if hl not in seen:
            seen.add(hl)
            uniq.append(h)
    return uniq


def platform_urls_for_handle(handle: str) -> dict[str, str]:
    h = handle.lstrip("@")
    return {k: tpl.format(h=h) for k, tpl in PLATFORM_TEMPLATES.items()}


def probe_url(url: str, timeout: float = 8.0) -> dict[str, Any]:
    """Lightweight public probe — status only, no captcha bypass."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "TraceLockFootprint/1.1 (+https://github.com/SeraKah-1/tracelock; research)",
            "Accept": "text/html,application/json,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            body = resp.read(8000)
            text = body.decode("utf-8", errors="ignore")
            title = ""
            m = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
            # soft existence heuristics
            low = text.lower()
            miss = any(
                x in low
                for x in (
                    "page not found",
                    "isn't available",
                    "not found",
                    "doesn't exist",
                    "user not found",
                    "couldn't find",
                )
            )
            return {
                "url": url,
                "http_status": int(code),
                "reachable": True,
                "title": title,
                "likely_missing": miss,
                "grade": "portal_metadata",
            }
    except urllib.error.HTTPError as e:
        return {
            "url": url,
            "http_status": int(e.code),
            "reachable": True,
            "title": "",
            "likely_missing": e.code == 404,
            "grade": "portal_metadata",
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "url": url,
            "http_status": None,
            "reachable": False,
            "title": "",
            "likely_missing": None,
            "grade": "operator_clue",
            "error": str(e)[:120],
        }


def enum_handle_platforms(
    handle: str,
    *,
    platforms: list[str] | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    urls = platform_urls_for_handle(handle)
    if platforms:
        urls = {k: v for k, v in urls.items() if k in platforms}
    results = []
    for name, url in urls.items():
        row = probe_url(url, timeout=timeout)
        row["platform"] = name
        row["handle"] = handle
        results.append(row)
    hits = [
        r
        for r in results
        if r.get("reachable")
        and not r.get("likely_missing")
        and r.get("http_status") not in (404, 410)
    ]
    return {
        "handle": handle,
        "probed": len(results),
        "hit_count": len(hits),
        "hits": hits,
        "all": results,
        "checklist_ref": "S3_username_enum",
    }


def serp_query_pack(clues: list[str], handles: list[str]) -> list[str]:
    qs: list[str] = []
    for h in handles:
        qs.append(f'"{h}"')
        qs.append(f'"{h}" (instagram OR tiktok OR threads OR github OR twitter)')
        qs.append(f"site:instagram.com/{h}")
    for c in clues:
        if c.lower().startswith("name:"):
            n = c.split(":", 1)[1].strip()
            qs.append(f'"{n}"')
            qs.append(f'"{n}" (mahasiswa OR alumni OR linkedin)')
        if c.lower().startswith("phone:"):
            qs.append(f'"{c.split(":", 1)[1].strip()}"')
    # unique
    out: list[str] = []
    seen: set[str] = set()
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def footprint_brief(clues: list[str]) -> dict[str, Any]:
    """Machine + human summary: what short prompt expands into."""
    handles = handles_from_clues(clues)
    return {
        "product": "TraceLock",
        "feature": "digital_footprint",
        "input_clues": clues,
        "handles": handles,
        "checklist": FOOTPRINT_CHECKLIST,
        "serp_queries": serp_query_pack(clues, handles),
        "policy": {
            "public_only": True,
            "digital_ne_civil": True,
            "no_breach_nik": True,
            "anti_lazy_full_checklist": True,
            "short_prompt_ok": True,
        },
        "workflow": [
            "1. Parse short clue → typed seeds",
            "2. Cross-platform username enum (public HTTP)",
            "3. Phone Layer-A if phone present; Layer-B HITL only",
            "4. Name-pattern if no legal name",
            "5. SERP pack + archive soft",
            "6. Correlate; open HITL on walls",
            "7. Graded dossier (gaps explicit)",
        ],
    }
