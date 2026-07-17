"""Digital footprint + short-prompt osint expansion (synthetic only)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tracelock.demo import main as demo_main
from tracelock.footprint import (
    FOOTPRINT_CHECKLIST,
    handles_from_clues,
    parse_freeform_clue,
    serp_query_pack,
)
from tracelock.qwen_client import QwenConfig, offline_plan_for_clues
from tracelock.tools import run_tool


def test_parse_short_osint_phrase():
    clues = parse_freeform_clue("lakukan osint ke @demo_subject_ig")
    assert any(c.startswith("username:demo_subject_ig") for c in clues)
    clues2 = parse_freeform_clue("https://www.instagram.com/demo_subject_ig/")
    assert any("demo_subject_ig" in c for c in clues2)
    clues3 = parse_freeform_clue("phone:0812-5550-0100")
    assert any("phone:" in c for c in clues3)


def test_checklist_is_full_anti_lazy():
    assert len(FOOTPRINT_CHECKLIST) >= 10
    ids = {c["id"] for c in FOOTPRINT_CHECKLIST}
    assert "S3_username_enum" in ids
    assert "S12_dossier" in ids


def test_offline_plan_includes_digital_footprint():
    plan = offline_plan_for_clues(["username:demo_subject_ig"])
    tools = [s.tool for s in plan.steps]
    assert "digital_footprint" in tools
    assert "report" in tools


def test_digital_footprint_tool_quick(tmp_path: Path):
    case = tmp_path / "case.json"
    assert run_tool("init_case", case)["ok"]
    assert run_tool(
        "analyze_clues",
        case,
        clues=["username:demo_subject_ig"],
    )["ok"]
    r = run_tool(
        "digital_footprint",
        case,
        clues=["username:demo_subject_ig"],
        args={"quick": True, "timeout": 3},
    )
    assert r["ok"] is True
    assert r["checklist_steps"] >= 10
    assert "demo_subject_ig" in (r.get("handles") or [])
    assert r["serp_query_count"] >= 1


def test_osint_cli_short_prompt():
    td = Path(tempfile.mkdtemp())
    code = demo_main(
        [
            "osint",
            "@demo_subject_ig",
            "--offline",
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
    assert data.get("short_prompt_mode") is True
    assert any("demo_subject_ig" in c for c in data.get("expanded_clues") or [])
    tools = [t["tool"] for t in data.get("tool_traces") or []]
    assert "digital_footprint" in tools
    assert "TraceLock" in (data.get("report_markdown") or "")


def test_handles_and_serp():
    clues = ["username:demo_subject_ig", "name:Jordan Sample Subject"]
    h = handles_from_clues(clues)
    assert "demo_subject_ig" in h
    qs = serp_query_pack(clues, h)
    assert any("demo_subject_ig" in q for q in qs)
