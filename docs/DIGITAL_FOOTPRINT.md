# Digital footprint tracking

## Already in TraceLock?

| Capability | Status |
|------------|--------|
| Case evidence trail (durable JSON) | Yes |
| Phone Layer-A footprint + Layer-B HITL | Yes |
| Name-pattern / dual-handle path | Yes |
| Cross-platform username enum | **Yes (`digital_footprint` tool)** |
| Full SOCMINT checklist (anti-lazy) | **Yes (auto-expanded)** |
| Short prompt → full workflow | **Yes (`tracelock osint …`)** |
| Continuous monitoring / alerts | No (point-in-time investigation) |
| Sherlock/Maigret 300+ sites | Partial public set (extensible) |

## Research-backed workflow (what we encode)

Industry SOCMINT practice (username correlation, multi-platform enum, validate before lock):

1. **Scope** — exact seed strings only  
2. **Normalize** — E.164 phone, bare handle, URL→platform  
3. **Enumerate** — same handle across IG/TikTok/Threads/X/GitHub/…  
4. **Pivot** — bio links, dual handles, name morph if legal name blank  
5. **SERP pack** — quoted queries for operators/host agents  
6. **Correlate** — multi-signal; digital ≠ civil  
7. **HITL** — captcha / Layer-B / civil lock  
8. **Report** — graded dossier; gaps explicit  

Sources informing design: cross-platform username reuse, Sherlock/Maigret-style enum, intelligence cycle (collect→analyze→report), no dark-web/breach default.

## Short prompt (user) vs full quality (system)

User can say:

```bash
python3 -m tracelock osint @demo_subject_ig
# or
python3 -m tracelock osint "lakukan osint ke username:demo_subject_ig"
# or
python3 -m tracelock osint "phone:0812-5550-0100"
```

System expands to typed seeds + **full checklist** + tool plan (same quality as a long operator prompt).

Preview expansion only:

```bash
python3 -m tracelock footprint "@demo_subject_ig phone:0812-5550-0100"
```

## Host AI agents (Claude / Qwen / Grok)

Instead of pasting a page-long OSINT prompt, the host agent runs:

```text
python3 -m tracelock osint <clue>
```

Then reads the dossier / case JSON. Host may still use its own websearch for SERP hits from the emitted query pack.

## Policy

- Public HTTP only for enum  
- No captcha farms, no NIK/breach bots  
- Soft platform “hits” need human corroboration before civil claims  
