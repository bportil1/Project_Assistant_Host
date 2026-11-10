"""P5-01: host project/instance identities and stale-context safety."""
from __future__ import annotations

from pathlib import Path

import pytest

from pah.context_scope import StaleWorkspaceContext, WorkspaceContextGuard
from pah.contracts import ModuleContext
from pah.core.workspace import WorkspaceManager
from pah.instance_runtime import InstanceRuntime
from pah.runtime import RuntimeRegistry


def test_context_identity_keeps_host_project_and_module_local_ids_separate(tmp_path: Path):
    root = tmp_path / "project"
    context = ModuleContext(
        workspace_id="ws-a", project_root=root, resources={"datasets": root / "data"},
        runtime={"instance_id": "host-a"}, context_token="scope-a",
    )
    assert context.host_project_id == str(root.resolve())
    assert context.module_id is None
    assert context.module_local_project_id is None
    module = context.for_module("hsqa_dbn", local_project_id="run-42")
    assert module.module_id == "hsqa_dbn"
    assert module.module_instance_id == "host-a:hsqa_dbn"
    assert module.module_local_project_id == "run-42"
    assert module.host_project_id == context.host_project_id
    assert module.context_token == "scope-a"
    assert context.module_id is None  # immutable, no shared mutable child context
    assert module.to_dict()["module_instance_id"] == "host-a:hsqa_dbn"
    assert ModuleContext(workspace_id="docs", runtime={"instance_id": "host-a"}).host_project_id is None
    with pytest.raises(ValueError, match="module_id"):
        context.for_module("  ")


def test_context_guard_rotates_on_project_switch_and_resource_change(tmp_path: Path):
    guard = WorkspaceContextGuard("host-a")
    root = tmp_path / "project-a"
    first = guard.capture(workspace_id="a", project_root=root, resources={"repository": str(root)}, enabled_modules=("hsqa_dbn", "pypique"))
    again = guard.capture(workspace_id="a", project_root=root, resources={"repository": str(root)}, enabled_modules=("pypique", "hsqa_dbn"))
    assert first == again
    guard.require_current(first.context_token)
    other = guard.capture(workspace_id="b", project_root=root, resources={"repository": str(root)}, enabled_modules=("hsqa_dbn", "pypique"))
    assert other.revision == first.revision + 1
    assert other.context_token != first.context_token  # even with identical physical project
    with pytest.raises(StaleWorkspaceContext, match="Refresh"):
        guard.require_current(first.context_token)
    remapped = guard.capture(workspace_id="b", project_root=root, resources={"datasets": str(root / "new")}, enabled_modules=("hsqa_dbn", "pypique"))
    assert remapped.context_token != other.context_token
    guard.require_current(None)  # compatibility with older API and CLI callers
    with pytest.raises(StaleWorkspaceContext):
        guard.require_current("")
    independent = WorkspaceContextGuard("host-b")
    parallel = independent.capture(workspace_id="b", project_root=root)
    assert parallel.context_token != remapped.context_token
    assert parallel.instance_id == "host-b"


def test_launched_module_record_has_host_scope_but_no_inferred_module_project(tmp_path: Path):
    class Runtime:
        module_id = "demo"

        def status(self, *, context=None):
            return {"available": True, "launchable": True}

        def launch(self, *, context=None, detached=False):
            return {"launched": True, "presentation": "url", "metadata": {"pid": 1234}}

    instance = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-a")
    try:
        registry = RuntimeRegistry((Runtime(),), instance_runtime=instance)
        context = ModuleContext(
            workspace_id="w", project_root=tmp_path / "repo", runtime={"instance_id": "host-a"}
        ).for_module("demo")
        registry.launch("demo", context)
        record = instance.module_processes()["demo"]
        assert record["metadata"]["workspace_id"] == "w"
        assert record["metadata"]["host_project_id"] == str((tmp_path / "repo").resolve())
        assert record["metadata"]["module_instance_id"] == "host-a:demo"
        assert record["metadata"]["module_local_project_id"] is None
    finally:
        instance.stop()


def test_http_context_rejects_stale_launch_without_breaking_legacy_clients(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    state = tmp_path / "state"
    repo_a, repo_b = tmp_path / "repo-a", tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    seed = WorkspaceManager(state)
    seed.register_root("repo-a", role="repository", path=repo_a)
    seed.register_root("repo-b", role="repository", path=repo_b)
    seed.create_workspace("A", workspace_id="a", activate=True, resources={"repository": {"root_id": "repo-a"}})
    seed.create_workspace("B", workspace_id="b", resources={"repository": {"root_id": "repo-b"}})

    app = create_app(state_dir=state, instance_id="host-a")
    app.config.update(TESTING=True)
    calls = []

    class SpyRuntime:
        module_id = "pypique"

        def status(self, *, context=None):
            return {"available": True, "launchable": True, "running": False}

        def launch(self, *, context=None, detached=False):
            calls.append(context)
            return {"launched": True, "presentation": "url", "url": "http://127.0.0.1:9999/"}

    app.extensions["pah_runtime_registry"].register(SpyRuntime(), replace=True)
    try:
        with app.test_client() as client:
            first = client.get("/api/orchestration/context").get_json()
            assert first["workspace_id"] == "a"
            assert first["host_project_id"] == str(repo_a.resolve())
            old_token = first["context_token"]
            assert client.get("/api/orchestration/modules").get_json()["context_token"] == old_token

            assert client.post("/api/research-workspaces/b/activate").status_code == 200
            second = client.get("/api/orchestration/context").get_json()
            assert second["context_token"] != old_token
            assert second["host_project_id"] == str(repo_b.resolve())
            stale = client.post("/api/orchestration/modules/pypique/launch", json={}, headers={"X-PAH-Context-Token": old_token})
            assert stale.status_code == 409
            assert "Refresh" in stale.get_json()["error"]
            assert calls == []

            current = client.post("/api/orchestration/modules/pypique/launch", json={}, headers={"X-PAH-Context-Token": second["context_token"]})
            assert current.status_code == 200
            assert calls[-1].workspace_id == "b"
            assert calls[-1].host_project_id == str(repo_b.resolve())
            assert calls[-1].module_instance_id == "host-a:pypique"
            assert calls[-1].module_local_project_id is None

            legacy = client.post("/api/orchestration/modules/pypique/launch", json={})
            assert legacy.status_code == 200  # backwards compatible, no header
            assert calls[-1].workspace_id == "b"

            # Inactive workspace resource changes must not invalidate the active one.
            token = client.get("/api/orchestration/context").get_json()["context_token"]
            new_docs = tmp_path / "docs"
            new_docs.mkdir()
            client.put("/api/shared-roots/docs", json={"role": "documents", "path": str(new_docs)})
            client.put("/api/research-workspaces/a/resources/documents", json={"root_id": "docs"})
            assert client.get("/api/orchestration/context").get_json()["context_token"] == token
    finally:
        app.extensions["pah_shutdown"]()


def test_frontend_attaches_context_to_mutating_orchestration_calls():
    js = (Path(__file__).resolve().parents[1] / "pah/web/static/pah.js").read_text(encoding="utf-8")
    assert "X-PAH-Context-Token" in js
    assert "data.context_token || null" in js
    assert "url.startsWith('/api/orchestration/')" in js
