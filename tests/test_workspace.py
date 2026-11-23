from pathlib import Path

import pytest

from pah.core.workspace import RESOURCE_ROLES, WorkspaceError, WorkspaceManager


def test_workspace_state_lives_outside_project(tmp_path: Path):
    project = tmp_path / "project"
    state_dir = tmp_path / "state"
    project.mkdir()
    manager = WorkspaceManager(state_dir)
    manager.open(project)
    assert manager.root == project.resolve()
    assert not (project / ".pah").exists()
    assert (state_dir / "state.json").exists()


def test_legacy_open_promotes_directory_to_research_workspace(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    manager = WorkspaceManager(tmp_path / "state")

    manager.open(project)

    snapshot = manager.snapshot()
    assert snapshot["workspace_id"]
    assert snapshot["workspace_name"] == "project"
    assert snapshot["resources"]["repository"]["path"] == str(project.resolve())
    assert snapshot["resources"]["repository"]["available"] is True
    assert manager.resolve_resource("repository") == project.resolve()


def test_workspace_resources_reference_registered_roots_not_absolute_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    shared = tmp_path / "research"
    docs = shared / "HSQA" / "overleaf"
    papers = shared / "papers"
    for path in (repo, docs, papers):
        path.mkdir(parents=True)

    manager = WorkspaceManager(tmp_path / "state")
    workspace = manager.create_workspace("HSQA Thesis", workspace_id="hsqa-thesis", activate=True)
    assert workspace["id"] == "hsqa-thesis"

    manager.register_root("research-projects", name="Research Projects", path=shared)
    manager.register_root(
        "paper-library",
        name="Paper Library",
        role="papers",
        path=papers,
        sync_policy="externally_managed",
        transport_hint="syncthing",
    )
    manager.register_root("hsqa-repo", name="HSQA Repository", role="repository", path=repo)
    manager.set_resource("hsqa-thesis", "repository", root_id="hsqa-repo")
    manager.set_resource(
        "hsqa-thesis",
        "documents",
        root_id="research-projects",
        relative_path="HSQA/overleaf",
    )
    manager.set_resource("hsqa-thesis", "papers", root_id="paper-library")

    assert manager.root == repo.resolve()
    assert manager.resolve_resource("documents") == docs.resolve()
    assert manager.resolve_resource("papers") == papers.resolve()

    catalog = manager.catalog_snapshot()
    definition = next(item for item in catalog["workspaces"] if item["id"] == "hsqa-thesis")
    assert definition["resources"]["documents"]["root_id"] == "research-projects"
    assert definition["resources"]["documents"]["relative_path"] == "HSQA/overleaf"
    assert set(catalog["resource_roles"]) == set(RESOURCE_ROLES)


def test_unavailable_registered_root_is_visible_without_becoming_active_path(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "state")
    manager.create_workspace("Portable", workspace_id="portable", activate=True)
    missing = tmp_path / "other-machine" / "papers"
    manager.register_root("paper-library", role="papers", path=missing)
    manager.set_resource("portable", "papers", root_id="paper-library")

    resource = manager.snapshot()["resources"]["papers"]
    assert resource["path"] == str(missing.resolve())
    assert resource["available"] is False
    assert manager.resolve_resource("papers") is None


def test_workspace_resource_subpath_cannot_escape_registered_root(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    manager = WorkspaceManager(tmp_path / "state")
    manager.create_workspace("Safe", workspace_id="safe")
    manager.register_root("base", path=base)

    with pytest.raises(WorkspaceError, match="stay relative"):
        manager.set_resource("safe", "documents", root_id="base", relative_path="../escape")


def test_separate_managers_do_not_lose_catalog_updates(tmp_path: Path):
    # Both hosts started before either created a workspace (the old failure).
    state = tmp_path / "state"
    first = WorkspaceManager(state, persist_active_workspace=False)
    second = WorkspaceManager(state, persist_active_workspace=False)

    first.create_workspace("A", workspace_id="a", activate=True)
    second.create_workspace("B", workspace_id="b", activate=True)

    stored = WorkspaceManager(state).catalog_snapshot()
    assert {workspace["id"] for workspace in stored["workspaces"]} == {"a", "b"}
    assert first.active_workspace_id == "a"
    assert second.active_workspace_id == "b"
    # A catalog refresh on one host must not replace its own active selection.
    assert {workspace["id"] for workspace in first.catalog_snapshot()["workspaces"]} == {"a", "b"}
    assert first.active_workspace_id == "a"


def test_separate_managers_preserve_other_hosts_root_and_module_changes(tmp_path: Path):
    state = tmp_path / "state"
    first = WorkspaceManager(state)
    second = WorkspaceManager(state)
    first.configure_available_modules(["ml_lab", "pypique"])
    first.create_workspace("A", workspace_id="a")
    second.create_workspace("B", workspace_id="b")
    first.register_root("papers", path=tmp_path)
    second.set_enabled_modules("a", ["ml_lab"])
    first.set_resource("a", "documents", root_id="papers")
    # This mutation uses a fresh in-transaction module profile, not a stale snapshot.
    second.set_module_enabled("a", "pypique", True)
    loaded = WorkspaceManager(state)
    assert loaded.enabled_modules("a") == ("ml_lab", "pypique")
    assert loaded.resolve_resource("documents", workspace_id="a") == tmp_path
    assert {workspace["id"] for workspace in loaded.catalog_snapshot()["workspaces"]} == {"a", "b"}


def test_bad_existing_catalog_is_not_silently_overwritten(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    catalog = state / "state.json"
    catalog.write_text("{incomplete-json")
    manager = WorkspaceManager(state)
    with pytest.raises(WorkspaceError, match="unreadable workspace catalog"):
        manager.create_workspace("Must not overwrite")
    assert catalog.read_text() == "{incomplete-json"
