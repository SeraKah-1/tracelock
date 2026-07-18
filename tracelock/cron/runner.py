"""Execute due cron jobs via OSINT skill + delivery adapters."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional

from tracelock.cron.jobs import CronJob, JobStore, compute_next_run, parse_interval_seconds
from tracelock.skills.osint_skill import SkillResult, run_osint_skill


DeliverFn = Callable[[str, str], dict[str, Any]]  # (target, message) -> result


def _default_deliver(target: str, message: str) -> dict[str, Any]:
    """Best-effort delivery: file:/ telegram:/ email:/ stdout:."""
    target = (target or "").strip()
    if not target:
        return {"ok": False, "error": "empty target"}

    if target.startswith("file:"):
        path = Path(target[5:])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(message)
            f.write("\n")
        return {"ok": True, "channel": "file", "path": str(path)}

    if target.startswith("stdout:") or target == "stdout":
        print(message)
        return {"ok": True, "channel": "stdout"}

    if target.startswith("telegram:"):
        try:
            from tracelock.gateway.adapters.telegram import send_message

            chat_id = target.split(":", 1)[1]
            return send_message(chat_id, message)
        except Exception as e:
            return {"ok": False, "channel": "telegram", "error": str(e)}

    if target.startswith("email:"):
        try:
            from tracelock.gateway.adapters.email_file import queue_email

            addr = target.split(":", 1)[1]
            return queue_email(addr, subject="TraceLock OSINT report", body=message)
        except Exception as e:
            return {"ok": False, "channel": "email", "error": str(e)}

    if target.startswith("webhook:"):
        try:
            from tracelock.gateway.adapters.webhook import post_json

            url = target[len("webhook:") :]
            return post_json(url, {"text": message, "source": "tracelock-cron"})
        except Exception as e:
            return {"ok": False, "channel": "webhook", "error": str(e)}

    # bare path → file
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(message + "\n", encoding="utf-8")
    return {"ok": True, "channel": "file", "path": str(path)}


def _case_path_for(job: CronJob) -> Path:
    base = Path(job.case_dir) if job.case_dir else Path.home() / ".tracelock" / "cases"
    base.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.name)[:48]
    return base / f"{safe}_{job.id}.json"


def execute_job(
    job: CronJob,
    *,
    deliver_fn: Optional[DeliverFn] = None,
    no_network: bool = False,
) -> dict[str, Any]:
    deliver_fn = deliver_fn or _default_deliver
    case_path = _case_path_for(job)
    result: SkillResult = run_osint_skill(
        job.prompt,
        case_path=case_path,
        max_waves=job.max_waves,
        min_waves=1,
        no_network=no_network,
        continue_existing=case_path.is_file(),
    )
    msg = result.to_message()
    deliveries = []
    for t in job.deliver or ["stdout"]:
        deliveries.append({"target": t, **deliver_fn(t, msg)})
    return {
        "ok": result.ok,
        "job_id": job.id,
        "case_path": result.case_path,
        "stop_reason": result.stop_reason,
        "waves": result.waves,
        "deliveries": deliveries,
        "preview": (result.report_brief or "")[:500],
    }


def run_due_jobs(
    *,
    store: Optional[JobStore] = None,
    now: Optional[float] = None,
    deliver_fn: Optional[DeliverFn] = None,
    no_network: bool = False,
    force_all: bool = False,
) -> list[dict[str, Any]]:
    store = store or JobStore()
    now = now if now is not None else time.time()
    jobs = store.load()
    results: list[dict[str, Any]] = []
    updated: list[CronJob] = []

    for job in jobs:
        if not job.enabled and not force_all:
            updated.append(job)
            continue
        due = force_all or (job.next_run > 0 and job.next_run <= now) or job.next_run == 0
        if not due:
            updated.append(job)
            continue
        out = execute_job(job, deliver_fn=deliver_fn, no_network=no_network)
        results.append(out)
        job.last_run = now
        job.last_status = "ok" if out.get("ok") else "error"
        job.last_result_preview = str(out.get("preview") or "")[:400]
        # schedule next
        if job.meta.get("oneshot") or job.schedule.startswith("once:"):
            job.enabled = False
            job.next_run = 0
        else:
            sec = parse_interval_seconds(job.schedule)
            if sec:
                job.next_run = now + sec
            else:
                job.next_run = compute_next_run(job.schedule, now)
        updated.append(job)

    store.save(updated)
    return results


def tick_once(**kwargs: Any) -> list[dict[str, Any]]:
    return run_due_jobs(**kwargs)
