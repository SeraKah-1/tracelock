"""JSON-backed scheduled OSINT job store.

Schedules:
  - interval:Ns / Nm / Nh / Nd  (seconds/minutes/hours/days)
  - once:ISO8601
  - @startup  (run once when gateway/cron starts)
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


def default_jobs_path() -> Path:
    base = Path(
        __import__("os").environ.get("TRACELOCK_HOME")
        or Path.home() / ".tracelock"
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / "cron_jobs.json"


@dataclass
class CronJob:
    id: str
    name: str
    schedule: str  # e.g. interval:1h, interval:30m, @startup
    prompt: str  # OSINT subject / free text for skill
    skill: str = "osint-investigate"
    enabled: bool = True
    deliver: list[str] = field(default_factory=list)  # telegram:chat_id, email:addr, file:path
    case_dir: str = ""
    max_waves: int = 3
    next_run: float = 0.0
    last_run: float = 0.0
    last_status: str = ""
    last_result_preview: str = ""
    created_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CronJob":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


_INTERVAL_RE = re.compile(r"^interval:(\d+)([smhd])$", re.I)


def parse_interval_seconds(schedule: str) -> Optional[float]:
    s = (schedule or "").strip()
    if s.startswith("@"):
        return None
    if s.startswith("once:"):
        return None
    m = _INTERVAL_RE.match(s)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return float(n * mult)


def compute_next_run(schedule: str, now: Optional[float] = None) -> float:
    now = now if now is not None else time.time()
    s = (schedule or "").strip()
    if s == "@startup":
        return now  # due immediately once; runner disables after fire if one-shot meta
    if s.startswith("once:"):
        # once:ISO or once:unix
        rest = s[5:].strip()
        try:
            if rest.isdigit():
                return float(rest)
            # simple ISO date/time without zone → local
            from datetime import datetime

            for fmt in (
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d",
            ):
                try:
                    return datetime.strptime(rest, fmt).timestamp()
                except ValueError:
                    continue
        except Exception:
            pass
        return now
    sec = parse_interval_seconds(s)
    if sec is not None:
        return now + sec
    # unknown → 1 hour default
    return now + 3600


class JobStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_jobs_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[CronJob]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            jobs = data.get("jobs") if isinstance(data, dict) else data
            return [CronJob.from_dict(j) for j in (jobs or []) if isinstance(j, dict)]
        except Exception:
            return []

    def save(self, jobs: list[CronJob]) -> None:
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "jobs": [j.to_dict() for j in jobs],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def upsert(self, job: CronJob) -> CronJob:
        jobs = self.load()
        out: list[CronJob] = []
        found = False
        for j in jobs:
            if j.id == job.id:
                out.append(job)
                found = True
            else:
                out.append(j)
        if not found:
            out.append(job)
        self.save(out)
        return job

    def delete(self, job_id: str) -> bool:
        jobs = self.load()
        n = len(jobs)
        jobs = [j for j in jobs if j.id != job_id]
        self.save(jobs)
        return len(jobs) < n


def add_job(
    name: str,
    schedule: str,
    prompt: str,
    *,
    deliver: Optional[list[str]] = None,
    case_dir: str = "",
    max_waves: int = 3,
    store: Optional[JobStore] = None,
    job_id: Optional[str] = None,
) -> CronJob:
    store = store or JobStore()
    jid = job_id or uuid.uuid4().hex[:12]
    now = time.time()
    job = CronJob(
        id=jid,
        name=name,
        schedule=schedule,
        prompt=prompt,
        deliver=list(deliver or []),
        case_dir=case_dir,
        max_waves=max_waves,
        next_run=compute_next_run(schedule, now),
        enabled=True,
    )
    if schedule == "@startup":
        job.meta["oneshot"] = True
    return store.upsert(job)


def list_jobs(store: Optional[JobStore] = None) -> list[dict[str, Any]]:
    store = store or JobStore()
    return [j.to_dict() for j in store.load()]


def remove_job(job_id: str, store: Optional[JobStore] = None) -> bool:
    store = store or JobStore()
    return store.delete(job_id)
