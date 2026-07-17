"""Runtime platform probe for CDP / browser automation capability."""

from __future__ import annotations

import platform
import shutil
import sys
from typing import Any


def probe_browser_capability() -> dict[str, Any]:
    """Return whether local Chrome/Playwright CDP is expected to work."""
    machine = platform.machine().lower()
    system = platform.system().lower()
    # Termux / Android often reports aarch64 + linux
    is_android = (
        "android" in system
        or "ANDROID_ROOT" in __import__("os").environ
        or "TERMUX_VERSION" in __import__("os").environ
    )
    is_arm = any(x in machine for x in ("arm", "aarch64", "arm64"))
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    playwright_ok = False
    playwright_err = None
    try:
        import playwright  # noqa: F401

        playwright_ok = True
    except Exception as e:
        playwright_err = str(e)

    # Known failure mode from session: Chrome DevTools MCP binary missing on android arm64
    binary_likely_missing = is_android and is_arm

    recommended = []
    if binary_likely_missing or (is_arm and not chromium):
        recommended.extend(
            [
                "hitl import-file — paste HTML/JSON after opening portal in phone browser",
                "hitl complete --gate gN --grade full_page --value '{...}'",
                "collect --modules tiktok_embed,tiktok_comments (no Chrome binary)",
                "Remote x86_64 host with Chrome --remote-debugging-port=9222 if needed",
            ]
        )
    else:
        recommended.extend(
            [
                "chromium --remote-debugging-port=9222 --user-data-dir=$HOME/chrome-osint-profile",
                "collect --modules browser_cdp",
            ]
        )

    return {
        "ok": True,
        "python": sys.version.split()[0],
        "system": system,
        "machine": machine,
        "is_android": is_android,
        "is_arm": is_arm,
        "chromium_path": chromium,
        "playwright_importable": playwright_ok,
        "playwright_error": playwright_err,
        "cdp_binary_likely_unavailable": binary_likely_missing,
        "prefer_hitl_over_cdp": bool(binary_likely_missing or not chromium),
        "recommended_path": recommended,
        "note": (
            "On Android/Termux arm64, Chrome DevTools MCP / desktop Chrome binaries often fail; "
            "use HITL import or public embed/API collectors instead of forcing CDP."
        ),
    }
