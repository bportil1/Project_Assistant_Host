from __future__ import annotations

from pathlib import Path

import pytest

from pah.core.workspace import WorkspaceError, WorkspaceManager
from pah.module_catalog import MODULE_CATEGORIES, WORKSPACE_PRESETS


def test_workspace_creation_can_atomically_apply_initial_resources_and_module_profile(tmp_path: Path):
    repo = tmp_path / "repo"
    docs = tmp_path / "research" / "paper"
    repo.mkdir()
    docs.mkdir(parents=True)

    manager = WorkspaceManager(tmp_path / "state")
    manager.configure_available_modules(["code_analyzer", "tech_documents"])
    manager.register_root("repo", role="repository", path=repo)
    manager.register_root("writing", role="documents", path=tmp_path / "research")

    workspace = manager.create_workspace(
        "Paper",
        workspace_id="paper",
        activate=True,
        enabled_modules=["tech_documents"],
        resources={
            "repository": {"root_id": "repo"},
            "documents": {"root_id": "writing", "relative_path": "paper"},
        },
    )

    assert workspace["enabled_modules"] == ["tech_documents"]
    assert workspace["resources"]["repository"]["path"] == str(repo.resolve())
    assert workspace["resources"]["documents"]["path"] == str(docs.resolve())
    assert manager.root == repo.resolve()


def test_workspace_creation_validates_all_initial_resources_before_mutating_state(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "state")
    manager.configure_available_modules(["tech_documents"])

    with pytest.raises(WorkspaceError, match="Unknown registered root"):
        manager.create_workspace(
            "Broken",
            workspace_id="broken",
            resources={"documents": {"root_id": "missing-root"}},
        )

    assert manager.workspace_snapshot("broken") == {}
    assert manager.catalog_snapshot()["workspaces"] == []


def test_workspace_presets_are_generic_research_presets():
    labels = {item["label"] for item in WORKSPACE_PRESETS.values()}
    assert labels == {
        "Blank Workspace",
        "Document Creation",
        "Literature Review",
        "Software Analysis",
        "ML / Data Research",
        "Full Research Workspace",
    }
    assert "Document Creation" in MODULE_CATEGORIES.values()
    assert all("thesis" not in item["label"].lower() for item in WORKSPACE_PRESETS.values())


def test_workspace_initialization_http_contract_when_flask_available(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    docs = tmp_path / "documents"
    docs.mkdir()
    app = create_app(state_dir=tmp_path / "state-http")
    app.config.update(TESTING=True)

    with app.test_client() as client:
        client.put(
            "/api/shared-roots/writing",
            json={"name": "Writing", "role": "documents", "path": str(docs)},
        )
        metadata = client.get("/api/research-workspaces/initialization")
        assert metadata.status_code == 200
        payload = metadata.get_json()
        assert {item["label"] for item in payload["presets"]} >= {
            "Blank Workspace",
            "Full Research Workspace",
        }
        assert payload["categories"] == MODULE_CATEGORIES
        assert "documents" in payload["resource_roles"]
        assert next(root for root in payload["shared_roots"] if root["id"] == "writing")["available"] is True

        installed = {item["module_id"] for item in payload["modules"]}
        assert "tech_documents" in installed

        created = client.post(
            "/api/research-workspaces/initialize",
            json={
                "name": "Paper Workspace",
                "activate": True,
                "enabled_modules": ["tech_documents"],
                "resources": {"documents": {"root_id": "writing"}},
            },
        )
        assert created.status_code == 200
        workspace = created.get_json()["workspace"]
        assert workspace["name"] == "Paper Workspace"
        assert workspace["active"] is True
        assert workspace["enabled_modules"] == ["tech_documents"]
        assert workspace["resources"]["documents"]["path"] == str(docs.resolve())

        state = client.get("/api/workspace").get_json()
        assert state["workspace_id"] == workspace["id"]
        assert state["enabled_modules"] == ["tech_documents"]


def test_workspace_initializer_rejects_unavailable_modules_and_roots(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state-validation")
    app.config.update(TESTING=True)
    missing_root = tmp_path / "not-mounted-here"

    with app.test_client() as client:
        client.put(
            "/api/shared-roots/portable-papers",
            json={"name": "Portable Papers", "role": "papers", "path": str(missing_root)},
        )

        bad_module = client.post(
            "/api/research-workspaces/initialize",
            json={
                "name": "Bad Module",
                "enabled_modules": ["not_installed_here"],
                "resources": {},
            },
        )
        assert bad_module.status_code == 400
        assert "Unavailable modules selected" in bad_module.get_json()["error"]

        bad_root = client.post(
            "/api/research-workspaces/initialize",
            json={
                "name": "Bad Root",
                "enabled_modules": [],
                "resources": {"papers": {"root_id": "portable-papers"}},
            },
        )
        assert bad_root.status_code == 400
        assert "Unavailable resource roots selected" in bad_root.get_json()["error"]

        names = {item["name"] for item in client.get("/api/research-workspaces").get_json()["workspaces"]}
        assert "Bad Module" not in names
        assert "Bad Root" not in names


def test_workspace_initialization_frontend_contract():
    root = Path(__file__).resolve().parents[1]
    html = (root / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (root / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    css = (root / "pah" / "web" / "static" / "pah-workspace.css").read_text(encoding="utf-8")

    for element_id in [
        "workspaceNewButton",
        "workspaceInitializationDialog",
        "workspaceInitName",
        "workspaceInitPreset",
        "workspaceInitResourceRows",
        "workspaceInitCapabilityRows",
        "workspaceInitModuleRows",
        "workspaceInitValidation",
        "workspaceInitCreate",
    ]:
        assert f'id="{element_id}"' in html
        assert f"$('{element_id}')" in js

    for function_name in [
        "loadWorkspaceInitialization",
        "openWorkspaceInitialization",
        "applyWorkspaceInitializationPreset",
        "validateWorkspaceInitialization",
        "submitWorkspaceInitialization",
    ]:
        assert f"function {function_name}" in js or f"async function {function_name}" in js

    assert "/api/research-workspaces/initialization" in js
    assert "/api/research-workspaces/initialize" in js
    assert ".workspace-initialization-dialog" in css
