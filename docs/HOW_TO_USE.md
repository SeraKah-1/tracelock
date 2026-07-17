# How to use TraceLock

TraceLock is **both**:

1. A **CLI autopilot** you run yourself (`python3 -m tracelock run`)  
2. A **toolbelt for AI agents** (Claude / Cursor / Grok / custom agents) that call the same commands and tools  

It is **not** a chat website. You (or an AI with shell access) drive it.

---

## Path A — You run the demo (no AI agent required)

```bash
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock

# Offline demo (no Qwen key) — always works
python3 -m tracelock run --offline

# Live planner (Qwen Cloud)
export DASHSCOPE_API_KEY=sk-your-key
pip install '.[qwen]'
python3 -m tracelock run

# Custom clues
python3 -m tracelock run --offline \
  --clue 'username:some_handle' \
  --clue 'phone:0812xxxxxxx'
```

**What you get:** plan → tool steps → HITL gates → markdown dossier report.

---

## Path B — Ask an AI agent that has shell/tools (recommended day-to-day)

Any coding agent that can run terminal commands in this repo:

> “Run TraceLock offline on these seeds: username:… phone:…  
> Then open the case JSON and summarize the dossier + open HITL gates.”

Example prompts:

```text
cd /path/to/tracelock
python3 -m tracelock run --offline --clue 'username:demo_subject_ig' --clue 'phone:0811-6060-0613'
Read the case path printed at the end and list HITL zero-autonomy items.
```

```text
Use osint-cli under this repo for a deeper case:
python3 -m osint_cli -c /tmp/case.json init --force
python3 -m osint_cli -c /tmp/case.json seed add "username:…" "phone:…"
python3 -m osint_cli -c /tmp/case.json plan
python3 -m osint_cli -c /tmp/case.json next
```

The agent does **not** magically know private Instagram followers without login/HITL. It runs **public** tools + pauses where humans must act.

---

## Path C — Wire into your own agent (function calling / MCP-style)

| Piece | Role |
|-------|------|
| `tracelock.agent.run_agent(clues, case_path)` | Python API: plan + execute + dossier |
| `tracelock.tools.REGISTRY` | Named tools: `normalize_phone`, `open_hitl`, `report`, … |
| `python3 -m osint_cli …` | Full investigation CLI (collect, differentiate, identity-lock) |
| `DASHSCOPE_API_KEY` | Optional: Qwen plans the step list |

Pseudocode for a host agent:

```python
from pathlib import Path
from tracelock.agent import run_agent
from tracelock.qwen_client import QwenConfig

result = run_agent(
    clues=["username:x", "phone:0811…"],
    case_path=Path("/tmp/case.json"),
    cfg=QwenConfig.from_env(),  # offline if no key
)
print(result.report_markdown)
# if HITL gates open → ask human, then continue with osint_cli hitl complete
```

---

## What “autopilot” means (and does not)

| Does | Does not |
|------|----------|
| Plans multi-step public investigation | Bypass captcha / private accounts without you |
| Calls real tools (phone normalize, query packs, HITL open) | Auto e-wallet / civil lock / doxx |
| Emits graded dossier | Invent NIM/KTP as fact |
| Stops on zero-autonomy gates | Replace your legal/ethical judgment |

---

## Hackathon / judges

```bash
python3 -m tracelock run --offline
python3 -m tracelock deploy-proof
```

Repo: https://github.com/SeraKah-1/tracelock  
Track: **4 Autopilot Agent** · Qwen Cloud Global AI Hackathon
