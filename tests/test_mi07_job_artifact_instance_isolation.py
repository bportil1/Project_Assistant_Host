"""MI-07: PAH-only instance routing for read-only jobs and artifact references."""
from __future__ import annotations

from pathlib import Path

import pytest

from pah.jobs import JobMonitorAggregator
from pah_jobs import JobRegistry
from pah_jobs.exchange import WorkspaceJobReader
from pah.context_scope import WorkspaceContextGuard
from pah.instance_runtime import InstanceRuntime
from pah.contracts import ArtifactRef
from pah.contracts.uca_coordination import AnalysisHandoff, HandoffError, inspect_handoff
from pah.labs.artifacts import ArtifactRegistry
from pah.labs.artifact_publication import publish_reference, observe_reference_status
from pah.labs.artifact_reference_index import ArtifactReferenceIndex
from pah.contracts.publications import PUBLICATION_SCHEMA


def test_same_module_job_readers_have_independent_source_routing():
    one = JobRegistry("ml_lab")
    two = JobRegistry("ml_lab")
    a = one.start("logical", "Dataset A")
    b = two.start("logical", "Dataset B")
    one.output(a, "first output")
    two.output(b, "second output")
    monitor = JobMonitorAggregator()
    monitor.attach(one.reader(), module_instance_id="host:ml_lab:first")
    monitor.attach(two.reader(), module_instance_id="host:ml_lab:second")
    sources = {item["owner"]: item for item in monitor.snapshot()["sources"]}
    assert len(sources) == 2
    assert {item["module_id"] for item in sources.values()} == {"ml_lab"}
    assert sources["host:ml_lab:first"]["jobs"][0]["owner"] == "host:ml_lab:first"
    assert sources["host:ml_lab:second"]["jobs"][0]["owner"] == "host:ml_lab:second"
    assert {item["owner"] for item in monitor.snapshot()["observations"]} == set(sources)
    assert monitor.outputs("host:ml_lab:first", a)[0]["text"] == "first output"
    with pytest.raises(KeyError):
        monitor.outputs("host:ml_lab:second", a)
    with pytest.raises(ValueError, match="duplicate"):
        monitor.attach(one.reader(), module_instance_id="host:ml_lab:first")
    monitor.detach("host:ml_lab:first")
    assert list(monitor.readers_snapshot()) == ["host:ml_lab:second"]
    assert two.job(b)["owner"] == "ml_lab"  # Producer state unchanged.


def test_existing_cross_process_workspace_readers_still_attach(tmp_path):
    monitor = JobMonitorAggregator()
    monitor.attach(WorkspaceJobReader(tmp_path, "pypique"))
    assert monitor.snapshot()["sources"][0]["owner"] == "pypique"
    assert monitor.snapshot()["job_count"] == 0
    with pytest.raises(ValueError, match="duplicate"):
        monitor.attach(WorkspaceJobReader(tmp_path, "pypique"))


def _context(tmp_path, name="ws-a", project="repo-a"):
    return WorkspaceContextGuard("host-mi07").capture(
        workspace_id=name, project_root=tmp_path / project,
        resources={"repository": str(tmp_path / project)}, enabled_modules=("ml_lab",)
    )


def _publication(active, identity, artifact_id):
    return {
        "schema": PUBLICATION_SCHEMA,
        "schema_version": 1,
        "revision": 1,
        "context": {
            "instance_id": active.instance_id,
            "workspace_id": active.workspace_id,
            "host_project_id": active.host_project_id,
            "module_id": "ml_lab",
            "module_instance_id": identity,
            "context_token": active.context_token,
        },
        "artifact": {
            "artifact_id": artifact_id, "kind": "dataset", "producer_module": "ml_lab",
            "project_id": active.host_project_id, "validation_state": "valid",
        },
    }


