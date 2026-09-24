from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.core.workspace import WorkspaceManager
from pah.module_catalog import default_module_registry


def test_legacy_workspace_migrates_to_configured_available_modules(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": 2,
        "current_root": None,
        "recent_roots": [],
        "environments": {},
        "active_workspace_id": "legacy",
        "research_workspaces": {
            "legacy": {"id": "legacy", "name": "Legacy", "resources": {}},
        },
        "shared_roots": {},
    }), encoding="utf-8")

    manager = WorkspaceManager(state_dir)
    manager.configure_available_modules(["code_analyzer", "tech_documents", "reference_manager"])

    workspace = manager.workspace_snapshot("legacy")
    assert workspace["enabled_modules"] == ["code_analyzer", "tech_documents", "reference_manager"]
    persisted = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 3
    assert persisted["research_workspaces"]["legacy"]["enabled_modules"] == workspace["enabled_modules"]


def test_workspace_module_profile_persists_and_keeps_unavailable_enabled_ids(tmp_path: Path):
    state_dir = tmp_path / "state"
    manager = WorkspaceManager(state_dir)
    manager.configure_available_modules(["code_analyzer", "tech_documents"])
    manager.create_workspace("Research", workspace_id="research", activate=True)

    manager.set_enabled_modules("research", ["tech_documents", "missing_optional_module"])
    assert manager.is_module_enabled("code_analyzer") is False
    assert manager.is_module_enabled("tech_documents") is True
    assert manager.is_module_enabled("missing_optional_module") is True

    restarted = WorkspaceManager(state_dir)
    restarted.configure_available_modules(["code_analyzer", "tech_documents"])
    assert restarted.workspace_snapshot("research")["enabled_modules"] == [
        "tech_documents", "missing_optional_module"
    ]


def test_workspace_manager_new_workspaces_use_configured_module_defaults(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "state")
    manager.configure_available_modules(["a", "b"])
    created = manager.create_workspace("Research", workspace_id="research")
    assert created["enabled_modules"] == ["a", "b"]

    manager.set_module_enabled("research", "a", False)
    assert manager.workspace_snapshot("research")["enabled_modules"] == ["b"]



def test_workspace_module_ids_are_persisted_without_workspace_id_normalization(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "state")
    manager.configure_available_modules(["vendor.module:alpha"])
    manager.create_workspace("Research", workspace_id="research", activate=True)

    assert manager.enabled_modules() == ("vendor.module:alpha",)
    assert manager.is_module_enabled("vendor.module:alpha") is True


def test_module_catalog_exposes_general_category_metadata():
    registry = default_module_registry(discover=False)
    analyzer = registry.get("code_analyzer")
    documents = registry.get("tech_documents")
    references = registry.get("reference_manager")
    assert analyzer.metadata["category_label"] == "Software Analysis"
    assert documents.metadata["category_label"] == "Document Creation"
    assert references.metadata["category_label"] == "Literature & References"


def test_workspace_module_http_profile_filters_labs_and_blocks_launch_when_flask_available(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client.post("/api/research-workspaces", json={"id": "research", "name": "Research", "activate": True})
        disabled = client.put(
            "/api/research-workspaces/research/modules/code_analyzer",
            json={"enabled": False},
        )
        assert disabled.status_code == 200

        modules = client.get("/api/orchestration/modules").get_json()["modules"]
        analyzer = next(item for item in modules if item["module_id"] == "code_analyzer")
        assert analyzer["installed"] is True
        assert analyzer["enabled"] is False
        assert analyzer["running"] is False

        lab = client.get("/api/orchestration/labs/code_analysis_lab").get_json()
        assert "code_analyzer" not in {item["module_id"] for item in lab["modules"]}

        launch = client.post("/api/orchestration/modules/code_analyzer/launch", json={})
        assert launch.status_code == 503
        assert "disabled" in launch.get_json()["error"].lower()


def test_workspace_module_http_keeps_artifacts_and_reports_enabled_uninstalled_when_flask_available(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client.post("/api/research-workspaces", json={"id": "research", "name": "Research", "activate": True})
        created = client.post("/api/orchestration/artifacts", json={
            "artifact_id": "keep-me",
            "kind": "code_analysis",
            "producer_module": "code_analyzer",
            "validation_state": "valid",
        })
        assert created.status_code == 201

        client.put("/api/research-workspaces/research/modules/code_analyzer", json={"enabled": False})
        fetched = client.get("/api/orchestration/artifacts/keep-me")
        assert fetched.status_code == 200

        profile = client.put(
            "/api/research-workspaces/research/modules",
            json={"enabled_modules": ["tech_documents", "missing_optional_module"]},
        ).get_json()["module_profile"]["modules"]
        missing = next(item for item in profile if item["module_id"] == "missing_optional_module")
        assert missing["enabled"] is True
        assert missing["installed"] is False
        assert missing["running"] is False
