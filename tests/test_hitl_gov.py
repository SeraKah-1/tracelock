"""HITL gates + gov source routing tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from osint_cli.cli import main
from osint_cli.gov_sources import GOV_POLICY, directed_queries
from osint_cli.hitl import complete_gate, open_gate
from osint_cli.state import new_investigation, save_state


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


def test_hitl_open_complete_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "case.json"
        r = _run(["-c", str(case), "init", "--force"])
        assert r["ok"] is True
        r = _run(
            [
                "-c",
                str(case),
                "seed",
                "add",
                "name:Testa Personita",
            ]
        )
        assert r["ok"] is True
        r = _run(
            [
                "-c",
                str(case),
                "hitl",
                "open",
                "--source",
                "pddikti",
                "--why",
                "cloudflare",
            ]
        )
        assert r["ok"] is True
        gate_id = r["gate"]["id"]
        assert gate_id.startswith("g")
        r = _run(["-c", str(case), "hitl", "list", "--status", "open"])
        assert any(g["id"] == gate_id for g in r["gates"])
        r = _run(
            [
                "-c",
                str(case),
                "hitl",
                "complete",
                "--gate",
                gate_id,
                "--grade",
                "full_page",
                "--value",
                json.dumps(
                    {
                        "nama": "TESTA PERSONITA",
                        "nim": "25081109901",
                        "nama_pt": "UNIVERSITAS CONTOH",
                    }
                ),
            ]
        )
        assert r["ok"] is True
        assert r["gate"]["status"] == "completed"
        assert r["evidence"]["id"]
        assert "hitl" in r["evidence"]["tags"]


def test_hitl_import_file():
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "case.json"
        html = Path(td) / "page.html"
        html.write_text("<html><title>PDDIKTI Demo</title><body>OK</body></html>", encoding="utf-8")
        _run(["-c", str(case), "init", "--force"])
        _run(["-c", str(case), "seed", "add", "name:Demo User"])
        r = _run(
            [
                "-c",
                str(case),
                "hitl",
                "import-file",
                "--path",
                str(html),
                "--source",
                "pddikti",
                "--grade",
                "full_page",
            ]
        )
        assert r["ok"] is True
        assert r["gate"]["status"] == "completed"
        assert r["evidence"]["value"].get("title") == "PDDIKTI Demo"


def test_gov_directed_queries_passive():
    qs = directed_queries("Testa Personita", sources=["putusan_ma", "ahu"])
    assert qs
    assert any("putusan3.mahkamahagung" in q["query"] for q in qs)
    assert any("ahu.go.id" in q["query"] for q in qs)
    assert GOV_POLICY["mode"] == "passive_public"
    assert any("IDOR" in x for x in GOV_POLICY["forbid"])
    # queries themselves must stay passive dorks (no id= enumeration patterns)
    blob = " ".join(q["query"] for q in qs)
    assert "?id=" not in blob
    assert "Intruder" not in blob


def test_pddikti_api_missing_key_offlineish():
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "case.json"
        _run(["-c", str(case), "init", "--force"])
        _run(["-c", str(case), "seed", "add", "name:Test Mahasiswa"])
        # ensure no key
        import os

        old = os.environ.pop("PARSE_API_KEY", None)
        old2 = os.environ.pop("PARSE_BOT_API_KEY", None)
        try:
            r = _run(
                [
                    "-c",
                    str(case),
                    "collect",
                    "--modules",
                    "pddikti_api",
                    "--offline",
                ]
            )
            assert r["ok"] is True
            assert "pddikti_api" in r["modules_run"]
        finally:
            if old is not None:
                os.environ["PARSE_API_KEY"] = old
            if old2 is not None:
                os.environ["PARSE_BOT_API_KEY"] = old2


def test_plan_includes_gov_route():
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "case.json"
        _run(["-c", str(case), "init", "--force"])
        _run(
            [
                "-c",
                str(case),
                "seed",
                "add",
                "name:Testa Personita",
                "other:FK CONTOH",
            ]
        )
        r = _run(["-c", str(case), "plan"])
        assert r["ok"] is True
        sources = [s["source"] for s in r["analysis"]["source_plan"]]
        assert "gov_id" in sources or r["analysis"].get("gov_catalog")
        assert r["analysis"]["policy"].get("gov_sources_passive_only") is True


def test_open_gate_helper_direct():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.json"
        state = new_investigation(path)
        g = open_gate(state, source="ahu", why="test")
        assert g["id"] == "g1"
        res = complete_gate(
            state,
            g["id"],
            value={"nama_badan_hukum": "PT DEMO"},
            grade="full_page",
        )
        assert res["gate"]["status"] == "completed"
        save_state(state, path)
