"""JM-3A: non-invasive host workflow and artifact lifecycle observability.

The host owns only its observations. It never starts, waits for, signals, or
redirects module processes. Submodules may expose an explicit JobReader for
fine-grained training/SAT events (documented in JOB_MONITOR.md).
"""
from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Any, Mapping

from pah_jobs import JobRegistry, JobReader, observe_pid


class HostWorkflowMonitor:
    def __init__(self):
        self.registry = JobRegistry("pah", max_jobs=512, max_output_lines=200)
        self._lock = RLock()
        self._artifacts: dict[tuple[str, str, str], tuple] = {}
        self._workflow: dict[tuple[str, str], tuple[str, str]] = {}
        self._tracked_processes: set[str] = set()

    def _safe(self, callback, *args, **kwargs):
        # Telemetry must never block an actual research run.
        try:
            return callback(*args, **kwargs)
        except Exception:
            return None

    @contextmanager
    def trace(self, label: str):
        job_id = self._safe(self.registry.start, "logical", label)
        try:
            yield _Trace(self, job_id)
        except BaseException as exc:
            if job_id is not None:
                self._safe(self.registry.output, job_id, f"{type(exc).__name__}: {exc}", stream="stderr")
                self._safe(self.registry.transition, job_id,
                           "timed_out" if isinstance(exc, TimeoutError) else "failed",
                           reason=type(exc).__name__)
            raise
        else:
            if job_id is not None:
                self._safe(self.registry.transition, job_id, "succeeded")

    def _record(self, label: str, messages: list[str], *, failed: bool = False):
        job_id = self._safe(self.registry.start, "logical", label)
        if job_id is None:
            return
        for message in messages:
            self._safe(self.registry.output, job_id, message, stream="event")
        self._safe(self.registry.transition, job_id, "failed" if failed else "succeeded",
                   reason="Provider discovery error" if failed else None)

    def artifact_refresh(self, module_id: str, discovered, *, workspace: str = "", phase: str = ""):
        """Report only changed discovery results; never exposes matrix contents."""
        items = []
        for raw in discovered:
            if not isinstance(raw, Mapping):
                raw = raw.to_dict() if hasattr(raw, "to_dict") else {}
            if not isinstance(raw, Mapping):
                continue
            items.append((str(raw.get("kind") or ""), str(raw.get("artifact_id") or ""),
                          str(raw.get("validation_state") or ""),
                          tuple(sorted(str(x) for x in (raw.get("capabilities") or ())))))
        signature = tuple(sorted(items))
        key = (str(workspace), str(module_id), str(phase))
        with self._lock:
            if self._artifacts.get(key) == signature:
                return
            self._artifacts[key] = signature
        messages = [f"Workspace: {workspace or '(none)'}", f"Workflow context: {phase or 'general'}",
                    f"Advertised artifacts: {len(signature)}"]
        for kind, artifact_id, validity, capabilities in signature[:35]:
            messages.append(f"{kind or '?'} / {artifact_id or '?'}: {validity or 'unspecified'}; capabilities: {', '.join(capabilities) or 'none'}")
        if len(signature) > 35:
            messages.append(f"{len(signature)-35} more artifacts omitted")
        if module_id == "pypique" and phase in ("", "quality_modeling") and not any(
            kind == "feature_dataset" and "benchmark_reference" in capabilities
            for kind, _, _, capabilities in signature
        ):
            messages.append("Warning: no benchmark_reference feature_dataset advertised by this context")
        self._safe(self._record, f"{module_id} artifact refresh", messages)

    def discovery_error(self, module_id: str, exc: Exception):
        self._safe(self._record, f"{module_id} artifact discovery failed",
                   [f"{type(exc).__name__}: {exc}"], failed=True)

    def workflow_snapshot(self, workflow: Mapping[str, Any], *, workspace: str = ""):
        """Record readiness changes, especially missing dependencies and stale outputs."""
        for step in workflow.get("steps") or ():
            step_id = str(step.get("step_id") or "")
            if not step_id:
                continue
            state = str(step.get("state") or "unknown")
            reason = str(step.get("blocking_reason") or "")
            key = (str(workspace), step_id)
            with self._lock:
                before = self._workflow.get(key)
                if before == (state, reason):
                    continue
                self._workflow[key] = (state, reason)
            self._safe(self._record, f"Workflow {step_id}: {state}",
                       [f"Previous: {before[0] if before else 'not observed'}",
                        f"Current: {state}", reason or "No blocking reason reported"])

    def observe_processes(self):
        """Read-only PID checks; disappearance never implies success or failure."""
        with self._lock:
            tracked = tuple(self._tracked_processes)
        for job_id in tracked:
            job = self.registry.job(job_id)
            if job is None or job.get("state") not in ("running", "unknown"):
                with self._lock:
                    self._tracked_processes.discard(job_id)
                continue
            observed = self._safe(self.registry.observe_process, job_id)
            if isinstance(observed, dict) and observed.get("status") in {"gone", "reused"}:
                if job.get("state") == "running":
                    self._safe(self.registry.transition, job_id, "unknown",
                               reason="PID is no longer the recorded process; exit outcome unknown")
                    self._safe(self.registry.output, job_id,
                               "Process no longer observable; do not infer successful completion", stream="event")
                with self._lock:
                    self._tracked_processes.discard(job_id)

    def attach_runtime_readers(self, runtime_registry, aggregator):
        """Opt-in only: a trusted adapter may explicitly provide a JobReader."""
        for module_id in runtime_registry.module_ids():
            adapter = runtime_registry.get(module_id)
            candidate = adapter.get("job_reader") if isinstance(adapter, Mapping) else getattr(adapter, "job_reader", None)
            if candidate is None:
                continue
            reader = self._safe(candidate) if callable(candidate) else candidate
            if not isinstance(reader, JobReader) or reader.owner != module_id:
                continue
            try:
                aggregator.attach(reader)
            except ValueError:
                pass  # The same owner was already registered. Never replace silently.


class _Trace:
    def __init__(self, monitor: HostWorkflowMonitor, job_id: str | None):
        self.monitor = monitor
        self.job_id = job_id

    def note(self, message: str):
        if self.job_id is not None:
            self.monitor._safe(self.monitor.registry.output, self.job_id, message, stream="event")

    def launched(self, launch):
        """A launch response is not a completed experiment; observe PID if provided."""
        self.note(f"Dispatch result: launched={bool(launch.launched)}; presentation={launch.presentation or 'unspecified'}")
        raw_pid = dict(launch.metadata or {}).get("pid")
        try:
            pid = int(raw_pid)
        except (ValueError, TypeError):
            return
        if pid <= 0 or self.job_id is None:
            return
        initial = self.monitor._safe(observe_pid, pid)
        obs = self.monitor._safe(observe_pid, pid, expected_start_id=initial.start_id) if initial and initial.start_id else None
        if obs is None or obs.status != "alive" or not obs.start_id:
            self.note("PID supplied but its Linux process identity could not be verified")
            return
        child = self.monitor._safe(self.monitor.registry.start, "process",
                                  f"{launch.module_id} runtime PID {pid}", parent_id=self.job_id,
                                  pid=pid, process_start_id=obs.start_id)
        if child is not None:
            with self.monitor._lock:
                self.monitor._tracked_processes.add(child)
