# Deployment (Qwen Cloud / DashScope)

TraceLock’s planner uses **Alibaba Cloud DashScope (Qwen Cloud)** OpenAI-compatible APIs. This page documents env, endpoints, and the code path.

> *Proof of Alibaba Cloud Deployment: a link to a code file in the repo that demonstrates use of Alibaba Cloud services and APIs.*

**Primary code proof (link this on Devpost):**  
[`../tracelock/qwen_client.py`](../tracelock/qwen_client.py)

---

## What is deployed / called

| Item | Value |
|------|--------|
| Cloud provider | **Alibaba Cloud** |
| Service | **DashScope / Qwen Cloud** OpenAI-compatible mode |
| Default base URL | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| Mainland alternate | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Default model | `qwen-plus` (`QWEN_MODEL`) |
| Auth env | `DASHSCOPE_API_KEY` or `QWEN_API_KEY` |
| SDK | Official pattern: OpenAI Python client with custom `base_url` |

Hackathon resources document the same compatible-mode base URL pattern  
(see Devpost Resources: API Base URL `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`).

---

## Code path (no secrets)

```python
# tracelock/qwen_client.py (excerpt concept)
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"

# Live path:
# client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DEFAULT_BASE_URL)
# client.chat.completions.create(model=QWEN_MODEL, messages=[...])
```

Fingerprint CLI (safe to paste in video):

```bash
python3 -m tracelock deploy-proof
```

Example output shape:

```json
{
  "cloud_provider": "Alibaba Cloud",
  "service": "DashScope / Qwen Cloud (OpenAI-compatible mode)",
  "api_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
  "model": "qwen-plus",
  "auth_env_vars": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
  "proof_module": "tracelock/qwen_client.py"
}
```

---

## Local / lab “deploy” steps

1. Create Qwen Cloud account and API key (hackathon free quota / voucher as applicable).  
2. Copy env:

```bash
cp .env.example .env
# edit DASHSCOPE_API_KEY=
cp deploy/qwen_cloud.env.example deploy/qwen_cloud.env
```

3. Install optional SDK:

```bash
pip install '.[qwen]'
```

4. Run live planner:

```bash
export DASHSCOPE_API_KEY=sk-...
python3 -m tracelock run
```

5. Optional: run agent process next to a static file server for architecture SVG, or containerize with the sample Compose file in `deploy/docker-compose.qwen.yml` (agent still calls DashScope **cloud** API — compute may be local or on an Alibaba ECS you attach later).

---

## What “deployment proof” means here

Hackathon wording asks for a **repo link demonstrating Alibaba Cloud services/APIs**, not necessarily a paid always-on ECS. TraceLock’s backend planner is **defined against DashScope endpoints**. Offline mode is for reproducibility when judges lack keys; live mode is the production path.

If you later host the CLI/API on **Alibaba Cloud ECS / ACK / Function Compute**, add the instance region and a screenshot to the Devpost gallery and mention it in the description — optional stretch, not required for this repo’s gating proof file.

---

## Related files

| File | Role |
|------|------|
| `tracelock/qwen_client.py` | **Canonical API proof** |
| `deploy/qwen_cloud.env.example` | Env template |
| `deploy/docker-compose.qwen.yml` | Optional runtime wrapper |
| `.env.example` | Developer env |
