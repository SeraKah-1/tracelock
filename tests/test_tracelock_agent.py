"""Tests for TraceLock autopilot agent — real shipped entry points."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tracelock.agent import run_agent
from tracelock.demo import main as demo_main
from tracelock.qwen_client import (
    DEFAULT_BASE_URL,
    QwenConfig,
    deployment_fingerprint,
    offline_plan_for_clues,
    plan_with_qwen,
)
from tracelock.tools import REGISTRY, run_tool


@pytest.fixture()
def case_path(tmp_path: Path) -> Path:
    return tmp_path / "case.json"


def test_offline_plan_has_tools_and_hitl():
    plan = offline_plan_for_clues(
        ["username:demo_subject_ig", "phone:0812-5550-0100"]
    )
    assert plan.mode == "offline"
    tools = [s.tool for s in plan.steps]
    assert "init_case" in tools
    assert "normalize_phone" in tools
    assert "report" in tools
    assert plan.steps  # non-empty
    assert plan.provider == "alibaba-cloud-dashscope"
    assert "dashscope" in plan.base_url or plan.base_url == DEFAULT_BASE_URL


def test_deployment_fingerprint_references_alibaba():
    fp = deployment_fingerprint()
    assert fp["cloud_provider"] == "Alibaba Cloud"
    assert "dashscope" in fp["api_base_url"].lower()
    assert fp["proof_module"].endswith("qwen_client.py")
    assert "DASHSCOPE_API_KEY" in fp["auth_env_vars"]


def test_plan_with_qwen_offline_env(monkeypatch):
    monkeypatch.setenv("TRACELOCK_OFFLINE", "1")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    cfg = QwenConfig.from_env()
    assert cfg.offline is True
    plan = plan_with_qwen(["phone:081255500100"], cfg)
    assert plan.mode == "offline"
    assert len(plan.steps) >= 3


def test_tool_init_and_report_dossier(case_path: Path):
    r0 = run_tool("init_case", case_path)
    assert r0["ok"] is True
    r1 = run_tool(
        "analyze_clues",
        case_path,
        clues=["username:demo_subject_ig", "phone:0812-5550-0100"],
    )
    assert r1["ok"] is True
    r2 = run_tool("normalize_phone", case_path, args={"phone": "0812-5550-0100"})
    assert r2["ok"] is True
    assert r2["record"]["e164"].startswith("+62")
    r3 = run_tool("phone_checklist", case_path, args={"phone": "0812-5550-0100"})
    assert r3["ok"] is True
    assert r3.get("hitl") is True
    r4 = run_tool("build_dossier", case_path)
    assert r4["ok"] is True
    assert "dimensions" in r4["dossier"]
    r5 = run_tool("report", case_path)
    assert r5["ok"] is True
    assert r5["report_class"] == "dossier"
    assert "TraceLock Investigation Report" in r5["markdown"]
    assert len(r5["markdown"]) > 100


def test_run_agent_offline_end_to_end(case_path: Path, monkeypatch):
    monkeypatch.setenv("TRACELOCK_OFFLINE", "1")
    cfg = QwenConfig(offline=True, base_url=DEFAULT_BASE_URL, model="offline-stub")
    result = run_agent(
        [
            "username:demo_subject_ig",
            "phone:0812-5550-0100",
            "other:FK demo university fixture",
        ],
        case_path,
        cfg=cfg,
    )
    assert result.ok is True
    assert result.mode == "offline"
    assert len(result.tool_traces) >= 5
    tools = [t.tool for t in result.tool_traces]
    assert "init_case" in tools
    assert "report" in tools
    assert result.report_markdown.strip()
    assert "TraceLock" in result.report_markdown
    assert result.dossier
    assert result.dossier.get("dimensions") or result.to_dict()["dossier"]
    payload = result.to_dict()
    assert payload["track"].startswith("Track 4")
    assert payload["report_markdown"].strip()


def test_demo_main_offline_exit_zero(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("TRACELOCK_OFFLINE", "1")
    out_json = tmp_path / "run.json"
    code = demo_main(
        [
            "run",
            "--offline",
            "--quiet",
            "--json-out",
            str(out_json),
            "--case",
            str(tmp_path / "case.json"),
            "--clue",
            "phone:0812-5550-0100",
            "--clue",
            "username:demo_subject_ig",
        ]
    )
    assert code == 0
    assert out_json.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["mode"] == "offline"
    assert data["report_markdown"].strip()
    assert len(data["tool_traces"]) >= 4
    # stdout also JSON in quiet mode
    captured = capsys.readouterr().out
    assert "report_markdown" in captured


def test_registry_covers_core_tools():
    required = {
        "init_case",
        "analyze_clues",
        "normalize_phone",
        "phone_queries",
        "phone_checklist",
        "plan_sources",
        "open_hitl",
        "build_dossier",
        "report",
    }
    assert required.issubset(set(REGISTRY))


def test_license_and_readme_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "LICENSE").is_file()
    assert "MIT" in (root / "LICENSE").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "TraceLock" in readme
    assert "Qwen" in readme or "DashScope" in readme
    # product-facing docs (not hackathon coaching on the front door)
    assert (root / "docs" / "USAGE.md").is_file()
    assert (root / "docs" / "SCENARIOS.md").is_file()
    assert (root / "docs" / "assets" / "architecture.svg").stat().st_size > 500
    assert (root / "docs" / "DEPLOYMENT.md").is_file()
    proof = (root / "tracelock" / "qwen_client.py").read_text(encoding="utf-8")
    assert "dashscope-intl.aliyuncs.com" in proof
    # README should not tutor "win strategy" / name alternatives
    assert "WIN_STRATEGY" not in readme
    assert "Name alternatives" not in readme
