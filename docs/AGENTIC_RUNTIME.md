# TraceLock agentic runtime

TraceLock v2 adds a long-running **operator runtime** around the existing OSINT core: messaging channels, scheduled jobs, reusable skills, and proactive case continuation.

## Why

CLI one-shots are enough for demos. Production investigation needs:

- chat / webhook intake (Telegram, WhatsApp Cloud API hooks, email)
- jobs that re-check subjects without a human prompt
- a slim tool pack (no noisy modules by default)
- the same multi-wave investigate loop from every entry point

## Architecture

```text
  Telegram / HTTP webhook / email outbox
              │
              ▼
     ┌────────────────────┐
     │  TraceLock Gateway │  long-lived process
     │  + cron tick       │
     └────────┬───────────┘
              │ /osint <clue>
              ▼
     ┌────────────────────┐
     │ Skill: osint-      │
     │ investigate        │  multi-wave continuous loop
     └────────┬───────────┘
              │
              ▼
     ┌────────────────────┐
     │ Toolset osint_core │  analyze → footprint → collect_public → report
     │ + HITL gates       │
     └────────┬───────────┘
              │
              ▼
         Case JSON + human report → deliver to channel
```

## Modules

| Module | Role |
|--------|------|
| `tracelock/core_tools.py` | Slim packs: `osint_core`, `osint_full` |
| `tracelock/skills/` | Skill wrapper around continuous investigate |
| `tracelock/cron/` | Job store + due runner + delivery targets |
| `tracelock/gateway/` | HTTP + Telegram poll/webhook + cron thread |
| `tracelock/proactive.py` | Scan case dir → continue open gaps |

## CLI

```bash
python3 -m tracelock core
python3 -m tracelock skill list
python3 -m tracelock skill run @handle

python3 -m tracelock cron add \
  --name daily-check \
  --schedule interval:1d \
  --prompt '@handle' \
  --deliver 'file:/tmp/tracelock-out.txt'
python3 -m tracelock cron run-due --force

export TRACELOCK_TELEGRAM_BOT_TOKEN=...   # optional
export TRACELOCK_TELEGRAM_ALLOWLIST=...   # set in production
python3 -m tracelock gateway start --port 8787

python3 -m tracelock watch --cases-dir ~/.tracelock/cases --once
```

## Delivery targets

| Target | Example |
|--------|---------|
| File | `file:/var/lib/tracelock/reports/out.txt` |
| Telegram | `telegram:CHAT_ID` |
| Email | `email:ops@example.com` (SMTP or outbox) |
| Webhook | `webhook:https://…` |
| Stdout | `stdout` |

## Policy

- Public sources only  
- HITL for captcha / Layer-B phone apps / civil lock  
- Telegram allowlist in production  
- Default path is **live** collection (not offline fixtures)

## Deploy

See [`deploy/alibaba-agentic.md`](../deploy/alibaba-agentic.md).
