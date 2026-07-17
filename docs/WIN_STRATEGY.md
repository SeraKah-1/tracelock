# TraceLock — Win strategy & judges notes

Hackathon: **Global AI Hackathon Series with Qwen Cloud**  
Track: **4 — Autopilot Agent**  
Official site: https://qwencloud-hackathon.devpost.com/  
Rules: https://qwencloud-hackathon.devpost.com/rules  

**We do not claim a prize outcome.** This doc aligns the product with published criteria and patterns observed in strong Autopilot submissions (e.g. HITL “zero-autonomy” framing, production workflow, English docs).

---

## Official judging weights

| Criterion | Weight | How TraceLock answers |
|-----------|--------|------------------------|
| **Innovation & AI Creativity** | 30% | Qwen as **workflow planner** over a real OSINT toolbelt; digital≠civil lock as product idea; offline twin of the same loop |
| **Technical Depth & Engineering** | 30% | Modular agent/tools/case store; evidence chain; HITL gates; pytest on real entry points |
| **Problem Value & Impact** | 25% | Real investigator pain (ambiguous clues, ethical walls); campus/fraud-ops personas |
| **Presentation & Documentation** | 15% | English README, architecture SVG, use cases, submit checklist, deploy proof |

Stage One is pass/fail on theme + required APIs (Qwen on Qwen Cloud). Stage Two uses the weights above.

---

## Research takeaways (what tends to win Autopilot)

Distilled from official rules, resources, and public writeups of strong Track-4 style work:

1. **Problem-first, not model-first.** Judges reward end-to-end workflow that replaces a messy human process — not “chat with Qwen about OSINT.”  
2. **One polished demo path.** ≤3 minutes video; one fixture story with a clear before/after.  
3. **HITL is a feature.** “Zero-autonomy zones” (stop before civil claims, wallet checks, LE escalation) beat unbounded agents.  
4. **Production signals.** Durable state, audit-ish evidence, deploy proof on Alibaba, architecture diagram — required and scored under tech/presentation.  
5. **English everything.** Rules require English materials (or translation).  
6. **Public OSS + LICENSE at root.** Detectable MIT/Apache on GitHub About.  
7. **Significant update if pre-existing.** Document Qwen agent packaging during Submission Period (TraceLock README does).  
8. **Optional blog prize.** Separate $500 path for a public journey post with Qwen Cloud — link on Devpost.

---

## Demo narrative (≤3 min)

| Time | Beat |
|------|------|
| 0:00–0:20 | Problem: ambiguous handle + phone ticket |
| 0:20–0:50 | `python3 -m tracelock run` — show plan JSON from Qwen/offline |
| 0:50–1:40 | Tool loop scrolling: normalize, queries, HITL gate open |
| 1:40–2:20 | Dossier report: digital partial, civil open, policy lines |
| 2:20–2:50 | Architecture diagram + DashScope base URL in code |
| 2:50–3:00 | Ethics one-liner + CTA repo URL |

Shot list: `docs/DEMO_SHOTLIST.md`.

---

## Submission package must-haves

From official **Submission Requirements**:

- [x] Public OSS repo + root **LICENSE**  
- [x] Text description (README + Devpost fields in checklist)  
- [x] **Proof of Alibaba Cloud deployment** = link to code file using Alibaba/Qwen APIs (`tracelock/qwen_client.py`)  
- [x] **Architecture diagram** (`docs/assets/architecture.svg`)  
- [ ] Demo video ≤3 min on YouTube/Vimeo/Youku (**operator records**)  
- [x] Identify **Track 4**  
- [ ] Optional blog/social journey post  

Fillable form: `docs/SUBMISSION_CHECKLIST.md`.

---

## Naming

**TraceLock** — investigation *trace* + identity *lock* / HITL gates.  
Pitch fits Autopilot language without sounding like a toy chatbot.
