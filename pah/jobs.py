"""PAH read-only aggregator for explicitly supplied module job readers.

Modules own their process runtimes and storage. PAH never accesses their
private DBs, auto-discovers OS processes, or gains permission to terminate jobs.
"""
from __future__ import annotations

from threading import RLock

from pah_jobs import JobReader
from pah_jobs.observations import observe


class JobMonitorAggregator:
    def __init__(self):
        self._readers: dict[str, JobReader] = {}
        self._lock = RLock()

    def attach(self, reader: JobReader) -> None:
        with self._lock:
            if reader.owner in self._readers:
                raise ValueError(f"duplicate job source: {reader.owner}")
            self._readers[reader.owner] = reader

    def detach(self, owner: str) -> None:
        with self._lock:
            self._readers.pop(owner, None)

    def readers_snapshot(self) -> dict[str, JobReader]:
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
