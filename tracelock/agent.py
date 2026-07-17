"""TraceLock autopilot agent: plan (Qwen or offline) → execute tools → dossier."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from tracelock.qwen_client import AgentPlan, QwenConfig, plan_with_qwen
from tracelock.tools import REGISTRY, run_tool


@dataclass
class ToolTrace:
    step_index: int
    tool: str
    args: dict[str, Any]
    reason: str
    result: dict[str, Any]


@dataclass
class AgentRunResult:
    mode: str
    plan: dict[str, Any]
    tool_traces: list[ToolTrace] = field(default_factory=list)
    report_markdown: str = ""
    dossier: dict[str, Any] = field(default_factory=dict)
    case_path: str = ""
    hitl_checkpoints: list[str] = field(default_factory=list)
    ok: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "case_path": self.case_path,
            "plan": self.plan,
            "hitl_checkpoints": self.hitl_checkpoints,
            "tool_traces": [
                {
                    "step_index": t.step_index,
                    "tool": t.tool,
                    "args": t.args,
                    "reason": t.reason,
                    "result_ok": bool(t.result.get("ok")),
                    "result_summary": _summarize_result(t.result),
                }
                for t in self.tool_traces
            ],
            "dossier": self.dossier,
            "report_markdown": self.report_markdown,
            "errors": self.errors,
            "product": "TraceLock",
            "track": "Track 4: Autopilot Agent",
        }


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "tool",
        "ok",
        "error",
        "count",
        "evidence_count",
        "hitl_gate_count",
        "investigation_id",
        "zero_autonomy",
        "report_class",
    )
    out = {k: result[k] for k in keys if k in result}
    if "record" in result and isinstance(result["record"], dict):
        out["e164"] = result["record"].get("e164")
    if "queries" in result and isinstance(result["queries"], list):
        out["query_count"] = len(result["queries"])
    if "gate" in result and isinstance(result["gate"], dict):
        out["gate_id"] = result["gate"].get("id")
    if "dossier" in result and isinstance(result["dossier"], dict):
        out["dimension_keys"] = list(
            (result["dossier"].get("dimensions") or {}).keys()
        )
    if "markdown" in result:
        out["markdown_chars"] = len(result["markdown"] or "")
    return out


def run_agent(
    clues: list[str],
    case_path: Path | str,
    *,
    cfg: Optional[QwenConfig] = None,
    max_steps: int = 20,
) -> AgentRunResult:
    """End-to-end autopilot loop: plan → tools → structured dossier report."""
    case_path = Path(case_path)
    cfg = cfg or QwenConfig.from_env()
    plan: AgentPlan = plan_with_qwen(clues, cfg)

    traces: list[ToolTrace] = []
    errors: list[str] = []
    report_md = ""
    dossier: dict[str, Any] = {}

    # Always ensure init runs first if planner skipped it
    step_tools = [s.tool for s in plan.steps]
    ordered_steps = list(plan.steps)
    if "init_case" not in step_tools:
        from tracelock.qwen_client import PlanStep

        ordered_steps.insert(
            0, PlanStep("init_case", {}, "Ensure case store exists")
        )
    if "report" not in step_tools:
        from tracelock.qwen_client import PlanStep

        ordered_steps.append(PlanStep("report", {}, "Emit dossier report"))

    for i, step in enumerate(ordered_steps[:max_steps]):
        if step.tool not in REGISTRY:
            errors.append(f"unknown tool skipped: {step.tool}")
            traces.append(
                ToolTrace(
                    step_index=i,
                    tool=step.tool,
                    args=step.args,
                    reason=step.reason,
                    result={"ok": False, "error": "unknown tool"},
                )
            )
            continue
        result = run_tool(step.tool, case_path, clues=clues, args=step.args)
        traces.append(
            ToolTrace(
                step_index=i,
                tool=step.tool,
                args=step.args,
                reason=step.reason,
                result=result,
            )
        )
        if not result.get("ok"):
            errors.append(f"{step.tool}: {result.get('error')}")
        if step.tool == "report":
            report_md = result.get("markdown") or ""
            dossier = result.get("dossier") or dossier
        if step.tool == "build_dossier" and result.get("dossier"):
            dossier = result["dossier"]

    # If report never produced markdown, force it
    if not report_md:
        result = run_tool("report", case_path, clues=clues, args={})
        traces.append(
            ToolTrace(
                step_index=len(traces),
                tool="report",
                args={},
                reason="forced final report",
                result=result,
            )
        )
        report_md = result.get("markdown") or ""
        dossier = result.get("dossier") or dossier

    ok = bool(report_md.strip()) and bool(traces) and not (
        len(errors) == len(traces)
    )
    return AgentRunResult(
        mode=plan.mode,
        plan=plan.to_dict(),
        tool_traces=traces,
        report_markdown=report_md,
        dossier=dossier,
        case_path=str(case_path),
        hitl_checkpoints=list(plan.hitl_checkpoints),
        ok=ok,
        errors=errors,
    )


def format_run_text(result: AgentRunResult) -> str:
    """Human-readable run transcript for CLI / demo logs."""
    lines = [
        "=" * 72,
        "TraceLock Autopilot Agent — Run Transcript",
        f"Mode: {result.mode} | Track: 4 Autopilot Agent | OK: {result.ok}",
        f"Case: {result.case_path}",
        "=" * 72,
        "",
        "## Plan",
        json.dumps(result.plan, indent=2, ensure_ascii=False)[:4000],
        "",
        "## HITL checkpoints (planned)",
    ]
    for h in result.hitl_checkpoints or ["(none)"]:
        lines.append(f"- {h}")
    lines.append("")
    lines.append("## Tool loop")
    for t in result.tool_traces:
        status = "OK" if t.result.get("ok") else "FAIL"
        lines.append(
            f"[{t.step_index}] {t.tool} → {status} | {t.reason}"
        )
        lines.append(
            f"    summary: {json.dumps(_summarize_result(t.result), ensure_ascii=False)}"
        )
    lines.append("")
    lines.append("## Dossier (structured)")
    lines.append(json.dumps(result.dossier, indent=2, ensure_ascii=False)[:5000])
    lines.append("")
    lines.append("## Report")
    lines.append(result.report_markdown or "(empty report)")
    if result.errors:
        lines.append("")
        lines.append("## Errors")
        for e in result.errors:
            lines.append(f"- {e}")
    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)
