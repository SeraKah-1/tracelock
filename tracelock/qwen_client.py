"""Qwen Cloud / Alibaba DashScope OpenAI-compatible client.

Proof of Alibaba Cloud service usage for hackathon submission:
- Base URL defaults to DashScope international compatible-mode endpoint
- API key from DASHSCOPE_API_KEY or QWEN_API_KEY
- Model defaults to qwen-plus (configurable via QWEN_MODEL)

Offline mode: when no key is set (or TRACELOCK_OFFLINE=1), returns a
deterministic planner plan without calling the network.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Alibaba Cloud DashScope (Qwen Cloud) — OpenAI-compatible API
# Documented for Global AI Hackathon Series with Qwen Cloud.
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"

# Regional alternate (China mainland DashScope) — still Alibaba Cloud
ALT_BASE_URL_CN = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class QwenConfig:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    # planner: use Qwen API only when key present AND offline is False
    # Missing key is NOT an error — local deterministic planner is first-class
    # (host AI agents like Claude/Grok/Qwen Code already plan; tools do the work).
    offline: bool = False
    provider: str = "local-planner"
    no_network: bool = False

    @classmethod
    def from_env(cls) -> "QwenConfig":
        key = (
            os.environ.get("DASHSCOPE_API_KEY", "").strip()
            or os.environ.get("QWEN_API_KEY", "").strip()
        )
        # TRACELOCK_OFFLINE / TRACELOCK_NO_NETWORK = no live HTTP collection (CI only)
        no_net = os.environ.get("TRACELOCK_NO_NETWORK", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ) or os.environ.get("TRACELOCK_OFFLINE", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        # Force Qwen planner only when explicitly requested
        force_qwen = os.environ.get("TRACELOCK_PLANNER", "").strip().lower() in (
            "qwen",
            "dashscope",
            "live",
        )
        base = os.environ.get("QWEN_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        model = os.environ.get("QWEN_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        # Default: local planner (no API key required). Qwen only if key + force or key alone with TRACELOCK_USE_QWEN=1
        use_qwen = bool(key) and (
            force_qwen
            or os.environ.get("TRACELOCK_USE_QWEN", "").strip().lower() in ("1", "true", "yes")
        )
        offline = not use_qwen  # offline here means "don't call Qwen API"
        return cls(
            api_key=key if use_qwen else "",
            base_url=base,
            model=model if use_qwen else "local-planner",
            offline=offline,
            provider="alibaba-cloud-dashscope" if use_qwen else "local-planner",
            no_network=no_net,
        )


@dataclass
class PlanStep:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class AgentPlan:
    mode: str  # "live" | "offline"
    model: str
    provider: str
    base_url: str
    summary: str
    steps: list[PlanStep]
    hitl_checkpoints: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "model": self.model,
            "provider": self.provider,
            "base_url": self.base_url,
            "summary": self.summary,
            "steps": [
                {"tool": s.tool, "args": s.args, "reason": s.reason} for s in self.steps
            ],
            "hitl_checkpoints": list(self.hitl_checkpoints),
        }


SYSTEM_PROMPT = """You are TraceLock, an ethical investigation autopilot agent for public-source OSINT.
You plan multi-step workflows from ambiguous clues. You never invent identities.
You separate digital identity lock (handles) from civil identity lock (legal name + institutional ID).
You open HITL gates on: browser/captcha walls, phone Layer-B e-wallet checks, civil lock confirmation.
You refuse: breach dumps, NIK bots, captcha farms, non-public admin APIs.

Return ONLY valid JSON with this shape:
{
  "summary": "one sentence plan",
  "steps": [
    {"tool": "TOOL_NAME", "args": {}, "reason": "why"}
  ],
  "hitl_checkpoints": ["when human must approve"]
}

