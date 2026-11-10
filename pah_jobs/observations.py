"""Versioned, read-only interpretation of producer-owned job snapshots.

Never equate a lost heartbeat with a failed/cancelled job. Scientific state
belongs to the producer; observation freshness belongs to the observer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA = "pah.job-observation"
VERSION = 1
TERMINAL = frozenset({"succeeded", "failed", "timed_out", "interrupted", "cancelled"})


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def observe(job: dict[str, Any], *, owner: str, now: datetime | None = None,
            stale_after_seconds: int = 30) -> dict[str, Any]:
    """Compute monitoring status, without guessing or changing job state."""
    if not isinstance(job, dict):
        raise ValueError("job must be a mapping")
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner is required")
    if not isinstance(stale_after_seconds, int) or stale_after_seconds < 1:
        raise ValueError("stale_after_seconds must be positive")
    stamp = _as_datetime(job.get("updated_at"))
    now = now or datetime.now(timezone.utc)
    status = job.get("observation_status")
    if status not in {"current", "stale", "unavailable", "undated"}:
        if stamp is None:
            status = "undated"
        elif (now - stamp).total_seconds() > stale_after_seconds:
            status = "stale"
        else:
            status = "current"
    producer_state = job.get("reported_state") or job.get("state") or "unknown"
    observed_state = job.get("state") or "unknown"
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "owner": owner,
        "job_id": job.get("job_id"),
        "run_id": job.get("run_id"),
        "producer_state": producer_state,
        "observed_state": observed_state,
        "telemetry_status": status,
        "producer_confirmed_terminal": producer_state in TERMINAL,
        "cancellation_requested": job.get("cancellation_requested_at") is not None,
        "cancellation_requested_at": job.get("cancellation_requested_at"),
        "updated_at": job.get("updated_at"),
    }
