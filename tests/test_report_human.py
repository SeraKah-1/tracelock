"""Human report formatter — clean output, synthetic data only."""

from __future__ import annotations

import tempfile
from pathlib import Path

from osint_cli.state import new_investigation, save_state
from osint_cli.normalize import add_seed, add_evidence

from tracelock.report_human import build_human_report
from tracelock.tools import run_tool


def test_human_report_structure():
    td = Path(tempfile.mkdtemp())
    case = td / "case.json"
    st = new_investigation(str(case))
    add_seed(st, "name:Jordan Sample Subject")
    add_seed(st, "username:demo_subject_ig")
    add_evidence(
        st,
        {
            "type": "web_hit",
            "value": {"title": "Jordan Sample Subject — public bio page"},
            "source_name": "websearch",
            "source_url": "https://example.com/jordan",
            "confidence": 0.5,
        },
    )
    add_evidence(
        st,
        {
            "type": "web_hit",
            "value": {"title": "GPS Coordinates Converter - LatLong"},
            "source_name": "websearch",
            "source_url": "https://example.com/noise",
            "confidence": 0.2,
        },
    )
    add_evidence(
        st,
        {
            "type": "username_platform_hit",
            "value": {
                "handle": "demo_subject_ig",
                "platform": "instagram",
                "url": "https://www.instagram.com/demo_subject_ig/",
                "http_status": 200,
            },
            "source_name": "tracelock_agent",
            "confidence": 0.55,
        },
    )
    st["agent_dossier"] = {
        "dimensions": {
            "identity_digital": {"status": "partial", "signals": ["handle seed"]},
            "identity_civil": {"status": "open", "signals": []},
            "phone": {"status": "open", "signals": []},
            "education": {"status": "open", "signals": []},
            "risk_notes": {"status": "open", "signals": ["public-source run"]},
        }
    }
    save_state(st, case)
    packs = build_human_report(st)
    human = packs["human_md"]
    assert "Laporan OSINT" in human
    assert "Ringkasan eksekutif" in human
    assert "Jordan Sample Subject" in human
    assert "instagram" in human.lower()
    # noise filtered
    assert "GPS Coordinates" not in human
    assert "example.com/jordan" in human
    assert "Brief" not in packs["brief_txt"] or "OSINT ringkas" in packs["brief_txt"]
    assert "OSINT ringkas" in packs["brief_txt"]


def test_tool_report_writes_files():
    td = Path(tempfile.mkdtemp())
    case = td / "case.json"
    assert run_tool("init_case", case)["ok"]
    assert run_tool(
        "analyze_clues", case, clues=["name:Jordan Sample Subject", "username:demo_subject_ig"]
    )["ok"]
    assert run_tool("build_dossier", case)["ok"]
    r = run_tool("report", case)
    assert r["ok"] is True
    assert r["report_class"] == "human_report"
    assert "Laporan OSINT" in (r.get("markdown") or "")
    assert r.get("brief")
    assert Path(str(case).replace(".json", ".report.md")).is_file() or (
        case.with_suffix(".report.md").is_file()
    )
