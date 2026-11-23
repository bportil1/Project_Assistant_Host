"""MI-04: explicit instance routes remain bound to their original host context.

These tests run local subprocesses; no third-party services or module internals.
"""
from __future__ import annotations

from pathlib import Path
import sys
import time

import pytest

from pah.contracts import ModuleContext
from pah.instance_runtime import InstanceRuntime
from pah.runtime import (
    RuntimeRegistry,
    ModuleInstanceConflict,
    ModuleInstanceNotFound,
)


CHILD = "import time; print('ready', flush=True); time.sleep(22)"


def context(root: Path, host: str, name: str) -> ModuleContext:
    return ModuleContext(
        workspace_id=name,
        project_root=root / name,
        resources={"datasets": root / name / "datasets"},
        context_token=f"token-{name}",
        runtime={"instance_id": host},
    ).for_module("ml_lab")


def test_routing_by_instance_id_never_uses_mutable_current_workspace(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-1")
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        a = context(tmp_path, "host-1", "alpha")
        b = context(tmp_path, "host-1", "beta")
        first = registry.launch_process("ml_lab", [sys.executable, "-c", CHILD], context=a, requested_port=None)
        second = registry.launch_process("ml_lab", [sys.executable, "-c", CHILD], context=b, requested_port=None)
        id_a, id_b = first["module_instance_id"], second["module_instance_id"]
        assert id_a != id_b
        assert registry.route_instance(id_a)["workspace_id"] == "alpha"
        assert registry.route_instance(id_b)["workspace_id"] == "beta"
        assert registry.route_instance(id_a)["host_project_id"] == str((tmp_path / "alpha").resolve())
        assert registry.instance_context(id_a).resources["datasets"] == (tmp_path / "alpha/datasets").resolve()
        assert registry.instance_context(id_b).resources["datasets"] == (tmp_path / "beta/datasets").resolve()
        assert registry.instance_context(id_a).module_instance_id == id_a
        assert registry.instance_context(id_b).module_instance_id == id_b
        assert registry.route_instance(id_a)["managed_process"]
        assert registry.route_instance(id_b)["managed_process"]

        # No mutation of the returned context may alter the captured binding.
        detached = registry.instance_context(id_a)
        detached.runtime["instance_id"] = "wrong"
        detached.resources["datasets"] = tmp_path / "wrong"
        assert registry.instance_context(id_a).runtime["instance_id"] == "host-1"
        assert registry.instance_context(id_a).resources["datasets"] != tmp_path / "wrong"

        # One child can be stopped even after the caller has moved to B.
        assert registry.stop_process(id_a)
        assert set(registry.instances("ml_lab")) == {id_b}
        assert registry.route_instance(id_b)["workspace_id"] == "beta"
        with pytest.raises(ModuleInstanceNotFound):
            registry.route_instance(id_a)
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_unknown_foreign_module_and_legacy_instance_are_not_redirected(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-2")
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        selected = registry.launch_process("ml_lab", [sys.executable, "-c", CHILD], requested_port=None)
        identity = selected["module_instance_id"]
        assert registry.route_instance(identity, module_id="ml_lab")["module_id"] == "ml_lab"
        with pytest.raises(ModuleInstanceConflict, match="belongs to"):
            registry.route_instance(identity, module_id="pypique")
        with pytest.raises(ModuleInstanceNotFound):
            registry.route_instance("host-other:ml_lab:unknown")
        with pytest.raises(ModuleInstanceNotFound):
            registry.stop_process("host-other:ml_lab:unknown")
        with pytest.raises(ModuleInstanceConflict, match="no captured"):
            registry.instance_context(identity)

        # Registry presence alone must never allow a PID-based kill.
        legacy = runtime.register_module_runtime("ml_lab", pid=999999)
        with pytest.raises(ModuleInstanceConflict, match="not a PAH-owned"):
            registry.stop_process(legacy["module_instance_id"])
        assert identity in registry.instances("ml_lab")
        assert legacy["module_instance_id"] in registry.instances("ml_lab")
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_legacy_adapters_reject_explicit_child_context(tmp_path: Path):
    class Adapter:
        module_id = "ml_lab"
        calls = 0

        def launch(self, *, context=None, detached=False):
            self.calls += 1
            return {"launched": True}

        def shutdown(self, *, context=None):
            self.calls += 1

        def status(self, *, context=None):
            self.calls += 1
            return {"available": True, "launchable": True}

        def artifacts(self, *, context=None):
            self.calls += 1
            return []

    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-3")
    adapter = Adapter()
    registry = RuntimeRegistry((adapter,), instance_runtime=runtime)
    try:
        child = context(tmp_path, "host-3", "alpha").for_module(
            "ml_lab", module_instance_id="host-3:ml_lab:specific"
        )
        with pytest.raises(ModuleInstanceConflict, match="instance-ID routing"):
            registry.launch("ml_lab", child)
        with pytest.raises(ModuleInstanceConflict, match="instance-ID routing"):
            registry.status("ml_lab", child)
        with pytest.raises(ModuleInstanceConflict, match="instance-ID routing"):
            registry.shutdown("ml_lab", child)
        with pytest.raises(ModuleInstanceConflict, match="instance-ID routing"):
            registry.artifacts("ml_lab", child)
        assert adapter.calls == 0
        assert registry.launch("ml_lab", context(tmp_path, "host-3", "alpha")).launched
        assert adapter.calls == 1
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_inconsistent_launch_bindings_fail_without_process_spawn(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-4")
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        a = context(tmp_path, "host-4", "alpha")
        args = [sys.executable, "-c", CHILD]
        with pytest.raises(ModuleInstanceConflict, match="workspace"):
            registry.launch_process("ml_lab", args, context=a, workspace_id="beta")
        with pytest.raises(ModuleInstanceConflict, match="host project"):
            registry.launch_process("ml_lab", args, context=a, host_project_id="unexpected")
        with pytest.raises(ModuleInstanceConflict, match="module type"):
            registry.launch_process("pypique", args, context=a)
        specific = a.for_module("ml_lab", module_instance_id="host-4:ml_lab:chosen")
        with pytest.raises(ModuleInstanceConflict, match="module instance"):
            registry.launch_process("ml_lab", args, context=specific, module_instance_id="host-4:ml_lab:other")
        assert registry.instances() == {}
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_explicit_identity_and_reaped_process_binding(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="host-5")
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        bound = context(tmp_path, "host-5", "alpha").for_module(
            "ml_lab", module_instance_id="host-5:ml_lab:chosen"
        )
        launched = registry.launch_process(
            "ml_lab", [sys.executable, "-c", "print('exited')"], context=bound, requested_port=None
        )
        identity = launched["module_instance_id"]
        assert identity == "host-5:ml_lab:chosen"
        assert registry.process_launcher is not None
        registry.process_launcher._owned[identity].process.wait(timeout=5)
        assert identity not in registry.instances()
        with pytest.raises(ModuleInstanceNotFound):
            registry.instance_context(identity)
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_http_routes_are_explicit_and_do_not_run_legacy_shutdown(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state", instance_id="host-http")
    app.config.update(TESTING=True)
    runtime = app.extensions["pah_runtime_registry"]
    try:
        with app.test_client() as client:
            first = runtime.launch_process("ml_lab", [sys.executable, "-c", CHILD], requested_port=None)
            second = runtime.launch_process("ml_lab", [sys.executable, "-c", CHILD], requested_port=None)
            first_id = first["module_instance_id"]
            second_id = second["module_instance_id"]
            listed = client.get("/api/orchestration/instances").get_json()
            assert {item["module_instance_id"] for item in listed["instances"]} >= {first_id, second_id}
            assert client.get(f"/api/orchestration/instances/{first_id}").get_json()["instance"]["managed_process"]
            assert client.get("/api/orchestration/instances/unknown").status_code == 404
            # A stale active-workspace token does not rebind an explicitly addressed child.
            response = client.post(
                f"/api/orchestration/instances/{first_id}/shutdown",
                headers={"X-PAH-Context-Token": "some-old-workspace-token"},
            )
            assert response.status_code == 200
            assert set(runtime.instances("ml_lab")) == {second_id}
            assert client.post(f"/api/orchestration/instances/{first_id}/shutdown").status_code == 404
    finally:
        app.extensions["pah_shutdown"]()
