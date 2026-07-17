"""Digital vs civil identity lock split."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from osint_cli.cli import main
from osint_cli.dossier import ensure_dossier, set_identity_lock, build_dossier_report
from osint_cli.state import new_investigation


def _run(argv: list[str]) -> dict:
    import sys
    from io import StringIO

    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    data = json.loads(buf.getvalue() or "{}")
    data["_exit"] = code
    return data


def test_digital_lock_leaves_civil_open():
    with tempfile.TemporaryDirectory() as td:
        state = new_investigation(str(Path(td) / "c.json"))
    ensure_dossier(state)
    state["candidates"] = [
        {"id": "c1", "label": "cell!", "status": "active", "score": 1, "evidence_ids": [], "identifiers": []}
    ]
    lock = set_identity_lock(
        state,
        locked=True,
        candidate_id="c1",
        signals=["dual_handle_pointer", "display_name_chain"],
        kind="digital",
        notes="IG×TT same person",
    )
    assert lock["digital"]["locked"] is True
    assert lock["civil"]["locked"] is False
    assert lock["locked"] is True  # compat: digital drives top-level
    assert lock["civil_open"] is True
    report = build_dossier_report(state)
    assert report["subject"]["digital_locked"] is True
    assert report["subject"]["civil_locked"] is False
    assert report["subject"]["civil_open"] is True
    assert report["subject"]["lock_note"]


def test_civil_lock_via_cli():
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "inv.json"
        _run(["-c", str(case), "init", "--force"])
        _run(["-c", str(case), "seed", "add", "name:Test Subject"])
        _run(
            [
                "-c",
                str(case),
                "evidence",
                "add",
                "--type",
                "profile",
                "--grade",
                "search_snippet",
                "--value",
                json.dumps({"name": "Test Subject"}),
                "--identifier",
                "name:Test Subject",
            ]
        )
        # differentiate may need more — create candidate manually via fixture collect
        _run(["-c", str(case), "collect", "--modules", "fixture", "--offline"])
        _run(["-c", str(case), "differentiate"])
        st = _run(["-c", str(case), "status"])
        # pick any candidate if present
        # force lock via python if no candidate
        from osint_cli.state import load_state, save_state

        state = load_state(case)
        ensure_dossier(state)
        if not state.get("candidates"):
            state["candidates"] = [
                {
                    "id": "c1",
                    "label": "Test Subject",
                    "status": "active",
                    "score": 1,
                    "evidence_ids": [],
                    "identifiers": [{"type": "name", "value": "Test Subject"}],
                }
            ]
            save_state(state)
        r = _run(
            [
                "-c",
                str(case),
                "identity-lock",
                "--candidate",
                "c1",
                "--kind",
                "civil",
                "--signal",
                "nim_match",
                "--signal",
                "name_consistency",
            ]
        )
        assert r["ok"] is True
        assert r["identity_lock"]["civil"]["locked"] is True
        assert r["identity_lock"]["digital"]["locked"] is False
