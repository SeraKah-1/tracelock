"""Proactive agent loop — continue open cases without being asked.

Scans cases_dir for case JSON with open gaps / open HITL / stale evidence,
then runs continue waves and optional delivery. Complements schedule-driven
cron with case-driven autopilot.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from tracelock.loop import assess_gaps, continue_case
from tracelock.skills.osint_skill import SkillResult, run_osint_skill


def _open_hitl(state: dict[str, Any]) -> int:
    return sum(
        1
        for g in (state.get("hitl_gates") or [])
        if isinstance(g, dict) and g.get("status") == "open"
    )


def scan_cases(cases_dir: Path) -> list[dict[str, Any]]:
    cases_dir = Path(cases_dir)
    if not cases_dir.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for p in sorted(cases_dir.glob("**/*.json")):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(st, dict):
            continue
        if "seeds" not in st and "evidence" not in st:
            continue
        gaps = assess_gaps(st)
        hitl = _open_hitl(st)
        found.append(
            {
                "path": str(p),
                "gaps": gaps,
                "hitl_open": hitl,
                "needs_work": bool(gaps) and hitl == 0,
                "evidence_count": len(st.get("evidence") or []),
            }
        )
    return found


def proactive_tick(
    cases_dir: Path,
    *,
    max_cases: int = 3,
    max_waves: int = 2,
    no_network: bool = False,
    deliver: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Continue cases that still have productive gaps (no open HITL-only stall)."""
    from tracelock.cron.runner import _default_deliver

    results: list[dict[str, Any]] = []
    candidates = [c for c in scan_cases(cases_dir) if c.get("needs_work")]
    for c in candidates[:max_cases]:
        path = Path(c["path"])
        loop = continue_case(path, max_extra_waves=max_waves)
        res = {
            "path": str(path),
            "ok": loop.ok,
            "stop_reason": loop.stop_reason,
            "waves": len(loop.waves),
            "preview": (loop.final_report or "")[:400],
        }
        msg = (
            f"TraceLock proactive continue\ncase={path}\n"
            f"stop={loop.stop_reason} waves={len(loop.waves)}\n\n"
            f"{(loop.final_report or '')[:2500]}"
        )
        if deliver:
            res["deliveries"] = [_default_deliver(t, msg) for t in deliver]
        results.append(res)
    return results


def watch_forever(
    cases_dir: Path,
    *,
    interval_sec: float = 300.0,
    **kwargs: Any,
) -> None:
    print(
        json.dumps(
            {
                "event": "proactive_watch_start",
                "cases_dir": str(cases_dir),
                "interval_sec": interval_sec,
            }
        )
    )
    while True:
        out = proactive_tick(cases_dir, **kwargs)
        if out:
            print(json.dumps({"event": "proactive_tick", "results": out}, indent=2)[:4000])
        time.sleep(interval_sec)
