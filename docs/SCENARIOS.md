# Scenarios

Synthetic fixtures only — no real-person data in the repo.

---

## 1. Dual handle, legal name unknown

**Situation.** Two social usernames may belong to one person. Legal name is not available at intake.

**Clues**

```text
username:demo_subject_ig
username:demo_subject_tt
other:cohort note — public sources only
```

**What TraceLock does**

- Seeds handles into a durable case  
- Runs name-pattern expansion (hypotheses, not confirmed civil identity)  
- Plans public sources; opens HITL if a portal wall appears  
- Reports digital identity as partial and civil as open until multi-signal proof  

```bash
python3 -m tracelock run --offline \
  --clue 'username:demo_subject_ig' \
  --clue 'username:demo_subject_tt'
```

---

## 2. Phone-only fraud ticket

**Situation.** Ticket contains a phone number and a short note. Analyst needs a public footprint first; app-side checks stay human-only.

**Clues**

```text
phone:0811-6060-0613
other:ticket — public footprint first
```

**What TraceLock does**

- Normalizes to E.164  
- Builds Layer-A SERP / variant query pack  
- Emits Layer-B checklist and opens a zero-autonomy HITL gate (no auto e-wallet call)  
- Writes phone dimension + evidence trail  

```bash
python3 -m tracelock run --offline \
  --clue 'phone:0811-6060-0613' \
  --clue 'other:ticket — public footprint first'
```
