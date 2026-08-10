from pathlib import Path

from pah.core.environments import EnvironmentManager
from pah.core.workspace import WorkspaceManager


def test_create_and_select_venv(tmp_path: Path):
    project = tmp_path / "project"
    state = tmp_path / "state"
    project.mkdir()
    workspaces = WorkspaceManager(state)
    workspaces.open(project)
    envs = EnvironmentManager(workspaces)
    status = envs.create(".venv")
    assert status["is_venv"] is True
    assert Path(status["interpreter"]).exists()
    status = envs.select(None)
    assert status["is_venv"] is False