def test_published_refs_bound_to_real_launch_records_and_status_owner(tmp_path):
    active = _context(tmp_path)
    runtime = InstanceRuntime(state_dir=tmp_path / "runtime", instance_id="host-mi07")
    first = "host-mi07:ml_lab:first"
    second = "host-mi07:ml_lab:second"
    for identity in (first, second):
        runtime.register_module_runtime("ml_lab", module_instance_id=identity, metadata={
            "workspace_id": active.workspace_id,
            "host_project_id": active.host_project_id,
        })
    try:
        inventory = ArtifactRegistry()
        scope = runtime.module_instances()
        for identity, artifact_id in ((first, "dataset-a"), (second, "dataset-b")):
            saved, created = publish_reference(inventory, _publication(active, identity, artifact_id),
                                               active_context=active, known_modules={"ml_lab"},
                                               module_instances=scope)
            assert created
            assert saved["metadata"]["pah_publication"]["module_instance_id"] == identity
        with pytest.raises(ValueError, match="module instance"):
            observe_reference_status(inventory, "dataset-a", state="stale", reason="changed",
                                     active_context=active, module_id="ml_lab",
                                     module_instance_id=second, module_instances=scope)
        with pytest.raises(ValueError, match="module instance"):
            observe_reference_status(inventory, "dataset-a", state="stale", reason="changed",
                                     active_context=active, module_id="ml_lab", module_instances=scope)
        observe_reference_status(inventory, "dataset-a", state="stale", reason="changed",
                                 active_context=active, module_id="ml_lab",
                                 module_instance_id=first, module_instances=scope)
        assert inventory.get("dataset-a").metadata["pah_reference_status"]["state"] == "stale"
        assert inventory.get("dataset-b").metadata["pah_reference_status"]["state"] == "active"
        index = ArtifactReferenceIndex(tmp_path / "refs.sqlite3")
        kwargs = {"host_project_id": active.host_project_id, "workspace_id": active.workspace_id}
        assert index.query(inventory, **kwargs)["total"] == 2
        found = index.query(inventory, **kwargs, module_instance_id=second)
        assert [item["artifact_id"] for item in found["items"]] == ["dataset-b"]
        assert found["items"][0]["module_instance_id"] == second
        with pytest.raises(ValueError, match="not registered"):
            publish_reference(inventory, _publication(active, "host-mi07:ml_lab:third", "other"),
                              active_context=active, known_modules={"ml_lab"}, module_instances=scope)
        alternate = _context(tmp_path, name="ws-b")
        with pytest.raises(ValueError, match="active producer/project"):
            publish_reference(inventory, _publication(alternate, first, "wrong"),
                              active_context=alternate,
                              known_modules={"ml_lab"}, module_instances=scope)
    finally:
        runtime.stop()


def test_existing_sqlite_index_upgrades_without_deleting_old_entries(tmp_path):
    import sqlite3
    old = tmp_path / "refs.sqlite3"
    with sqlite3.connect(old) as db:
        # The exact schema previously used by P5-05 (prior to MI-07).
        db.execute("""CREATE TABLE artifact_refs (
            artifact_id TEXT PRIMARY KEY, project_id TEXT, workspace_id TEXT,
            kind TEXT NOT NULL, producer_module TEXT NOT NULL,
            schema_id TEXT, schema_version TEXT, validation_state TEXT NOT NULL,
            created_at TEXT, is_alias INTEGER NOT NULL, is_history INTEGER NOT NULL,
            publication_revision INTEGER, source_fingerprint TEXT,
            reference_status TEXT, search_text TEXT NOT NULL
        )""")
        db.execute("""INSERT INTO artifact_refs (
            artifact_id, project_id, kind, producer_module, validation_state,
            is_alias, is_history, search_text) VALUES
            ('old', 'project', 'dataset', 'ml_lab', 'valid', 0, 0, 'old')""")
    # DDL migration adds the new column. A rebuild of the disposable index
    # happens on the next query against authoritative JSON records.
    index = ArtifactReferenceIndex(old)
    with sqlite3.connect(index.path) as db:
        assert "module_instance_id" in {row[1] for row in db.execute("PRAGMA table_info(artifact_refs)")}


