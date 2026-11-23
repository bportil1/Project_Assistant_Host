"""MI-08: host-only end-to-end boundaries; no scientific submodules needed."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from pah.instance_runtime import InstanceRuntime, InstanceRuntimeError
from pah.module_processes import ModuleProcessError, ModuleProcessLauncher
from pah.runtime import RuntimeRegistry, ModuleInstanceNotFound


CHILD = (
    "import os,pathlib,time;"
    "pathlib.Path('identity.json').write_text("
    "os.environ['PAH_MODULE_INSTANCE_ID'] + '\\n' + "
    "os.environ.get('PAH_WORKSPACE_ID', '') + '\\n');"
    "time.sleep(30)"
)


def test_legacy_view_never_substitutes_a_modern_child(tmp_path: Path):
    host = InstanceRuntime(state_dir=tmp_path, instance_id="host")
    try:
        a = host.register_module_runtime("ml_lab", module_instance_id="host:ml_lab:alpha", pid=101)
        b = host.register_module_runtime("ml_lab", module_instance_id="host:ml_lab:beta", pid=102)
        assert host.module_processes() == {}
        snap = host.snapshot()
        assert snap["child_processes"] == {}
        assert set(snap["module_instances"]) == {a["module_instance_id"], b["module_instance_id"]}
        recorded = json.loads(host.process_file.read_text())
        assert set(recorded["processes"]) == set(snap["module_instances"])

        legacy = host.register_module_runtime("ml_lab", pid=103)
        assert host.module_processes()["ml_lab"]["module_instance_id"] == legacy["module_instance_id"]
        assert len(host.module_instances("ml_lab")) == 3
        host.unregister_module_runtime("ml_lab")
        assert host.module_processes() == {}
        assert len(host.module_instances("ml_lab")) == 2
    finally:
        host.stop()


def test_reserved_legacy_identity_cannot_be_claimed_by_child(tmp_path: Path):
    host = InstanceRuntime(state_dir=tmp_path, instance_id="owner")
    launcher = ModuleProcessLauncher(host)
    try:
        before = set(host.modules_dir.iterdir())
        with pytest.raises(ModuleProcessError, match="reserved for legacy"):
            launcher.launch("ml_lab", [sys.executable, "-c", CHILD],
                            module_instance_id="owner:ml_lab", requested_port=None)
        with pytest.raises(InstanceRuntimeError, match="reserved for the legacy"):
            host.register_module_runtime("ml_lab", module_instance_id="owner:ml_lab")
        assert host.module_instances() == {}
        assert set(host.modules_dir.iterdir()) == before
    finally:
        launcher.stop_all()
        host.stop()


@pytest.mark.parametrize("identity", [".", ".."])
def test_host_instance_id_cannot_escape_its_runtime_directory(tmp_path: Path, identity: str):
    with pytest.raises(InstanceRuntimeError, match="runtime directory name"):
        InstanceRuntime(state_dir=tmp_path, instance_id=identity)


def test_failed_process_start_does_not_leave_an_orphaned_instance(tmp_path: Path):
    host = InstanceRuntime(state_dir=tmp_path, instance_id="broken")
    launcher = ModuleProcessLauncher(host)
    try:
        with pytest.raises(ModuleProcessError, match="Could not launch"):
            launcher.launch("ml_lab", [str(tmp_path / "missing-executable")], requested_port=None)
        assert not host.module_instances()
        assert not list(host.modules_dir.iterdir())
    finally:
        launcher.stop_all()
        host.stop()


def test_same_module_siblings_survive_peer_shutdown_and_legacy_compat(tmp_path: Path):
    host = InstanceRuntime(state_dir=tmp_path, instance_id="multi")
    registry = RuntimeRegistry(instance_runtime=host)
    try:
        alpha = registry.launch_process("ml_lab", [sys.executable, "-c", CHILD],
                                        workspace_id="alpha", requested_port=None)
        beta = registry.launch_process("ml_lab", [sys.executable, "-c", CHILD],
                                       workspace_id="beta", requested_port=None)
        a, b = alpha["module_instance_id"], beta["module_instance_id"]
        assert a != b
        assert registry.route_instance(a)["workspace_id"] == "alpha"
        assert registry.route_instance(b)["workspace_id"] == "beta"
        assert host.module_processes() == {}  # no synthetic type-level alias
        host.set_workspace("gamma")
        assert registry.route_instance(a)["workspace_id"] == "alpha"
        assert registry.route_instance(b)["workspace_id"] == "beta"
        assert registry.stop_process(a)
        with pytest.raises(ModuleInstanceNotFound):
            registry.route_instance(a)
        assert registry.route_instance(b)["managed_process"]
        assert host.module_processes() == {}
        assert list(registry.instances()) == [b]
    finally:
        registry.shutdown_all()
        host.stop()


def test_ui_requires_enabled_multi_instance_capability_even_after_refresh():
    source = (Path(__file__).resolve().parents[1] / "pah/web/static/module-instances.js").read_text()
    assert 'loading || !selected?.enabled || !selected?.multi_instance_launchable' in source
    assert source.count('finally { loading = false; syncLaunchDisabled(); }') == 2
