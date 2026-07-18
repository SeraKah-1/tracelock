"""Bounded persistent memory (MEMORY.md + USER.md).

Injected into system prompt at session start (frozen snapshot).
Agent mutates via memory tool during turns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from tracelock.runtime.config import RuntimeConfig, load_config, tracelock_home


SEP = "\n§\n"


@dataclass
class MemoryStore:
    memory_path: Path
    user_path: Path
    memory_limit: int = 2200
    user_limit: int = 1375

    @classmethod
    def from_config(cls, cfg: Optional[RuntimeConfig] = None) -> "MemoryStore":
        cfg = cfg or load_config()
        base = tracelock_home() / "memories"
        base.mkdir(parents=True, exist_ok=True)
        return cls(
            memory_path=base / "MEMORY.md",
            user_path=base / "USER.md",
            memory_limit=cfg.memory_char_limit,
            user_limit=cfg.user_char_limit,
        )

    def _path(self, target: str) -> Path:
        return self.user_path if target == "user" else self.memory_path

    def _limit(self, target: str) -> int:
        return self.user_limit if target == "user" else self.memory_limit

    def entries(self, target: str) -> list[str]:
        path = self._path(target)
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        parts = [p.strip() for p in text.split("§")]
        return [p for p in parts if p]

    def usage(self, target: str) -> dict[str, Any]:
        entries = self.entries(target)
        used = len(SEP.join(entries)) if entries else 0
        limit = self._limit(target)
        return {
            "target": target,
            "used": used,
            "limit": limit,
            "pct": int(100 * used / limit) if limit else 0,
            "count": len(entries),
        }

    def save_entries(self, target: str, entries: list[str]) -> None:
        path = self._path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = SEP.join(e.strip() for e in entries if e.strip())
        path.write_text(body + ("\n" if body else ""), encoding="utf-8")

    def add(self, target: str, content: str) -> dict[str, Any]:
        content = (content or "").strip()
        if not content:
            return {"ok": False, "error": "empty content"}
        # block obvious injection/exfil
        if re.search(r"(?i)ignore (all )?(previous|prior) instructions", content):
            return {"ok": False, "error": "blocked: injection pattern"}
        entries = self.entries(target)
        if content in entries:
            return {"ok": True, "note": "duplicate skipped", "usage": self.usage(target)}
        trial = entries + [content]
        used = len(SEP.join(trial))
        limit = self._limit(target)
        if used > limit:
            return {
                "ok": False,
                "error": (
                    f"Memory full {used}/{limit}. Consolidate with replace/remove, then retry."
                ),
                "current_entries": entries,
                "usage": f"{self.usage(target)['used']}/{limit}",
            }
        self.save_entries(target, trial)
        return {"ok": True, "action": "add", "usage": self.usage(target)}

    def replace(self, target: str, old_text: str, content: str) -> dict[str, Any]:
        entries = self.entries(target)
        matches = [i for i, e in enumerate(entries) if old_text and old_text in e]
        if not matches:
            return {"ok": False, "error": "no match for old_text", "current_entries": entries}
        if len(matches) > 1:
            return {"ok": False, "error": "ambiguous old_text — be more specific"}
        entries[matches[0]] = content.strip()
        used = len(SEP.join(entries))
        limit = self._limit(target)
        if used > limit:
            return {"ok": False, "error": f"replace would exceed limit {used}/{limit}"}
        self.save_entries(target, entries)
        return {"ok": True, "action": "replace", "usage": self.usage(target)}

    def remove(self, target: str, old_text: str) -> dict[str, Any]:
        entries = self.entries(target)
        matches = [i for i, e in enumerate(entries) if old_text and old_text in e]
        if not matches:
            return {"ok": False, "error": "no match", "current_entries": entries}
        if len(matches) > 1:
            return {"ok": False, "error": "ambiguous old_text"}
        entries.pop(matches[0])
        self.save_entries(target, entries)
        return {"ok": True, "action": "remove", "usage": self.usage(target)}

    def handle(self, action: str, target: str = "memory", content: str = "", old_text: str = "", **_: Any) -> dict[str, Any]:
        target = target if target in ("memory", "user") else "memory"
        action = (action or "list").lower()
        if action == "list":
            return {
                "ok": True,
                "entries": self.entries(target),
                "usage": self.usage(target),
            }
        if action == "add":
            return self.add(target, content)
        if action == "replace":
            return self.replace(target, old_text, content)
        if action == "remove":
            return self.remove(target, old_text)
        return {"ok": False, "error": f"unknown action {action}"}

    def prompt_block(self) -> str:
        """Frozen snapshot for system prompt."""
        lines = []
        for target, title in (("memory", "MEMORY (agent notes)"), ("user", "USER PROFILE")):
            u = self.usage(target)
            entries = self.entries(target)
            lines.append(
                f"══ {title} [{u['pct']}% — {u['used']}/{u['limit']} chars] ══"
            )
            if entries:
                lines.append(SEP.join(entries))
            else:
                lines.append("(empty)")
            lines.append("")
        return "\n".join(lines)