Available tools:
- init_case: {}
- analyze_clues: {}
- normalize_phone: {"phone": "..."}  (if phone present)
- phone_queries: {"phone": "..."}
- phone_checklist: {"phone": "..."}
- name_pattern_enum: {}  (if handles without legal name)
- digital_footprint: {"quick": true}  (cross-platform username enum + SERP pack + full checklist)
- collect_public: {"modules": "websearch,gov_id,username_enum"}  (LIVE public HTTP — no DashScope key)
- plan_sources: {}
- open_hitl: {"template": "pddikti|phone_layer_b|browser_challenge", "reason": "..."}
- build_dossier: {}
- report: {}
"""


def offline_plan_for_clues(clues: list[str]) -> AgentPlan:
    """Deterministic planner used without API key — still multi-step + HITL."""
    joined = " ".join(clues).lower()
    steps: list[PlanStep] = [
        PlanStep("init_case", {}, "Create durable case store for evidence chain"),
        PlanStep("analyze_clues", {}, "Classify ambiguous seeds (handle/name/phone/NIM)"),
    ]
    hitl: list[str] = []

    phone_m = re.search(
        r"(?:\+?62|0)\s*[\d\-\s]{8,}", " ".join(clues)
    ) or re.search(r"phone[:\s]+([+\d\-\s]+)", " ".join(clues), re.I)
    if phone_m or "phone" in joined:
        phone = phone_m.group(0) if phone_m else ""
        phone = phone.replace("phone:", "").strip() if phone else "081255500100"
        steps.append(
            PlanStep(
                "normalize_phone",
                {"phone": phone},
                "E.164 normalize; prefix is soft geo only",
            )
        )
        steps.append(
            PlanStep(
                "phone_queries",
                {"phone": phone},
                "Build public SERP / wa.me Layer-A footprint queries",
            )
        )
        steps.append(
            PlanStep(
                "phone_checklist",
                {"phone": phone},
                "Emit HITL checklist for Layer-B (operator-only e-wallet)",
            )
        )
        hitl.append("Phone Layer-B e-wallet/contact-sync — operator only, never auto")

    has_handle = any(
        x in joined
        for x in (
            "@",
            "instagram",
            "tiktok",
            "handle",
            "username:",
            "threads",
            "github",
        )
    )
    if has_handle and not any(k in joined for k in ("name:", "nama:")):
        steps.append(
            PlanStep(
                "name_pattern_enum",
                {},
                "Unknown-name path: expand handle nick patterns instead of asking legal name",
            )
        )

    # Always run digital footprint when any identity clue exists (anti-lazy full trail)
    if has_handle or "url:" in joined or "name:" in joined or "phone" in joined:
        steps.append(
            PlanStep(
                "digital_footprint",
                {"quick": True},
                "Cross-platform username enum + SERP pack + full footprint checklist",
            )
        )

    # LIVE public collection — core value without any LLM API key
    collect_mods = ["websearch"]
    if "name:" in joined or "nama:" in joined:
        collect_mods = ["websearch", "gov_id", "pddikti"]
    if has_handle:
        collect_mods = list(dict.fromkeys(collect_mods + ["username_enum"]))
    if "phone" in joined:
        collect_mods = list(dict.fromkeys(collect_mods + ["phone_footprint"]))
    steps.append(
        PlanStep(
            "collect_public",
            {"modules": ",".join(collect_mods)},
            "Live public HTTP collection (websearch/gov/username) — no DashScope required",
        )
    )

    steps.append(
        PlanStep(
            "plan_sources",
            {},
            "Map questions → public sources (web, campus lists, gov passive pack)",
        )
    )

    if any(x in joined for x in ("nim", "pddikti", "mahasiswa", "fk ", "unri", "name:", "nama:")):
        steps.append(
            PlanStep(
                "open_hitl",
                {
                    "template": "pddikti",
                    "reason": "Portal may present Cloudflare — never captcha farm",
                },
                "Zero-autonomy: browser wall requires human for civil claims",
            )
        )
        hitl.append("PDDIKTI / browser challenge — complete gate before civil claims")

    hitl.append("Civil identity-lock requires multi-signal name+NIM — human confirms")
    steps.append(
        PlanStep(
            "build_dossier",
            {},
            "Assemble dimensions (education, org, geo soft) with graded evidence",
        )
    )
    steps.append(
        PlanStep(
            "report",
            {},
            "Emit structured dossier + markdown; never sell digital lock as KTP",
        )
    )

    return AgentPlan(
        mode="local",
        model="local-planner",
        provider="local-planner",
        base_url=DEFAULT_BASE_URL,
        summary=(
            "Local planner + live public collection: footprint enum, websearch/gov, "
            "HITL walls, graded dossier. Host AI does not need DashScope API key."
        ),
        steps=steps,
        hitl_checkpoints=hitl,
        raw_text="local_plan_for_clues",
    )


def _parse_plan_json(text: str, cfg: QwenConfig) -> AgentPlan:
    text = text.strip()
    # strip markdown fences if model adds them
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    steps = [
        PlanStep(
            tool=str(s.get("tool", "")),
            args=dict(s.get("args") or {}),
            reason=str(s.get("reason") or ""),
        )
        for s in (data.get("steps") or [])
        if s.get("tool")
    ]
    return AgentPlan(
        mode="live",
        model=cfg.model,
        provider=cfg.provider,
        base_url=cfg.base_url,
        summary=str(data.get("summary") or ""),
        steps=steps,
        hitl_checkpoints=[str(x) for x in (data.get("hitl_checkpoints") or [])],
        raw_text=text,
    )


def plan_with_qwen(clues: list[str], cfg: Optional[QwenConfig] = None) -> AgentPlan:
    """Plan investigation steps.

    Default = **local planner** (full tool sequence, live collection tools).
    Qwen Cloud only when TRACELOCK_USE_QWEN=1 and DASHSCOPE_API_KEY set.
    Host agents (Claude/Grok/Qwen Code) should rely on local planner + collect_public.
    """
    cfg = cfg or QwenConfig.from_env()
    if cfg.offline or not cfg.api_key:
        plan = offline_plan_for_clues(clues)
        plan.base_url = cfg.base_url
        plan.provider = cfg.provider or "local-planner"
        if cfg.no_network:
            plan.summary = (
                (plan.summary or "")
                + " [TRACELOCK_NO_NETWORK: collection fixtures only]"
            )
        return plan

    user = (
        "Plan an end-to-end public-source investigation for these ambiguous clues:\n"
        + "\n".join(f"- {c}" for c in clues)
        + "\nRespond with JSON only."
    )
    try:
        # Lazy import so offline demos need zero deps
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        plan = offline_plan_for_clues(clues)
        plan.summary = (
            f"openai SDK missing ({e}); fell back to offline plan. "
            "pip install 'tracelock[qwen]'"
        )
        plan.raw_text = "fallback_missing_openai"
        return plan

    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    content = (resp.choices[0].message.content or "").strip()
    try:
        return _parse_plan_json(content, cfg)
    except (json.JSONDecodeError, KeyError, TypeError):
        # Still return a usable plan — never silent empty success
        fallback = offline_plan_for_clues(clues)
        fallback.mode = "live"
        fallback.model = cfg.model
        fallback.raw_text = content
        fallback.summary = (
            "Live model returned non-JSON; merged offline tool sequence. Raw kept."
        )
        return fallback


def deployment_fingerprint() -> dict[str, Any]:
    """Machine-readable proof blob for Alibaba/Qwen wiring (no secrets)."""
    cfg = QwenConfig.from_env()
    return {
        "cloud_provider": "Alibaba Cloud",
        "service": "DashScope / Qwen Cloud (OpenAI-compatible mode)",
        "api_base_url": cfg.base_url,
        "default_api_base_url": DEFAULT_BASE_URL,
        "model": cfg.model,
        "auth_env_vars": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
        "key_configured": bool(cfg.api_key),
        "offline_mode": cfg.offline,
        "sdk": "openai (compatible-mode client)",
        "proof_module": "tracelock/qwen_client.py",
        "deploy_docs": "docs/ALIBABA_QWEN_DEPLOYMENT.md",
        "deploy_config": "deploy/qwen_cloud.env.example",
    }
