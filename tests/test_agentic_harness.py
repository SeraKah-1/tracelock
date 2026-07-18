"""Tests for TraceLock gateway/cron/skills (no live network, no full multi-wave)."""

from __future__ import annotations

import os
from pathlib import Path

from tracelock.core_tools import CORE_OSINT, list_toolset, slim_summary
from tracelock.cron.jobs import (
    JobStore,
    add_job,
    compute_next_run,
    list_jobs,
    parse_interval_seconds,
    remove_job,
)
from tracelock.gateway.runner import GatewayConfig, handle_inbound_text
from tracelock.skills.osint_skill import SkillResult, skill_manifest


def test_core_toolset_nonempty():
    s = slim_summary()
    assert "collect_public" in s["core"]
    assert "report" in s["core"]
    assert list_toolset("osint_core") == list(CORE_OSINT)
    assert "runtime" in s


def test_skill_manifest():
    m = skill_manifest()
    assert m["name"] == "osint-investigate"
    assert "osint" in m["triggers"]


def test_skill_result_message():
    r = SkillResult(
        ok=True,
        skill="osint-investigate",
        case_path="/tmp/case.json",
        report_brief="Subject footprint summary.",
        stop_reason="done",
        waves=2,
        hitl_open=0,
    )
    msg = r.to_message()
    assert "TraceLock" in msg
    assert "footprint" in msg


def test_interval_parse():
    assert parse_interval_seconds("interval:30m") == 1800
    assert parse_interval_seconds("interval:1h") == 3600
    assert parse_interval_seconds("interval:2d") == 172800
    assert parse_interval_seconds("@startup") is None
    assert compute_next_run("interval:1h") > 0


def test_job_store_roundtrip(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    j = add_job(
        "t1",
        "interval:1h",
        "username:demo_fixture",
        deliver=["stdout"],
        store=store,
    )
    assert j.id
    jobs = list_jobs(store)
    assert len(jobs) == 1
    assert jobs[0]["prompt"] == "username:demo_fixture"
    assert remove_job(j.id, store=store)
    assert list_jobs(store) == []


def test_handle_inbound_help():
    cfg = GatewayConfig(no_network=True, cases_dir="/tmp/tl-cases-test")
    out = handle_inbound_text("/help", cfg=cfg)
    assert "TraceLock" in out
    assert "/osint" in out


def test_handle_inbound_status():
    cfg = GatewayConfig(no_network=True, cases_dir="/tmp/tl-cases-test")
    out = handle_inbound_text("/status", cfg=cfg)
    assert "gateway" in out.lower() or "TraceLock" in out or "osint" in out.lower()


def test_email_outbox(tmp_path: Path, monkeypatch=None):
    home = tmp_path / "home"
    if monkeypatch is not None:
        monkeypatch.setenv("TRACELOCK_HOME", str(home))
    else:
        os.environ["TRACELOCK_HOME"] = str(home)
    from tracelock.gateway.adapters.email_file import queue_email

    r = queue_email("ops@example.com", "subj", "body hello")
    assert r["ok"]
    assert Path(r["path"]).is_file()


def test_cli_core_and_gateway_status():
    from tracelock.demo import main
    import io
    import sys

    # core
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = main(["core"])
    finally:
        sys.stdout = old
    assert rc == 0
    assert "osint_core" in buf.getvalue() or "collect_public" in buf.getvalue()

    buf2 = io.StringIO()
    sys.stdout = buf2
    try:
        rc2 = main(["gateway", "status"])
    finally:
        sys.stdout = old
    assert rc2 == 0
    assert "skill" in buf2.getvalue().lower() or "TraceLock" in buf2.getvalue() or "port" in buf2.getvalue()
