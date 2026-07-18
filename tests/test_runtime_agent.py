"""Unit tests for agentic runtime (no live LLM required)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from tracelock.runtime.config import RuntimeConfig, save_config, tracelock_home
from tracelock.runtime.memory import MemoryStore
from tracelock.runtime.session import SessionStore
from tracelock.runtime.slash import dispatch_slash
from tracelock.runtime.tool_schema import openai_tools
from tracelock.runtime.pipeline import handle_message


def test_openai_tool_schemas_include_osint():
    tools = openai_tools()
    names = {t["function"]["name"] for t in tools}
    assert "collect_public" in names
    assert "report" in names
    assert "memory" in names


def test_memory_add_and_prompt(tmp_path: Path, monkeypatch=None):
    os.environ["TRACELOCK_HOME"] = str(tmp_path / "home")
    store = MemoryStore(
        memory_path=tmp_path / "MEMORY.md",
        user_path=tmp_path / "USER.md",
        memory_limit=500,
        user_limit=300,
    )
    r = store.add("memory", "Prefer live SERP over offline fixtures")
    assert r["ok"]
    block = store.prompt_block()
    assert "SERP" in block
    r2 = store.add("memory", "x" * 600)
    assert r2["ok"] is False


def test_session_roundtrip(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions")
    s = store.get_or_create(platform="test", external_id="u1", case_dir=str(tmp_path / "c"))
    store.append_message(s, "user", "hello @demo")
    store.append_message(s, "assistant", "hi")
    s2 = store.get(s.id)
    assert s2 is not None
    assert len(s2.messages) == 2
    hits = store.search("demo")
    assert hits["ok"]
    assert hits["count"] >= 1


def test_slash_help_and_model(tmp_path: Path):
    os.environ["TRACELOCK_HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    cfg = RuntimeConfig(api_base="http://example/v1", api_key="", model="m1")
    save_config(cfg)
    store = SessionStore(tmp_path / "sessions")
    sess = store.get_or_create(platform="t", external_id="1")
    r = dispatch_slash("/help", cfg=cfg, session=sess, platform="t")
    assert r.handled
    assert "/models" in r.reply
    r2 = dispatch_slash("/osint @demo_subject_ig", cfg=cfg, session=sess)
    assert r2.passthrough
    assert "demo_subject" in r2.passthrough


def test_pipeline_slash_status(tmp_path: Path):
    os.environ["TRACELOCK_HOME"] = str(tmp_path / "home")
    out = handle_message("/status", platform="test", external_id="pipe1")
    assert out.slash
    assert "model" in out.reply.lower() or "api_base" in out.reply


def test_llm_list_models_error_shape():
    from tracelock.runtime.llm import list_models

    r = list_models("http://127.0.0.1:9", "x", timeout=1.0)
    assert r["ok"] is False
    assert "error" in r
