"""Conversation sessions — JSON store with simple search.

One session per platform chat (telegram chat_id, tui, webhook session_id).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from tracelock.runtime.config import tracelock_home


def sessions_dir() -> Path:
    d = tracelock_home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Session:
    id: str
    platform: str = "cli"
    external_id: str = ""  # chat_id / user key
    title: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    case_path: str = ""
    clues: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Session":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class SessionStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else sessions_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sid: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:80]
        return self.root / f"{safe}.json"

    def get(self, sid: str) -> Optional[Session]:
        p = self._path(sid)
        if not p.is_file():
            return None
        try:
            return Session.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def save(self, session: Session) -> None:
        session.touch()
        p = self._path(session.id)
        p.write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def get_or_create(
        self,
        *,
        platform: str,
        external_id: str,
        case_dir: str = "",
    ) -> Session:
        sid = f"{platform}_{external_id}" if external_id else f"{platform}_{uuid.uuid4().hex[:10]}"
        s = self.get(sid)
        if s:
            return s
        case = ""
        if case_dir:
            cdir = Path(case_dir)
            cdir.mkdir(parents=True, exist_ok=True)
            case = str(cdir / f"{sid}.json")
        s = Session(
            id=sid,
            platform=platform,
            external_id=external_id,
            case_path=case,
            title=f"{platform}:{external_id}"[:60],
        )
        self.save(s)
        return s

    def reset(self, sid: str) -> Session:
        old = self.get(sid)
        platform = old.platform if old else "cli"
        external = old.external_id if old else ""
        case = old.case_path if old else ""
        s = Session(
            id=sid,
            platform=platform,
            external_id=external,
            case_path=case,
            title=old.title if old else "",
        )
        self.save(s)
        return s

    def append_message(self, session: Session, role: str, content: str, **extra: Any) -> None:
        msg: dict[str, Any] = {"role": role, "content": content, "ts": time.time()}
        msg.update(extra)
        session.messages.append(msg)
        # keep last 80 messages for disk (agent may compress further)
        if len(session.messages) > 80:
            session.messages = session.messages[-80:]
        self.save(session)

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        q = (query or "").lower().strip()
        if not q:
            return {"ok": False, "error": "empty query", "hits": []}
        hits: list[dict[str, Any]] = []
        for p in sorted(self.root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            blob = json.dumps(data, ensure_ascii=False).lower()
            if q not in blob:
                continue
            msgs = data.get("messages") or []
            snippet = ""
            for m in reversed(msgs):
                c = str(m.get("content") or "")
                if q in c.lower():
                    snippet = c[:240]
                    break
            hits.append(
                {
                    "session_id": data.get("id"),
                    "platform": data.get("platform"),
                    "title": data.get("title"),
                    "snippet": snippet,
                    "updated_at": data.get("updated_at"),
                }
            )
            if len(hits) >= limit:
                break
        return {"ok": True, "query": query, "hits": hits, "count": len(hits)}
