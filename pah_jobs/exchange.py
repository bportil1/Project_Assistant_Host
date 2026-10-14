"""JM-3B opt-in, read-only cross-process job snapshots.

Only monitor records are shared; no module-private database or experiment files
are read by PAH. This is not a command channel. Every writer uses a unique file.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from contextvars import ContextVar
import json
import os
from pathlib import Path
from threading import RLock
import time
from uuid import uuid4

from .process import observe_pid
from .registry import JobRegistry

_CURRENT_JOB: ContextVar[str | None] = ContextVar("pah_monitor_current_job", default=None)
_MONITOR_DIRECTORY: ContextVar[str | None] = ContextVar("pah_monitor_directory", default=None)
_SUPPORTED_OWNERS = frozenset({"pypique", "hsqa_dbn", "ml_lab", "code_analyzer",
                               "tech_documents", "reference_manager", "research_search"})
_WRITERS: dict[str, "PublishedJobRegistry"] = {}
_WRITERS_LOCK = RLock()
_MAX_FILE_BYTES = 2_000_000


class PublishedJobRegistry(JobRegistry):
    """A normal bounded JobRegistry with an atomic, low-frequency snapshot."""

    def __init__(self, owner: str, directory: str | Path):
        super().__init__(owner, max_jobs=160, max_output_lines=150, max_events=256)
        self._directory = Path(directory).expanduser().resolve()
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._path = self._directory / f"{owner}-{os.getpid()}-{uuid4().hex[:12]}.json"
        self._last_write = 0.0
        self._write_snapshot()

    def _write_snapshot(self):
        # Called while JobRegistry holds its RLock. Never emit an event from here.
        payload = {
            "schema": "pah.job-monitor.snapshot", "version": 1,
            "owner": self.owner, "writer_pid": os.getpid(),
            "writer_start_id": observe_pid(os.getpid()).start_id,
            "updated_epoch": time.time(),
            "jobs": [item.snapshot.to_dict() for item in list(self._jobs.values())[-75:]],
            "outputs": {key: [dict(line.to_dict(), text=str(line.to_dict().get("text", ""))[-480:])
                              for line in list(value.output)[-30:]]
                        for key, value in list(self._jobs.items())[-75:]},
        }
        tmp = self._path.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as stream:
                os.chmod(tmp, 0o600)
                json.dump(payload, stream, separators=(",", ":"), ensure_ascii=False)
            os.replace(tmp, self._path)
            self._last_write = time.monotonic()
        except OSError:
            # Monitoring is best effort and must not interrupt a scientific job.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _event(self, job_id: str, event_type: str, detail: object = "") -> None:
        super()._event(job_id, event_type, detail)
        if event_type in {"started", "state"} or time.monotonic() - self._last_write >= 0.7:
            self._write_snapshot()


def monitor_root() -> str | None:
    """Effective opt-in monitor location for trusted module worker handoff."""
    return _MONITOR_DIRECTORY.get() or os.environ.get("PAH_JOB_MONITOR_DIR", "").strip() or None


def publisher(owner: str) -> PublishedJobRegistry | None:
    """Opt in only through an explicitly supplied PAH monitor directory."""
    directory = (monitor_root() or "").strip()
    if not directory or owner not in _SUPPORTED_OWNERS:
        return None
    key = f"{owner}:{os.getpid()}:{directory}"
    with _WRITERS_LOCK:
        if key not in _WRITERS:
            try:
                _WRITERS[key] = PublishedJobRegistry(owner, directory)
            except OSError:
                return None
        return _WRITERS[key]


def current_job() -> str | None:
    return _CURRENT_JOB.get()


def begin(owner: str, label: str, *, parent_id: str | None = None,
          run_id: str | None = None, pid: int | None = None) -> str | None:
    registry = publisher(owner)
    if registry is None:
        return None
    try:
        return registry.start("process" if pid else "logical", label,
                              parent_id=parent_id or _CURRENT_JOB.get(), run_id=run_id,
                              pid=pid)
    except Exception:
        return None


def note(owner: str, job_id: str | None, message: object, *, stream: str = "event") -> None:
    registry = publisher(owner)
    if registry is not None and job_id:
        try:
            registry.output(job_id, message, stream=stream)
        except (KeyError, ValueError, OSError):
            pass


def finish(owner: str, job_id: str | None, *, state: str = "succeeded",
           reason: str | None = None, exit_code: int | None = None) -> None:
    registry = publisher(owner)
    if registry is not None and job_id:
        try:
            registry.transition(job_id, state, reason=reason, exit_code=exit_code)
        except (KeyError, ValueError, OSError):
            pass


def heartbeat(owner: str, job_id: str | None, *, progress: float | None = None) -> None:
    registry = publisher(owner)
    if registry is not None and job_id:
        try:
            registry.heartbeat(job_id, progress=progress)
        except (KeyError, ValueError, OSError):
            pass


@contextmanager
def job_scope(owner: str, label: str, *, run_id: str | None = None):
    job_id = begin(owner, label, run_id=run_id)
    token = _CURRENT_JOB.set(job_id or _CURRENT_JOB.get())
    try:
        yield job_id
    except BaseException as exc:
        note(owner, job_id, f"{type(exc).__name__}: {exc}", stream="stderr")
        finish(owner, job_id, state="timed_out" if isinstance(exc, TimeoutError) or
               getattr(exc, "timed_out", False) else "failed", reason=type(exc).__name__)
        raise
    else:
        finish(owner, job_id)
    finally:
        _CURRENT_JOB.reset(token)


@contextmanager
def monitor_directory(directory: str | Path):
    """Scope in-process hosted UI requests to one selected PAH workspace.

    No process-global environment mutation; simultaneous PAH workspaces do not
    redirect each other's module events. This is for trusted local callers only.
    """
    token = _MONITOR_DIRECTORY.set(str(Path(directory).expanduser().resolve()))
    try:
        yield
    finally:
        _MONITOR_DIRECTORY.reset(token)


def observed(owner: str, label: str):
    """Optional, result-preserving instrumentation for synchronous public calls.

    A domain module may import this decorator, but never depends on monitoring
    to run. Only a fixed descriptive label is logged; not arguments or payloads.
    """
    def decorate(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            with job_scope(owner, label) as job_id:
                result = function(*args, **kwargs)
                if job_id and getattr(result, "ok", True) is False:
                    note(owner, job_id, "Operation returned an unsuccessful result", stream="event")
                    finish(owner, job_id, state="failed", reason="Unsuccessful operation result")
                return result
        return wrapper
    return decorate


class WorkspaceJobReader:
    """Explicit workspace-scoped view for one module's opt-in snapshot files."""

    def __init__(self, directory: str | Path, owner: str):
        if owner not in _SUPPORTED_OWNERS:
            raise ValueError("unsupported module owner")
        self.directory = Path(directory).expanduser().resolve()
        self.owner = owner

    def _records(self):
        if not self.directory.is_dir():
            return []
        records = []
        def modified(path: Path) -> float:
            try:
                return path.stat().st_mtime if not path.is_symlink() else 0.0
            except OSError:
                return 0.0
        for file in sorted(self.directory.glob(f"{self.owner}-*.json"),
                           key=modified, reverse=True)[:32]:
            try:
                if file.is_symlink() or file.stat().st_size > _MAX_FILE_BYTES:
                    continue
                raw = json.loads(file.read_text(encoding="utf-8"))
                if (not isinstance(raw, dict) or raw.get("owner") != self.owner or
                        raw.get("schema") != "pah.job-monitor.snapshot" or
                        raw.get("version") != 1):
                    continue
                jobs = raw.get("jobs")
                if not isinstance(jobs, list):
                    continue
                # Only the explicitly registered process's state is considered.
                pid = raw.get("writer_pid")
                if isinstance(pid, int) and pid > 0:
                    start_id = raw.get("writer_start_id")
                    raw["writer_alive"] = bool(start_id) and observe_pid(
                        pid, expected_start_id=start_id).status == "alive"
                else:
                    raw["writer_alive"] = False
                records.append(raw)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return records

    def snapshot(self, *, states=None):
        jobs = []
        for record in self._records():
            for item in record["jobs"]:
                if not isinstance(item, dict) or item.get("owner") != self.owner:
                    continue
                result = dict(item)
                if result.get("kind") == "process" and result.get("state") == "running":
                    pid = result.get("pid")
                    start = result.get("process_start_id")
                    if isinstance(pid, int) and isinstance(start, str) and start:
                        observation = observe_pid(pid, expected_start_id=start)
                        result["liveness"] = observation.status
                        result["cpu_seconds"] = observation.cpu_seconds
                        result["rss_bytes"] = observation.rss_bytes
                if not record["writer_alive"] and result.get("state") in {
                    "running", "paused", "completing", "queued"
                }:
                    result["state"] = "unknown"
                    result["reason"] = "Publisher process no longer observable; result unconfirmed"
                if states is None or result.get("state") in states:
                    jobs.append(result)
        return {"owner": self.owner, "sequence": 0, "jobs": jobs}

    def job(self, job_id: str):
        return next((x for x in self.snapshot()["jobs"] if x.get("job_id") == job_id), None)

    def outputs(self, job_id: str, *, limit: int = 100):
        if not 1 <= limit <= 100:
            raise ValueError("limit out of range")
        for record in self._records():
            if any(isinstance(x, dict) and x.get("job_id") == job_id for x in record["jobs"]):
                return (record.get("outputs") or {}).get(job_id, [])[-limit:]
        raise KeyError(job_id)


def subprocess_monitor_env(workspace: str | Path) -> dict[str, str]:
    """Environment for a trusted, explicitly launched local module process."""
    env = dict(os.environ)
    root = Path(workspace).expanduser().resolve()
    env["PAH_JOB_MONITOR_DIR"] = str(root / ".pah" / "job_monitor")
    package_root = str(Path(__file__).resolve().parent.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = package_root + (os.pathsep + existing if existing else "")
    return env
