# Deploy TraceLock agentic gateway on Alibaba Cloud

Target: long-running OSINT agent on **ECS** (or Container Service), optional **DashScope** for planner, messaging via Telegram / webhook / email.

## 1. ECS (minimal)

- Ubuntu 22.04 / Alibaba Linux 3  
- 1–2 vCPU, 2 GB RAM (gateway is light; SERP is I/O bound)  
- Security group: open **8787/tcp** (gateway HTTP) only from your IP or LB  
- Outbound HTTPS required for public SERP + Telegram API  

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# optional Qwen planner
# export DASHSCOPE_API_KEY=sk-...
# pip install -e '.[qwen]'
```

## 2. Environment

```bash
export TRACELOCK_HOME=/var/lib/tracelock
export TRACELOCK_CASES_DIR=$TRACELOCK_HOME/cases
export TRACELOCK_GATEWAY_HOST=0.0.0.0
export TRACELOCK_GATEWAY_PORT=8787

# OpenAI-compatible planner (DashScope / other)
export TRACELOCK_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export TRACELOCK_API_KEY=sk-...          # or DASHSCOPE_API_KEY
export TRACELOCK_MODEL=qwen-plus
# On first boot you can also: python -m tracelock setup

# Telegram (recommended first channel)
export TRACELOCK_TELEGRAM_BOT_TOKEN=123456:ABC...
export TRACELOCK_TELEGRAM_ALLOWLIST=your_telegram_user_id

# Optional live SMTP (else email → $TRACELOCK_HOME/outbox/*.eml)
# export TRACELOCK_SMTP_HOST=smtpdm.aliyun.com
# export TRACELOCK_SMTP_PORT=465
# export TRACELOCK_SMTP_USER=...
# export TRACELOCK_SMTP_PASS=...
# export TRACELOCK_SMTP_FROM=osint@yourdomain.com
```

## 3. systemd unit

`/etc/systemd/system/tracelock-gateway.service`:

```ini
[Unit]
Description=TraceLock OSINT Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tracelock
WorkingDirectory=/opt/tracelock
EnvironmentFile=/etc/tracelock/env
ExecStart=/opt/tracelock/.venv/bin/python -m tracelock gateway start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tracelock-gateway
sudo systemctl status tracelock-gateway
curl -s http://127.0.0.1:8787/health
```

## 4. Channels

| Channel | How |
|---------|-----|
| **Telegram** | Set bot token; long-poll is default. Or set webhook `https://your-host/telegram` |
| **WhatsApp** | Use Meta Cloud API → POST JSON `{ "text": "…" }` to `/webhook` or `/osint`; reply field `reply` |
| **Email** | Cron `--deliver email:you@x.com` or SMTP env; without SMTP uses outbox files |
| **Generic** | `POST /osint` `{"text":"@handle"}` |

## 5. Proactive jobs

```bash
python -m tracelock cron add \
  --name nightly-watch \
  --schedule interval:1d \
  --prompt 'username:target_handle' \
  --deliver telegram:CHAT_ID \
  --deliver file:/var/lib/tracelock/reports/nightly.txt
```

Gateway process ticks cron every `TRACELOCK_CRON_INTERVAL` (default 60s).

Also:

```bash
python -m tracelock watch --cases-dir /var/lib/tracelock/cases --interval 600
```

## 6. DashScope (optional)

Default planner is **local** (host AI or rule plan). For Qwen-as-planner:

```bash
export DASHSCOPE_API_KEY=sk-...
export TRACELOCK_USE_QWEN=1
# region: https://dashscope.aliyuncs.com/compatible-mode/v1
```

## 7. Policy reminder

- Public sources only  
- HITL for captcha / Layer-B phone apps / civil lock  
- Never store breach corpora or captcha-farm keys  
- Set Telegram allowlist in production  

## 8. Health checklist

```bash
python -m tracelock model --list
python -m tracelock gateway status
python -m tracelock ask "/status"
curl -s http://127.0.0.1:8787/health
# Telegram: message bot with /help then /osint @handle
```
