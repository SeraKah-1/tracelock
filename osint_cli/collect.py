"""Collection modules: websearch, username enum, email registration probe, fixture."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .normalize import add_evidence, platform_from_url
from .state import utc_now


Collector = Callable[[dict[str, Any], dict[str, Any], str | None], list[dict[str, Any]]]

USER_AGENT = "ai-osint-terminal/0.4 (+educational research; agent-cli)"

# Optional third-party maintained wrapper over public PDDIKTI surfaces (not official API).
# Requires PARSE_API_KEY env. See docs/GOV_SOURCES.md.
PARSE_PDDIKTI_BASE = (
    "https://api.parse.bot/scraper/7adc51d7-b63d-45f5-87a7-49a7987989c3"
)


def _http_get(
    url: str,
    timeout: float = 12.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, str | None]:
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,*/*",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        url,
        headers=hdrs,
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(200_000).decode("utf-8", errors="replace")
            return int(resp.status), body, resp.geturl()
    except urllib.error.HTTPError as e:
        body = e.read(50_000).decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), body, url
    except Exception as e:
        raise RuntimeError(str(e)) from e


# --- username enum: public profile URL probes ---------------------------------

# platform -> url template with {u}
USERNAME_SITES: list[tuple[str, str]] = [
    ("github", "https://github.com/{u}"),
    ("gitlab", "https://gitlab.com/{u}"),
    ("reddit", "https://www.reddit.com/user/{u}"),
    ("instagram", "https://www.instagram.com/{u}/"),
    ("x", "https://x.com/{u}"),
    ("tiktok", "https://www.tiktok.com/@{u}"),
    ("medium", "https://medium.com/@{u}"),
    ("keybase", "https://keybase.io/{u}"),
    ("aboutme", "https://about.me/{u}"),
    ("pinterest", "https://www.pinterest.com/{u}/"),
]


def collect_username_enum(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    if seed.get("type") != "username":
        return []
    u = seed["normalized"]
    out: list[dict[str, Any]] = []
    if offline:
        # deterministic fixture hits for known demo usernames
        if u in ("octocat", "torvalds", "demo_user_a"):
            sites = [("github", f"https://github.com/{u}"), ("reddit", f"https://www.reddit.com/user/{u}")]
            for plat, url in sites:
                out.append(
                    {
                        "type": "profile",
                        "value": {"username": u, "platform": plat, "status": "exists"},
                        "source_name": "username_enum",
                        "source_url": url,
                        "collected_at": utc_now(),
                        "confidence": 0.65,
                        "tags": ["username_enum", "fixture" if offline else "live"],
                        "seed_ids": [seed["id"]],
                        "platform": plat,
                        "identifiers": [
                            {"type": "username", "value": u, "platform": plat}
                        ],
                    }
                )
        return out

    for plat, tmpl in USERNAME_SITES:
        url = tmpl.format(u=urllib.parse.quote(u))
        try:
            status, body, final = _http_get(url)
            exists = status == 200 and not _looks_like_missing(plat, body, status)
            if not exists:
                # still record negative as low-conf optional? skip to reduce noise
                continue
            # light parse for display name / bio-ish text
            title = _extract_title(body)
            out.append(
                {
                    "type": "profile",
                    "value": {
                        "username": u,
                        "platform": plat,
                        "status": "exists",
                        "title": title,
                        "http_status": status,
                    },
                    "source_name": "username_enum",
                    "source_url": final or url,
                    "collected_at": utc_now(),
                    "confidence": 0.7,
                    "tags": ["username_enum", "live"],
                    "seed_ids": [seed["id"]],
                    "platform": plat,
                    "identifiers": [
                        {"type": "username", "value": u, "platform": plat}
                    ],
                    "meta": {"title": title},
                }
            )
        except Exception as e:
            out.append(
                {
                    "type": "other",
                    "value": {"error": str(e), "platform": plat, "username": u},
                    "source_name": "username_enum",
                    "source_url": url,
                    "collected_at": utc_now(),
                    "confidence": 0.1,
                    "tags": ["username_enum", "error"],
                    "seed_ids": [seed["id"]],
                    "platform": plat,
                }
            )
    return out


def _looks_like_missing(platform: str, body: str, status: int) -> bool:
    if status in (404, 410):
        return True
    low = body.lower()
    markers = [
        "page not found",
        "doesn't exist",
        "does not exist",
        "not found",
        "sorry, this page isn't available",
        "user not found",
        "account suspended",
        "404",
    ]
    # only treat as missing if strong markers and short-ish body hints
    hits = sum(1 for m in markers if m in low)
    return hits >= 2 and status != 200


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return None
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    return t[:200] if t else None


# --- email registration: public gravatar + simple signals ----------------------


def collect_email_reg(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    if seed.get("type") != "email":
        return []
    email = seed["normalized"]
    out: list[dict[str, Any]] = []
    if offline:
        out.append(
            {
                "type": "registration",
                "value": {"service": "gravatar", "registered": email.endswith("@example.com") is False},
                "source_name": "email_reg",
                "source_url": "https://gravatar.com/",
                "collected_at": utc_now(),
                "confidence": 0.4,
                "tags": ["email_reg", "fixture"],
                "seed_ids": [seed["id"]],
                "identifiers": [{"type": "email", "value": email}],
            }
        )
        # synthetic linked username for escalate demos
        local = email.split("@")[0]
        out.append(
            {
                "type": "profile",
                "value": {
                    "username": local,
                    "platform": "github",
                    "status": "exists",
                    "linked_from": "email_localpart",
                },
                "source_name": "email_reg",
                "source_url": f"https://github.com/{local}",
                "collected_at": utc_now(),
                "confidence": 0.35,
                "tags": ["email_reg", "fixture", "derived_username"],
                "seed_ids": [seed["id"]],
                "platform": "github",
                "identifiers": [
                    {"type": "email", "value": email},
                    {"type": "username", "value": local, "platform": "github"},
                ],
            }
        )
        return out

    # Gravatar: public profile JSON if exists
    import hashlib

    h = hashlib.md5(email.encode("utf-8")).hexdigest()
    gurl = f"https://en.gravatar.com/{h}.json"
    try:
        status, body, final = _http_get(gurl)
        if status == 200:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"raw": body[:500]}
            entry = {}
            if isinstance(data, dict):
                entries = data.get("entry") or []
                if entries:
                    entry = entries[0]
            display = entry.get("displayName") or entry.get("preferredUsername")
            out.append(
                {
                    "type": "registration",
                    "value": {
                        "service": "gravatar",
                        "registered": True,
                        "displayName": display,
                        "preferredUsername": entry.get("preferredUsername"),
                        "profileUrl": entry.get("profileUrl"),
                    },
                    "source_name": "email_reg",
                    "source_url": final or gurl,
                    "collected_at": utc_now(),
                    "confidence": 0.8,
                    "tags": ["email_reg", "live", "gravatar"],
                    "seed_ids": [seed["id"]],
                    "identifiers": [{"type": "email", "value": email}],
                    "meta": {"gravatar": entry},
                }
            )
            pref = entry.get("preferredUsername")
            if pref:
                out.append(
                    {
                        "type": "profile",
                        "value": {
                            "username": str(pref).lower(),
                            "platform": "gravatar",
                            "status": "exists",
                        },
                        "source_name": "email_reg",
                        "source_url": entry.get("profileUrl") or final or gurl,
                        "collected_at": utc_now(),
                        "confidence": 0.75,
                        "tags": ["email_reg", "derived_username"],
                        "seed_ids": [seed["id"]],
                        "platform": "gravatar",
                        "identifiers": [
                            {"type": "email", "value": email},
                            {
                                "type": "username",
                                "value": str(pref).lower(),
                                "platform": "gravatar",
                            },
                        ],
                    }
                )
        else:
            out.append(
                {
                    "type": "registration",
                    "value": {"service": "gravatar", "registered": False, "http_status": status},
                    "source_name": "email_reg",
                    "source_url": gurl,
                    "collected_at": utc_now(),
                    "confidence": 0.5,
                    "tags": ["email_reg", "live"],
                    "seed_ids": [seed["id"]],
                    "identifiers": [{"type": "email", "value": email}],
                }
            )
    except Exception as e:
        out.append(
            {
                "type": "other",
                "value": {"error": str(e), "service": "gravatar"},
                "source_name": "email_reg",
                "source_url": gurl,
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["email_reg", "error"],
                "seed_ids": [seed["id"]],
            }
        )
    return out


# --- websearch: DuckDuckGo HTML (no API key) -----------------------------------


def collect_websearch(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    q_parts = []
    if goal:
        q_parts.append(goal)
    q_parts.append(seed.get("normalized") or seed.get("value") or "")
    query = " ".join(p for p in q_parts if p).strip()
    if not query:
        return []
    if offline:
        return [
            {
                "type": "web_hit",
                "value": {
                    "title": f"Fixture hit for {seed.get('normalized')}",
                    "snippet": f"Offline fixture result for query: {query}",
                    "query": query,
                },
                "source_name": "websearch",
                "source_url": f"https://example.invalid/search?q={urllib.parse.quote(query)}",
                "collected_at": utc_now(),
                "confidence": 0.3,
                "tags": ["websearch", "fixture"],
                "seed_ids": [seed["id"]],
                "identifiers": _ids_from_seed(seed),
            }
        ]

    out: list[dict[str, Any]] = []
    engines_tried: list[str] = []
    hits: list[dict[str, str]] = []
    final_url = None
    engine_used = None

    # Multi-engine fallback (session flaw: DDG empty-parse ≠ no results)
    engine_specs: list[tuple[str, str, Any]] = [
        (
            "duckduckgo",
            "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query}),
            _parse_ddg_html,
        ),
        (
            "bing",
            "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query}),
            _parse_bing_html,
        ),
        (
            "mojeek",
            "https://www.mojeek.com/search?" + urllib.parse.urlencode({"q": query}),
            _parse_mojeek_html,
        ),
    ]

    for eng_name, url, parser in engine_specs:
        engines_tried.append(eng_name)
        try:
            status, body, final = _http_get(url, timeout=14.0)
            final_url = final or url
            if status != 200 or not body:
                continue
            parsed = parser(body) or []
            if parsed:
                hits = parsed
                engine_used = eng_name
                break
        except Exception:
            continue

    if hits:
        for h in hits[:8]:
            out.append(
                {
                    "type": "web_hit",
                    "value": {
                        "title": h.get("title"),
                        "snippet": h.get("snippet"),
                        "query": query,
                        "engine": engine_used,
                        "engines_tried": engines_tried,
                    },
                    "source_name": "websearch",
                    "source_url": h.get("url"),
                    "collected_at": utc_now(),
                    "confidence": 0.45 if engine_used == "duckduckgo" else 0.42,
                    "tags": ["websearch", "live", f"engine_{engine_used}"],
                    "seed_ids": [seed["id"]],
                    "identifiers": _ids_from_seed(seed),
                    "platform": platform_from_url(h.get("url")),
                }
            )
    else:
        out.append(
            {
                "type": "web_hit",
                "value": {
                    "title": None,
                    "snippet": "no_parseable_hits_all_engines",
                    "query": query,
                    "engines_tried": engines_tried,
                },
                "source_name": "websearch",
                "source_url": final_url,
                "collected_at": utc_now(),
                "confidence": 0.15,
                "tags": ["websearch", "empty", "multi_engine"],
                "seed_ids": [seed["id"]],
            }
        )
    return out


def _parse_ddg_html(html: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    # result links
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        href = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        # DDG often wraps uddg=
        if "uddg=" in href:
            qs = urllib.parse.urlparse(href).query
            uddg = urllib.parse.parse_qs(qs).get("uddg", [None])[0]
            if uddg:
                href = urllib.parse.unquote(uddg)
        hits.append({"url": href, "title": title, "snippet": ""})
    # snippets
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)', html, re.I | re.S)
    for i, sn in enumerate(snippets):
        if i < len(hits):
            hits[i]["snippet"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sn)).strip()[:300]
    return hits


def _parse_bing_html(html: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for m in re.finditer(
        r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'(?:<p[^>]*>(.*?)</p>|<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>)',
        html,
        re.I | re.S,
    ):
        href = m.group(1)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        sn = m.group(3) or m.group(4) or ""
        sn = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sn)).strip()[:300]
        if href and title:
            hits.append({"url": href, "title": title, "snippet": sn})
    if not hits:
        # lighter fallback
        for m in re.finditer(
            r'<h2[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            html,
            re.I | re.S,
        ):
            href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
            title = re.sub(r"\s+", " ", title).strip()
            if "bing.com" in href:
                continue
            hits.append({"url": href, "title": title, "snippet": ""})
            if len(hits) >= 8:
                break
    return hits


def _parse_mojeek_html(html: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for m in re.finditer(
        r'<a class="title"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        href = m.group(1)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if href and title:
            hits.append({"url": href, "title": title, "snippet": ""})
    # snippets adjacent
    snippets = re.findall(r'<p class="s"[^>]*>(.*?)</p>', html, re.I | re.S)
    for i, sn in enumerate(snippets):
        if i < len(hits):
            hits[i]["snippet"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sn)).strip()[:300]
    return hits


def _ids_from_seed(seed: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"type": seed.get("type"), "value": seed.get("normalized")}]


def collect_fixture(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = True,
) -> list[dict[str, Any]]:
    """Rich deterministic multi-platform evidence for differentiation tests & demos."""
    out: list[dict[str, Any]] = []
    if seed.get("type") == "username":
        u = seed["normalized"]
        # two platforms same bare username — must NOT auto-merge without signals
        for plat in ("github", "instagram"):
            out.append(
                {
                    "type": "profile",
                    "value": {
                        "username": u,
                        "platform": plat,
                        "status": "exists",
                        "bio": f"fixture bio {plat}",
                    },
                    "source_name": "fixture",
                    "source_url": f"https://{plat}.com/{u}",
                    "collected_at": utc_now(),
                    "confidence": 0.6,
                    "tags": ["fixture"],
                    "seed_ids": [seed["id"]],
                    "platform": plat,
                    "identifiers": [
                        {"type": "username", "value": u, "platform": plat}
                    ],
                }
            )
        # optional linked email on github only (platform-specific)
        out.append(
            {
                "type": "profile",
                "value": {
                    "username": u,
                    "platform": "github",
                    "public_email": f"{u}@users.noreply.github.com",
                },
                "source_name": "fixture",
                "source_url": f"https://github.com/{u}",
                "collected_at": utc_now(),
                "confidence": 0.5,
                "tags": ["fixture", "public_email"],
                "seed_ids": [seed["id"]],
                "platform": "github",
                "identifiers": [
                    {"type": "username", "value": u, "platform": "github"},
                    {
                        "type": "email",
                        "value": f"{u}@users.noreply.github.com",
                    },
                ],
            }
        )
    elif seed.get("type") == "email":
        email = seed["normalized"]
        local = email.split("@")[0]
        out.append(
            {
                "type": "registration",
                "value": {"service": "fixture_svc", "registered": True},
                "source_name": "fixture",
                "source_url": "https://example.invalid/reg",
                "collected_at": utc_now(),
                "confidence": 0.55,
                "tags": ["fixture"],
                "seed_ids": [seed["id"]],
                "identifiers": [{"type": "email", "value": email}],
            }
        )
        out.append(
            {
                "type": "profile",
                "value": {"username": local, "platform": "github", "status": "exists"},
                "source_name": "fixture",
                "source_url": f"https://github.com/{local}",
                "collected_at": utc_now(),
                "confidence": 0.5,
                "tags": ["fixture", "derived_username"],
                "seed_ids": [seed["id"]],
                "platform": "github",
                "identifiers": [
                    {"type": "email", "value": email},
                    {"type": "username", "value": local, "platform": "github"},
                ],
            }
        )
    return out


def collect_pddikti(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """
    Academic needle: search public PDDIKTI / Kemdikti surfaces for a person name.
    Does not bypass captchas; records honest HTTP outcomes + directed query evidence.
    """
    if seed.get("type") not in ("name", "other") and not (
        seed.get("type") == "other" and " " in (seed.get("normalized") or "")
    ):
        # only run meaningfully on name-like seeds
        if seed.get("type") != "name":
            return []
    name = seed.get("normalized") or seed.get("value") or ""
    if not name or len(name) < 3:
        return []
    # skip pure geo/year seeds
    if re.search(r"^(masuk\s+)?20\d{2}$", name.strip(), re.I):
        return []
    if re.search(r"simalungun|perdagangan|sumatera", name, re.I) and " " not in name.strip():
        return []

    out: list[dict[str, Any]] = []
    if offline:
        out.append(
            {
                "type": "public_record",
                "value": {
                    "service": "pddikti",
                    "query_name": name,
                    "status": "offline_fixture",
                    "note": "Offline mode: no live PDDIKTI call; run without --offline for live attempt",
                },
                "source_name": "pddikti",
                "source_url": "https://pddikti.kemdiktisaintek.go.id/",
                "collected_at": utc_now(),
                "confidence": 0.2,
                "tags": ["pddikti", "academic", "fixture"],
                "seed_ids": [seed["id"]],
                "identifiers": [{"type": "name", "value": name}],
            }
        )
        return out

    # Live: try official portal + public search surfaces (best-effort)
    from .hitl import maybe_open_from_collect_block

    portals = [
        "https://pddikti.kemdiktisaintek.go.id/",
        "https://pddikti.kemdikbud.go.id/",
    ]
    for portal in portals:
        try:
            status, body, final = _http_get(portal, timeout=10.0)
            reachable = status == 200 and not _looks_like_challenge(body, status)
            out.append(
                {
                    "type": "public_record",
                    "value": {
                        "service": "pddikti_portal",
                        "query_name": name,
                        "http_status": status,
                        "reachable": reachable,
                        "challenge_wall": not reachable,
                        "note": (
                            "Portal reachable"
                            if reachable
                            else "Browser/captcha wall or blocked — use hitl / browser_cdp / pddikti_api"
                        ),
                    },
                    "source_name": "pddikti",
                    "source_url": final or portal,
                    "collected_at": utc_now(),
                    "confidence": 0.35 if reachable else 0.15,
                    "tags": ["pddikti", "academic", "portal"]
                    + (["challenge_wall"] if not reachable else []),
                    "seed_ids": [seed["id"]],
                    "identifiers": [{"type": "name", "value": name}],
                }
            )
            if not reachable:
                gate = maybe_open_from_collect_block(
                    state,
                    source="pddikti",
                    url=final or portal,
                    body_or_note=body or f"http {status}",
                    seed_ids=[seed["id"]],
                    why=f"PDDIKTI wall for query name={name}",
                )
                if gate:
                    out.append(
                        {
                            "type": "other",
                            "value": {
                                "service": "hitl_gate",
                                "gate_id": gate["id"],
                                "status": gate["status"],
                                "url": gate.get("url"),
                                "command_hint": (
                                    f'hitl complete --gate {gate["id"]} --grade full_page '
                                    f'--value \'{{"nama":"{name}","nim":"…","nama_pt":"…"}}\''
                                ),
                            },
                            "source_name": "hitl",
                            "source_url": gate.get("url"),
                            "collected_at": utc_now(),
                            "confidence": 0.2,
                            "tags": ["hitl", "pddikti", "human_in_loop"],
                            "seed_ids": [seed["id"]],
                        }
                    )
        except Exception as e:
            out.append(
                {
                    "type": "other",
                    "value": {"error": str(e), "service": "pddikti", "portal": portal},
                    "source_name": "pddikti",
                    "source_url": portal,
                    "collected_at": utc_now(),
                    "confidence": 0.1,
                    "tags": ["pddikti", "error"],
                    "seed_ids": [seed["id"]],
                }
            )
            maybe_open_from_collect_block(
                state,
                source="pddikti",
                url=portal,
                body_or_note=str(e),
                seed_ids=[seed["id"]],
            )

    # Directed websearch needles (site: and PDDIKTI keywords)
    for q in (
        f'"{name}" PDDIKTI',
        f'"{name}" site:pddikti.kemdikbud.go.id',
        f'"{name}" site:pddikti.kemdiktisaintek.go.id',
    ):
        # reuse websearch collector logic with synthetic seed value
        fake = dict(seed)
        fake["normalized"] = name
        hits = collect_websearch(state, fake, goal=q, offline=False)
        for h in hits:
            h = dict(h)
            h["tags"] = list(h.get("tags") or []) + ["pddikti", "academic", "directed"]
            h["source_name"] = "pddikti_websearch"
            if isinstance(h.get("value"), dict):
                h["value"] = dict(h["value"])
                h["value"]["pddikti_query"] = q
            out.append(h)
    return out


def _looks_like_challenge(body: str | None, status: int) -> bool:
    if status in (401, 403, 429, 503):
        return True
    text = (body or "").lower()
    needles = (
        "cf-browser-verification",
        "just a moment",
        "memverifikasi browser",
        "checking your browser",
        "cloudflare",
        "attention required",
        "captcha",
        "enable javascript and cookies",
    )
    return any(n in text for n in needles)


def collect_pddikti_api(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """
    Optional PDDIKTI via Parse.bot marketplace wrapper (third-party, not official).
    Auth: env PARSE_API_KEY. Free tier rate limits apply.
    """
    import os

    if seed.get("type") not in ("name", "other"):
        return []
    name = seed.get("normalized") or seed.get("value") or ""
    if not name or len(name) < 3:
        return []
    if re.search(r"^(masuk\s+)?20\d{2}$", name.strip(), re.I):
        return []

    out: list[dict[str, Any]] = []
    if offline:
        out.append(
            {
                "type": "public_record",
                "value": {
                    "service": "pddikti_api",
                    "status": "offline_skip",
                    "provider": "parse.bot",
                },
                "source_name": "pddikti_api",
                "source_url": PARSE_PDDIKTI_BASE + "/search",
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["pddikti", "pddikti_api", "fixture"],
                "seed_ids": [seed["id"]],
            }
        )
        return out

    api_key = os.environ.get("PARSE_API_KEY") or os.environ.get("PARSE_BOT_API_KEY")
    if not api_key:
        out.append(
            {
                "type": "other",
                "value": {
                    "service": "pddikti_api",
                    "status": "missing_api_key",
                    "provider": "parse.bot",
                    "note": (
                        "Set PARSE_API_KEY for optional third-party PDDIKTI wrapper. "
                        "Without key: use pddikti module + hitl complete after real browser."
                    ),
                    "marketplace": (
                        "https://parse.bot/marketplace/"
                        "1b43c018-8c62-47d3-9843-6b24a057ad8b/pddikti-kemdiktisaintek-go-id-api"
                    ),
                    "fallback": "hitl open --source pddikti",
                },
                "source_name": "pddikti_api",
                "source_url": PARSE_PDDIKTI_BASE + "/search",
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["pddikti_api", "needs_key"],
                "seed_ids": [seed["id"]],
            }
        )
        return out

    category = "mahasiswa"
    if goal and re.search(r"\bdosen\b", goal, re.I):
        category = "dosen"
    elif goal and re.search(r"\b(pt|universitas|kampus)\b", goal, re.I):
        category = "pt"

    q = urllib.parse.urlencode({"keyword": name, "category": category})
    url = f"{PARSE_PDDIKTI_BASE}/search?{q}"
    try:
        status, body, final = _http_get(
            url,
            timeout=25.0,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
        )
        parsed: Any = None
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = {"raw_excerpt": (body or "")[:2000]}

        students: list[Any] = []
        if isinstance(parsed, dict):
            data = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            if isinstance(data, dict):
                students = list(data.get("mahasiswa") or data.get("results") or [])
            elif isinstance(parsed.get("mahasiswa"), list):
                students = list(parsed["mahasiswa"])

        idents: list[dict[str, Any]] = [{"type": "name", "value": name}]
        for row in students[:25]:
            if not isinstance(row, dict):
                continue
            if row.get("nama"):
                idents.append({"type": "name", "value": str(row["nama"])})
            if row.get("nim"):
                idents.append({"type": "nim", "value": str(row["nim"])})

        out.append(
            {
                "type": "public_record",
                "value": {
                    "service": "pddikti_api",
                    "provider": "parse.bot",
                    "official_api": False,
                    "query_name": name,
                    "category": category,
                    "http_status": status,
                    "result": parsed,
                    "match_count": len(students),
                    "note": (
                        "Third-party wrapper over public PDDIKTI data — verify important "
                        "claims against official portal via HITL when possible"
                    ),
                },
                "source_name": "pddikti_api",
                "source_url": final or url,
                "collected_at": utc_now(),
                "confidence": 0.72 if status == 200 and students else (0.4 if status == 200 else 0.15),
                "tags": ["pddikti", "pddikti_api", "academic", "third_party_api"],
                "seed_ids": [seed["id"]],
                "identifiers": idents,
                "meta": {
                    "observation_grade": "portal_metadata"
                    if students
                    else "search_snippet"
                },
            }
        )

        # detail first match if student id present
        if students and isinstance(students[0], dict) and students[0].get("id"):
            sid = students[0]["id"]
            dq = urllib.parse.urlencode({"student_id": sid})
            # Parse docs use path-style; try query variants commonly used
            detail_url = f"{PARSE_PDDIKTI_BASE}/get_student_detail?{dq}"
            try:
                d_status, d_body, d_final = _http_get(
                    detail_url,
                    timeout=25.0,
                    headers={"X-API-Key": api_key, "Accept": "application/json"},
                )
                try:
                    d_parsed = json.loads(d_body) if d_body else None
                except json.JSONDecodeError:
                    d_parsed = {"raw_excerpt": (d_body or "")[:2000]}
                out.append(
                    {
                        "type": "public_record",
                        "value": {
                            "service": "pddikti_api_detail",
                            "provider": "parse.bot",
                            "student_id": sid,
                            "http_status": d_status,
                            "result": d_parsed,
                        },
                        "source_name": "pddikti_api",
                        "source_url": d_final or detail_url,
                        "collected_at": utc_now(),
                        "confidence": 0.78 if d_status == 200 else 0.25,
                        "tags": ["pddikti", "pddikti_api", "student_detail"],
                        "seed_ids": [seed["id"]],
                        "identifiers": idents[:10],
                        "meta": {"observation_grade": "portal_metadata"},
                    }
                )
            except Exception as e:
                out.append(
                    {
                        "type": "other",
                        "value": {"error": str(e), "phase": "get_student_detail"},
                        "source_name": "pddikti_api",
                        "source_url": detail_url,
                        "collected_at": utc_now(),
                        "confidence": 0.1,
                        "tags": ["pddikti_api", "error"],
                        "seed_ids": [seed["id"]],
                    }
                )
    except Exception as e:
        out.append(
            {
                "type": "other",
                "value": {"error": str(e), "service": "pddikti_api"},
                "source_name": "pddikti_api",
                "source_url": url,
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["pddikti_api", "error"],
                "seed_ids": [seed["id"]],
            }
        )
    return out


def collect_gov_id(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """
    Passive Indonesian government source pack: portal probes + directed dorks.
    Sources: putusan MA, AHU, LPSE, KPU (+ PDDIKTI dorks). No IDOR, no scanning.
    """
    from .gov_sources import GOV_POLICY, directed_queries
    from .hitl import maybe_open_from_collect_block

    if seed.get("type") not in ("name", "other", "organization"):
        return []
    name = seed.get("normalized") or seed.get("value") or ""
    if not name or len(name) < 3:
        return []
    if re.search(r"^(masuk\s+)?20\d{2}$", name.strip(), re.I):
        return []

    # optional filter via goal: sources=putusan_ma,ahu
    src_filter: list[str] | None = None
    if goal:
        m = re.search(r"sources=([a-z0-9_,]+)", goal, re.I)
        if m:
            src_filter = [x.strip() for x in m.group(1).split(",") if x.strip()]

    out: list[dict[str, Any]] = []
    out.append(
        {
            "type": "other",
            "value": {
                "service": "gov_id",
                "policy": GOV_POLICY,
                "query_name": name,
                "note": "Passive public government routing only",
            },
            "source_name": "gov_id",
            "source_url": None,
            "collected_at": utc_now(),
            "confidence": 0.3,
            "tags": ["gov_id", "policy", "passive"],
            "seed_ids": [seed["id"]],
        }
    )

    if offline:
        out.append(
            {
                "type": "public_record",
                "value": {"service": "gov_id", "status": "offline_fixture", "name": name},
                "source_name": "gov_id",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.15,
                "tags": ["gov_id", "fixture"],
                "seed_ids": [seed["id"]],
            }
        )
        return out

    portal_map = {
        "putusan_ma": "https://putusan3.mahkamahagung.go.id/",
        "ahu": "https://ahu.go.id/",
        "lpse": "https://lpse.lkpp.go.id/",
        "kpu": "https://infopemilu.kpu.go.id/",
        "pddikti": "https://pddikti.kemdiktisaintek.go.id/",
    }
    sources = src_filter or list(portal_map.keys())
    for src in sources:
        portal = portal_map.get(src)
        if not portal:
            continue
        try:
            status, body, final = _http_get(portal, timeout=10.0)
            challenged = _looks_like_challenge(body, status)
            out.append(
                {
                    "type": "public_record",
                    "value": {
                        "service": "gov_id_portal",
                        "source": src,
                        "http_status": status,
                        "challenge_wall": challenged,
                        "query_name": name,
                    },
                    "source_name": "gov_id",
                    "source_url": final or portal,
                    "collected_at": utc_now(),
                    "confidence": 0.3 if status == 200 and not challenged else 0.15,
                    "tags": ["gov_id", src, "portal"]
                    + (["challenge_wall"] if challenged else []),
                    "seed_ids": [seed["id"]],
                    "identifiers": [{"type": "name", "value": name}],
                }
            )
            if challenged or status in (403, 503):
                maybe_open_from_collect_block(
                    state,
                    source=src if src in (
                        "pddikti",
                        "putusan_ma",
                        "ahu",
                        "lpse",
                        "kpu",
                    ) else "generic",
                    url=final or portal,
                    body_or_note=body or f"http {status}",
                    seed_ids=[seed["id"]],
                    why=f"gov_id portal wall: {src} for {name}",
                )
        except Exception as e:
            out.append(
                {
                    "type": "other",
                    "value": {"error": str(e), "source": src, "portal": portal},
                    "source_name": "gov_id",
                    "source_url": portal,
                    "collected_at": utc_now(),
                    "confidence": 0.1,
                    "tags": ["gov_id", "error", src],
                    "seed_ids": [seed["id"]],
                }
            )

    # Directed passive dorks via websearch
    for item in directed_queries(name, sources=sources)[:12]:
        fake = dict(seed)
        fake["normalized"] = name
        hits = collect_websearch(state, fake, goal=item["query"], offline=False)
        for h in hits:
            h = dict(h)
            h["tags"] = list(h.get("tags") or []) + [
                "gov_id",
                item["source"],
                "directed",
                "passive",
            ]
            h["source_name"] = f"gov_id_{item['source']}"
            if isinstance(h.get("value"), dict):
                h["value"] = dict(h["value"])
                h["value"]["gov_query"] = item["query"]
                h["value"]["gov_source"] = item["source"]
            out.append(h)
    return out


def collect_primary_page(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """
    Fetch a URL seed (or URLs in goal) and extract light on-page signals:
    title, outbound links, @mentions, emails — bio/tag/connection style pivots.
    """
    urls: list[str] = []
    if seed.get("type") == "url":
        urls.append(seed.get("normalized") or seed.get("value") or "")
    # also URLs embedded in goal
    if goal:
        urls += re.findall(r"https?://[^\s\"'<>]+", goal)
    urls = [u.rstrip(".,);]") for u in urls if u.startswith("http")]
    # dedupe
    seen: set[str] = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    if not urls:
        return []

    out: list[dict[str, Any]] = []
    if offline:
        for u in urls:
            out.append(
                {
                    "type": "profile",
                    "value": {
                        "url": u,
                        "status": "offline_skip",
                        "note": "primary_page skipped offline",
                    },
                    "source_name": "primary_page",
                    "source_url": u,
                    "collected_at": utc_now(),
                    "confidence": 0.2,
                    "tags": ["primary_page", "fixture"],
                    "seed_ids": [seed["id"]],
                }
            )
        return out

    for u in urls[:5]:
        try:
            status, body, final = _http_get(u, timeout=15.0)
            title = _extract_title(body) if body else None
            links = _extract_outbound_links(body, final or u)[:30]
            html = body or ""
            mentions = sorted(set(re.findall(r"@([A-Za-z0-9_.]{2,32})", html)))[:40]
            emails = sorted(
                set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html))
            )[:20]
            # crude "bio-like" meta description
            bio = None
            m = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                body or "",
                re.I,
            )
            if m:
                bio = re.sub(r"\s+", " ", m.group(1)).strip()[:400]

            idents: list[dict[str, Any]] = []
            for ment in mentions[:15]:
                idents.append(
                    {"type": "username", "value": ment.lower(), "platform": platform_from_url(final or u) or "web"}
                )
            for em in emails[:10]:
                if not re.search(r"example\.(com|invalid)|sentry|wixpress|schema", em, re.I):
                    idents.append({"type": "email", "value": em.lower()})

            out.append(
                {
                    "type": "profile",
                    "value": {
                        "url": final or u,
                        "http_status": status,
                        "title": title,
                        "bio_or_description": bio,
                        "outbound_links": links,
                        "mentions": mentions,
                        "emails_found": emails,
                        "signal_summary": {
                            "n_links": len(links),
                            "n_mentions": len(mentions),
                            "n_emails": len(emails),
                        },
                    },
                    "source_name": "primary_page",
                    "source_url": final or u,
                    "collected_at": utc_now(),
                    "confidence": 0.65 if status == 200 else 0.25,
                    "tags": ["primary_page", "on_page", "bio_tags_links"],
                    "seed_ids": [seed["id"]],
                    "platform": platform_from_url(final or u),
                    "identifiers": idents,
                    "meta": {"parsed": True},
                }
            )
        except Exception as e:
            out.append(
                {
                    "type": "other",
                    "value": {"error": str(e), "url": u},
                    "source_name": "primary_page",
                    "source_url": u,
                    "collected_at": utc_now(),
                    "confidence": 0.1,
                    "tags": ["primary_page", "error"],
                    "seed_ids": [seed["id"]],
                }
            )
    return out


def _extract_outbound_links(html: str, base: str) -> list[str]:
    if not html:
        return []
    hrefs = re.findall(r'href=["\'](https?://[^"\']+)["\']', html, re.I)
    out: list[str] = []
    seen: set[str] = set()
    for h in hrefs:
        if any(x in h for x in ("facebook.com/sharer", "twitter.com/intent", "mailto:", "javascript:")):
            continue
        if h in seen:
            continue
        seen.add(h)
        out.append(h)
    return out


def collect_browser_cdp_module(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    from .browser_cdp import collect_browser_cdp

    return collect_browser_cdp(state, seed, goal=goal, offline=offline)


def collect_tiktok_embed(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """Parse TikTok embed/oembed for signature (bio), nickName, dual-handle pointers.

    Public embed HTML often exposes authorInfos.signature without login.
    Grade: portal_metadata / full_page_embed when signature present.
    """
    if offline:
        return []
    urls: list[str] = []
    if seed.get("type") == "url":
        u = seed.get("normalized") or seed.get("value") or ""
        if "tiktok.com" in u.lower():
            urls.append(u)
    elif seed.get("type") == "username":
        u = (seed.get("normalized") or seed.get("value") or "").lstrip("@")
        if u:
            urls.append(f"https://www.tiktok.com/@{u}")
    else:
        return []

    out: list[dict[str, Any]] = []
    for page_url in urls[:3]:
        # prefer profile embed via oembed + page scrape of /embed if video id known
        video_m = re.search(r"/video/(\d+)", page_url)
        try_urls = []
        if video_m:
            try_urls.append(f"https://www.tiktok.com/embed/v2/{video_m.group(1)}")
        try_urls.append(
            "https://www.tiktok.com/oembed?url=" + urllib.parse.quote(page_url, safe="")
        )
        try_urls.append(page_url)

        signature = None
        nick = None
        unique = None
        user_id = None
        region = None
        stats: dict[str, Any] = {}
        source_used = None
        grade = "portal_metadata"

        for tu in try_urls:
            try:
                status, body, final = _http_get(tu, timeout=14.0)
            except Exception as e:
                out.append(
                    {
                        "type": "other",
                        "value": {"error": str(e), "url": tu},
                        "source_name": "tiktok_embed",
                        "source_url": tu,
                        "collected_at": utc_now(),
                        "confidence": 0.1,
                        "tags": ["tiktok_embed", "error"],
                        "seed_ids": [seed["id"]],
                    }
                )
                continue
            if status >= 400 or not body:
                continue
            source_used = final or tu
            # oembed JSON
            if "oembed" in tu or body.strip().startswith("{"):
                try:
                    data = json.loads(body)
                    nick = data.get("author_name") or nick
                    unique = None
                    if data.get("author_url"):
                        m = re.search(r"@([^/?#]+)", data["author_url"])
                        if m:
                            unique = m.group(1)
                    if data.get("title") and not signature:
                        # title is often video caption, not bio
                        stats["oembed_title"] = data.get("title")
                except Exception:
                    pass
            # embed HTML / page
            sigs = re.findall(r'"signature"\s*:\s*"((?:\\.|[^"\\])*)"', body)
            nicks = re.findall(r'"nickName"\s*:\s*"((?:\\.|[^"\\])*)"', body)
            uniques = re.findall(r'"uniqueId"\s*:\s*"((?:\\.|[^"\\])*)"', body)
            uids = re.findall(r'"authorId"\s*:\s*"(\d+)"|"userId"\s*:\s*"(\d+)"', body)
            regions = re.findall(r'"region"\s*:\s*"([A-Za-z]{2})"', body)
            def _unesc(s: str) -> str:
                try:
                    return bytes(s, "utf-8").decode("unicode_escape")
                except Exception:
                    return s.replace("\\n", "\n")

            if sigs:
                signature = _unesc(sigs[0])
                grade = "full_page_embed"
            if nicks:
                nick = _unesc(nicks[0])
            if uniques:
                unique = uniques[0]
            if uids:
                user_id = uids[0][0] or uids[0][1]
            if regions:
                region = regions[0]
            for key, pat in (
                ("followerCount", r'"followerCount"\s*:\s*(\d+)'),
                ("followingCount", r'"followingCount"\s*:\s*(\d+)'),
                ("videoCount", r'"videoCount"\s*:\s*(\d+)'),
                ("heartCount", r'"heartCount"\s*:\s*(\d+)'),
            ):
                m = re.search(pat, body)
                if m:
                    stats[key] = int(m.group(1))
            if signature or nick or unique:
                break

        # dual-handle pointer: ig: handle in signature
        ig_pointer = None
        age_claim = None
        if signature:
            m_ig = re.search(r"(?i)\big\s*[:：]\s*@?([A-Za-z0-9._]+)", signature)
            if m_ig:
                ig_pointer = m_ig.group(1)
            m_age = re.search(r"(?m)^\s*(\d{2})\s*$", signature.strip().split("\n")[0] if signature else "")
            # first line number as age claim
            first = (signature or "").strip().split("\n")[0].strip()
            if re.fullmatch(r"\d{2}", first):
                age_claim = int(first)

        val = {
            "platform": "tiktok",
            "page_url": page_url,
            "uniqueId": unique,
            "nickName": nick,
            "signature": signature,
            "userId": user_id,
            "region": region,
            "stats": stats,
            "ig_pointer": ig_pointer,
            "age_claim": age_claim,
            "source_fetch": source_used,
        }
        tags = ["tiktok_embed", "profile"]
        if ig_pointer:
            tags.append("dual_handle_pointer")
        if signature:
            tags.append("bio_signature")
        conf = 0.75 if signature else 0.45 if nick else 0.25
        idents = []
        if unique:
            idents.append({"type": "username", "value": unique, "platform": "tiktok"})
        if ig_pointer:
            idents.append({"type": "username", "value": ig_pointer, "platform": "instagram"})
        out.append(
            {
                "type": "profile",
                "value": val,
                "source_name": "tiktok_embed",
                "source_url": source_used or page_url,
                "collected_at": utc_now(),
                "confidence": conf,
                "tags": tags,
                "seed_ids": [seed["id"]],
                "identifiers": idents,
                "meta": {"observation_grade": grade},
            }
        )
    return out


def collect_name_pattern_enum(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """Emit name-pattern matrix evidence from usernames (no network required).

    Does not claim legal identity — hypotheses only for downstream scoring.
    """
    # Run once per collect batch when any username seed present
    if seed.get("type") not in ("username", "name", "url", "other"):
        return []
    # Only attach to first username seed to avoid N duplicate matrices
    users = [s for s in (state.get("seeds") or []) if s.get("type") == "username"]
    if users and seed.get("id") != users[0].get("id"):
        return []
    try:
        from .name_pattern import as_evidence_payload

        payload = as_evidence_payload(state)
    except Exception as e:
        return [
            {
                "type": "other",
                "value": {"error": str(e), "kind": "name_pattern_matrix"},
                "source_name": "name_pattern_enum",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["name_pattern", "error"],
                "seed_ids": [seed["id"]],
            }
        ]
    hyps = payload.get("given_name_hypotheses") or []
    return [
        {
            "type": "other",
            "value": payload,
            "source_name": "name_pattern_enum",
            "source_url": None,
            "collected_at": utc_now(),
            "confidence": 0.55 if hyps else 0.25,
            "tags": ["name_pattern", "hypothesis", "not_legal_identity"],
            "seed_ids": [seed["id"]],
            "meta": {
                "observation_grade": "operator_clue",
                "note": "Morphology hypotheses only — ban treat-as-legal-name",
            },
        }
    ]


def collect_tiktok_comments(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """Public TikTok comment API (no login) with pagination.

    Seed: url containing /video/ID  OR goal video_id=...
    Goal options: max_pages=N (default 5), count=50
    """
    if offline:
        return [
            {
                "type": "other",
                "value": {"kind": "tiktok_comments", "offline": True, "comments": []},
                "source_name": "tiktok_comments",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.2,
                "tags": ["tiktok_comments", "fixture"],
                "seed_ids": [seed["id"]],
            }
        ]

    video_id = None
    url = seed.get("normalized") or seed.get("value") or ""
    m = re.search(r"/video/(\d+)", url)
    if m:
        video_id = m.group(1)
    if goal:
        m2 = re.search(r"video_id\s*=\s*(\d+)", goal)
        if m2:
            video_id = m2.group(1)
        m3 = re.search(r"tiktok\.com/@[^/\s]+/video/(\d+)", goal)
        if m3:
            video_id = m3.group(1)
    if not video_id:
        return []

    max_pages = 5
    count = 50
    if goal:
        mp = re.search(r"max_pages\s*=\s*(\d+)", goal)
        if mp:
            max_pages = min(20, int(mp.group(1)))
        ct = re.search(r"count\s*=\s*(\d+)", goal)
        if ct:
            count = min(50, int(ct.group(1)))

    comments: list[dict[str, Any]] = []
    cursor = 0
    total = None
    for _page in range(max_pages):
        api = "https://www.tiktok.com/api/comment/list/?" + urllib.parse.urlencode(
            {
                "aid": "1988",
                "aweme_id": video_id,
                "count": str(count),
                "cursor": str(cursor),
            }
        )
        try:
            status, body, _final = _http_get(
                api,
                timeout=15.0,
                headers={
                    "Referer": f"https://www.tiktok.com/@x/video/{video_id}",
                    "Accept": "application/json",
                },
            )
        except Exception as e:
            return [
                {
                    "type": "other",
                    "value": {"error": str(e), "video_id": video_id},
                    "source_name": "tiktok_comments",
                    "source_url": api,
                    "collected_at": utc_now(),
                    "confidence": 0.1,
                    "tags": ["tiktok_comments", "error"],
                    "seed_ids": [seed["id"]],
                }
            ]
        if status != 200 or not body:
            break
        try:
            data = json.loads(body)
        except Exception:
            break
        batch = data.get("comments") or []
        total = data.get("total")
        for c in batch:
            user = c.get("user") or {}
            comments.append(
                {
                    "cid": c.get("cid"),
                    "text": c.get("text"),
                    "digg": c.get("digg_count"),
                    "create_time": c.get("create_time"),
                    "unique_id": user.get("unique_id") or user.get("uniqueId"),
                    "nickname": user.get("nickname") or user.get("nickName"),
                }
            )
        if not data.get("has_more") or not batch:
            break
        cursor = data.get("cursor") or (cursor + len(batch))

    # peer-name heuristics for agent
    namey = [
        c
        for c in comments
        if c.get("text")
        and re.search(
            r"\b(nama|nim|angkatan|seangkatan|kak\s+[A-Za-z]{3,}|@\w+)",
            c["text"],
            re.I,
        )
    ]
    return [
        {
            "type": "other",
            "value": {
                "kind": "tiktok_comments",
                "video_id": video_id,
                "total_api": total,
                "scraped": len(comments),
                "comments": comments,
                "interesting_subset": namey[:40],
            },
            "source_name": "tiktok_comments",
            "source_url": f"https://www.tiktok.com/@x/video/{video_id}",
            "collected_at": utc_now(),
            "confidence": 0.7 if comments else 0.3,
            "tags": ["tiktok_comments", "network", "full_page_api"],
            "seed_ids": [seed["id"]],
            "meta": {"observation_grade": "full_page_api"},
        }
    ]


def collect_campus_list_ingest(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """Ingest campus list text from file path or seed body.

    Goal: path=/abs/file.txt  OR  file=...  OR seed value is path / raw text
    Optional: pattern=CEL|CEC for grep (default Cel family)
    """
    from pathlib import Path as P

    from .campus_list import (
        grep_name_family,
        ingest_summary,
        parse_campus_list_text,
    )

    text = None
    source_label = "campus_list"
    path = None
    pattern = None
    blob = f"{goal or ''} {seed.get('normalized') or ''} {seed.get('value') or ''}"
    m = re.search(r"(?:path|file)\s*=\s*(\S+)", blob)
    if m:
        path = m.group(1).strip("\"'")
    mp = re.search(r"pattern\s*=\s*(\S+)", blob)
    if mp:
        pattern = mp.group(1).strip("\"'")

    if path and P(path).is_file():
        text = P(path).read_text(encoding="utf-8", errors="replace")
        source_label = path
    elif seed.get("type") in ("other", "name") and seed.get("value"):
        v = str(seed.get("value") or "")
        if len(v) > 200 and re.search(r"2[0-9]{10}", v):
            text = v
            source_label = "seed_value"
        elif P(v).is_file():
            text = P(v).read_text(encoding="utf-8", errors="replace")
            source_label = v

    if not text:
        # look for prior evidence with campus list raw
        for e in reversed(state.get("evidence") or []):
            val = e.get("value")
            if isinstance(val, dict) and val.get("raw_text") and "campus" in (e.get("tags") or []):
                text = val["raw_text"]
                source_label = e.get("source_url") or "prior_evidence"
                break

    if not text:
        return [
            {
                "type": "other",
                "value": {
                    "kind": "campus_list_ingest",
                    "error": "no_text",
                    "hint": (
                        "collect --modules campus_list_ingest "
                        '--goal "path=/path/to/ept_extract.txt"'
                    ),
                },
                "source_name": "campus_list_ingest",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["campus_list", "error"],
                "seed_ids": [seed["id"]],
            }
        ]

    rows = parse_campus_list_text(text, source_label=source_label)
    greps = grep_name_family(rows, pattern=pattern)
    summary = ingest_summary(rows, greps)
    summary["source_label"] = source_label
    summary["text_chars"] = len(text)
    return [
        {
            "type": "document",
            "value": summary,
            "source_name": "campus_list_ingest",
            "source_url": source_label if source_label.startswith("http") else None,
            "collected_at": utc_now(),
            "confidence": 0.65 if rows else 0.25,
            "tags": ["campus_list", "cohort", "document"],
            "seed_ids": [seed["id"]],
            "meta": {"observation_grade": "full_page" if rows else "blank_after_methods"},
        }
    ]


MODULE_MAP: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "username_enum": collect_username_enum,
    "name_pattern_enum": collect_name_pattern_enum,
    "tiktok_embed": collect_tiktok_embed,
    "tiktok_comments": collect_tiktok_comments,
    "campus_list_ingest": collect_campus_list_ingest,
    "email_reg": collect_email_reg,
    "websearch": collect_websearch,
    "fixture": collect_fixture,
    "pddikti": collect_pddikti,
    "pddikti_api": collect_pddikti_api,
    "primary_page": collect_primary_page,
    "gov_id": collect_gov_id,
    "browser_cdp": collect_browser_cdp_module,
}


def collect_phone_footprint(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
) -> list[dict[str, Any]]:
    from .phone_pivot import collect_phone_footprint as _cpf

    return _cpf(state, seed, goal=goal, offline=offline)


MODULE_MAP["phone_footprint"] = collect_phone_footprint


def run_collect(
    state: dict[str, Any],
    goal: str | None = None,
    modules: list[str] | None = None,
    offline: bool = False,
    seed_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run collection modules against seeds; write evidence into state."""
    allowed = state.get("scope", {}).get("allowed_modules") or list(MODULE_MAP)
    if modules:
        run_mods = [m for m in modules if m in MODULE_MAP and (m in allowed or m in MODULE_MAP)]
        # allow new modules even if old case allowed_modules list is stale
        run_mods = [m for m in run_mods if m in MODULE_MAP]
    else:
        # default: identity-oriented; no blind username_enum unless username seeds exist
        has_user = any(s.get("type") == "username" for s in state.get("seeds") or [])
        has_email = any(s.get("type") == "email" for s in state.get("seeds") or [])
        has_url = any(s.get("type") == "url" for s in state.get("seeds") or [])
        has_name = any(s.get("type") == "name" for s in state.get("seeds") or [])
        has_phone = any(s.get("type") == "phone" for s in state.get("seeds") or [])
        run_mods = ["websearch"]
        if has_name:
            run_mods = ["pddikti", "websearch"]
        if has_url:
            run_mods = list(dict.fromkeys(["primary_page"] + run_mods))
        if has_user:
            run_mods = list(dict.fromkeys(run_mods + ["username_enum", "name_pattern_enum"]))
            # tiktok seeds/urls → embed bio pointer
            has_tt = any(
                s.get("type") == "url" and "tiktok.com" in (s.get("normalized") or "").lower()
                for s in state.get("seeds") or []
            ) or any(
                s.get("type") == "username"
                for s in state.get("seeds") or []
            )
            if has_tt:
                run_mods = list(dict.fromkeys(run_mods + ["tiktok_embed"]))
        if has_email:
            run_mods = list(dict.fromkeys(run_mods + ["email_reg"]))
        if has_phone:
            run_mods = list(dict.fromkeys(["phone_footprint"] + run_mods))
        if offline and "fixture" in (allowed or MODULE_MAP):
            run_mods = ["fixture"] + [m for m in run_mods if m != "fixture"]
        run_mods = [m for m in run_mods if m in MODULE_MAP]

    seeds = state["seeds"]
    if seed_ids:
        seeds = [s for s in seeds if s["id"] in seed_ids]

    # browser_cdp runs once per collect (not per seed) — attach to human browser
    name_like = ("name", "other", "organization")
    added_ids: list[str] = []
    modules_actually: list[str] = []

    if "browser_cdp" in run_mods:
        seed0 = seeds[0] if seeds else {"id": "s0", "type": "other", "normalized": "cdp"}
        fn = MODULE_MAP["browser_cdp"]
        try:
            items = fn(state, seed0, goal=goal, offline=offline)
        except Exception as e:
            items = [
                {
                    "type": "other",
                    "value": {"error": str(e), "module": "browser_cdp"},
                    "source_name": "browser_cdp",
                    "source_url": None,
                    "collected_at": utc_now(),
                    "confidence": 0.05,
                    "tags": ["error"],
                    "seed_ids": [seed0.get("id")],
                }
            ]
        modules_actually.append("browser_cdp")
        for raw in items:
            ev = add_evidence(state, raw)
            if ev:
                added_ids.append(ev["id"])
        run_mods = [m for m in run_mods if m != "browser_cdp"]

    for seed in seeds:
        for mod in run_mods:
            if mod in ("pddikti", "pddikti_api", "gov_id") and seed.get("type") not in name_like:
                continue
            if mod == "tiktok_embed":
                is_tt_url = seed.get("type") == "url" and "tiktok.com" in (
                    seed.get("normalized") or ""
                ).lower()
                is_user = seed.get("type") == "username"
                if not (is_tt_url or is_user):
                    continue
            if mod == "tiktok_comments":
                blob = f"{seed.get('normalized') or ''} {goal or ''}"
                if "/video/" not in blob and "video_id=" not in blob:
                    continue
            if mod == "campus_list_ingest":
                # run once on first seed only
                if seeds and seed.get("id") != seeds[0].get("id"):
                    continue
            if mod == "primary_page":
                goal_has_url = bool(goal and re.search(r"https?://", goal))
                if seed.get("type") != "url" and not goal_has_url:
                    continue
            if mod == "username_enum" and seed.get("type") != "username":
                continue
            if mod == "email_reg" and seed.get("type") != "email":
                continue
            if mod == "phone_footprint" and seed.get("type") != "phone":
                continue
            fn = MODULE_MAP[mod]
            try:
                items = fn(state, seed, goal=goal, offline=offline)
            except TypeError:
                items = fn(state, seed, goal)
            except Exception as e:
                items = [
                    {
                        "type": "other",
                        "value": {"error": str(e), "module": mod},
                        "source_name": mod,
                        "source_url": None,
                        "collected_at": utc_now(),
                        "confidence": 0.05,
                        "tags": ["error"],
                        "seed_ids": [seed["id"]],
                    }
                ]
            modules_actually.append(mod)
            for raw in items:
                ev = add_evidence(state, raw)
                if ev:
                    added_ids.append(ev["id"])

    # unique modules list preserve order
    seen: set[str] = set()
    mods_unique = []
    for m in modules_actually:
        if m not in seen:
            seen.add(m)
            mods_unique.append(m)

    from .hitl import open_gates_summary

    return {
        "modules_run": mods_unique,
        "evidence_ids_added": added_ids,
        "seeds_processed": [s["id"] for s in seeds],
        "offline": offline,
        "goal": goal,
        "open_hitl_gates": open_gates_summary(state),
    }
