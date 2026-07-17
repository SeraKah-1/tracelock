# Host AI agent guide (Claude Code / Grok Build / Qwen Code / Cursor)

## Do this

```bash
# Real OSINT — LIVE public collection, local planner (NO DashScope key needed)
python3 -m tracelock osint "name:Subject Name"
python3 -m tracelock osint @some_handle
python3 -m tracelock osint "lakukan osint ke name:Subject"

# Then read the report / case JSON path printed at the end
```

You (the host model) already reason. TraceLock **runs tools** (websearch, username enum, gov pack, phone, footprint). Do **not** ask the user for `DASHSCOPE_API_KEY` unless they explicitly want the optional Qwen planner.

## Do NOT do this

| Bad | Why |
|-----|-----|
| `tracelock run --offline` for real people | Disables live SERP; demo/fixture only |
| Demand DashScope API key | Optional; local planner is default |
| Over-refuse public OSINT of public figures | Use public sources + graded dossier; no breach/NIK |
| Invent civil identity from one name seed | Keep civil `open`/`partial` until multi-signal + HITL |

## Optional Qwen planner

```bash
export DASHSCOPE_API_KEY=sk-...
export TRACELOCK_USE_QWEN=1
python3 -m tracelock osint "name:Subject" --use-qwen
```

## Fixture / CI only

```bash
TRACELOCK_NO_NETWORK=1 python3 -m tracelock osint "name:Test" --no-network
```

## Policy

Public sources only · digital ≠ civil · HITL on captcha/civil lock · no captcha farms.
