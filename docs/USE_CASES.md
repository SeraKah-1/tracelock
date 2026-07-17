# TraceLock — Use cases (Track 4 Autopilot)

Each use case is an **end-to-end workflow**: ambiguous input → tool calls → HITL → structured dossier.  
Fixtures are synthetic; do not substitute real-person doxx data in the public repo.

---

## Use case 1 — Unknown-name dual-handle SOCMINT

### Persona
**Maya**, junior investigator at a campus safety desk. She receives two social handles that *might* be the same person after a harassment report. Legal name is blank. Asking the reporter for a full name may re-traumatize or be impossible.

### Ambiguous input
```text
username:demo_subject_ig
username:demo_subject_tt
other:FK demo university maba cohort fixture 2025
other:ambiguous dual-handle research — legal name blank on purpose
```

### Autopilot workflow
| Step | Agent action | Tool / HITL |
|------|----------------|-------------|
| 1 | Init durable case | `init_case` |
| 2 | Classify seeds | `analyze_clues` |
| 3 | Expand nick → given-name *hypotheses* | `name_pattern_enum` |
| 4 | Map public sources | `plan_sources` |
| 5 | If campus portal wall appears | `open_hitl` template `pddikti` (**zero-autonomy**) |
| 6 | Build graded dimensions | `build_dossier` |
| 7 | Emit report | `report` |

### Track 4 signals
- **Ambiguity:** no legal name; dual handle.  
- **Tools:** real `osint_cli` name-pattern + case evidence chain.  
- **HITL:** never auto-claim civil identity; portal walls open gates.  
- **Output:** digital identity partial vs civil open — explicit in report.

### Demo command
```bash
python3 -m tracelock run --offline \
  --clue 'username:demo_subject_ig' \
  --clue 'username:demo_subject_tt' \
  --clue 'other:FK demo university maba cohort fixture 2025'
```

### Success criteria (judges can verify offline)
- Plan lists ≥5 tool steps.  
- Report markdown non-empty with `identity_digital` dimension.  
- No fabricated NIM/KTP fields.

---

## Use case 2 — Phone-as-clue compliance pivot

### Persona
**Rafi**, fraud-ops analyst. A ticket contains only a customer phone number and a short free-text note. He must build a **public** footprint and escalate sensitive app checks to a human.

### Ambiguous input
```text
phone:0811-6060-0613
other:ticket: possible mule account — public footprint only first
```

### Autopilot workflow
| Step | Agent action | Tool / HITL |
|------|----------------|-------------|
| 1 | Init case | `init_case` |
| 2 | Analyze seeds | `analyze_clues` |
| 3 | E.164 normalize + provider soft hint | `normalize_phone` |
| 4 | Build Layer-A SERP / variant queries | `phone_queries` |
| 5 | Emit Layer-B checklist + open gate | `phone_checklist` → **HITL zero-autonomy** |
| 6 | Source plan | `plan_sources` |
| 7 | Dossier + report | `build_dossier`, `report` |

### Track 4 signals
- **Ambiguity:** phone-only ticket.  
- **Tools:** `normalize_phone_record`, `build_footprint_queries`, `hitl_phone_checklist` (shipped).  
- **HITL:** e-wallet name preview / contact sync never auto-executed.  
- **Production policy:** prefix ≠ domicile; display name ≠ civil lock.

### Demo command
```bash
python3 -m tracelock run --offline \
  --clue 'phone:0811-6060-0613' \
  --clue 'other:ticket: possible mule account — public footprint only first'
```

### Success criteria
- Report shows phone dimension `partial` with E.164 evidence.  
- At least one HITL gate with kind/source `phone_layer_b`.  
- Checklist includes Layer-B steps without executing wallet APIs.

---

## Optional wow path (video script beat)

Combine both: dual-handle **plus** phone fixture → show planner ordering tools, pause on HITL, then scroll dossier.  
Live Qwen: set `DASHSCOPE_API_KEY` and drop `--offline` so the plan summary is model-authored while tools remain deterministic.
