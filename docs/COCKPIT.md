# Operator cockpit (improvement)

Thin UI on top of the existing TraceLock CLI/agent. **Does not replace** `tracelock run` or host AI tools (websearch, bash).

## What it adds

| Feature | Purpose |
|---------|---------|
| Live event log | See plan → tool steps as they run |
| HITL panel | When a zero-autonomy gate opens (captcha/portal/Layer-B), show URL + checklist |
| Complete gate | Operator marks challenge done → evidence attached to case |
| Same engine | Calls `run_agent()` — offline/live planner unchanged |

## Run

```bash
python3 -m tracelock serve --port 8765
# open http://127.0.0.1:8765/
```

CLI still works:

```bash
python3 -m tracelock run --offline --events-out /tmp/events.jsonl
python3 -m tracelock hitl list --case /path/to/case.json
python3 -m tracelock hitl complete --case /path/to/case.json --gate g1 \
  --value '{"operator":"completed Cloudflare"}'
```

## Host AI agents

Claude Code / Qwen Code / Grok Build keep their built-in websearch and shell. They can:

1. `python3 -m tracelock run …` or start `serve`
2. Watch logs / open cockpit for HITL
3. Continue with their own tools when needed

## Captcha policy

TraceLock **never** auto-solves captchas. Flow:

1. Tool hits wall → `hitl_open` event  
2. Operator opens portal URL in a **real browser**  
3. Operator completes challenge  
4. Operator marks gate complete (cockpit or CLI)  
5. Case gains graded evidence (`operator_clue` / `full_page`)

Optional later: attach Chrome CDP (`osint_cli` browser_cdp) after the human solve — not required for cockpit demo.
