"""Optional Cyborg Mode: attach to a real Chrome via CDP after human unlock.

Default agent path is HITL paste/import. This module is opt-in:
  1) Operator: chromium --remote-debugging-port=9222 --user-data-dir=...
  2) Operator: open portal, pass Cloudflare, land on results
  3) Agent: collect --modules browser_cdp

Requires either:
  - stdlib only for /json/list tab discovery, or
  - playwright (optional extra) for full DOM extract via connect_over_cdp

Never solves captchas. Never launches aggressive scanners.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .state import utc_now

DEFAULT_CDP = "http://127.0.0.1:9222"
USER_AGENT = "ai-osint-terminal/0.4 (+educational; cdp-attach)"


def normalize_cdp_http(endpoint: str | None) -> str:
    ep = (endpoint or DEFAULT_CDP).strip().rstrip("/")
    if ep.startswith("ws://") or ep.startswith("wss://"):
        # convert ws host to http for /json/list
        ep = "http://" + ep.split("://", 1)[1]
        ep = ep.split("/")[0]
        if not ep.startswith("http"):
            ep = "http://" + ep
    if not ep.startswith("http"):
        ep = "http://" + ep
    return ep.rstrip("/")


def list_cdp_targets(endpoint: str | None = None, timeout: float = 5.0) -> dict[str, Any]:
    """List open tabs via Chrome DevTools HTTP /json/list (no Playwright needed)."""
    base = normalize_cdp_http(endpoint)
    url = f"{base}/json/list"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000).decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "error": f"CDP not reachable at {base}: {e}",
            "hint": (
                "Start Chrome/Chromium with "
                f"--remote-debugging-port={urlparse(base).port or 9222} "
                "--user-data-dir=$HOME/chrome-osint-profile"
            ),
            "endpoint": base,
            "targets": [],
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "endpoint": base, "targets": []}

    targets = []
    if isinstance(data, list):
        for t in data:
            if not isinstance(t, dict):
                continue
            targets.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "url": t.get("url"),
                    "type": t.get("type"),
                    "webSocketDebuggerUrl": t.get("webSocketDebuggerUrl"),
                }
            )
    return {"ok": True, "endpoint": base, "targets": targets, "count": len(targets)}


def extract_via_playwright(
    endpoint: str | None = None,
    *,
    url_contains: str | None = None,
    timeout_ms: int = 15_000,
) -> dict[str, Any]:
    """Attach with Playwright connect_over_cdp and extract light page signals."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return {
            "ok": False,
            "error": "playwright not installed",
            "hint": "pip install playwright && playwright install chromium  (optional)",
            "fallback": "Use hitl complete / hitl import-file after manual browser unlock",
        }

    base = normalize_cdp_http(endpoint)
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(base)
            contexts = browser.contexts
            if not contexts:
                return {"ok": False, "error": "no browser contexts on CDP endpoint", "endpoint": base}
            pages = []
            for ctx in contexts:
                pages.extend(ctx.pages)
            if not pages:
                return {"ok": False, "error": "no open pages", "endpoint": base}

            page = pages[0]
            if url_contains:
                for pg in pages:
                    if url_contains.lower() in (pg.url or "").lower():
                        page = pg
                        break

            # Do not navigate away if already on useful page; only wait load
            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass

            title = page.title()
            url = page.url
            # light extract — avoid dumping secrets-heavy forms blindly
            body_text = ""
            try:
                body_text = page.inner_text("body")[:20_000]
            except Exception:
                body_text = ""
            html = ""
            try:
                html = page.content()[:80_000]
            except Exception:
                html = ""

            emails = sorted(
                set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", body_text))
            )[:30]
            mentions = sorted(set(re.findall(r"@([A-Za-z0-9_.]{2,32})", body_text)))[:40]

            return {
                "ok": True,
                "endpoint": base,
                "url": url,
                "title": title,
                "text_excerpt": body_text[:12_000],
                "html_excerpt_len": len(html),
                "emails_found": emails,
                "mentions": mentions,
                "pages_open": [{"url": pg.url, "title": pg.title()} for pg in pages[:20]],
                "method": "playwright_connect_over_cdp",
                "note": "Human must have already passed captcha/challenge in this browser",
            }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "endpoint": base,
            "hint": "Ensure Chrome is running with remote debugging and a tab is open",
        }


