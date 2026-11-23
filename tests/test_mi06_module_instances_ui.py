"""MI-06: independent module UI uses only trusted launch specs and instance IDs."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

from pah.contracts import ModuleContext
from pah.instance_runtime import InstanceRuntime
from pah.runtime import RuntimeRegistry, RuntimeRegistryError, ModuleInstanceNotFound

CHILD = "import time; time.sleep(20)"


class OptInAdapter:
    module_id = "dummy_module"

    def __init__(self, *, ui_path=None):
        self.ui_path = ui_path
        self.seen_contexts = []

    def process_launch_spec(self, *, context):
        self.seen_contexts.append(context.workspace_id)
        return {
            "command": [sys.executable, "-c", CHILD],
            "requested_port": 0 if self.ui_path else None,
            **({"ui_path": self.ui_path} if self.ui_path is not None else {}),
        }


class LegacyAdapter:
    module_id = "legacy_module"


def scoped(runtime: InstanceRuntime, workspace: str, module_id: str = "dummy_module") -> ModuleContext:
    return ModuleContext(
        workspace_id=workspace,
        runtime={"instance_id": runtime.instance_id},
    ).for_module(module_id)


def test_opt_in_adapter_launches_distinct_processes_and_stops_only_one(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="mi06-host")
    adapter = OptInAdapter()
    registry = RuntimeRegistry((adapter, LegacyAdapter()), instance_runtime=runtime)
    try:
        assert registry.can_launch_instance("dummy_module")
        assert not registry.can_launch_instance("legacy_module")
        assert not registry.can_launch_instance("missing_module")
        first = registry.launch_instance("dummy_module", context=scoped(runtime, "workspace-a"))
        second = registry.launch_instance("dummy_module", context=scoped(runtime, "workspace-b"))
        a, b = first["module_instance_id"], second["module_instance_id"]
        assert a != b and first["pid"] != second["pid"]
        route_a = registry.route_instance(a)
        route_b = registry.route_instance(b)
        assert route_a["workspace_id"] == "workspace-a"
        assert route_b["workspace_id"] == "workspace-b"
        assert route_a["runtime_dir"] != route_b["runtime_dir"]
        assert not route_a["url"] and not route_b["url"]
        assert route_a["managed_process"] and route_b["managed_process"]
        assert adapter.seen_contexts == ["workspace-a", "workspace-b"]
        assert registry.stop_process(a)
        assert registry.route_instance(b)["managed_process"]
        with pytest.raises(ModuleInstanceNotFound):
            registry.route_instance(a)
        with pytest.raises(RuntimeRegistryError, match="no independent"):
            registry.launch_instance("legacy_module", context=scoped(runtime, "workspace-a"))
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_explicit_ui_advertisement_and_invalid_url_are_safe(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="mi06-ui-host")
    adapter = OptInAdapter(ui_path="/viewer")
    registry = RuntimeRegistry((adapter,), instance_runtime=runtime)
    try:
        record = registry.launch_instance("dummy_module", context=scoped(runtime, "alpha"))
        url = registry.route_instance(record["module_instance_id"])["url"]
        assert url == f"http://127.0.0.1:{registry.route_instance(record['module_instance_id'])['port']}/viewer"
        assert registry.stop_process(record["module_instance_id"])

        for invalid in ("//example.com", "https://example.com", "/?token=x", "/\\evil", "/foo bar"):
            adapter.ui_path = invalid
            with pytest.raises(RuntimeRegistryError, match="ui_path"):
                registry.launch_instance("dummy_module", context=scoped(runtime, "alpha"))
        assert not registry.instances()
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_bad_recipe_never_launches_or_uses_user_supplied_command(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / "state", instance_id="mi06-bad-host")
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        registry.register({"module_id": "bad", "process_launch_spec": lambda **k: {"command": "echo bad"}})
        with pytest.raises(RuntimeRegistryError, match="argv"):
            registry.launch_instance("bad", context=scoped(runtime, "alpha", "bad"))
        registry.register({"module_id": "extra", "process_launch_spec": lambda **k: {
            "command": [sys.executable, "-c", CHILD], "dangerous_client_argument": "x"
        }})
        with pytest.raises(RuntimeRegistryError, match="only documented"):
            registry.launch_instance("extra", context=scoped(runtime, "alpha", "extra"))
        assert registry.instances() == {}
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_frontend_controls_are_instance_addressed_and_no_command_editor():
    root = Path(__file__).resolve().parents[1]
    html = (root / "pah/web/templates/index.html").read_text(encoding="utf-8")
    js = (root / "pah/web/static/module-instances.js").read_text(encoding="utf-8")
    assert 'id="moduleInstancesDialog"' in html
    assert 'id="moduleInstancesLaunch"' in html
    assert '/api/orchestration/instances/' in js
    assert '/api/orchestration/modules/' in js
    assert 'window.confirm' in js
    assert 'instance.managed_process' in js
    assert 'instance.url' in js
    assert 'textContent' in js
    assert 'innerHTML' not in js
    assert 'userCommand' not in js


def test_http_launch_requires_trusted_adapter_and_rejects_parameters(tmp_path: Path):
    pytest.importorskip('flask')
    from pah import create_app
    app = create_app(state_dir=tmp_path / 'state', instance_id='mi06-http')
    app.config.update(TESTING=True)
    registry = app.extensions['pah_runtime_registry']
    try:
        with app.test_client() as client:
            bad = client.post('/api/orchestration/modules/ml_lab/instances', json={"command": ["bad"]})
            assert bad.status_code == 400
            unavailable = client.post('/api/orchestration/modules/ml_lab/instances', json={})
            assert unavailable.status_code == 503
            registry.register(OptInAdapter(), replace=True)
            # Dummy isn't declared as installed/enabled: the module-policy gate must hold.
            denied = client.post('/api/orchestration/modules/dummy_module/instances', json={})
            assert denied.status_code == 503
    finally:
        app.extensions['pah_shutdown']()
