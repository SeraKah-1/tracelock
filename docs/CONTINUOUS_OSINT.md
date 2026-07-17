# Continuous OSINT processing (anti-lazy agents)

## Why AI looks “lazy” on OSINT

Same disease as half-done coding:

| Failure | What it looks like |
|---------|-------------------|
| **One-shot** | One `osint` call → prose summary → stop |
| **Phantom done** | Marks complete while gaps open |
| **Wrong stop** | Uses `--offline` / skips tools |
| **No replan** | Ignores thin SERP / missing enum |

Coding agents work on “hundreds of files from one prompt” because the **harness** runs a loop, not because the model is magically diligent once.

## Research: the mechanism

### 1. Agent loop (universal)

```text
while not done:
  context = task + memory + last observations
  decision = LLM(context)          # reason / plan next
  if tool_calls:
    results = execute(tools)
    append observations
  else:
    done = True                    # final answer
```

Sources: ReAct (Yao et al.), Claude Code / Cursor / Codex harnesses — all reduce to this.

### 2. Plan-and-execute + replan

- **Plan** once (or refresh at milestones)
- **Execute** steps
- **Replan** when observations invalidate the plan  
  (LangChain plan-and-execute; Magentic-One outer/inner loop)

### 3. Checklist as execution contract

Partial-completion papers/practice: break the goal into **tickable tasks**; do not accept “done” until tasks close or are explicitly blocked (HITL).

### 4. Stop conditions

| Stop | Meaning |
|------|---------|
| Checklist coverage ≥ threshold | Enough work done |
| No productive gaps | Only HITL left (human must act) |
| Max waves / max tool calls | Safety cap (loops must not run forever) |

### 5. Host AI (Claude/Grok) vs TraceLock

| Layer | Who |
|-------|-----|
| Multi-turn reasoning | Host agent loop (their product) |
| OSINT tools + case memory + gap assessor | TraceLock |
| Captcha / civil lock | Human (HITL) |

TraceLock cannot force Claude’s outer loop — but it can:

1. Run **multi-wave** inside one CLI command (`investigate`)
2. Expose **gaps + next_actions** so the host continues
3. Ship **AGENTS.md** rules against one-shot stop

## TraceLock commands

```bash
# Preferred for real OSINT: multi-wave continuous
python3 -m tracelock investigate "name:Subject"
python3 -m tracelock investigate @handle --max-waves 5

# Single wave (still full tool plan + live collect)
python3 -m tracelock osint "name:Subject"

# Host agent after reading gaps:
python3 -m tracelock continue --case /path/to/case.json
```

### Internal continuous algorithm

```text
wave 1: run_agent(plan + digital_footprint + collect_public + report)
loop wave 2..N:
  gaps = assess_gaps(case)
  if no productive gaps and wave >= min: stop
  actions = propose_next_actions(gaps)
  execute actions (collect_public / footprint / phone / report)
  refresh dossier
stop: max_waves | gaps closed | checklist_ok
```

## Protocol for host AI (copy into system rules)

```text
When user asks for OSINT:
1. Run: python3 -m tracelock investigate "<clue>"   # NOT --offline
2. Read case_path + final_report + waves[].open_gaps
3. If productive gaps remain: tracelock continue --case <path>
4. If only hitl_open_*: tell user which portals to complete
5. Do NOT stop after one shell command with empty digital dimensions
6. Do NOT ask for DASHSCOPE_API_KEY (local planner default)
7. Do NOT invent civil identity
```

## Analogy to coding agents

| Coding | OSINT |
|--------|--------|
| Edit many files | Many collect modules / platforms |
| Run tests → fix → re-run | Collect → assess gaps → deepen wave |
| Todo list in harness | Checklist S1–S12 + assess_gaps |
| Don’t claim PR done if tests fail | Don’t claim OSINT done if SERP thin / enum skipped |

## What we intentionally do not do

- Infinite loops without max_waves  
- Auto-solve captchas  
- Breach/NIK to “complete” civil lock  
- Pretend one web_hit = identity lock  