def test_explicit_instance_handoff_never_uses_sibling_job_or_artifact(tmp_path):
    first = JobRegistry("ml_lab")
    second = JobRegistry("ml_lab")
    first_id = first.start("logical", "A")
    second_id = second.start("logical", "B")
    monitor = JobMonitorAggregator()
    monitor.attach(first.reader(), module_instance_id="host:ml_lab:a")
    monitor.attach(second.reader(), module_instance_id="host:ml_lab:b")
    handoff = AnalysisHandoff("project", "repository", "ml_lab", "f" * 64,
                              job_id=first_id, artifact_id="artifact-a", module_instance_id="host:ml_lab:a")
    artifact = ArtifactRef(artifact_id="artifact-a", kind="result", producer_module="ml_lab",
                           project_id="project", validation_state="valid", provenance={"source_sha256": "f" * 64},
                           metadata={"pah_publication": {"instance_id": "host", "module_instance_id": "host:ml_lab:a"}})
    matched = inspect_handoff(handoff, project_id="project", repository_id="repository",
                              readers=monitor.readers_snapshot(), artifact=artifact)
    assert matched["job"]["verification"] == "observed"
    assert matched["artifact"]["verification"] == "producer_validated"
    wrong = AnalysisHandoff("project", "repository", "ml_lab", "f" * 64,
                            job_id=second_id, artifact_id="artifact-a", module_instance_id="host:ml_lab:b")
    with pytest.raises(HandoffError, match="requested module instance"):
        inspect_handoff(wrong, project_id="project", repository_id="repository",
                        readers=monitor.readers_snapshot(), artifact=artifact)
    legacy = AnalysisHandoff("project", "repository", "ml_lab", "f" * 64, artifact_id="artifact-a")
    with pytest.raises(HandoffError, match="Explicit module_instance_id"):
        inspect_handoff(legacy, project_id="project", repository_id="repository",
                        readers=monitor.readers_snapshot(), artifact=artifact)


def test_adapter_instance_job_reader_bridge_checks_runtime_ownership():
    from pah.job_instrumentation import HostWorkflowMonitor
    first = JobRegistry("ml_lab")
    second = JobRegistry("ml_lab")
    first.start("logical", "A")
    second.start("logical", "B")

    class Adapter:
        module_id = "ml_lab"
        readers = {"host:ml_lab:a": first.reader(), "host:ml_lab:b": second.reader()}

        def instance_job_readers(self):
            return self.readers

    adapter = Adapter()

    class Runtime:
        def module_ids(self):
            return ("ml_lab",)

        def get(self, module_id):
            assert module_id == "ml_lab"
            return adapter

        def route_instance(self, identity, *, module_id):
            assert module_id == "ml_lab"
            if identity not in {"host:ml_lab:a", "host:ml_lab:b"}:
                raise KeyError("instance missing")
            return {"module_instance_id": identity, "module_id": module_id}

    observer = HostWorkflowMonitor()
    aggregator = JobMonitorAggregator()
    observer.attach_runtime_readers(Runtime(), aggregator)
    observer.attach_runtime_readers(Runtime(), aggregator)  # idempotent
    assert set(aggregator.readers_snapshot()) == {"host:ml_lab:a", "host:ml_lab:b"}
    adapter.readers = {"host:ml_lab:b": second.reader()}
    observer.attach_runtime_readers(Runtime(), aggregator)
    assert set(aggregator.readers_snapshot()) == {"host:ml_lab:b"}
    adapter.readers = {"host:ml_lab:forged": first.reader()}
    observer.attach_runtime_readers(Runtime(), aggregator)
    assert aggregator.readers_snapshot() == {}
