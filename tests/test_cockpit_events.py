"""Events + HITL complete + cockpit API (stdlib) — non-breaking improvements."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tracelock.agent import run_agent
from tracelock.events import EventLog, make_event_callback
from tracelock.qwen_client import QwenConfig


def test_event_log_emit_and_since(tmp_path: Path):
    log = EventLog(jsonl_path=tmp_path / "e.jsonl")
    log.emit("run_start", "hi")
    log.emit("tool_end", "done", tool="report", ok=True)
    assert len(log.snapshot()) == 2
    assert len(log.since(0)) == 2
    assert len(log.since(1)) == 1
    lines = (tmp_path / "e.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_run_agent_emits_hitl_events(tmp_path: Path):
    log = EventLog()
    case = tmp_path / "case.json"
    cfg = QwenConfig(offline=True)
    result = run_agent(
        ["phone:0811-6060-0613", "username:demo_subject_ig"],
        case,
        cfg=cfg,
        on_event=make_event_callback(log),
    )
    assert result.ok
    kinds = [e["kind"] for e in log.snapshot()]
    assert "run_start" in kinds
    assert "plan" in kinds
    assert "tool_start" in kinds
    assert "tool_end" in kinds
    assert "run_end" in kinds
    # phone checklist opens HITL
    assert "hitl_open" in kinds
    # existing contract preserved
    assert "TraceLock" in result.report_markdown


def test_hitl_complete_cli_path(tmp_path: Path):
    from osint_cli.hitl import complete_gate, list_gates
    from osint_cli.state import load_state, save_state

    case = tmp_path / "case.json"
    cfg = QwenConfig(offline=True)
    run_agent(["phone:0811-6060-0613"], case, cfg=cfg)
    st = load_state(case)
    open_g = list_gates(st, status="open")
    assert open_g, "expected at least one open HITL gate from phone checklist"
    gid = open_g[0]["id"]
    complete_gate(
        st,
        gid,
        value={"operator": "done", "technique": "B1_demo"},
        grade="operator_clue",
    )
    save_state(st, case)
    st2 = load_state(case)
    g = next(x for x in st2["hitl_gates"] if x["id"] == gid)
    assert g["status"] == "completed"


def test_cockpit_api_run_and_events(tmp_path: Path):
    from tracelock.cockpit import CockpitState, make_handler
    from http.server import ThreadingHTTPServer

    case = tmp_path / "case.json"
    work = tmp_path / "work"
    work.mkdir()
    state = CockpitState(case_path=case, work_dir=work)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        # homepage
        with urlopen(base + "/", timeout=5) as r:
            html = r.read().decode("utf-8")
        assert "TraceLock Cockpit" in html
        assert "HITL" in html

        body = json.dumps(
            {
                "clues": ["phone:0811-6060-0613", "username:demo_subject_ig"],
                "offline": True,
            }
        ).encode()
        req = Request(
            base + "/api/run",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=5) as r:
            started = json.loads(r.read().decode())
        assert started.get("ok") is True

        # wait for run
        deadline = time.time() + 30
        while time.time() < deadline:
            with urlopen(base + "/api/status", timeout=5) as r:
                st = json.loads(r.read().decode())
            if not st.get("running") and st.get("report_markdown"):
                break
            time.sleep(0.2)
        assert st.get("report_markdown")
        assert "TraceLock" in st["report_markdown"]
        # open gates may still be present after run
        with urlopen(base + "/api/events?since=0", timeout=5) as r:
            ev = json.loads(r.read().decode())
        kinds = {e["kind"] for e in ev.get("events") or []}
        assert "plan" in kinds or "run_start" in kinds

        if st.get("open_gates"):
            gid = st["open_gates"][0]["id"]
            cbody = json.dumps(
                {
                    "gate_id": gid,
                    "value": {"operator": "captcha_done"},
                    "grade": "operator_clue",
                }
            ).encode()
            creq = Request(
                base + "/api/hitl/complete",
                data=cbody,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(creq, timeout=5) as r:
                done = json.loads(r.read().decode())
            assert done.get("ok") is True
    finally:
        httpd.shutdown()
