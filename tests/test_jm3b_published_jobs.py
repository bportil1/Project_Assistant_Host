"""JM-3B cross-process producer/reader tests (no Flask or external services)."""
from pathlib import Path
import json
import os
import subprocess
import sys

from pah_jobs.exchange import WorkspaceJobReader, publisher, job_scope, note


def test_published_tree_and_output(tmp_path, monkeypatch):
    monkeypatch.setenv("PAH_JOB_MONITOR_DIR", str(tmp_path))
    registry = publisher("pypique")
    assert registry is not None
    with job_scope("pypique", "Benchmark") as parent:
        assert parent
        with job_scope("pypique", "Cppcheck") as child:
            note("pypique", child, "running provider", stream="event")
    reader = WorkspaceJobReader(tmp_path, "pypique")
    jobs = reader.snapshot()["jobs"]
    assert any(j["job_id"] == parent and j["state"] == "succeeded" for j in jobs)
    match = next(j for j in jobs if j["job_id"] == child)
    assert match["parent_id"] == parent
    assert any("running provider" in str(x) for x in reader.outputs(child))


def test_reject_symlink_and_wrong_owner(tmp_path):
    path = tmp_path / "pypique-fake.json"
    path.write_text(json.dumps({"schema": "pah.job-monitor.snapshot", "version": 1,
                                "owner": "hsqa_dbn", "jobs": [{"job_id": "bad"}]}))
    other = tmp_path / "pypique-link.json"
    other.symlink_to(path)
    assert not WorkspaceJobReader(tmp_path, "pypique").snapshot()["jobs"]


def test_reader_does_not_infer_completed_when_publisher_is_dead(tmp_path):
    file = tmp_path / "hsqa_dbn-ghost.json"
    file.write_text(json.dumps({"schema": "pah.job-monitor.snapshot", "version": 1,
                                "owner": "hsqa_dbn", "writer_pid": 999999,
                                "writer_start_id": "invalid", "jobs": [
                                    {"owner": "hsqa_dbn", "job_id": "a", "state": "running", "kind": "logical"},
                                    {"owner": "hsqa_dbn", "job_id": "b", "state": "succeeded", "kind": "logical"}],
                                "outputs": {}}))
    jobs = WorkspaceJobReader(tmp_path, "hsqa_dbn").snapshot()["jobs"]
    assert next(j for j in jobs if j["job_id"] == "a")["state"] == "unknown"
    assert next(j for j in jobs if j["job_id"] == "b")["state"] == "succeeded"


def test_opt_in_does_not_touch_unrelated_workspace(tmp_path):
    assert WorkspaceJobReader(tmp_path / "missing", "pypique").snapshot()["jobs"] == []
