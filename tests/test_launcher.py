from __future__ import annotations

import json
import os
from pathlib import Path

from pah.core.workspace import WorkspaceManager
from pah.launcher import LauncherManager
from pah.module_catalog import default_module_registry


def _write_instance(state: Path, instance_id: str, *, workspace_id: str, pid: int, port: int, health: str = "running") -> Path:
    runtime_dir = state / "runtime" / instance_id
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = runtime_dir / "instance.json"
    path.write_text(json.dumps({
        "instance_id": instance_id,
        "workspace_id": workspace_id,
        "pid": pid,
        "host": "127.0.0.1",
        "port": port,
        "ports": {"host": port},
        "runtime_dir": str(runtime_dir),
        "started_at": "2026-09-24T12:00:00+00:00",
        "health": health,
    }), encoding="utf-8")
    return path


def test_launcher_snapshot_combines_workspaces_instances_and_warnings(tmp_path: Path):
    state = tmp_path / "state"
    manager = WorkspaceManager(state)
    manager.configure_available_modules(["code_analyzer"])
    missing = tmp_path / "not-mounted"
    manager.register_root("repo", role="repository", path=missing)
    manager.create_workspace(
        "Alpha",
        workspace_id="alpha",
        enabled_modules=["code_analyzer", "not_installed_here"],
        resources={"repository": {"root_id": "repo"}},
    )
    _write_instance(state, "instance-a", workspace_id="alpha", pid=os.getpid(), port=9101)

    launcher = LauncherManager(
        state_dir=state,
        module_registry=default_module_registry(discover=False),
        current_instance_id="instance-a",
    )
    snapshot = launcher.snapshot()
    alpha = next(item for item in snapshot["workspaces"] if item["id"] == "alpha")

    assert snapshot["running_count"] == 1
    assert alpha["running_count"] == 1
    assert alpha["instances"][0]["current"] is True
    assert alpha["instances"][0]["url"] == "http://127.0.0.1:9101/"
    assert "Software Analysis" in alpha["capability_labels"]
    assert alpha["missing_modules"] == ["not_installed_here"]
    assert alpha["unavailable_resources"][0]["role"] == "repository"
    assert any("Unavailable resources" in warning for warning in alpha["warnings"])
    assert any("not installed" in warning.lower() for warning in alpha["warnings"])


def test_open_reuses_running_instance_by_default(tmp_path: Path):
    state = tmp_path / "state"
    manager = WorkspaceManager(state)
    manager.configure_available_modules(["tech_documents"])
    manager.create_workspace("Writing", workspace_id="writing", enabled_modules=["tech_documents"])
    _write_instance(state, "instance-writing", workspace_id="writing", pid=os.getpid(), port=9201)

    launcher = LauncherManager(
        state_dir=state,
        module_registry=default_module_registry(discover=False),
        current_instance_id="other-instance",
    )
    result = launcher.open_workspace("writing")

    assert result["reused"] is True
    assert result["spawned"] is False
    assert result["instance"]["instance_id"] == "instance-writing"
    assert result["url"] == "http://127.0.0.1:9201/"


def test_open_new_instance_spawns_workspace_bound_runner(tmp_path: Path):
    state = tmp_path / "state"
    manager = WorkspaceManager(state)
    manager.configure_available_modules(["tech_documents"])
    manager.create_workspace("Writing", workspace_id="writing", enabled_modules=["tech_documents"])
    commands = []

    class FakeProcess:
        pid = 45678
        def poll(self):
            return None

    def process_factory(command, **kwargs):
        commands.append((list(command), dict(kwargs)))
        instance_id = command[command.index("--instance-id") + 1]
        workspace_id = command[command.index("--workspace-id") + 1]
        _write_instance(state, instance_id, workspace_id=workspace_id, pid=os.getpid(), port=9301)
        return FakeProcess()

    launcher = LauncherManager(
        state_dir=state,
        module_registry=default_module_registry(discover=False),
        run_script=Path(__file__).resolve().parents[1] / "run.py",
        process_factory=process_factory,
    )
    result = launcher.open_workspace("writing", new_instance=True)

    assert result["spawned"] is True
    assert result["reused"] is False
    assert result["url"] == "http://127.0.0.1:9301/"
    command, kwargs = commands[0]
    assert command[command.index("--workspace-id") + 1] == "writing"
    assert command[command.index("--state-dir") + 1] == str(state.resolve())
    assert "--no-browser" in command
    assert kwargs["start_new_session"] is True


def test_stop_instance_signals_only_non_current_running_process(tmp_path: Path, monkeypatch):
    state = tmp_path / "state"
    manager = WorkspaceManager(state)
    manager.create_workspace("Alpha", workspace_id="alpha")
    _write_instance(state, "external", workspace_id="alpha", pid=34567, port=9401)

    monkeypatch.setattr("pah.launcher._pid_alive", lambda pid: True)
    signals = []
    monkeypatch.setattr("pah.launcher.os.kill", lambda pid, sig: signals.append((pid, sig)))
    launcher = LauncherManager(
        state_dir=state,
        module_registry=default_module_registry(discover=False),
        current_instance_id="current",
    )

    result = launcher.stop_instance("external")
    assert result == {"instance_id": "external", "stopped": True, "already_stopped": False}
    assert signals and signals[0][0] == 34567


def test_launcher_frontend_and_http_contracts_are_present():
    root = Path(__file__).resolve().parents[1]
    app_py = (root / "pah" / "app.py").read_text(encoding="utf-8")
    template = (root / "pah" / "web" / "templates" / "launcher.html").read_text(encoding="utf-8")
    js = (root / "pah" / "web" / "static" / "pah-launcher.js").read_text(encoding="utf-8")
    run_py = (root / "run.py").read_text(encoding="utf-8")

    assert '@app.get("/launcher")' in app_py
    assert '@app.get("/api/launcher")' in app_py
    assert '/api/launcher/workspaces/<workspace_id>/open' in app_py
    assert '/api/launcher/instances/<instance_id>/stop' in app_py
    assert 'id="launcherWorkspaces"' in template
    assert 'data-new-instance' in js
    assert 'data-stop-instance' in js
    assert 'Open New Instance' in js
    assert '"/launcher"' in run_py
    assert 'parser.add_argument("--workspace-id"' in run_py
