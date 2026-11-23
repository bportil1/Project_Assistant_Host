from __future__ import annotations

import json
import os
from pathlib import Path
import socket

import pytest

from pah.contracts import RuntimeLaunch, RuntimeStatus
from pah.core.workspace import WorkspaceManager
from pah.instance_runtime import InstanceRuntime
from pah.runtime import RuntimeRegistry


def test_instance_runtime_allocates_isolated_runtime_state_and_ports(tmp_path: Path):
    state = tmp_path / "state"
    first = InstanceRuntime(state_dir=state, instance_id="instance-a")
    second = InstanceRuntime(state_dir=state, instance_id="instance-b")

    assert first.instance_id != second.instance_id
    assert first.runtime_dir != second.runtime_dir
    assert first.runtime_dir.parent == second.runtime_dir.parent == state.resolve() / "runtime"
    assert set(first.ports.values()).isdisjoint(set(second.ports.values()))

    first_payload = json.loads(first.instance_file.read_text(encoding="utf-8"))
    second_payload = json.loads(second.instance_file.read_text(encoding="utf-8"))
    assert first_payload["pid"] == second_payload["pid"] == os.getpid()
    assert first_payload["runtime_dir"] == str(first.runtime_dir)
    assert second_payload["runtime_dir"] == str(second.runtime_dir)
    assert Path(first_payload["log_file"]).is_file()
    assert Path(first_payload["temp_dir"]).is_dir()
    assert Path(first_payload["cache_dir"]).is_dir()

    first.stop()
    second.stop()


def test_instance_runtime_falls_back_when_preferred_port_is_already_bound(tmp_path: Path):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    occupied = int(blocker.getsockname()[1])
    try:
        runtime = InstanceRuntime(
            state_dir=tmp_path / "state",
            preferred_ports={"host": occupied},
        )
        assert runtime.port("host") != occupied
    finally:
        blocker.close()
        if "runtime" in locals():
            runtime.stop()


def test_instance_module_process_registry_is_owned_by_one_instance(tmp_path: Path):
    first = InstanceRuntime(state_dir=tmp_path / "state", instance_id="a")
    second = InstanceRuntime(state_dir=tmp_path / "state", instance_id="b")

    first.register_module_runtime("demo", pid=12345, metadata={"surface": "demo"})
    assert first.module_processes()["demo"]["owner_instance_id"] == "a"
    assert first.module_processes()["demo"]["pid"] == 12345
    assert second.module_processes() == {}

    first.unregister_module_runtime("demo")
    assert first.module_processes() == {}
    first.stop()
    second.stop()


def test_runtime_registry_updates_instance_process_registry(tmp_path: Path):
    class Adapter:
        module_id = "demo"

        def status(self, *, context=None):
            return RuntimeStatus("demo", available=True, running=False, launchable=True)

        def launch(self, *, context=None, detached=False):
            return RuntimeLaunch(
                "demo",
                launched=True,
                presentation="external",
                url="http://127.0.0.1:9999/",
                metadata={"pid": 4321},
            )

        def shutdown(self, *, context=None):
            return None

    runtime = InstanceRuntime(state_dir=tmp_path / "state")
    registry = RuntimeRegistry((Adapter(),), instance_runtime=runtime)
    registry.launch("demo")
    assert runtime.module_processes()["demo"]["pid"] == 4321
    registry.shutdown("demo")
    assert runtime.module_processes() == {}
    runtime.stop()


def test_workspace_selection_can_be_instance_local_without_changing_durable_default(tmp_path: Path):
    state = tmp_path / "state"
    seed = WorkspaceManager(state)
    seed.create_workspace("Alpha", workspace_id="alpha", activate=True)
    seed.create_workspace("Beta", workspace_id="beta")

    first = WorkspaceManager(state, persist_active_workspace=False)
    second = WorkspaceManager(state, persist_active_workspace=False)
    assert first.active_workspace_id == second.active_workspace_id == "alpha"

    first.activate("beta")
    assert first.active_workspace_id == "beta"
    assert second.active_workspace_id == "alpha"

    reloaded = WorkspaceManager(state)
    assert reloaded.active_workspace_id == "alpha"


