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
from tracelock.qwen_client import QwenConfig, deployment_fingerprint


DEFAULT_FIXTURE_CLUES = [
    "username:demo_subject_ig",
    "other:FK demo university maba cohort fixture",
    "phone:0811-6060-0613",
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
            f"{__product__} v{__version__} — {__pitch__} "
            "(Qwen Cloud Global AI Hackathon Track 4: Autopilot Agent)"
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
        help="Force offline planner (ignore API key)",
    )
    run_p.add_argument(
        "--json-out",
        default=None,
        help="Write full structured run JSON to this path",
    )
    run_p.add_argument(
        "--quiet",
        action="store_true",
        help="Only print structured JSON to stdout",
    )

    sub.add_parser("deploy-proof", help="Print Alibaba/Qwen deployment fingerprint JSON")
    sub.add_parser("tools", help="List agent tools")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # bare invocation → run offline demo
    if not argv:
        argv = ["run", "--offline"]

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

    if args.cmd != "run":
        parser.print_help()
        return 2

    if args.offline:
        os.environ["TRACELOCK_OFFLINE"] = "1"

    clues = args.clues if args.clues else _load_fixture_clues()
    if args.case:
        case_path = Path(args.case)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="tracelock-demo-"))
        case_path = tmp / "case.json"

    cfg = QwenConfig.from_env()
    result = run_agent(clues, case_path, cfg=cfg)
    payload = result.to_dict()

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

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
