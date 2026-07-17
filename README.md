# TraceLock

**Investigation autopilot for ambiguous public clues.**

Give it a handle, a phone number, or a short free-text lead. TraceLock plans the work, runs public-source tools, stops where a human must act, and writes a graded dossier. Digital identity (accounts) is never treated as civil identity (legal name / institutional ID).

```bash
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock
python3 -m tracelock run --offline
```

With a [Qwen Cloud](https://www.qwencloud.com/) key (Alibaba DashScope), the same command uses a live planner:

```bash
export DASHSCOPE_API_KEY=sk-...
pip install '.[qwen]'
python3 -m tracelock run --clue 'username:example' --clue 'phone:0812xxxxxxx'
```

| | |
|---|---|
| **License** | MIT |
| **Repo** | https://github.com/SeraKah-1/tracelock |
| **Stack** | Python · Qwen (DashScope) · durable case JSON |

---

## Who it’s for

- Fraud / trust & safety analysts who start from a phone or handle, not a CRM form  
- Campus / security desks doing public-source background work  
- Builders wiring an agent that must **call tools** and **pause** on policy walls  

Not for: breach dumps, NIK bots, captcha farms, or auto-unlocking private social graphs.

---

## What a run does

1. **Ingest** mixed clues (username, phone, free text)  
2. **Plan** multi-step work (Qwen on DashScope, or offline planner for CI/demo)  
3. **Execute tools** — phone E.164 normalize, SERP query packs, name-pattern expansion, evidence chain  
4. **HITL gates** — browser walls, phone Layer-B checks, civil-lock confirmation  
5. **Report** — structured dimensions + markdown dossier  

Architecture: [`docs/assets/architecture.svg`](docs/assets/architecture.svg) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Install

```bash
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock
# optional live planner
cp .env.example .env   # set DASHSCOPE_API_KEY
pip install '.[qwen]'
```

### CLI

```bash
python3 -m tracelock run --offline
python3 -m tracelock run --clue 'username:…' --clue 'phone:…'
python3 -m tracelock deploy-proof    # shows DashScope endpoint wiring (no secrets)
python3 -m tracelock tools           # list tool names
python3 -m osint_cli --help          # full investigation CLI
```

### From Python

```python
from pathlib import Path
from tracelock.agent import run_agent

result = run_agent(
    clues=["username:example_ig", "phone:081160600613"],
    case_path=Path("/tmp/tracelock-case.json"),
)
print(result.report_markdown)
```

More detail: [`docs/USAGE.md`](docs/USAGE.md)

---

## Example scenarios

1. **Dual social handle, no legal name** — expand nick patterns, keep civil ID open until multi-signal proof.  
2. **Phone-only ticket** — Layer-A public footprint automatically; e-wallet / contact-sync stays operator-only (HITL).  

Write-ups: [`docs/SCENARIOS.md`](docs/SCENARIOS.md)

---

## Policy (built in)

- Public sources only for automated collection  
- **Digital lock ≠ civil lock**  
- Phone prefix ≠ domicile; wallet display name ≠ KTP  
- No breach / dark-web / NIK modules  

See also: [`docs/PHONE_PIVOT.md`](docs/PHONE_PIVOT.md) · [`docs/HITL_AND_CYBORG.md`](docs/HITL_AND_CYBORG.md) · [`docs/GOV_SOURCES.md`](docs/GOV_SOURCES.md)

---

## Qwen / Alibaba Cloud

Planner calls **DashScope** OpenAI-compatible API:

- Base URL: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`  
- Auth: `DASHSCOPE_API_KEY`  
- Implementation: [`tracelock/qwen_client.py`](tracelock/qwen_client.py)  
- Deploy notes: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

Offline mode (`--offline` or no key) keeps the same tool loop for local demos and tests.

---

## Project layout

```text
tracelock/     # agent, tools, CLI
osint_cli/     # case engine & collectors
docs/          # usage, architecture, scenarios, deployment
deploy/        # env templates
tests/
```

---

## License

MIT — [`LICENSE`](./LICENSE)
