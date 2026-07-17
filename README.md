# TraceLock

**Ethical investigation autopilot** — ambiguous public clues → multi-tool workflow → **HITL zero-autonomy gates** → graded identity dossier.

> **Qwen Cloud Global AI Hackathon — Track 4: Autopilot Agent**  
> Multi-step real workflow · external tools · ambiguous input · human-in-the-loop at critical decisions · production-minded, not a toy chat demo.

| | |
|---|---|
| **Product** | TraceLock |
| **One-line pitch** | Autopilot agent that turns messy public clues into a graded person dossier — and **stops** when only a human may act. |
| **Track** | Track 4 — Autopilot Agent |
| **Cloud** | Alibaba Cloud **DashScope / Qwen Cloud** (OpenAI-compatible API) |
| **License** | MIT (see [`LICENSE`](./LICENSE) at repo root — GitHub-detectable) |
| **Deadline context** | Devpost Submission Period ends **2026-07-20** 14:00 PT |

---

## Problem → solution

**Problem.** Background checks and SOCMINT start from *ambiguous* inputs (a handle, a phone, a cohort rumor — not a clean CRM form). Operators drown in tabs; naive bots invent civil identity, hit captchas, or cross ethical lines (breach dumps, NIK bots).

**Solution.** TraceLock is an **autopilot workflow agent**:

1. **Ingest** mixed clues (username, phone, free text).  
2. **Plan** multi-step work with **Qwen** on Qwen Cloud (or a deterministic offline planner for demos/CI).  
3. **Call tools** that wrap a battle-tested OSINT CLI (`osint_cli`): normalize phone E.164, SERP query packs, name-pattern enum, case store, evidence chain.  
4. **Pause on zero-autonomy zones** (HITL): browser/Cloudflare walls, phone Layer-B e-wallet checks, civil lock (name+NIM multi-signal).  
5. **Emit** a structured **dossier report** (digital ≠ civil; graded evidence; never silent empty “success”).

---

## Track 4 mapping

| Track 4 requirement | TraceLock |
|---------------------|-----------|
| End-to-end business workflow | Clue intake → plan → tools → HITL → dossier report |
| Ambiguous inputs | Dual-handle / phone / blank legal name fixtures |
| Invoke external tools | Tool registry over `osint_cli` + optional live SERP modules |
| HITL at critical decisions | `open_hitl`, phone Layer-B checklist, civil-lock policy |
| Production-readiness | Case JSON on disk, evidence dedupe, offline mode, tests, ethics docs |

**Judging weights (official):** Innovation 30% · Technical depth 30% · Impact 25% · Presentation 15% — see [`docs/WIN_STRATEGY.md`](docs/WIN_STRATEGY.md).

---

## How Qwen Cloud is used

| Piece | Detail |
|-------|--------|
| **Service** | Alibaba Cloud **DashScope** OpenAI-compatible endpoint |
| **Default base URL** | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| **Auth** | `DASHSCOPE_API_KEY` or `QWEN_API_KEY` |
| **Model** | `QWEN_MODEL` (default `qwen-plus`) |
| **Role** | Planner: turns ambiguous clue list into ordered tool steps + HITL checkpoints (JSON) |
| **Code proof** | [`tracelock/qwen_client.py`](tracelock/qwen_client.py) · [`docs/ALIBABA_QWEN_DEPLOYMENT.md`](docs/ALIBABA_QWEN_DEPLOYMENT.md) · [`deploy/`](deploy/) |
| **Offline** | No key / `TRACELOCK_OFFLINE=1` → same tool-loop shape, mode labeled `offline` |

```text
Clues ──► Qwen planner (DashScope) ──► Tool loop (osint_cli)
                │                              │
                └── HITL checkpoints ──────────┴──► Case store + Dossier report
```

