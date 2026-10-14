"""Thread-safe, bounded, module-owned job and subprocess observation registry.

The registry NEVER launches, signals, cancels, or waits for a process. It records
what owners report, and can inspect only explicitly registered Linux PIDs.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Full, Queue
import re
from threading import RLock
from typing import Iterable
from uuid import uuid4

from .models import JobEvent, JobOutput, JobSnapshot
from .process import observe_pid

TERMINAL = frozenset({"succeeded", "failed", "timed_out", "interrupted"})
STATES = frozenset({"queued", "running", "paused", "completing", *TERMINAL, "unknown"})
TRANSITIONS = {
    "queued": frozenset({"running", "paused", "unknown", *TERMINAL}),
    "running": frozenset({"paused", "completing", "unknown", *TERMINAL}),
    "paused": frozenset({"running", "completing", "unknown", *TERMINAL}),
    "completing": frozenset({"unknown", *TERMINAL}),
    "unknown": frozenset({"running", "paused", "completing", *TERMINAL}),
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(\bauthorization\s*:\s*(?:bearer|basic)\s+)\S+"),
    re.compile(r"(?i)((?:[A-Za-z][\w-]*[_-])?(?:password|passwd|token|api[_-]?key|access[_-]?token|secret|client[_-]?secret)[\"\']?\s*[:=]\s*[\"\']?)[^\s,;\"\']+"),
    re.compile(r"\b(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: object, *, secrets: tuple[str, ...], limit: int) -> str:
    text = str(value)
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    text = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", text)
    text = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", text)
    text = _SECRET_PATTERNS[2].sub("[REDACTED]", text)
    text = _SECRET_PATTERNS[3].sub(r"\1[REDACTED]@", text)
    return text[:limit] + ("…[truncated]" if len(text) > limit else "")


@dataclass
class _Job:
    snapshot: JobSnapshot
    output: deque[JobOutput] = field(default_factory=deque)


class Subscription:
    """Bounded polling subscription; never executes user callbacks in job threads."""

    def __init__(self, registry: "JobRegistry", capacity: int):
        self._registry = registry
        self._queue: Queue[JobEvent] = Queue(maxsize=capacity)
        self._closed = False
        self._dropped = 0
        self._lock = RLock()

    def _publish(self, event: JobEvent) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._queue.put_nowait(event)
            except Full:
                # Subscriber is slow. Never block or exhaust producer memory.
                self._dropped += 1

    def poll(self, *, limit: int = 100, timeout: float = 0) -> dict:
        if not 1 <= limit <= 1000 or timeout < 0 or timeout > 30:
            raise ValueError("invalid poll limits")
        events: list[JobEvent] = []
        if not self._closed:
            try:
                events.append(self._queue.get(timeout=timeout) if timeout else self._queue.get_nowait())
            except Empty:
                pass
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                break
        with self._lock:
            dropped, self._dropped = self._dropped, 0
        return {"events": [item.to_dict() for item in events], "dropped": dropped}

    def close(self) -> None:
        with self._registry._lock:
            with self._lock:
                self._closed = True
            self._registry._subscribers.discard(self)


class JobReader:
    """Read-only surface shared with PAH or another viewer."""

    def __init__(self, registry: "JobRegistry"):
        self._registry = registry

    @property
    def owner(self) -> str:
        return self._registry.owner

    def snapshot(self, **kwargs) -> dict:
        return self._registry.snapshot(**kwargs)

    def job(self, job_id: str) -> dict | None:
        return self._registry.job(job_id)

    def outputs(self, job_id: str, *, limit: int = 100) -> list[dict]:
        return self._registry.outputs(job_id, limit=limit)

    def events_since(self, sequence: int, *, limit: int = 200) -> dict:
        return self._registry.events_since(sequence, limit=limit)

    def subscribe(self, *, capacity: int = 256) -> Subscription:
        return self._registry.subscribe(capacity=capacity)


class JobRegistry:
    """Per-module bounded registry. All writes must be made by the owning module."""

    def __init__(self, owner: str, *, max_jobs: int = 512,
                 max_output_lines: int = 200, max_events: int = 2048,
                 max_line_chars: int = 2048, secrets: Iterable[str] = ()):
        if not str(owner).strip():
            raise ValueError("owner must not be empty")
        if min(max_jobs, max_output_lines, max_events, max_line_chars) < 1:
            raise ValueError("limits must be positive")
        self.owner = owner
        self._max_jobs = max_jobs
        self._max_output = max_output_lines
        self._max_line = max_line_chars
        self._secrets = tuple(s for s in (str(x) for x in secrets) if len(s) >= 4)
        self._lock = RLock()
        self._jobs: OrderedDict[str, _Job] = OrderedDict()
        self._events: deque[JobEvent] = deque(maxlen=max_events)
        self._sequence = 0
        self._subscribers: set[Subscription] = set()

    def _clean(self, value: object) -> str:
        return _redact(value, secrets=self._secrets, limit=self._max_line)

    def reader(self) -> JobReader:
        return JobReader(self)

    def _event(self, job_id: str, event_type: str, detail: object = "") -> None:
        self._sequence += 1
        event = JobEvent(self._sequence, _now(), job_id, event_type, self._clean(detail))
        self._events.append(event)
        for observer in tuple(self._subscribers):
            observer._publish(event)

    def _job(self, job_id: str) -> _Job:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise KeyError(f"unknown job: {job_id}") from None

    def _trim(self) -> None:
        while len(self._jobs) >= self._max_jobs:
            parents = {j.snapshot.parent_id for j in self._jobs.values()}
            victim = next((key for key, job in self._jobs.items()
                           if job.snapshot.state in TERMINAL and key not in parents), None)
            if victim is None:
                raise RuntimeError("job registry full; no completed leaf can be evicted")
            del self._jobs[victim]

    def start(self, kind: str, label: str, *, parent_id: str | None = None,
              run_id: str | None = None, checkpoint_id: str | None = None,
              state: str = "running", pid: int | None = None,
              process_start_id: str | None = None) -> str:
        if kind not in {"logical", "process"}:
            raise ValueError("kind must be logical or process")
        if state not in STATES or state in TERMINAL:
            raise ValueError("initial job state must be non-terminal")
        if kind == "logical" and pid is not None:
            raise ValueError("only process jobs can have a pid")
        if kind == "process" and (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0):
            raise ValueError("process job requires positive pid")
        with self._lock:
            if parent_id is not None:
                self._job(parent_id)
            self._trim()
            job_id = uuid4().hex
            t = _now()
            if kind == "process" and process_start_id is None:
                process_start_id = observe_pid(pid).start_id
            snapshot = JobSnapshot(
                job_id=job_id, owner=self.owner, kind=kind, label=self._clean(label),
                state=state, parent_id=parent_id,
                run_id=self._clean(run_id) if run_id is not None else None,
                checkpoint_id=self._clean(checkpoint_id) if checkpoint_id is not None else None,
                created_at=t, started_at=t if state == "running" else None,
                ended_at=None, updated_at=t, heartbeat_at=t if state == "running" else None,
                last_output_at=None, progress=None, pid=pid,
                process_start_id=process_start_id, liveness="unknown",
                exit_code=None, reason=None, cpu_seconds=None, rss_bytes=None,
            )
            self._jobs[job_id] = _Job(snapshot, deque(maxlen=self._max_output))
            self._event(job_id, "started", state)
            return job_id

    def transition(self, job_id: str, state: str, *, exit_code: int | None = None,
                   reason: str | None = None) -> None:
        from dataclasses import replace
        with self._lock:
            job = self._job(job_id)
            old = job.snapshot
            if state not in TRANSITIONS.get(old.state, ()):
                raise ValueError(f"invalid job transition: {old.state} -> {state}")
            if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
                raise ValueError("exit_code must be an integer")
            t = _now()
            job.snapshot = replace(old, state=state, updated_at=t,
                                   started_at=old.started_at or (t if state == "running" else None),
                                   ended_at=t if state in TERMINAL else None,
                                   exit_code=exit_code,
                                   reason=self._clean(reason) if reason is not None else None)
            self._event(job_id, "state", state)

    def heartbeat(self, job_id: str, *, progress: float | None = None) -> None:
        from dataclasses import replace
        import math
        if progress is not None and (not isinstance(progress, (int, float)) or isinstance(progress, bool)
                                     or not math.isfinite(progress) or not 0 <= progress <= 1):
            raise ValueError("progress must be finite in [0, 1]")
        with self._lock:
            job = self._job(job_id)
            if job.snapshot.state in TERMINAL:
                raise ValueError("cannot heartbeat a completed job")
            t = _now()
            job.snapshot = replace(job.snapshot, heartbeat_at=t, updated_at=t,
                                   progress=float(progress) if progress is not None else job.snapshot.progress)
            self._event(job_id, "heartbeat", "")

    def output(self, job_id: str, text: object, *, stream: str = "stdout") -> None:
        from dataclasses import replace
        if stream not in {"stdout", "stderr", "event"}:
            raise ValueError("stream must be stdout, stderr, or event")
        with self._lock:
            job = self._job(job_id)
            t = _now()
            # Individual messages may be long; preserve at most max_output_lines.
            for line in (str(text).splitlines() or [""]):
                clean = self._clean(line)
                job.output.append(JobOutput(t, stream, clean))
                self._event(job_id, "output", f"{stream}: {clean}")
            job.snapshot = replace(job.snapshot, last_output_at=t, updated_at=t)

    def observe_process(self, job_id: str) -> dict:
        """Optional Linux identity check; does not change lifecycle state."""
        from dataclasses import replace
        with self._lock:
            job = self._job(job_id)
            old = job.snapshot
            if old.kind != "process" or old.pid is None:
                raise ValueError("job has no registered process")
            obs = observe_pid(old.pid, expected_start_id=old.process_start_id)
            job.snapshot = replace(old, liveness=obs.status,
                                   cpu_seconds=obs.cpu_seconds, rss_bytes=obs.rss_bytes)
            if old.liveness != obs.status:
                self._event(job_id, "liveness", obs.status)
            return {"status": obs.status, "cpu_seconds": obs.cpu_seconds,
                    "rss_bytes": obs.rss_bytes}

    def job(self, job_id: str) -> dict | None:
        with self._lock:
            item = self._jobs.get(job_id)
            return item.snapshot.to_dict() if item is not None else None

    def outputs(self, job_id: str, *, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= self._max_output:
            raise ValueError("output limit exceeds capacity")
        with self._lock:
            return [line.to_dict() for line in list(self._job(job_id).output)[-limit:]]

    def snapshot(self, *, states: Iterable[str] | None = None) -> dict:
        states_set = set(states) if states is not None else None
        with self._lock:
            return {"owner": self.owner, "sequence": self._sequence,
                    "jobs": [j.snapshot.to_dict() for j in self._jobs.values()
                             if states_set is None or j.snapshot.state in states_set]}

    def events_since(self, sequence: int, *, limit: int = 200) -> dict:
        if not isinstance(sequence, int) or sequence < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid sequence or limit")
        with self._lock:
            first = self._events[0].sequence if self._events else self._sequence + 1
            return {"owner": self.owner, "sequence": self._sequence,
                    "gap": sequence < first - 1,
                    "events": [event.to_dict() for event in self._events
                               if event.sequence > sequence][:limit]}

    def subscribe(self, *, capacity: int = 256) -> Subscription:
        if not 1 <= capacity <= 4096:
            raise ValueError("subscription capacity must be 1..4096")
        with self._lock:
            if len(self._subscribers) >= 32:
                raise RuntimeError("too many observers")
            subscriber = Subscription(self, capacity)
            self._subscribers.add(subscriber)
            return subscriber
