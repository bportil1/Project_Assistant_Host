from pathlib import Path

from pah.core.workspace import WorkspaceManager


def test_workspace_state_lives_outside_project(tmp_path: Path):
    project = tmp_path / "project"
    state_dir = tmp_path / "state"
    project.mkdir()
    manager = WorkspaceManager(state_dir)
    manager.open(project)
    assert manager.root == project.resolve()
    assert not (project / ".pah").exists()
    assert (state_dir / "state.json").exists()