Architecture diagram: [`docs/assets/architecture.svg`](docs/assets/architecture.svg) · source [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Public repo

**https://github.com/SeraKah-1/tracelock** (MIT · public)

## How to use (short)

| Mode | Who drives it | Command / idea |
|------|----------------|----------------|
| **CLI demo** | You | `python3 -m tracelock run --offline` |
| **AI agent** | Claude/Cursor/Grok with shell | Ask agent to run that command + summarize dossier |
| **Your code** | Python host agent | `from tracelock.agent import run_agent` |

Full guide: **[`docs/HOW_TO_USE.md`](docs/HOW_TO_USE.md)** — this is a **tool + autopilot CLI**, not a chat website. Agents call tools; humans still clear HITL gates (login walls, Layer-B phone checks, civil lock).

## Install / run (demo end-to-end)

```bash
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock

# Offline demo (no API key) — always works for judges/CI
python3 -m tracelock run --offline

# Live planner (Qwen Cloud)
cp .env.example .env   # set DASHSCOPE_API_KEY
pip install '.[qwen]'  # openai SDK for DashScope compatible-mode
python3 -m tracelock run

# Proof blob (no secrets)
python3 -m tracelock deploy-proof

# Underlying OSINT CLI (same repo)
python3 -m osint_cli --help
```

Expected offline output includes:

- non-empty **plan** with ordered **tool** steps  
- **HITL** checkpoints (e.g. phone Layer-B)  
- non-empty **dossier** dimensions + **markdown report**

---

## Use cases

See **[`docs/USE_CASES.md`](docs/USE_CASES.md)** (≥2 personas):

1. **Unknown-name dual-handle** SOCMINT → digital lock path, never ask operator for legal name.  
2. **Phone-as-clue** compliance-style pivot → Layer A auto, Layer B HITL only.  

---

## Ethics & public-source limits

- **Public sources only** for automated collection.  
- **No** breach dumps, dark-web phone bots, NIK/KTP scrapers, captcha farms, grey admin APIs.  
- **Digital identity lock ≠ civil lock** — handles are not a national ID.  
- Phone **prefix ≠ domicile**; e-wallet display name = candidate, not civil proof.  
- Demo fixtures are **synthetic** (`tracelock/fixtures/`).  

Details: lineage docs in `docs/HITL_AND_CYBORG.md`, `docs/PHONE_PIVOT.md`, `docs/GOV_SOURCES.md`.

---

## Significant update during Submission Period

This repository packages the pre-existing `osint_cli` investigation engine as a **Qwen Cloud Autopilot Agent** product (**TraceLock**): agent planner, offline fixture loop, Alibaba/DashScope client proof, architecture diagram, use cases, and Devpost submit pack — built for the **2026 Qwen Cloud Global AI Hackathon** Submission Period.

---

## Repo map

```text
tracelock/           # Autopilot agent (Qwen client, tools, demo CLI)
osint_cli/           # Investigation tools / case engine
docs/                # Use cases, win strategy, architecture, deploy proof, checklist
deploy/              # Alibaba/Qwen env + compose-style deploy notes
tests/               # pytest (tools + agent offline path + core OSINT)
LICENSE              # MIT (root)
```

---

## Submission pack (Devpost later)

Fillable checklist: **[`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md)**  

Win-oriented notes: **[`docs/WIN_STRATEGY.md`](docs/WIN_STRATEGY.md)**  

You still need (outside this goal): public GitHub push, ≤3 min demo video (YouTube/Vimeo/Youku), live DashScope key for the video, Devpost “Join / Submit”.

---

## Name alternatives considered

| Name | Why not chosen |
|------|----------------|
| CasePilot | Generic; weaker lock metaphor |
| DossierForge | Sounds generative / freer with facts |
| SeraKah CLI | Internal brand; less Track-4 “agent” clarity |
| **TraceLock** ✓ | Trace = investigation trail; Lock = digital/civil HITL gates |

---

## License

MIT — see [`LICENSE`](./LICENSE).
