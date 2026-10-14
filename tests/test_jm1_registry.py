"""JM-1 safety, concurrency, contract, and observability regression tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
import os

import pytest

from pah.jobs import JobMonitorAggregator
from pah_jobs import JobRegistry, ProcessStreamCapture


def test_hierarchy_transitions_and_checkpoint_identity():
    r = JobRegistry("pypique")
    parent = r.start("logical", "Github scrape", run_id="scrape-01", checkpoint_id="c1")
    child = r.start("process", "cppcheck", parent_id=parent, pid=os.getpid())
    assert r.job(child)["parent_id"] == parent
    assert r.job(child)["process_start_id"] or os.name != "posix"
    assert r.job(parent)["run_id"] == "scrape-01"
    r.heartbeat(parent, progress=.25)
    r.transition(child, "completing")
    r.transition(child, "succeeded", exit_code=0)
    assert r.job(child)["exit_code"] == 0
    assert r.job(child)["ended_at"] is not None
    with pytest.raises(ValueError):
        r.transition(child, "running")
    with pytest.raises(ValueError):
        r.heartbeat(child)
    assert r.job(parent)["progress"] == .25
    json.dumps(r.snapshot())


def test_bad_inputs_rejected_without_shell_behavior():
    r = JobRegistry("pypique")
    with pytest.raises(ValueError):
        r.start("process", "no pid")
    with pytest.raises(ValueError):
        r.start("logical", "bad", pid=42)
    with pytest.raises(KeyError):
        r.start("logical", "bad", parent_id="nonexistent")
    job = r.start("logical", "valid", state="queued")
    with pytest.raises(ValueError):
        r.heartbeat(job, progress=float("nan"))
    with pytest.raises(ValueError):
        r.heartbeat(job, progress=101)
    with pytest.raises(ValueError):
        r.transition(job, "something-else")
    r.transition(job, "running")
    r.transition(job, "failed", reason="timed out in child")
    assert r.job(job)["reason"] == "timed out in child"


def test_stream_redaction_and_bounded_capacity():
    r = JobRegistry("demo", max_jobs=3, max_output_lines=2, max_events=3,
                    max_line_chars=200, secrets=["custom-secret-456"])
    a = r.start("logical", "token=very-secret-abc")
    assert "very-secret-abc" not in r.job(a)["label"]
    for i in range(6):
        r.output(a, f"#{i} GITHUB_TOKEN=secret{i} Authorization: Bearer code{i}")
    lines = r.outputs(a, limit=2)
    assert len(lines) == 2
    assert all("Authorization: Bearer code" not in p["text"] for p in lines)
    assert all("secret5" not in p["text"] for p in lines)
    assert r.events_since(0)["gap"] is True
    assert r.events_since(0)["events"][0]["sequence"] >= 1
    b = r.start("logical", "b")
    c = r.start("logical", "c")
    with pytest.raises(RuntimeError):
        r.start("logical", "full with active jobs")
    r.transition(b, "succeeded")
    d = r.start("logical", "d")
    assert r.job(b) is None and r.job(d) is not None
    # A parent cannot be pruned while it has children.


def test_completed_parent_is_not_evicted_before_its_child():
    r = JobRegistry("pypique", max_jobs=2)
    parent = r.start("logical", "parent")
    child = r.start("logical", "child", parent_id=parent)
    r.transition(parent, "succeeded")
    with pytest.raises(RuntimeError):
        r.start("logical", "new")
    r.transition(child, "succeeded")
    r.start("logical", "new")
    assert r.job(parent) is not None and r.job(child) is None


def test_events_and_subscribe_do_not_block_producer():
    r = JobRegistry("ml_lab", max_events=2)
    s = r.reader().subscribe(capacity=1)
    job = r.start("logical", "training")
    for _ in range(100):
        r.heartbeat(job)
    result = s.poll()
    assert len(result["events"]) == 1
    assert result["dropped"] >= 99
    assert s.poll()["dropped"] == 0
    s.close()
    assert s.poll()["events"] == []


def test_parallel_worker_registrations_and_output():
    r = JobRegistry("pypique", max_jobs=200)
    top = r.start("logical", "benchmark")

    def worker(i):
        job = r.start("logical", f"worker {i}", parent_id=top)
        r.output(job, f"worker {i} output")
        r.transition(job, "succeeded")
        return job

    with ThreadPoolExecutor(max_workers=12) as pool:
        ids = list(pool.map(worker, range(100)))
    assert len(set(ids)) == 100
    assert len(r.snapshot()["jobs"]) == 101
    assert all(r.job(i)["state"] == "succeeded" for i in ids)


def test_read_only_aggregation_and_owner_isolation():
    p = JobRegistry("pypique")
    m = JobRegistry("ml_lab")
    pa = p.start("logical", "scraping")
    ma = m.start("logical", "training")
    agg = JobMonitorAggregator()
    agg.attach(p.reader())
    agg.attach(m.reader())
    assert agg.snapshot()["job_count"] == 2
    with pytest.raises(ValueError):
        agg.attach(p.reader())
    p.output(pa, "a line")
    assert len(agg.outputs("pypique", pa)) == 1
    with pytest.raises(KeyError):
        agg.outputs("ml_lab", pa)
    assert agg.outputs("ml_lab", ma) == []
    agg.detach("pypique")
    assert agg.snapshot()["job_count"] == 1


def test_linux_process_identity_is_observed_without_state_changes():
    r = JobRegistry("demo")
    job = r.start("process", "test", pid=os.getpid())
    result = r.observe_process(job)
    assert result["status"] in {"alive", "unobservable"}
    assert r.job(job)["state"] == "running"
    if result["status"] == "alive":
        assert result["rss_bytes"] >= 0
    # Deliberately wrong start identity detects PID recycling safely.
    mismatch = r.start("process", "mismatch", pid=os.getpid(), process_start_id="invalid")
    assert r.observe_process(mismatch)["status"] in {"reused", "unobservable"}


def test_stream_capture_drains_both_pipes_and_bounds_long_lines():
    r = JobRegistry("pypique")
    job = r.start("logical", "capture")
    stream = ProcessStreamCapture(r, job,
                                  stdout=io.BytesIO(b"hello\n" + b"A" * 1000 + b"\n"),
                                  stderr=io.BytesIO(b"oops\n"),
                                  chunk_size=64, max_pending_chars=128)
    assert stream.start().join(timeout=2)
    lines = r.outputs(job)
    assert any(p["stream"] == "stderr" and p["text"] == "oops" for p in lines)
    assert any(p["stream"] == "stdout" and p["text"] == "hello" for p in lines)
    assert all(len(p["text"]) <= 2048 + 15 for p in lines)
    with pytest.raises(RuntimeError):
        stream.start()
