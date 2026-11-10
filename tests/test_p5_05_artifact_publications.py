"""P5-05: authoritative JSON registry, immutable scoped producer publications and index."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3

import pytest

from pah.context_scope import WorkspaceContextGuard
from pah.contracts import ArtifactRef, ArtifactPublication, PUBLICATION_SCHEMA
from pah.labs.artifacts import ArtifactRegistry
from pah.labs.artifact_publication import publish_reference, observe_reference_status
from pah.labs.artifact_reference_index import ArtifactReferenceIndex


def context(tmp_path, *, workspace="ws-a", project="project-a"):
    guard = WorkspaceContextGuard("host-1")
    return guard.capture(
        workspace_id=workspace, project_root=tmp_path / project,
        resources={"repository": str(tmp_path / project)}, enabled_modules=("pypique", "ml_lab"),
    )


def publication(active, *, artifact_id="run-one", revision=1, module="pypique", fingerprint=True):
    return {
        "schema": PUBLICATION_SCHEMA, "schema_version": 1, "revision": revision,
        "source_fingerprint": "sha256:" + hashlib.sha256(b"example").hexdigest() if fingerprint else None,
        "context": {
            "instance_id": active.instance_id,
            "workspace_id": active.workspace_id,
            "host_project_id": active.host_project_id,
            "module_id": module,
            "module_instance_id": f"{active.instance_id}:{module}",
            "module_local_project_id": "native-run-1",
            "context_token": active.context_token,
        },
        "artifact": {
            "artifact_id": artifact_id, "kind": "sat_result", "producer_module": module,
            "project_id": active.host_project_id, "schema_id": "pypique.sat.evidence",
            "schema_version": "1", "capabilities": ["sat_evidence", "source_links"],
            "created_at": "2026-11-09T16:00:00Z", "validation_state": "valid",
            "location": "/producer/owned/data.json",
        },
    }


def test_published_reference_is_immutable_idempotent_and_json_authoritative(tmp_path):
    active = context(tmp_path)
    state = tmp_path / "artifacts.json"
    registry = ArtifactRegistry(state_path=state)
    payload = publication(active)
    saved, created = publish_reference(registry, payload, active_context=active, known_modules={"pypique"})
    assert created
    assert saved["metadata"]["pah_publication"]["fingerprint_verified"] is False
    assert saved["metadata"]["pah_reference_status"]["state"] == "active"
    again, created = publish_reference(registry, payload, active_context=active, known_modules={"pypique"})
    assert not created and saved == again
    changed = publication(active, revision=2)
    with pytest.raises(ValueError, match="already published"):
        publish_reference(registry, changed, active_context=active, known_modules={"pypique"})
    assert len(json.loads(state.read_text())["artifacts"]) == 1
    assert ArtifactRegistry(state_path=state).get("run-one").to_dict() == saved


def test_reject_stale_context_cross_project_and_producer_confusion(tmp_path):
    active = context(tmp_path)
    registry = ArtifactRegistry()
    changed = context(tmp_path, project="project-b")
    with pytest.raises(ValueError, match="stale"):
        publish_reference(registry, publication(active), active_context=changed, known_modules={"pypique"})
    wrong_project = publication(active)
    wrong_project["artifact"]["project_id"] = "/other/project"
    with pytest.raises(ValueError, match="project"):
        ArtifactPublication.from_dict(wrong_project)
    wrong_module = publication(active)
    wrong_module["context"]["module_id"] = "ml_lab"
    with pytest.raises(ValueError, match="producer"):
        ArtifactPublication.from_dict(wrong_module)
    wrong_instance = publication(active)
    wrong_instance["context"]["module_instance_id"] = "host-1:ml_lab"
    with pytest.raises(ValueError, match="module instance"):
        publish_reference(registry, wrong_instance, active_context=active, known_modules={"pypique", "ml_lab"})
    with pytest.raises(ValueError, match="registered"):
        publish_reference(registry, publication(active), active_context=active, known_modules=set())


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", "1"), ("revision", 0),
    ("revision", 2.5), ("source_fingerprint", "deadbeef"),
])
def test_reject_bad_contract_fields(tmp_path, field, value):
    payload = publication(context(tmp_path))
    payload[field] = value
    with pytest.raises((ValueError, TypeError)):
        ArtifactPublication.from_dict(payload)


def test_reject_registry_metadata_spoofing_and_cross_project_parent(tmp_path):
    active = context(tmp_path)
    payload = publication(active)
    payload["artifact"]["metadata"] = {"registry_alias": True}
    with pytest.raises(ValueError, match="reserved"):
        ArtifactPublication.from_dict(payload)
    payload = publication(active)
    payload["artifact"]["parent_artifact_ids"] = ["other-project"]
    registry = ArtifactRegistry([ArtifactRef(
        artifact_id="other-project", kind="dataset", producer_module="pypique", project_id="/elsewhere"
    )])
    with pytest.raises(ValueError, match="different project"):
        publish_reference(registry, payload, active_context=active, known_modules={"pypique"})


def test_sqlite_index_is_rebuildable_scoped_query_and_search(tmp_path):
    state = tmp_path / "registry.json"
    registry = ArtifactRegistry(state_path=state)
    index_path = tmp_path / "artifact-references.sqlite3"
    index = ArtifactReferenceIndex(index_path)
    a = context(tmp_path)
    pub, _ = publish_reference(registry, publication(a), active_context=a, known_modules={"pypique"})
    query = lambda **kw: index.query(registry, host_project_id=a.host_project_id, workspace_id=a.workspace_id, **kw)
    result = query()
    assert result["total"] == 1
    assert result["items"][0]["artifact_id"] == pub["artifact_id"]
    assert result["items"][0]["fingerprint_verified"] is False
    assert "location" not in result["items"][0]  # reference lookup does not expose file access
    assert query(capability="sat_evidence")["total"] == 1
    assert query()["items"][0]["reference_status"] == "active"
    observe_reference_status(registry, "run-one", state="stale", reason="input changed",
                             active_context=a, module_id="pypique")
    assert query()["items"][0]["reference_status"] == "stale"
    assert query(capability="missing")["total"] == 0
    assert query(search="run-one")["total"] == 1
    assert query(search="%_")["total"] == 0  # escaped LIKE wildcards
    assert query(producer_module="ml_lab")["total"] == 0
    assert query(kind="nope")["total"] == 0
    assert index.query(registry, host_project_id=str(tmp_path / "project-b"), workspace_id="ws-b")["total"] == 0
    assert index.query(registry, host_project_id=a.host_project_id, workspace_id="ws-b")["total"] == 0
    registry.register(ArtifactRef(artifact_id="legacy", kind="dataset", producer_module="ml_lab",
                                  project_id=a.host_project_id, capabilities=("dataset",)))
    assert query()["total"] == 2  # index refreshes after JSON changes
    assert query(limit=1, offset=1)["total"] == 2
    registry.remove("run-one")
    assert query()["total"] == 1
    assert registry.get("run-one") is None
    index_path.unlink()
    reloaded = ArtifactRegistry(state_path=state)
    rebuilt = ArtifactReferenceIndex(index_path)
    assert rebuilt.query(reloaded, host_project_id=a.host_project_id, workspace_id=a.workspace_id)["total"] == 1


def test_existing_alias_history_and_selection_survive_indexing(tmp_path):
    state = tmp_path / "registry.json"
    registry = ArtifactRegistry(state_path=state)
    active = context(tmp_path)
    data = tmp_path / "produced.json"
    data.write_text('{"ok":true}')
    alias, snapshot = registry.register_current(ArtifactRef(
        artifact_id="pypique-current", kind="result", producer_module="pypique",
        project_id=active.host_project_id, location=str(data), metadata={"runtime_managed": True},
    ))
    registry.select(project_id=active.host_project_id, workflow_id="flow", step_id="step",
                    kind="result", artifact_id=snapshot.artifact_id)
    index = ArtifactReferenceIndex(tmp_path / "refs.sqlite3")
    common = dict(host_project_id=active.host_project_id, workspace_id=active.workspace_id)
    assert index.query(registry, **common)["total"] == 0
    assert index.query(registry, **common, include_history=True)["total"] == 1
    assert index.query(registry, **common, include_aliases=True)["total"] == 1
    assert index.query(registry, **common, include_aliases=True, include_history=True)["total"] == 2
    assert registry.selected_id(project_id=active.host_project_id, workflow_id="flow", step_id="step", kind="result") == snapshot.artifact_id
    assert data.read_text() == '{"ok":true}'


def test_status_is_producer_scoped_and_does_not_delete_history(tmp_path):
    active = context(tmp_path)
    registry = ArtifactRegistry()
    publish_reference(registry, publication(active), active_context=active, known_modules={"pypique"})
    with pytest.raises(ValueError, match="producer/project"):
        observe_reference_status(registry, "run-one", state="withdrawn", reason="", active_context=active, module_id="ml_lab")
    with pytest.raises(ValueError, match="producer/project"):
        observe_reference_status(registry, "run-one", state="missing", reason="", active_context=context(tmp_path, project="project-b"), module_id="pypique")
    with pytest.raises(ValueError, match="status"):
        observe_reference_status(registry, "run-one", state="succeeded", reason="", active_context=active, module_id="pypique")
    observe_reference_status(registry, "run-one", state="withdrawn", reason="removed by producer", active_context=active, module_id="pypique")
    assert registry.get("run-one") is not None
    assert registry.get("run-one").metadata["pah_reference_status"]["state"] == "withdrawn"


def test_index_validation_and_no_project_returns_no_refs(tmp_path):
    index = ArtifactReferenceIndex(tmp_path / "refs.sqlite3")
    registry = ArtifactRegistry()
    with pytest.raises(ValueError, match="limit"):
        index.query(registry, host_project_id="/a", workspace_id="w", limit=101)
    with pytest.raises(ValueError, match="offset"):
        index.query(registry, host_project_id="/a", workspace_id="w", offset=-1)
    assert index.query(registry, host_project_id=None, workspace_id="w")["items"] == []
    with sqlite3.connect(index.path) as db:
        assert db.execute("SELECT COUNT(*) FROM artifact_refs").fetchone()[0] == 0


def test_publication_routes_optional_flask(tmp_path):
    pytest.importorskip("flask")
    from pah import create_app
    from pah.core.workspace import WorkspaceManager

    state = tmp_path / "state"
    project = tmp_path / "repo"
    project.mkdir()
    seed = WorkspaceManager(state)
    seed.register_root("repo", role="repository", path=project)
    seed.create_workspace("A", workspace_id="a", activate=True, resources={"repository": {"root_id": "repo"}})
    app = create_app(state_dir=state, instance_id="host-1")
    app.config.update(TESTING=True)
    try:
        with app.test_client() as client:
            active = client.get("/api/orchestration/context").get_json()
            class Context:
                pass
            ctx = Context()
            for key in ("instance_id", "workspace_id", "host_project_id", "context_token"):
                setattr(ctx, key, active[key])
            payload = publication(ctx)
            # Existing module identifier can be used without starting its runtime.
            made = client.post("/api/orchestration/artifact-references", json=payload,
                               headers={"X-PAH-Context-Token": active["context_token"]})
            assert made.status_code == 201, made.get_json()
            listed = client.get("/api/orchestration/artifact-references").get_json()
            assert listed["total"] == 1
            assert client.post("/api/orchestration/artifact-references", json=payload).status_code == 200
            payload["context"]["workspace_id"] = "elsewhere"
            assert client.post("/api/orchestration/artifact-references", json=payload).status_code == 409
    finally:
        app.extensions["pah_shutdown"]()
