"""Small immutable, JSON-safe structures for local job observability."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    owner: str
    kind: str  # logical | process
    label: str
    state: str
    parent_id: str | None
    run_id: str | None
    checkpoint_id: str | None
    created_at: str
    started_at: str | None
    ended_at: str | None
    updated_at: str
    heartbeat_at: str | None
    last_output_at: str | None
    progress: float | None
    pid: int | None
    process_start_id: str | None
    liveness: str  # unknown | alive | gone | reused | unobservable
    exit_code: int | None
    reason: str | None
    cpu_seconds: float | None
    rss_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JobOutput:
    timestamp: str
    stream: str  # stdout | stderr | event
    text: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class JobEvent:
    sequence: int
    timestamp: str
    job_id: str
    event_type: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