def collect_browser_cdp(
    state: dict[str, Any],
    seed: dict[str, Any],
    goal: str | None = None,
    offline: bool = False,
    *,
    cdp_endpoint: str | None = None,
    url_contains: str | None = None,
) -> list[dict[str, Any]]:
    """Collector entry: platform probe + list CDP tabs + optional Playwright extract."""
    if offline:
        return [
            {
                "type": "other",
                "value": {"service": "browser_cdp", "status": "offline_skip"},
                "source_name": "browser_cdp",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.1,
                "tags": ["browser_cdp", "fixture"],
                "seed_ids": [seed["id"]],
            }
        ]

    from .platform_probe import probe_browser_capability

    probe = probe_browser_capability()
    out: list[dict[str, Any]] = [
        {
            "type": "other",
            "value": {"service": "browser_cdp", "phase": "platform_probe", **probe},
            "source_name": "browser_cdp",
            "source_url": None,
            "collected_at": utc_now(),
            "confidence": 0.9,
            "tags": ["browser_cdp", "platform_probe"],
            "seed_ids": [seed["id"]],
        }
    ]

    # Hard skip CDP attach on known-broken platforms unless goal forces cdp_force=1
    force = bool(goal and re.search(r"cdp_force\s*=\s*1", goal, re.I))
    if probe.get("prefer_hitl_over_cdp") and not force:
        out.append(
            {
                "type": "other",
                "value": {
                    "service": "browser_cdp",
                    "phase": "skipped_platform",
                    "reason": "cdp_binary_likely_unavailable_or_no_chromium",
                    "recommended_path": probe.get("recommended_path"),
                    "note": probe.get("note"),
                    "override": "pass cdp_force=1 in --goal to attempt CDP anyway",
                },
                "source_name": "browser_cdp",
                "source_url": None,
                "collected_at": utc_now(),
                "confidence": 0.85,
                "tags": ["browser_cdp", "skipped", "prefer_hitl"],
                "seed_ids": [seed["id"]],
            }
        )
        return out

    # allow goal to carry cdp= and url_contains=
    ep = cdp_endpoint
    uc = url_contains
    if goal:
        m = re.search(r"cdp=(\S+)", goal)
        if m:
            ep = m.group(1).rstrip(",;")
        m2 = re.search(r"url_contains=(\S+)", goal)
        if m2:
            uc = m2.group(1).rstrip(",;")

    listing = list_cdp_targets(ep)

    out.append(
        {
            "type": "other",
            "value": {
                "service": "browser_cdp",
                "phase": "tab_list",
                **listing,
                "collected_at_note": utc_now(),
            },
            "source_name": "browser_cdp",
            "source_url": listing.get("endpoint"),
            "collected_at": utc_now(),
            "confidence": 0.5 if listing.get("ok") else 0.15,
            "tags": ["browser_cdp", "cdp", "cyborg", "tab_list"],
            "seed_ids": [seed["id"]],
        }
    )

    if not listing.get("ok"):
        # enrich failure with HITL fallback
        listing_hint = dict(listing)
        listing_hint["fallback"] = probe.get("recommended_path")
        out[-1]["value"] = {
            "service": "browser_cdp",
            "phase": "tab_list",
            **listing_hint,
        }
        return out

    # Prefer extract if playwright available
    extracted = extract_via_playwright(ep, url_contains=uc)
    conf = 0.8 if extracted.get("ok") else 0.35
    out.append(
        {
            "type": "profile" if extracted.get("ok") else "other",
            "value": {
                "service": "browser_cdp",
                "phase": "extract",
                **extracted,
            },
            "source_name": "browser_cdp",
            "source_url": extracted.get("url") or listing.get("endpoint"),
            "collected_at": utc_now(),
            "confidence": conf,
            "tags": [
                "browser_cdp",
                "cdp",
                "cyborg",
                "full_page" if extracted.get("ok") else "portal_metadata",
            ],
            "seed_ids": [seed["id"]],
            "identifiers": _idents_from_extract(extracted),
            "meta": {
                "observation_grade": "full_page" if extracted.get("ok") else "portal_metadata"
            },
        }
    )
    return out


def _idents_from_extract(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    idents: list[dict[str, Any]] = []
    for em in extracted.get("emails_found") or []:
        idents.append({"type": "email", "value": em.lower()})
    for ment in extracted.get("mentions") or []:
        idents.append({"type": "username", "value": ment.lower(), "platform": "web"})
    title = extracted.get("title")
    if title and len(title) > 3:
        idents.append({"type": "other", "value": title[:200]})
    return idents
