"""In-memory job status registry for sidecar background work."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from typing import Any

MAX_JOBS = 100

_LOCK = Lock()
_JOBS: OrderedDict[str, dict[str, Any]] = OrderedDict()


def _now() -> float:
    return time.time()


def _trim_locked() -> None:
    while len(_JOBS) > MAX_JOBS:
        _JOBS.popitem(last=False)


def _emit(send_event: Callable[[dict], None] | None, job: dict[str, Any]) -> None:
    if not send_event:
        return
    try:
        send_event({"id": "event", "result": {"type": "job_update", "job": dict(job)}})
    except Exception:
        pass


def start_job(
    job_id: str,
    *,
    kind: str = "task",
    label: str | None = None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    send_event: Callable[[dict], None] | None = None,
) -> dict[str, Any]:
    ts = _now()
    with _LOCK:
        job = {
            "id": job_id,
            "kind": kind,
            "label": label or job_id,
            "status": "running",
            "progress": 0.0,
            "message": message,
            "metadata": dict(metadata or {}),
            "created_at": ts,
            "updated_at": ts,
            "finished_at": None,
            "error": "",
        }
        _JOBS[job_id] = job
        _JOBS.move_to_end(job_id)
        _trim_locked()
        snapshot = dict(job)
    _emit(send_event, snapshot)
    return snapshot


def update_job(
    job_id: str,
    *,
    progress: float | None = None,
    message: str | None = None,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
    send_event: Callable[[dict], None] | None = None,
) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        if progress is not None:
            job["progress"] = max(0.0, min(1.0, float(progress)))
        if message is not None:
            job["message"] = message
        if status is not None:
            job["status"] = status
        if metadata:
            job.setdefault("metadata", {}).update(metadata)
        job["updated_at"] = _now()
        _JOBS.move_to_end(job_id)
        snapshot = dict(job)
    _emit(send_event, snapshot)
    return snapshot


def complete_job(
    job_id: str,
    *,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    send_event: Callable[[dict], None] | None = None,
) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        job["status"] = "complete"
        job["progress"] = 1.0
        if message:
            job["message"] = message
        if metadata:
            job.setdefault("metadata", {}).update(metadata)
        ts = _now()
        job["updated_at"] = ts
        job["finished_at"] = ts
        _JOBS.move_to_end(job_id)
        snapshot = dict(job)
    _emit(send_event, snapshot)
    return snapshot


def fail_job(
    job_id: str,
    error: str,
    *,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    send_event: Callable[[dict], None] | None = None,
) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        job["status"] = "failed"
        job["error"] = error
        job["message"] = message or error
        if metadata:
            job.setdefault("metadata", {}).update(metadata)
        ts = _now()
        job["updated_at"] = ts
        job["finished_at"] = ts
        _JOBS.move_to_end(job_id)
        snapshot = dict(job)
    _emit(send_event, snapshot)
    return snapshot


def cancel_job(
    job_id: str,
    *,
    message: str = "已取消",
    send_event: Callable[[dict], None] | None = None,
) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        job["status"] = "cancelled"
        job["message"] = message
        ts = _now()
        job["updated_at"] = ts
        job["finished_at"] = ts
        _JOBS.move_to_end(job_id)
        snapshot = dict(job)
    _emit(send_event, snapshot)
    return snapshot


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def list_jobs(
    *,
    include_finished: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with _LOCK:
        jobs = [dict(job) for job in reversed(_JOBS.values())]
    if not include_finished:
        jobs = [job for job in jobs if job.get("status") == "running"]
    return jobs[: max(1, min(limit, MAX_JOBS))]


def clear_jobs() -> None:
    with _LOCK:
        _JOBS.clear()
