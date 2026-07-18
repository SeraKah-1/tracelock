"""OpenAI function-calling schemas for TraceLock OSINT tools + agent tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from tracelock.tools import REGISTRY, run_tool


def _props(**fields: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": fields, "additionalProperties": True}


def openai_tools() -> list[dict[str, Any]]:
    """Schemas the model can call each turn."""
    specs: list[tuple[str, str, dict[str, Any]]] = [
        (
            "init_case",
            "Create/open the investigation case file store.",
            _props(),
        ),
        (
            "analyze_clues",
            "Parse and classify seeds (handle, phone, name, url) into structured analysis.",
            _props(
                clues={"type": "array", "items": {"type": "string"}, "description": "Clue strings"}
            ),
        ),
        (
            "normalize_phone",
            "Normalize a phone number to E.164 and carrier-style metadata (public).",
            _props(phone={"type": "string"}),
        ),
        (
            "phone_queries",
            "Build public SERP / footprint query pack for a phone (Layer-A only).",
            _props(phone={"type": "string"}),
        ),
        (
            "phone_checklist",
            "Open HITL gate for Layer-B phone checks (e-wallet etc). Never auto-completes.",
            _props(phone={"type": "string"}),
        ),
        (
            "name_pattern_enum",
            "Expand username morphs / name patterns for unknown civil name cases.",
            _props(clues={"type": "array", "items": {"type": "string"}}),
        ),
        (
            "digital_footprint",
            "Cross-platform digital footprint checklist + handle probes + SERP pack.",
            _props(clues={"type": "array", "items": {"type": "string"}}),
        ),
        (
            "collect_public",
            "LIVE public collection: websearch SERP, username enum, optional gov packs. Primary evidence tool.",
            _props(
                modules={
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "e.g. websearch, username_enum, phone_footprint, gov_id",
                },
                clues={"type": "array", "items": {"type": "string"}},
            ),
        ),
        (
            "plan_sources",
            "Record planned public source categories on the case.",
            _props(),
        ),
        (
            "open_hitl",
            "Open a human-in-the-loop zero-autonomy gate (captcha/browser/civil confirm).",
            _props(
                source={"type": "string"},
                kind={"type": "string"},
                why={"type": "string"},
            ),
        ),
        (
            "build_dossier",
            "Build structured graded dossier dimensions from evidence.",
            _props(),
        ),
        (
            "report",
            "Generate human-readable OSINT report (markdown + brief) from the case.",
            _props(),
        ),
        (
            "memory",
            "Persistent memory: add/replace/remove notes about user or environment. Survives sessions.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "replace", "remove", "list"],
                    },
                    "target": {
                        "type": "string",
                        "enum": ["memory", "user"],
                        "description": "memory=agent notes; user=operator profile",
                    },
                    "content": {"type": "string"},
                    "old_text": {
                        "type": "string",
                        "description": "substring match for replace/remove",
                    },
                },
                "required": ["action", "target"],
            },
        ),
        (
            "session_search",
            "Search past TraceLock conversation sessions by keyword.",
            _props(query={"type": "string"}, limit={"type": "integer"}),
        ),
    ]
    out: list[dict[str, Any]] = []
    for name, desc, params in specs:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params,
                },
            }
        )
    return out


def execute_tool_call(
    name: str,
    arguments: dict[str, Any],
    *,
    case_path: Path,
    clues: list[str],
    memory_handler: Optional[Callable[..., dict[str, Any]]] = None,
    session_search_handler: Optional[Callable[..., dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Dispatch one tool call; returns JSON-serializable result."""
    args = dict(arguments or {})
    if name == "memory" and memory_handler:
        return memory_handler(**args)
    if name == "session_search" and session_search_handler:
        return session_search_handler(**args)
    if name not in REGISTRY and name not in ("memory", "session_search"):
        return {"ok": False, "error": f"unknown tool: {name}"}
    # merge clues
    extra_clues = args.pop("clues", None)
    use_clues = list(clues)
    if isinstance(extra_clues, list):
        use_clues = [str(c) for c in extra_clues] or use_clues
    elif isinstance(extra_clues, str) and extra_clues.strip():
        use_clues = [extra_clues] + use_clues
    try:
        result = run_tool(name, case_path, clues=use_clues, args=args)
    except Exception as e:
        result = {"ok": False, "tool": name, "error": str(e)}
    # compact for model context
    return _compact(result)


def _compact(result: dict[str, Any], max_chars: int = 6000) -> dict[str, Any]:
    try:
        s = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        return {"ok": False, "error": "unserializable tool result"}
    if len(s) <= max_chars:
        return result
    # keep keys of interest
    keep = {
        k: result.get(k)
        for k in (
            "ok",
            "tool",
            "error",
            "evidence_count",
            "web_hit_count",
            "modules",
            "count",
            "hitl",
            "zero_autonomy",
            "gate",
            "report_class",
            "markdown_chars",
            "note",
            "brief",
        )
        if k in result
    }
    if "markdown" in result:
        md = str(result.get("markdown") or "")
        keep["markdown_preview"] = md[:1500]
    if "queries" in result and isinstance(result["queries"], list):
        keep["queries_sample"] = result["queries"][:8]
        keep["query_count"] = len(result["queries"])
    keep["_truncated"] = True
    keep["_orig_chars"] = len(s)
    return keep
