"""CLI entry: TraceLock demo (offline fixture by default; live Qwen when keyed)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from tracelock import __pitch__, __product__, __version__
from tracelock.agent import format_run_text, run_agent
from tracelock.events import EventLog, make_event_callback
from tracelock.footprint import footprint_brief, parse_freeform_clue
from tracelock.loop import continue_case, investigate_continuous
from tracelock.qwen_client import QwenConfig, deployment_fingerprint


DEFAULT_FIXTURE_CLUES = [
    "username:demo_subject_ig",
    "other:FK demo university maba cohort fixture",
    "phone:0812-5550-0100",
    "other:ambiguous dual-handle research — no legal name yet",
]


def _load_fixture_clues() -> list[str]:
    fixture = Path(__file__).resolve().parent / "fixtures" / "demo_clues.json"
    if fixture.is_file():
        data = json.loads(fixture.read_text(encoding="utf-8"))
        clues = data.get("clues") or DEFAULT_FIXTURE_CLUES
        return list(clues)
    return list(DEFAULT_FIXTURE_CLUES)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tracelock",
        description=(
            f"{__product__} v{__version__} — {__pitch__}"
        ),
    )
    p.add_argument("--version", action="version", version=f"{__product__} {__version__}")
    sub = p.add_subparsers(dest="cmd")

    run_p = sub.add_parser(
        "run",
        help="Run autopilot loop (offline fixture unless DASHSCOPE_API_KEY set)",
    )
    run_p.add_argument(
        "--clue",
        action="append",
        dest="clues",
        default=None,
        help="Clue string (repeatable). Default: demo fixture clues",
    )
    run_p.add_argument(
        "--case",
        default=None,
        help="Case JSON path (default: temp file)",
    )
    run_p.add_argument(
        "--offline",
        action="store_true",
        help="DEPRECATED alias: no-network fixture mode (CI only — not for real OSINT)",
    )
    run_p.add_argument(
        "--no-network",
        action="store_true",
        help="Disable live HTTP collection (fixtures only)",
    )
    run_p.add_argument(
        "--use-qwen",
        action="store_true",
        help="Use DashScope Qwen as planner (needs DASHSCOPE_API_KEY). Default: local planner.",
    )
    run_p.add_argument(
        "--json-out",
        default=None,
        help="Write full structured run JSON to this path",
    )
    run_p.add_argument(
        "--events-out",
        default=None,
        help="Append JSONL run events (tool/HITL stream) to this path",
    )
    run_p.add_argument(
        "--quiet",
        action="store_true",
        help="Only print structured JSON to stdout",
    )

    osint_p = sub.add_parser(
        "osint",
        help="Short prompt OSINT: 'osint @handle' or free text — expands to full footprint workflow",
    )
    osint_p.add_argument(
        "text",
        nargs="+",
        help="Short clue phrase (no long prompt needed), e.g. @demo_subject_ig or phone:08…",
    )
    osint_p.add_argument("--case", default=None)
    osint_p.add_argument(
        "--no-network",
        action="store_true",
        help="CI fixture only — skip live SERP (NOT default)",
    )
    osint_p.add_argument(
        "--offline",
        action="store_true",
        help="Alias for --no-network (discouraged for real OSINT)",
    )
    osint_p.add_argument(
        "--use-qwen",
        action="store_true",
        help="Optional: DashScope planner (host AI usually does NOT need this)",
    )
    osint_p.add_argument("--json-out", default=None)
    osint_p.add_argument("--events-out", default=None)
    osint_p.add_argument("--quiet", action="store_true")

    fp_p = sub.add_parser(
        "footprint",
        help="Show expanded digital-footprint checklist for a short clue (no full run)",
    )
    fp_p.add_argument("text", nargs="+", help="Short clue phrase")

    inv_p = sub.add_parser(
        "investigate",
        help="Continuous multi-wave OSINT (anti-lazy): plan→act→observe→replan until done",
    )
    inv_p.add_argument("text", nargs="+", help="Short clue / subject phrase")
    inv_p.add_argument("--case", default=None)
    inv_p.add_argument("--max-waves", type=int, default=5)
    inv_p.add_argument("--min-waves", type=int, default=2)
    inv_p.add_argument("--no-network", action="store_true")
    inv_p.add_argument("--offline", action="store_true")
    inv_p.add_argument("--json-out", default=None)
    inv_p.add_argument("--quiet", action="store_true")

    cont_p = sub.add_parser(
        "continue",
        help="Continue an existing case: more waves from open gaps",
    )
    cont_p.add_argument("--case", required=True, help="Existing case JSON path")
    cont_p.add_argument("--max-waves", type=int, default=2)
    cont_p.add_argument("--no-network", action="store_true")
    cont_p.add_argument("--json-out", default=None)
    cont_p.add_argument("--quiet", action="store_true")

    serve_p = sub.add_parser(
        "serve",
        help="Operator cockpit UI: live logs + HITL gate panel (stdlib HTTP)",
    )
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    serve_p.add_argument("--case", default=None, help="Persist case JSON path")
    serve_p.add_argument(
        "--open",
        action="store_true",
        help="Try to open browser",
    )

    hitl_p = sub.add_parser(
        "hitl",
        help="Complete or list HITL gates on a case file",
    )
    hitl_sub = hitl_p.add_subparsers(dest="hitl_cmd")
    hitl_list = hitl_sub.add_parser("list", help="List gates")
    hitl_list.add_argument("--case", required=True)
    hitl_list.add_argument("--status", default=None)
    hitl_c = hitl_sub.add_parser("complete", help="Complete an open gate")
    hitl_c.add_argument("--case", required=True)
    hitl_c.add_argument("--gate", required=True)
    hitl_c.add_argument(
        "--value",
        default='{"operator":"completed challenge"}',
        help="JSON or text evidence from operator",
    )
    hitl_c.add_argument("--grade", default="operator_clue")

    sub.add_parser("deploy-proof", help="Print Alibaba/Qwen deployment fingerprint JSON")
    sub.add_parser("tools", help="List agent tools")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # bare invocation → short help for host agents
    if not argv:
        argv = ["osint", "--help"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "deploy-proof":
        print(json.dumps(deployment_fingerprint(), indent=2))
        return 0

    if args.cmd == "tools":
        from tracelock.tools import REGISTRY

        for name in sorted(REGISTRY):
            print(name)
        return 0

    if args.cmd == "serve":
        from tracelock.cockpit import serve_cockpit

        case = Path(args.case) if args.case else None
        serve_cockpit(
            host=args.host,
            port=args.port,
            case_path=case,
            open_browser=bool(args.open),
        )
        return 0

    if args.cmd == "footprint":
        phrase = " ".join(args.text)
        clues = parse_freeform_clue(phrase)
        brief = footprint_brief(clues)
        print(json.dumps(brief, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "investigate":
        phrase = " ".join(args.text)
        if args.case:
            case_path = Path(args.case)
        else:
            case_path = Path(tempfile.mkdtemp(prefix="tracelock-inv-")) / "case.json"
        no_net = bool(args.no_network or args.offline)
        if no_net:
            os.environ["TRACELOCK_NO_NETWORK"] = "1"
            os.environ["TRACELOCK_OFFLINE"] = "1"
        else:
            os.environ.pop("TRACELOCK_NO_NETWORK", None)
            os.environ.pop("TRACELOCK_OFFLINE", None)
        loop = investigate_continuous(
            phrase,
            case_path,
            max_waves=int(args.max_waves),
            min_waves=int(args.min_waves),
        )
        payload = loop.to_dict()
        payload["input_phrase"] = phrase
        payload["host_agent_note"] = (
            "Continuous loop: wave1 full plan+collect, then deepen until gaps/HITL-only. "
            "Host AI should NOT stop after one shell command — use `continue --case` if gaps remain."
        )
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        if args.quiet:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"## Continuous investigate: {phrase}")
            print(f"Waves={len(loop.waves)} stop={loop.stop_reason} case={loop.case_path}")
            for w in loop.waves:
                print(f"  wave{w.wave}: tools={w.tools_run} gaps={w.open_gaps}")
            print()
            print(loop.final_report[:8000] if loop.final_report else "(no report)")
            print(
                json.dumps(
                    {
                        "ok": loop.ok,
                        "waves": len(loop.waves),
                        "stop_reason": loop.stop_reason,
                        "case_path": loop.case_path,
                        "checklist": loop.checklist_coverage,
                    },
                    indent=2,
                )
            )
        return 0 if loop.ok else 1

    if args.cmd == "continue":
        case_path = Path(args.case)
        if args.no_network:
            os.environ["TRACELOCK_NO_NETWORK"] = "1"
        loop = continue_case(case_path, max_extra_waves=int(args.max_waves))
        payload = loop.to_dict()
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        if args.quiet:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"## Continue case {case_path}")
            print(f"stop={loop.stop_reason} waves={len(loop.waves)}")
            print((loop.final_report or "")[:6000])
        return 0 if loop.ok else 1

    if args.cmd == "osint":
        phrase = " ".join(args.text)
        clues = parse_freeform_clue(phrase)
        if not clues:
            print(json.dumps({"ok": False, "error": "no clues parsed", "input": phrase}))
            return 2
        if args.case:
            case_path = Path(args.case)
        else:
            tmp = Path(tempfile.mkdtemp(prefix="tracelock-osint-"))
            case_path = tmp / "case.json"
        # Default: LIVE public collection + local planner (no DashScope needed)
        no_net = bool(args.no_network or args.offline)
        if no_net:
            os.environ["TRACELOCK_NO_NETWORK"] = "1"
            os.environ["TRACELOCK_OFFLINE"] = "1"
        else:
            os.environ.pop("TRACELOCK_NO_NETWORK", None)
            # do NOT set TRACELOCK_OFFLINE — that disables live collection
            os.environ.pop("TRACELOCK_OFFLINE", None)
        if args.use_qwen:
            os.environ["TRACELOCK_USE_QWEN"] = "1"
        else:
            os.environ.pop("TRACELOCK_USE_QWEN", None)
        cfg = QwenConfig.from_env()
        on_event = None
        if args.events_out:
            elog = EventLog(jsonl_path=Path(args.events_out))
            on_event = make_event_callback(elog)
        result = run_agent(clues, case_path, cfg=cfg, on_event=on_event)
        payload = result.to_dict()
        payload["input_phrase"] = phrase
        payload["expanded_clues"] = clues
        payload["short_prompt_mode"] = True
        payload["network_collection"] = not no_net
        payload["planner"] = cfg.provider
        payload["host_agent_note"] = (
            "DashScope API key is optional. Host AI (Claude/Grok/Qwen Code) plans; "
            "TraceLock runs public tools. Do not force --offline for real OSINT."
        )
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if args.quiet:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("## Expanded clues (from short prompt)")
            for c in clues:
                print(f"  - {c}")
            print(f"## Planner: {cfg.provider} | network_collection={not no_net}")
            print()
            print(format_run_text(result))
            print(
                json.dumps(
                    {
                        "ok": result.ok,
                        "mode": result.mode,
                        "planner": cfg.provider,
                        "network_collection": not no_net,
                        "expanded_clues": clues,
                        "tools_run": [t.tool for t in result.tool_traces],
                        "case_path": result.case_path,
                        "report_chars": len(result.report_markdown or ""),
                    },
                    indent=2,
                )
            )
        return 0 if result.ok else 1

    if args.cmd == "hitl":
        from osint_cli.hitl import complete_gate, list_gates
        from osint_cli.state import load_state, save_state

        if args.hitl_cmd == "list":
            st = load_state(args.case)
            gates = list_gates(st, status=args.status)
            print(json.dumps(gates, indent=2, ensure_ascii=False))
            return 0
        if args.hitl_cmd == "complete":
            st = load_state(args.case)
            try:
                val: object = json.loads(args.value)
            except json.JSONDecodeError:
                val = args.value
            out = complete_gate(
                st, args.gate, value=val, grade=args.grade, notes="cli"
            )
            save_state(st, args.case)
            print(json.dumps({"ok": True, "gate": out.get("gate")}, indent=2, default=str))
            return 0
        parser.parse_args(["hitl", "--help"])
        return 2

    if args.cmd != "run":
        parser.print_help()
        return 2

    if args.offline or args.no_network:
        os.environ["TRACELOCK_NO_NETWORK"] = "1"
        os.environ["TRACELOCK_OFFLINE"] = "1"
    else:
        os.environ.pop("TRACELOCK_NO_NETWORK", None)
        os.environ.pop("TRACELOCK_OFFLINE", None)
    if getattr(args, "use_qwen", False):
        os.environ["TRACELOCK_USE_QWEN"] = "1"

    clues = args.clues if args.clues else _load_fixture_clues()
    if args.case:
        case_path = Path(args.case)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="tracelock-demo-"))
        case_path = tmp / "case.json"

    cfg = QwenConfig.from_env()
    on_event = None
    if args.events_out:
        elog = EventLog(jsonl_path=Path(args.events_out))
        on_event = make_event_callback(elog)

    result = run_agent(clues, case_path, cfg=cfg, on_event=on_event)
    payload = result.to_dict()

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if args.quiet:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_run_text(result))
        print("\n--- structured summary ---")
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "mode": result.mode,
                    "tools_run": [t.tool for t in result.tool_traces],
                    "evidence_hint": (result.dossier or {}).get("evidence_count"),
                    "report_chars": len(result.report_markdown or ""),
                    "hitl_checkpoints": result.hitl_checkpoints,
                    "case_path": result.case_path,
                },
                indent=2,
            )
        )

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
