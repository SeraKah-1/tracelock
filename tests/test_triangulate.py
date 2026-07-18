"""Triangulation / lead graph unit tests."""

from __future__ import annotations

from tracelock.triangulate import (
    extract_leads_from_text,
    promote_leads,
    next_collect_modules,
)


def test_extract_handle_and_place():
    text = "bio: ig.com/foo_bar and lives in Bandung @friend_one"
    leads = extract_leads_from_text(text, source="bio")
    kinds = {L["kind"] for L in leads}
    assert "handle" in kinds
    assert "place" in kinds
    vals = {L["value"].lower() for L in leads if L["kind"] == "handle"}
    assert "foo_bar" in vals or "friend_one" in vals


def test_promote_leads_adds_seeds():
    state = {
        "seeds": [{"type": "username", "value": "demo_subject_ig", "normalized": "demo_subject_ig"}],
        "evidence": [
            {
                "type": "web_hit",
                "value": {
                    "title": "See also @second_account on campus",
                    "snippet": "Universitas Demo mahasiswa",
                    "url": "https://instagram.com/second_account",
                },
                "source_name": "websearch",
            }
        ],
    }
    tri = promote_leads(state, max_new_seeds=5, min_priority=0.5)
    assert tri["promoted_count"] >= 1
    assert state.get("lead_graph", {}).get("nodes")
    mods = next_collect_modules(state)
    assert "websearch" in mods


def test_cli_find_help():
    from tracelock.demo import main
    import io
    import sys

    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = main(["find", "--help"])
    finally:
        sys.stdout = old
    assert rc == 0
    assert "find" in buf.getvalue().lower() or "clue" in buf.getvalue().lower()
