# Host AI agent guide (Claude Code / Grok Build / Qwen Code / Cursor)

You are running **multi-step OSINT**, not a one-liner FAQ.

## Mandatory protocol (anti-lazy)

Same spirit as coding on a whole repo from one prompt:

```text
1. python3 -m tracelock investigate "<user clue>"
   # LIVE public tools. Do NOT pass --offline / --no-network for real subjects.
2. Read JSON/report: waves, open_gaps, checklist_coverage, case_path
3. If open_gaps has items other than hitl_open_*:
      python3 -m tracelock continue --case <case_path>
4. If only HITL gaps: list gates + portal URLs for the human operator
5. Final message = dossier summary with graded claims + remaining gaps
```

**Never stop after a single tool call** that leaves `identity_digital` empty when a name/handle was given.

## Correct commands

```bash
python3 -m tracelock investigate "name:Subject Name"
python3 -m tracelock investigate @handle
python3 -m tracelock osint "lakukan osint ke name:Subject"   # single wave OK mid-flow
python3 -m tracelock continue --case /path/to/case.json
python3 -m tracelock footprint "@handle"   # checklist preview only
```

## Forbidden shortcuts

| Bad | Why |
|-----|-----|
| `--offline` / `--no-network` on real OSINT | Kills live SERP — empty dossier |
| Demand `DASHSCOPE_API_KEY` | **Not required** — local planner + your reasoning |
| One `osint` then “selesai” with open productive gaps | Phantom completion |
| Invent KTP/NIM/address | Policy: digital ≠ civil; multi-signal only |
| Captcha farm / breach / NIK bots | Hard refuse |

## Continuous loop (what TraceLock does inside `investigate`)

```text
Wave 1: plan → footprint → collect_public (websearch/gov/enum) → report
Wave 2..N: assess_gaps → deepen tools → report again
Stop: no productive gaps | checklist ~ok | max_waves (default 5)
```

You (host) may still add your own websearch/browser tools **between** waves if TraceLock gaps say so.

## Optional Qwen planner only

```bash
export DASHSCOPE_API_KEY=sk-...
export TRACELOCK_USE_QWEN=1
python3 -m tracelock investigate "name:Subject" --use-qwen   # if flag exists on osint; else env only
```

## Policy

Public sources only · digital ≠ civil · HITL on captcha/civil lock · no captcha farms.

See `docs/CONTINUOUS_OSINT.md` and `docs/HOST_AGENT.md`.
