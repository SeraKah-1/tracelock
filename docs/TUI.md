# TraceLock TUI

Full-screen operator console (stdlib **curses** — no extra pip deps).

## Launch

```bash
tracelock                 # default → chat TUI
tracelock chat
tracelock tui
tracelock chat -c         # resume newest session
tracelock chat -r <id>    # resume id
tracelock chat --simple   # line mode
TRACELOCK_SIMPLE_TUI=1 tracelock chat
```

## Layout

```
┌─────────────────────────────────────────────────────────┐
│ TraceLock · detective OSINT                             │  header
│ model │ LLM/local │ session                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  conversation (scroll PgUp/PgDn)                        │  chat
│                                                         │
├─────────────────────────────────────────────────────────┤
│ ⚙ tool progress feed                                    │  tools
├─────────────────────────────────────────────────────────┤
│ BUSY│ mode=… turns=… tools=… │ case=… │ clock            │  status
├─────────────────────────────────────────────────────────┤
│ › input  (Tab = slash complete)                         │  input
└─────────────────────────────────────────────────────────┘
```

## Keys

| Key | Action |
|-----|--------|
| Enter | Send |
| Ctrl+N | Newline (multiline) |
| Tab | Autocomplete `/` commands |
| ↑ / ↓ | History / cycle completions |
| PgUp / PgDn | Scroll transcript |
| Ctrl+C | Interrupt busy agent; twice = quit |
| Ctrl+D | Quit |
| /help /keys | Command help / keymap overlay |

## Slash (same as Telegram)

`/find` `/who` `/hunt` `/f` `/pivot` `/models` `/key` `/endpoint` `/mem` `/new` `/status` `/sessions` …

## Why not a web UI

TraceLock is built for operators who live in the terminal — same agent pipeline as the gateway, with live tool feedback and session continuity.
