"""Slim OSINT core toolset — keep what works, demote noise.

Packs:
  CORE     — always run for real investigations
  HITL     — zero-autonomy operator gates
  DEMOTE   — keep callable, not default (optional probes)

General-purpose coding/browser tool sprawl is out of scope; this product is
public-source OSINT only, wrapped by TraceLock gateway + cron + skills.
"""

from __future__ import annotations

from typing import Any

# Tools that reliably move an investigation forward on public sources.
CORE_OSINT: tuple[str, ...] = (
    "init_case",
    "analyze_clues",
    "plan_sources",
    "normalize_phone",
    "phone_queries",
    "name_pattern_enum",
    "digital_footprint",
    "collect_public",  # live SERP + username enum
    "build_dossier",
    "report",
)

# Operator-only — open gate, never auto-complete restricted actions.
HITL_TOOLS: tuple[str, ...] = (
    "phone_checklist",  # Layer-B e-wallet
    "hitl_open",
)

# Callable but not default planner steps (noisy / passive packs).
DEMOTE: tuple[str, ...] = (
    # gov_id / pddikti modules still reachable via collect_public args.modules
    # when operator explicitly asks — not forced on every handle-only case.
)

# Toolsets for gateway / cron skill selection
TOOLSETS: dict[str, tuple[str, ...]] = {
    "osint_core": CORE_OSINT,
    "osint_hitl": HITL_TOOLS,
    "osint_full": CORE_OSINT + HITL_TOOLS,
}


def list_core() -> list[str]:
    return list(CORE_OSINT)


def list_toolset(name: str = "osint_full") -> list[str]:
    return list(TOOLSETS.get(name, CORE_OSINT))


def slim_summary() -> dict[str, Any]:
    return {
        "product": "TraceLock",
        "strategy": "slim public-source OSINT core + agentic gateway/cron/skills",
        "core": list(CORE_OSINT),
        "hitl": list(HITL_TOOLS),
        "demote": list(DEMOTE),
        "toolsets": {k: list(v) for k, v in TOOLSETS.items()},
        "runtime": [
            "toolset packs (osint_core / osint_full)",
            "messaging gateway (Telegram, webhook, email)",
            "scheduled OSINT jobs with delivery",
            "proactive continue from open case gaps",
            "skill wrapper around continuous investigate",
        ],
        "out_of_scope": [
            "general coding agents / terminal backends",
            "cloud browser farms",
            "breach corpora and grey APIs",
        ],
    }