def test_two_flask_instances_share_catalog_but_not_runtime_or_active_workspace(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    state = tmp_path / "state"
    seed = WorkspaceManager(state)
    seed.create_workspace("Alpha", workspace_id="alpha", activate=True)
    seed.create_workspace("Beta", workspace_id="beta")

    first = create_app(state_dir=state, instance_id="flask-a")
    second = create_app(state_dir=state, instance_id="flask-b")
    first.config.update(TESTING=True)
    second.config.update(TESTING=True)

    first_runtime = first.extensions["pah_instance_runtime"]
    second_runtime = second.extensions["pah_instance_runtime"]
    assert first_runtime.runtime_dir != second_runtime.runtime_dir
    assert set(first_runtime.ports.values()).isdisjoint(set(second_runtime.ports.values()))

    with first.test_client() as first_client, second.test_client() as second_client:
        assert first_client.get("/api/workspace").get_json()["workspace_id"] == "alpha"
        assert second_client.get("/api/workspace").get_json()["workspace_id"] == "alpha"

        response = first_client.post("/api/research-workspaces/beta/activate")
        assert response.status_code == 200
        assert first_client.get("/api/workspace").get_json()["workspace_id"] == "beta"
        assert second_client.get("/api/workspace").get_json()["workspace_id"] == "alpha"

        instance = first_client.get("/api/runtime/instance").get_json()
        assert instance["instance_id"] == "flask-a"
        assert instance["workspace_id"] == "beta"
        assert instance["health"] == "running"

    first_runtime.stop()
    second_runtime.stop()


def test_multiple_module_instances_do_not_overwrite_each_other(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-a")
    try:
        first = runtime.register_module_runtime(
            "ml_lab", module_instance_id="host-a:ml_lab:dataset-1", pid=10001,
            metadata={"workspace_id": "alpha"},
        )
        second = runtime.register_module_runtime(
            "ml_lab", module_instance_id="host-a:ml_lab:dataset-2", pid=10002,
            metadata={"workspace_id": "beta"},
        )
        assert first["module_instance_id"] != second["module_instance_id"]
        assert len(runtime.module_instances("ml_lab")) == 2
        assert {record["pid"] for record in runtime.module_instances("ml_lab").values()} == {10001, 10002}

        # Persisted state and the externally visible snapshot keep both IDs.
        payload = json.loads(runtime.process_file.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 2
        assert set(payload["processes"]) == {first["module_instance_id"], second["module_instance_id"]}
        assert set(runtime.snapshot()["module_instances"]) == set(payload["processes"])

        runtime.unregister_module_runtime("ml_lab", module_instance_id=first["module_instance_id"])
        assert set(runtime.module_instances("ml_lab")) == {second["module_instance_id"]}
    finally:
        runtime.stop()


def test_module_legacy_slot_is_idempotent_and_not_confused_with_parallel_instances(tmp_path: Path):
    from pah.instance_runtime import InstanceRuntimeError

    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-a")
    try:
        runtime.register_module_runtime("ml_lab", pid=11)
        runtime.register_module_runtime("ml_lab", pid=12)
        runtime.register_module_runtime("ml_lab", module_instance_id="host-a:ml_lab:second", pid=13)
        assert len(runtime.module_instances("ml_lab")) == 2
        assert runtime.module_processes()["ml_lab"]["pid"] == 12  # legacy interface
        assert runtime.module_processes()["ml_lab"]["module_instance_id"] == "host-a:ml_lab"
        with pytest.raises(InstanceRuntimeError, match="already registered"):
            runtime.register_module_runtime("ml_lab", module_instance_id="host-a:ml_lab:second", pid=99)
        with pytest.raises(InstanceRuntimeError, match="does not belong"):
            runtime.unregister_module_runtime("pypique", module_instance_id="host-a:ml_lab:second")
        with pytest.raises(InstanceRuntimeError, match="safe identifier"):
            runtime.register_module_runtime("ml_lab", module_instance_id="../unsafe", pid=22)

        # Accessors return copies, not direct references to shared records.
        copied = runtime.module_instances("ml_lab")
        copied["host-a:ml_lab:second"]["metadata"]["bad"] = "mutation"
        assert "bad" not in runtime.module_instances("ml_lab")["host-a:ml_lab:second"]["metadata"]

        runtime.unregister_module_runtime("ml_lab")  # only the old slot
        assert set(runtime.module_instances("ml_lab")) == {"host-a:ml_lab:second"}
        assert runtime.module_instances("pypique") == {}
    finally:
        runtime.stop()


def test_registry_exposes_individual_instances_without_duplicating_adapter_types(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-a")
    try:
        registry = RuntimeRegistry(instance_runtime=runtime)
        runtime.register_module_runtime("demo", module_instance_id="host-a:demo:1", pid=1001)
        runtime.register_module_runtime("demo", module_instance_id="host-a:demo:2", pid=1002)
        assert registry.module_ids() == ()  # discovery is separate from running instances
        assert set(registry.instances("demo")) == {"host-a:demo:1", "host-a:demo:2"}
        assert set(registry.instances()) == set(runtime.module_instances())
    finally:
        runtime.stop()
