# TraceLock architecture

## Diagram

Renderable source (Mermaid) and static asset for Devpost:

- **SVG (submit this):** [`assets/architecture.svg`](assets/architecture.svg)  
- **Mermaid (edit-friendly):** below  

```mermaid
flowchart LR
  subgraph Input
    C[Ambiguous clues<br/>handle / phone / text]
  end

  subgraph QwenCloud["Alibaba Cloud · Qwen Cloud / DashScope"]
    Q[Qwen planner<br/>qwen-plus via compatible-mode API]
  end

  subgraph Agent["TraceLock Agent"]
    P[Plan JSON<br/>steps + HITL checkpoints]
    L[Tool loop]
    H[HITL zero-autonomy gates]
  end

  subgraph Tools["Tool layer · osint_cli"]
    T1[normalize / phone pivot]
    T2[name pattern enum]
    T3[clue analyze]
    T4[HITL open gate]
  end

  subgraph Store["Durable store"]
    S[(Case JSON<br/>evidence chain)]
    D[Dossier report<br/>MD + structured]
  end

  subgraph Human
    O[Operator browser / Layer-B apps]
  end

  C --> Q
  Q --> P
  P --> L
  L --> T1 & T2 & T3 & T4
  T1 & T2 & T3 --> S
  T4 --> H
  H --> O
  O -->|hitl complete| S
  L --> D
  S --> D
```

## Components

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Planner | `tracelock/qwen_client.py` | Call DashScope OpenAI-compatible API; offline stub |
| Orchestrator | `tracelock/agent.py` | Execute plan steps; force report; structured result |
| CLI | `tracelock/demo.py` | `run` / `deploy-proof` / `tools` |
| Tools | `tracelock/tools.py` | Thin wrappers → real `osint_cli` functions |
| Case engine | `osint_cli/*` | Seeds, evidence, HITL, phone, dossier primitives |
| Deploy notes | `deploy/` + `docs/ALIBABA_QWEN_DEPLOYMENT.md` | Env, API base URL, proof path |

## Data flow (one run)

1. CLI loads clues (fixture or `--clue`).  
2. `plan_with_qwen` → `AgentPlan` (`mode=live|offline`).  
3. For each step, `run_tool` mutates case JSON via `osint_cli`.  
4. HITL tools open gates without performing restricted actions.  
5. `report` writes markdown + structured dossier into the result payload.

## Security / ethics boundaries

```text
ALLOWED auto: public normalize, query pack build, local case IO, pattern enum
HITL only:    captcha/browser walls, e-wallet name preview, civil lock confirm
FORBIDDEN:    breach/NIK bots, captcha farms, grey admin APIs, silent empty success
```
