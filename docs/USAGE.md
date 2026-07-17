# Usage

## Quick start

```bash
python3 -m tracelock run --offline
```

Custom clues:

```bash
python3 -m tracelock run --offline \
  --clue 'username:demo_subject_ig' \
  --clue 'phone:0811-6060-0613'
```

Live planner (Qwen Cloud / DashScope):

```bash
export DASHSCOPE_API_KEY=sk-...
pip install '.[qwen]'
python3 -m tracelock run --clue 'username:…'
```

Output includes a tool plan, any HITL gates, and a markdown dossier. Case JSON path is printed at the end of the run.

---

## Embedding in another agent

If your host agent can run shell or import Python:

```python
from pathlib import Path
from tracelock.agent import run_agent
from tracelock.qwen_client import QwenConfig

result = run_agent(
    clues=["username:x", "phone:0812…"],
    case_path=Path("/tmp/case.json"),
    cfg=QwenConfig.from_env(),
)
# result.report_markdown, result.dossier, result.tool_traces
```

Tool names: `python3 -m tracelock tools`

For a longer investigation (collect modules, identity-lock kinds, HITL complete), use:

```bash
python3 -m osint_cli -c /path/to/case.json init --force
python3 -m osint_cli -c /path/to/case.json seed add "username:…" "phone:…"
python3 -m osint_cli -c /path/to/case.json plan
python3 -m osint_cli -c /path/to/case.json next
```

---

## HITL

Automated steps never:

- solve captchas via farms  
- scrape non-public admin APIs  
- treat e-wallet name preview as civil ID  

When a gate opens, an operator completes it in a real browser / app, then resumes with `osint_cli hitl` (see [`HITL_AND_CYBORG.md`](HITL_AND_CYBORG.md)).

---

## Environment

| Variable | Purpose |
|----------|---------|
| `DASHSCOPE_API_KEY` / `QWEN_API_KEY` | Live Qwen planner |
| `QWEN_BASE_URL` | Default DashScope international compatible-mode URL |
| `QWEN_MODEL` | Default `qwen-plus` |
| `TRACELOCK_OFFLINE=1` | Force offline planner |
