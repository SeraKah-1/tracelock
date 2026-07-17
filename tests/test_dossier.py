"""Tests for person-centric dossier, next planner, identity lock, report."""

import json
import subprocess
import sys
from pathlib import Path

from osint_cli.dossier import (
    add_hypothesis,
    build_dossier_report,
    next_actions,
    reject_candidate,
    render_dossier_markdown,
    resolve_hypothesis,
    set_dimension,
    set_identity_lock,
)
from osint_cli.normalize import add_evidence, add_seed
from osint_cli.state import new_investigation
from osint_cli.differentiate import differentiate

ROOT = Path(__file__).resolve().parents[1]


def test_new_investigation_has_dossier_and_questions():
    st = new_investigation("/tmp/doss-init.json")
    assert st["schema_version"] == "1.2"
    assert "identity" in st["dossier"]["dimensions"]
    assert "education" in st["dossier"]["dimensions"]
    assert len(st["questions"]) >= 5
    assert st["identity_lock"]["locked"] is False
    assert st["scope"]["workflow"]["clue_is_not_goal"] is True


def test_identity_lock_blocks_soft_geo_confirm():
    st = new_investigation("/tmp/doss-lock.json")
    add_seed(st, "username:demo_user_a")
    add_evidence(
        st,
        {
            "type": "profile",
            "value": {"username": "demo_user_a", "platform": "github"},
            "source_name": "fixture",
            "source_url": "https://github.com/demo_user_a",
            "seed_ids": [st["seeds"][0]["id"]],
            "platform": "github",
            "identifiers": [
                {"type": "username", "value": "demo_user_a", "platform": "github"}
            ],
        },
    )
    differentiate(st)
    cid = st["candidates"][0]["id"]
    h = add_hypothesis(st, "Subject from Perdagangan", dimension="geo", from_clue=True)
    try:
        resolve_hypothesis(st, h["id"], "confirmed", method="guess", notes="from clue only")
        assert False, "should block confirm before lock"
    except ValueError as e:
        assert "identity_lock" in str(e).lower() or "identity" in str(e).lower()

    set_identity_lock(st, True, candidate_id=cid, signals=["handle", "profile"])
    resolve_hypothesis(st, h["id"], "blank", method="search name+geo", notes="no public link")
    assert st["hypotheses"][0]["status"] == "blank"
    assert st["dossier"]["dimensions"]["geo"]["status"] == "blank_after_methods"


def test_next_prefers_identity_before_geo():
    st = new_investigation("/tmp/doss-next.json")
    add_seed(st, "name:Someone")
    add_evidence(
        st,
        {
            "type": "web_hit",
            "value": {"title": "Org award Someone"},
            "source_name": "websearch_manual",
            "source_url": "https://example.invalid/award",
            "seed_ids": [st["seeds"][0]["id"]],
            "tags": ["primary_source"],
            "identifiers": [{"type": "name", "value": "Someone"}],
        },
    )
    differentiate(st)
    plan = next_actions(st, limit=10)
    actions = plan["actions"]
    assert actions, plan
    # should not tell agent to confirm geo first
    top = " ".join(json.dumps(a) for a in actions[:4]).lower()
    assert "identity" in top or "select" in top or "lock" in top


def test_reject_and_report_markdown():
    st = new_investigation("/tmp/doss-rep.json")
    add_seed(st, "username:alpha")
    add_evidence(
        st,
        {
            "type": "profile",
            "value": {"username": "alpha", "platform": "github"},
            "source_name": "fixture",
            "source_url": "https://github.com/alpha",
            "seed_ids": [st["seeds"][0]["id"]],
            "platform": "github",
            "identifiers": [
                {"type": "username", "value": "alpha", "platform": "github"}
            ],
        },
    )
    add_evidence(
        st,
        {
            "type": "profile",
            "value": {"username": "alpha", "platform": "instagram"},
            "source_name": "fixture",
            "source_url": "https://instagram.com/alpha",
            "seed_ids": [st["seeds"][0]["id"]],
            "platform": "instagram",
            "identifiers": [
                {"type": "username", "value": "alpha", "platform": "instagram"}
            ],
            "tags": ["collision"],
        },
    )
    differentiate(st)
    assert len(st["candidates"]) >= 2
    # reject one
    other = [c for c in st["candidates"] if c["id"] != st["candidates"][0]["id"]][0]
    reject_candidate(st, other["id"], "platform-only username collision")
    set_identity_lock(
        st, True, candidate_id=st["candidates"][0]["id"], signals=["handle"]
    )
    set_dimension(
        st,
        "org_activity",
        fact="Named in org award post",
        method="primary_source_read",
        evidence_ids=st["candidates"][0]["evidence_ids"][:1],
    )
    rep = build_dossier_report(st)
    assert rep["schema"] == "background_check_dossier_v1"
    assert rep["subject"]["identity_locked"] is True
    assert rep["collisions_rejected"]
    md = render_dossier_markdown(st)
    assert "Background check dossier" in md
    assert "Life dimensions" in md
    assert "Rejected collisions" in md
    # methodology essay markers should not be the main product framing
    assert "clue checklist" not in md.lower() or "not" in md.lower()


def test_cli_next_and_report_subcommands():
    proc = subprocess.run(
        [sys.executable, "-m", "osint_cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    out = proc.stdout
    for name in (
        "next",
        "report",
        "dossier",
        "identity-lock",
        "dimension",
        "timeline",
        "reject",
        "hypothesis",
        "question",
    ):
        assert name in out, name
