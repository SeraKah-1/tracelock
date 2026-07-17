# Phone as clue (v0.7)

See also: Documents playbook `PHONE_PIVOT_OSINT_PLAYBOOK.md`.

## Quick use

```bash
osint-cli phone normalize "0811-60600-613"
osint-cli -c case.json seed add "phone:0811-60600-613"
osint-cli -c case.json plan
osint-cli -c case.json collect --modules phone_footprint,websearch
osint-cli phone checklist "0811-60600-613"   # Layer B operator steps
```

## Layers

| Layer | What tool does |
|-------|----------------|
| **A** | Normalize E.164, prefix soft, multi-variant SERP, wa.me link, plan questions |
| **B** | Checklist only (wallet preview, WA, contact sync lab) — operator HITL |
| **C** | Forbidden: breach bots, NIK/alamat leaks, IDOR |

## Rules

- Phone is **clue** (hard_id), not goal.
- E-wallet displayed name → **name_candidate**, not civil lock.
- Carrier prefix → **soft**, not domicile.
- Multi-signal before identity-lock.
