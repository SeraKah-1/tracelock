# Devpost submission checklist — TraceLock (Track 4)

**Hackathon:** Global AI Hackathon Series with Qwen Cloud  
**URL:** https://qwencloud-hackathon.devpost.com/  
**Deadline:** 2026-07-20 14:00 Pacific Time (extended)  
**Track to select:** **Track 4: Autopilot Agent**

Use this as a fill-in form. Items marked **DONE IN REPO** are ready; items marked **OPERATOR** need your account/video/push.

---

## Before Devpost click

| # | Item | Status | Value / notes |
|---|------|--------|----------------|
| 1 | Devpost account + Join Hackathon | OPERATOR | |
| 2 | Qwen Cloud account + API key | OPERATOR | https://www.qwencloud.com/ · free quota / voucher per resources page |
| 3 | Discord (optional support) | OPERATOR | https://discord.gg/cDEHSV4Qqj |
| 4 | Public GitHub repo | OPERATOR | Suggested: `https://github.com/<you>/tracelock` |
| 5 | Root LICENSE visible | DONE IN REPO | MIT `LICENSE` |
| 6 | English README | DONE IN REPO | `README.md` |
| 7 | Architecture diagram | DONE IN REPO | `docs/assets/architecture.svg` |
| 8 | Alibaba/Qwen proof file | DONE IN REPO | `tracelock/qwen_client.py` + `docs/ALIBABA_QWEN_DEPLOYMENT.md` |
| 9 | Runnable demo offline | DONE IN REPO | `python3 -m tracelock run --offline` |
| 10 | Live demo with key | OPERATOR | `DASHSCOPE_API_KEY=... python3 -m tracelock run` |
| 11 | Demo video ≤3 min public | OPERATOR | YouTube / Vimeo / Youku |
| 12 | Optional blog/social journey | OPERATOR | Blog Post bonus prize eligibility |

---

## Devpost fields (paste draft)

### Project name
```
TraceLock — Ethical Investigation Autopilot (Qwen Track 4)
```

### Tagline (≤ few words if limited)
```
Ambiguous clues → tools → HITL → graded dossier
```

### Track
```
Track 4: Autopilot Agent
```

### Repository URL
```
https://github.com/<YOUR_ORG>/tracelock
```

### Architecture diagram URL (raw or docs path)
```
https://github.com/<YOUR_ORG>/tracelock/blob/main/docs/assets/architecture.svg
```

### Proof of Alibaba Cloud deployment (link to code file)
```
https://github.com/<YOUR_ORG>/tracelock/blob/main/tracelock/qwen_client.py
```
Secondary writeup:
```
https://github.com/<YOUR_ORG>/tracelock/blob/main/docs/ALIBABA_QWEN_DEPLOYMENT.md
```

### Demo video URL
```
https://youtube.com/watch?v=________   # OPERATOR fill
```

### Built with (suggested tags)
```
Qwen, Qwen Cloud, DashScope, Alibaba Cloud, Python, OpenAI-compatible API, HITL, OSINT
```

### Project description (English draft)

```markdown
TraceLock is an Autopilot Agent for ethical public-source investigation workflows.

Investigators rarely get clean forms — they get a handle, a phone number, or a
vague cohort note. TraceLock uses Qwen models on Qwen Cloud (Alibaba DashScope
OpenAI-compatible API) to plan multi-step work, then executes real tools:
phone E.164 normalization, SERP query packs, name-pattern expansion, durable
case storage, and graded dossier reporting.

Critical steps are Zero-Autonomy HITL gates: browser/captcha walls, phone
Layer-B e-wallet checks, and civil identity lock (legal name + institutional ID
only with multi-signal proof). The agent refuses breach dumps, NIK bots, and
captcha farms.

Offline mode runs the same tool-loop shape without an API key so judges can
reproduce the demo. Live mode swaps in Qwen as the planner.

Track 4 fit: end-to-end workflow, ambiguous inputs, external tools, HITL,
production-minded case files.
```

### How we used Qwen Cloud
```
Planner LLM via DashScope compatible-mode base URL
https://dashscope-intl.aliyuncs.com/compatible-mode/v1
with model qwen-plus (configurable). See tracelock/qwen_client.py.
```

### Significant update during Submission Period
```
Packaged the osint_cli investigation engine as TraceLock Autopilot Agent:
Qwen planner client, offline twin, architecture, use cases, deploy proof,
and Devpost submit pack for Track 4.
```

### Testing instructions for judges
```bash
git clone <repo>
cd tracelock
python3 -m tracelock run --offline
# optional live:
# export DASHSCOPE_API_KEY=...
# pip install '.[qwen]'
# python3 -m tracelock run
python3 -m tracelock deploy-proof
```

---

## Video checklist (operator)

- [ ] Show problem in one sentence  
- [ ] Run offline or live demo end-to-end  
- [ ] Show HITL gate in output  
- [ ] Show dossier markdown  
- [ ] Flash architecture + `qwen_client.py` base URL  
- [ ] Under 3:00, public, no copyrighted music  

---

## After submit

- [ ] Keep repo public through Judging Period (through ~2026-08-11)  
- [ ] Do not break clone/run path  
- [ ] Respond to judge questions if contacted  
