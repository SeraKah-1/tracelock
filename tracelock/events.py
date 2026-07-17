"""Lightweight run-event bus for CLI logs + cockpit UI (stdlib only)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class EventLog:
    """Thread-safe append-only event log with optional JSONL mirror."""

    events: list[dict[str, Any]] = field(default_factory=list)
    jsonl_path: Optional[Path] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _seq: int = 0
    _listeners: list[Callable[[dict[str, Any]], None]] = field(
        default_factory=list, repr=False
    )

    def emit(self, kind: str, message: str = "", **data: Any) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            ev = {
                "seq": self._seq,
                "ts": time.time(),
                "kind": kind,
                "message": message,
                "data": data or {},
            }
            self.events.append(ev)
            if self.jsonl_path is not None:
                self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                with self.jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(ev)
            except Exception:
                pass
        return ev

    def since(self, seq: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self.events if int(e.get("seq") or 0) > seq]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.events)

    def clear(self) -> None:
        with self._lock:
            self.events.clear()
            self._seq = 0

    def add_listener(self, fn: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners.append(fn)


def make_event_callback(log: EventLog) -> Callable[[str, str], None]:
    """Adapter: agent calls on_event(kind, message, **data)."""

    def _cb(kind: str, message: str = "", **data: Any) -> None:
        log.emit(kind, message, **data)

    return _cb
