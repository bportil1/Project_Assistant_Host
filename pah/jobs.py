"""PAH read-only aggregator for explicitly supplied module job readers.

Modules own their process runtimes and storage. PAH never accesses their
private DBs, auto-discovers OS processes, or gains permission to terminate jobs.
"""
from __future__ import annotations

from threading import RLock

from pah_jobs import JobReader
from pah_jobs.observations import observe

from .instance_runtime import _valid_module_instance_id


class _InstanceJobReader:
    """PAH-only addressable projection of a module-owned read-only reader.

    The module retains its original JobRegistry owner; PAH rewrites only the
    emitted observation namespace so sibling module processes cannot collide.
    """

    def __init__(self, reader: JobReader, identity: str):
        self._reader = reader
        self.owner = identity
        self.module_id = reader.owner
        self.module_instance_id = identity

    def _job(self, raw: dict | None) -> dict | None:
        return ({**raw, "owner": self.owner, "module_id": self.module_id,
                 "module_instance_id": self.module_instance_id} if isinstance(raw, dict) else None)

    def job(self, job_id: str) -> dict | None:
        return self._job(self._reader.job(job_id))

    def snapshot(self, **kwargs) -> dict:
        original = self._reader.snapshot(**kwargs)
        return {**original, "owner": self.owner, "module_id": self.module_id,
                "module_instance_id": self.module_instance_id,
                "jobs": [self._job(job) for job in original["jobs"]]}

    def outputs(self, job_id: str, *, limit: int = 100) -> list[dict]:
        return self._reader.outputs(job_id, limit=limit)


class JobMonitorAggregator:
    def __init__(self):
        self._readers: dict[str, JobReader | _InstanceJobReader] = {}
        self._lock = RLock()

    def attach(self, reader: JobReader, *, module_instance_id: str | None = None) -> None:
        """Attach a producer-owned reader under a unique PAH routing identity.

        Without an instance ID, retain the original module-name endpoint.
        With one, only PAH-owned observation addressing changes; the producer
        and its job registry are not mutated.
        """
        # Published cross-process sources expose the same read-only methods
        # without subclassing JobReader. Preserve that existing JM-3B contract.
        if not isinstance(getattr(reader, "owner", None), str) or not reader.owner or not all(
            callable(getattr(reader, method, None)) for method in ("snapshot", "job", "outputs")
        ):
            raise TypeError("reader must implement the read-only job reader contract")
        identity = _valid_module_instance_id(module_instance_id) if module_instance_id is not None else reader.owner
        if module_instance_id is not None and identity == reader.owner:
            raise ValueError("instance-specific job source must differ from the module owner")
        with self._lock:
            if identity in self._readers:
                raise ValueError(f"duplicate job source: {identity}")
            self._readers[identity] = _InstanceJobReader(reader, identity) if module_instance_id is not None else reader

    def detach(self, owner: str) -> None:
        with self._lock:
            self._readers.pop(owner, None)

    def readers_snapshot(self) -> dict[str, JobReader | _InstanceJobReader]:
        """Copy explicitly attached readers for a bounded read-only handoff check."""
        with self._lock:
            return dict(self._readers)

    def snapshot(self, *, states=None) -> dict:
        with self._lock:
            readers = tuple(self._readers.values())
        data = [reader.snapshot(states=states) for reader in readers]
        observations = [observe(job, owner=source["owner"])
                        for source in data for job in source["jobs"]]
        return {"sources": data, "job_count": sum(len(source["jobs"]) for source in data),
                "observation_schema": "pah.job-observation", "observation_version": 1,
                "observations": observations}

    def outputs(self, owner: str, job_id: str, *, limit: int = 100) -> list[dict]:
        with self._lock:
            reader = self._readers[owner]
        # Never expose a record from another owner even if the ID was guessed.
        if reader.job(job_id) is None:
            raise KeyError(job_id)
        return reader.outputs(job_id, limit=limit)
