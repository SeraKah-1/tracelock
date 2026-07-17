"""Clue→questions→sources engine (framework acceptance)."""

import json
import subprocess
import sys
from pathlib import Path

from osint_cli.clue_analyze import analyze_clues, apply_analysis_to_state
from osint_cli.normalize import add_seed
from osint_cli.state import new_investigation

ROOT = Path(__file__).resolve().parents[1]


def _sample_academic_state():
    st = new_investigation("/tmp/plan-sample-subject.json")
    add_seed(st, "name:Jordan Sample Subject")
    add_seed(st, "other:FK CONTOH")
    add_seed(st, "other:SAMPLE_STUDENT_ORG FK CONTOH")
    add_seed(st, "other:Kota Contoh")
    add_seed(st, "other:masuk 2025")
    return st


def test_analyze_emits_pddikti_and_primary_org_routes():
    st = _sample_academic_state()
    a = analyze_clues(st)
    assert a["schema"] == "clue_analysis_v1"
    assert a["summary"]["question_count"] >= 3
    assert a["summary"]["has_academic_route"] is True
    assert a["summary"]["has_primary_org_route"] is True
    blob = json.dumps(a).lower()
    assert "pddikti" in blob
    assert "primary_page" in blob or "social_tags" in blob
    assert a["policy"]["reverse_image_default"] is False
    assert "blind_username_enum_before_handle_candidate" in a["do_not"]
    # geo/year should be lower priority than p0 academic
    p0 = [q for q in a["questions"] if q["priority"] == 0]
    assert any("pddikti" in (q.get("suggested_sources") or []) for q in p0)
    assert any(
        "tag" in q["text"].lower() or "primary" in q["text"].lower() or "sample" in q["text"].lower() or "org" in q["text"].lower()
        for q in p0
    )


def test_apply_merges_questions_into_state():
    st = _sample_academic_state()
    before = len(st.get("questions") or [])
    a = apply_analysis_to_state(st, merge_questions=True)
    assert st.get("clue_analysis")
    assert len(st["questions"]) > before
    assert a.get("questions_merged_ids")


def test_cli_plan_subcommand():
    proc = subprocess.run(
        [sys.executable, "-m", "osint_cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "plan" in proc.stdout

    case = Path("/tmp/cli-plan-case.json")
    if case.exists():
        case.unlink()
    r1 = subprocess.run(
        [sys.executable, "-m", "osint_cli", "-c", str(case), "init", "--force"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0
    r2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "osint_cli",
            "-c",
            str(case),
            "seed",
            "add",
            "name:Jordan Sample Subject",
            "other:FK CONTOH",
            "other:SAMPLE_STUDENT_ORG",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr + r2.stdout
    data = json.loads(r2.stdout)
    assert data.get("plan_summary", {}).get("has_academic_route") is True

    r3 = subprocess.run(
        [sys.executable, "-m", "osint_cli", "-c", str(case), "plan"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r3.returncode == 0, r3.stderr + r3.stdout
    plan = json.loads(r3.stdout)
    assert plan["ok"] is True
    assert plan["action"] == "plan"
    assert plan["analysis"]["summary"]["has_academic_route"] is True
    assert plan["analysis"]["summary"]["has_primary_org_route"] is True
