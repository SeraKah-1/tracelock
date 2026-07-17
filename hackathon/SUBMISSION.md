# Devpost fields (operator)

**Repo:** https://github.com/SeraKah-1/tracelock  
**Track:** Track 4 — Autopilot Agent  
**Deadline:** 2026-07-20 14:00 PT  

## Still required (not in git)

1. Demo video ≤3 minutes (YouTube / Vimeo / Youku), public  
2. Click Submit on https://qwencloud-hackathon.devpost.com/  
3. Optional: short public post about building on Qwen Cloud (blog prize)

## Paste-ready links

| Field | URL |
|-------|-----|
| Repository | https://github.com/SeraKah-1/tracelock |
| Architecture | https://github.com/SeraKah-1/tracelock/blob/main/docs/assets/architecture.svg |
| Alibaba / Qwen API proof | https://github.com/SeraKah-1/tracelock/blob/main/tracelock/qwen_client.py |
| Deployment notes | https://github.com/SeraKah-1/tracelock/blob/main/docs/DEPLOYMENT.md |

## Description (short)

TraceLock is an autopilot agent for ethical public-source investigations. It accepts ambiguous clues (handle, phone, free text), plans work with Qwen on Alibaba DashScope, runs real tools, pauses on human-in-the-loop gates, and emits a graded dossier that separates digital identity from civil identity.

## Test for judges

```bash
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock
python3 -m tracelock run --offline
```
