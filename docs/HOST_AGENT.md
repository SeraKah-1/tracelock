# Why host agents were "dumb" (and the fix)

## Symptoms

1. Forced `--offline` → empty digital dimensions  
2. Asked user for DashScope key even though Claude/Grok already plans  
3. Over-explained ethics instead of running public tools  

## Root cause

TraceLock treated "no DashScope key" as "offline useless mode".  
That conflated **planner** with **collection**.

| Concern | Correct default |
|---------|-----------------|
| Planner | **Local** tool sequence (host AI can also plan) |
| Collection | **Live public HTTP** (websearch, enum, gov) |
| Qwen Cloud | Optional (`--use-qwen` + key) |
| No-network fixtures | Explicit `--no-network` / `TRACELOCK_NO_NETWORK=1` |

## Correct one-liner for host agents

```bash
python3 -m tracelock osint "name:Prabowo Subianto"
```

Not:

```bash
python3 -m tracelock run --offline --clue "name:Prabowo Subianto"  # BAD for real OSINT
```

See root `AGENTS.md`.
