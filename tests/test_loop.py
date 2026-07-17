"""Continuous investigation loop (synthetic, no-network)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from tracelock.demo import main as demo_main
from tracelock.loop import (
    assess_gaps,
    checklist_coverage,
    investigate_continuous,
    propose_next_actions,
)
from tracelock.qwen_client import QwenConfig


def test_assess_gaps_name_without_web():
    state = {
        "seeds": [{"type": "name", "value": "Jordan Sample Subject"}],
        "evidence": [],
        "report_markdown": "",
    }
    gaps = assess_gaps(state)
    assert "name_seed_needs_more_public_serp" in gaps or "no_report_yet" in gaps
    acts = propose_next_actions(state, gaps)
    assert any(a["tool"] == "collect_public" for a in acts)


def test_investigate_continuous_no_network():
    os.environ["TRACELOCK_NO_NETWORK"] = "1"
    os.environ["TRACELOCK_OFFLINE"] = "1"
    os.environ.pop("TRACELOCK_USE_QWEN", None)
    td = Path(tempfile.mkdtemp())
    case = td / "case.json"
    loop = investigate_continuous(
        "username:demo_subject_ig",
        case,
        cfg=QwenConfig(offline=True, no_network=True, provider="local-planner"),
        max_waves=3,
        min_waves=2,
    )
    assert loop.ok
    assert len(loop.waves) >= 2
    assert loop.case_path
    assert loop.checklist_coverage.get("total", 0) >= 10
    assert "Continuous investigation loop" in (loop.final_report or "")


def test_investigate_cli():
    td = Path(tempfile.mkdtemp())
    code = demo_main(
        [
            "investigate",
            "@demo_subject_ig",
            "--no-network",
            "--max-waves",
            "3",
            "--min-waves",
            "2",
            "--quiet",
            "--case",
            str(td / "case.json"),
            "--json-out",
            str(td / "out.json"),
        ]
    )
    assert code == 0
    data = json.loads((td / "out.json").read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["mode"] == "continuous_investigate"
    assert len(data["waves"]) >= 2
