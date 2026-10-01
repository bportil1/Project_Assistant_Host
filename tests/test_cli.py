from __future__ import annotations

import json
from pathlib import Path
import signal

from pah import cli
from pah.core.workspace import WorkspaceManager
from pah.launcher import LauncherManager
from pah.module_catalog import default_module_registry


def _write_instance(state: Path, instance_id: str, *, workspace_id: str, pid: int, port: int, health: str = "running") -> Path:
    runtime = state / "runtime" / instance_id
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "instance.json"
    path.write_text(json.dumps({
        "instance_id": instance_id,
        "workspace_id": workspace_id,
        "pid": pid,
        "host": "127.0.0.1",
        "port": port,
        "ports": {"host": port},
        "runtime_dir": str(runtime),
        "started_at": "2026-09-24T12:00:00+00:00",
        "health": health,
    }), encoding="utf-8")
    return path


def test_cli_list_marks_dead_unclean_instances_stale(tmp_path: Path, capsys):
    state = tmp_path / "state"
    manager = WorkspaceManager(state)
    manager.create_workspace("Alpha", workspace_id="alpha")
    marker = _write_instance(state, "dead-one", workspace_id="alpha", pid=99999999, port=9101)

    assert cli.main(["--state-dir", str(state), "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    instance = next(item for item in payload["instances"] if item["instance_id"] == "dead-one")
    assert instance["health"] == "stale"
    assert instance["stale"] is True
    persisted = json.loads(marker.read_text(encoding="utf-8"))
    assert persisted["health"] == "stale"
    assert persisted.get("stale_detected_at")


def test_cli_open_and_stop_workspace_delegate_to_process_manager(monkeypatch, capsys):
    calls = []

    class FakeLauncher:
        def resolve_workspace(self, ref):
            calls.append(("resolve", ref))
            return {"id": "alpha", "name": "Alpha"}

        def open_workspace(self, workspace_id, *, new_instance=False):
            calls.append(("open", workspace_id, new_instance))
            return {
                "reused": False,
                "spawned": True,
                "url": "http://127.0.0.1:9123/",
                "instance": {"instance_id": "instance-a"},
            }

        def stop_workspace(self, workspace_id, *, wait_timeout=5.0, force=False):
            calls.append(("stop-workspace", workspace_id, wait_timeout, force))
            return {"workspace_id": workspace_id, "stopped_count": 2, "already_stopped_count": 1, "results": []}

    fake = FakeLauncher()
    monkeypatch.setattr(cli, "_launcher", lambda state_dir=None: fake)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: calls.append(("browser", url)))

    assert cli.main(["open", "Alpha", "--new-instance", "--no-browser"]) == 0
    assert cli.main(["stop", "--workspace", "Alpha", "--timeout", "3", "--force"]) == 0
    output = capsys.readouterr().out
    assert "started PAH instance instance-a" in output
    assert "Stopped 2 instance(s)" in output
    assert ("open", "alpha", True) in calls
    assert ("stop-workspace", "alpha", 3.0, True) in calls
    assert not any(item[0] == "browser" for item in calls)


def test_launcher_resolves_workspace_name_and_waits_for_clean_stop(tmp_path: Path, monkeypatch):
    state = tmp_path / "state"
    manager = WorkspaceManager(state)
    manager.create_workspace("My Research Workspace", workspace_id="research")
    _write_instance(state, "instance-a", workspace_id="research", pid=45678, port=9201)

    alive_answers = iter([True, True, False, False])
    monkeypatch.setattr("pah.launcher._pid_alive", lambda pid: next(alive_answers, False))
    signals = []
    monkeypatch.setattr("pah.launcher.os.kill", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr("pah.launcher.time.sleep", lambda seconds: None)

    launcher = LauncherManager(state_dir=state, module_registry=default_module_registry(discover=False))
    assert launcher.resolve_workspace("My Research Workspace")["id"] == "research"
    result = launcher.stop_instance("instance-a", wait_timeout=1.0)
    assert result["stopped"] is True
    assert result["already_stopped"] is False
    assert signals == [(45678, signal.SIGTERM)]


def test_sprint5_cli_and_signal_contracts_are_packaged():
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    run_py = (root / "run.py").read_text(encoding="utf-8")
    app_py = (root / "pah" / "app.py").read_text(encoding="utf-8")
    cli_py = (root / "pah" / "cli.py").read_text(encoding="utf-8")

    assert 'pah = "pah.cli:main"' in pyproject
    assert 'subparsers.add_parser("list"' in cli_py
    assert 'subparsers.add_parser("open"' in cli_py
    assert 'subparsers.add_parser("stop"' in cli_py
    assert 'target.add_argument("--workspace"' in cli_py
    assert "signal.SIGTERM" in run_py
    assert 'app.extensions["pah_shutdown"]' in app_py
