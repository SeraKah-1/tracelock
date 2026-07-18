"""Persistent runtime config: API endpoint, key, model, platforms.

Stored at TRACELOCK_HOME/config.json (default ~/.tracelock/config.json).
Env vars still override when set (for deploy).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


def tracelock_home() -> Path:
    raw = os.environ.get("TRACELOCK_HOME") or str(Path.home() / ".tracelock")
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return tracelock_home() / "config.json"


@dataclass
class RuntimeConfig:
    # OpenAI-compatible LLM
    api_base: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
    model: str = "qwen-plus"
    # agent loop
    max_turns: int = 24
    temperature: float = 0.2
    # memory
    memory_enabled: bool = True
    memory_char_limit: int = 2200
    user_char_limit: int = 1375
    # sessions
    cases_dir: str = ""
    # gateway / platforms
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8787
    telegram_bot_token: str = ""
    telegram_allowlist: str = ""  # comma ids
    # display
    show_tool_progress: bool = True
    # product
    personality: str = "operator"  # operator | brief | forensic

    def __post_init__(self) -> None:
        if not self.cases_dir:
            self.cases_dir = str(tracelock_home() / "cases")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # never echo full key in casual status unless requested
        return d

    def public_status(self) -> dict[str, Any]:
        key = self.api_key or ""
        masked = (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("set" if key else "missing")
        return {
            "api_base": self.api_base,
            "api_key": masked,
            "model": self.model,
            "max_turns": self.max_turns,
            "memory_enabled": self.memory_enabled,
            "gateway": f"{self.gateway_host}:{self.gateway_port}",
            "telegram": bool(self.telegram_bot_token),
            "cases_dir": self.cases_dir,
            "personality": self.personality,
        }

    def apply_env_overrides(self) -> "RuntimeConfig":
        """Env wins for deploy secrets."""
        if os.environ.get("TRACELOCK_API_BASE") or os.environ.get("QWEN_BASE_URL"):
            self.api_base = (
                os.environ.get("TRACELOCK_API_BASE")
                or os.environ.get("QWEN_BASE_URL")
                or self.api_base
            ).rstrip("/")
        if os.environ.get("TRACELOCK_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY"):
            self.api_key = (
                os.environ.get("TRACELOCK_API_KEY")
                or os.environ.get("DASHSCOPE_API_KEY")
                or os.environ.get("QWEN_API_KEY")
                or self.api_key
            )
        if os.environ.get("TRACELOCK_MODEL") or os.environ.get("QWEN_MODEL"):
            self.model = (
                os.environ.get("TRACELOCK_MODEL")
                or os.environ.get("QWEN_MODEL")
                or self.model
            )
        if os.environ.get("TRACELOCK_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN"):
            self.telegram_bot_token = (
                os.environ.get("TRACELOCK_TELEGRAM_BOT_TOKEN")
                or os.environ.get("TELEGRAM_BOT_TOKEN")
                or self.telegram_bot_token
            )
        if os.environ.get("TRACELOCK_TELEGRAM_ALLOWLIST") or os.environ.get("TELEGRAM_ALLOWLIST"):
            self.telegram_allowlist = (
                os.environ.get("TRACELOCK_TELEGRAM_ALLOWLIST")
                or os.environ.get("TELEGRAM_ALLOWLIST")
                or self.telegram_allowlist
            )
        # sync token into env for telegram adapter
        if self.telegram_bot_token:
            os.environ.setdefault("TRACELOCK_TELEGRAM_BOT_TOKEN", self.telegram_bot_token)
        if self.telegram_allowlist:
            os.environ.setdefault("TRACELOCK_TELEGRAM_ALLOWLIST", self.telegram_allowlist)
        return self

    @property
    def has_llm(self) -> bool:
        return bool(self.api_key and self.api_base)


def load_config() -> RuntimeConfig:
    path = config_path()
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    known = {f.name for f in RuntimeConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    cfg = RuntimeConfig(**{k: v for k, v in data.items() if k in known})
    return cfg.apply_env_overrides()


def save_config(cfg: RuntimeConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # persist without re-applying env into file for empty secrets if already on disk
    payload = asdict(cfg)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def update_config(**kwargs: Any) -> RuntimeConfig:
    cfg = load_config()
    for k, v in kwargs.items():
        if hasattr(cfg, k) and v is not None:
            setattr(cfg, k, v)
    save_config(cfg)
    return cfg.apply_env_overrides()
