# TraceLock agentic runtime

TraceLock is a **true agent loop**, not a one-shot script:

```text
user / platform message
        │
        ▼
   slash commands? ──yes──► handle (/model /osint /memory …)
        │ no
        ▼
   ReactAgent (chat/completions + tools)
        │
        ├─ tool_calls → OSINT tools + memory + session_search
        │      │
        │      └── observations back into messages → loop
        │
        └─ final text → deliver (TUI / Telegram / webhook / email)
```

## Configure LLM (OpenAI-compatible)

```bash
python3 -m tracelock setup
# or:
python3 -m tracelock model --list          # GET {api_base}/models
python3 -m tracelock model qwen-plus
```

Config file: `~/.tracelock/config.json`

| Field | Meaning |
|-------|---------|
| `api_base` | e.g. `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| `api_key` | Bearer token |
| `model` | id from `/models` |
| `max_turns` | agent loop budget (default 24) |

Env overrides: `TRACELOCK_API_BASE`, `TRACELOCK_API_KEY`, `TRACELOCK_MODEL`, or `DASHSCOPE_API_KEY` / `QWEN_BASE_URL`.

Without a key, the agent **still runs tools** via local investigate skill (fallback).

## Interactive console

```bash
python3 -m tracelock chat
```

Slash commands (TUI **and** Telegram/webhook):

| Command | Action |
|---------|--------|
| `/help` | list commands |
| `/new` `/reset` | clear session |
| `/status` | config + session |
| `/endpoint <url>` | set API base |
| `/key <secret>` | set API key |
| `/models` | fetch `/v1/models` |
| `/model <id>` | select model |
| `/osint <clue>` | force full investigation prompt |
| `/memory` | show MEMORY.md + USER.md |
| `/personality operator\|brief\|forensic` | style |
| `/case` | active case path |
| `/undo` | drop last exchange |

## One-shot

```bash
python3 -m tracelock ask "Investigate public footprint for @demo_subject_ig"
```

## Gateway pipeline

```bash
python3 -m tracelock gateway start --port 8787
```

| Inbound | Path |
|---------|------|
| Telegram long-poll / webhook `POST /telegram` | `platform=telegram` |
| WhatsApp / generic `POST /whatsapp` or `/webhook` | JSON `text` → agent |
| HTTP `POST /message` | same pipeline |
| Cron jobs | skill/investigate + deliver |

Every channel uses **`runtime.pipeline.handle_message`** so slash + tool loop behave the same.

## Memory

- `~/.tracelock/memories/MEMORY.md` — agent notes  
- `~/.tracelock/memories/USER.md` — operator profile  
- Bounded (default 2200 / 1375 chars)  
- Model uses `memory` tool: add / replace / remove / list  
- Injected into system prompt at session start  

## Sessions

- `~/.tracelock/sessions/<platform>_<id>.json`  
- Per chat continuity on Telegram / webhook / TUI  
- `session_search` tool for past keyword recall  

## Tools (function calling)

OSINT pack: `init_case`, `analyze_clues`, `normalize_phone`, `phone_queries`, `phone_checklist`, `name_pattern_enum`, `digital_footprint`, `collect_public`, `plan_sources`, `open_hitl`, `build_dossier`, `report`, plus `memory`, `session_search`.

Anti-lazy rule in system prompt: multi-step tools until report / HITL-only / max turns.

## Deploy

See [`deploy/alibaba-agentic.md`](../deploy/alibaba-agentic.md).
