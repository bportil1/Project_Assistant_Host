from __future__ import annotations

from pathlib import Path

import pytest

from pah.contracts import ModuleContext
from pah.runtime import HostSurfaceRuntimeAdapter, RuntimeRegistry, RuntimeRegistryError


class DemoRuntime:
    module_id = "demo"

    def __init__(self):
        self.running = False
        self.last_context = None
        self.detached = None

    def status(self, *, context=None):
        return {
            "module_id": self.module_id,
            "available": True,
            "running": self.running,
            "launchable": True,
            "presentation": "url",
            "url": "http://127.0.0.1:9999/" if self.running else None,
        }

    def launch(self, *, context=None, detached=False):
        self.running = True
        self.last_context = context
        self.detached = detached
        return {
            "module_id": self.module_id,
            "launched": True,
            "presentation": "url",
            "url": "http://127.0.0.1:9999/",
            "metadata": {"detached": detached},
        }

    def shutdown(self, *, context=None):
        self.running = False


class FakeFullTools:
    def __init__(self):
        self.running = False

    def status(self):
        return {"tools": {"analysis": {
            "available": self.running,
            "url": "http://127.0.0.1:8766/" if self.running else None,
            "error": None,
        }}}

    def start(self, name):
        assert name == "analysis"
        self.running = True
        return self.status()["tools"][name]

    def stop(self, name):
        assert name == "analysis"
        self.running = False


def test_runtime_registry_passes_explicit_module_context_and_detach_choice(tmp_path: Path):
    adapter = DemoRuntime()
    registry = RuntimeRegistry((adapter,))
    context = ModuleContext(project_root=tmp_path, working_root=tmp_path)

    before = registry.status("demo", context)
    assert before.launchable is True
    assert before.running is False

    launch = registry.launch("demo", context, detached=True)
    assert launch.launched is True
    assert launch.presentation == "url"
    assert adapter.last_context == context
    assert adapter.detached is True
    assert registry.status("demo", context).running is True

    registry.shutdown("demo", context)
    assert registry.status("demo", context).running is False


def test_runtime_registry_reports_missing_adapter_without_guessing():
    registry = RuntimeRegistry()
    status = registry.status("missing")
    assert status.available is False
    assert status.launchable is False
    with pytest.raises(RuntimeRegistryError, match="No runtime adapter"):
        registry.launch("missing")


def test_host_surface_adapter_bridges_existing_analysis_runtime_without_exposing_it_to_lab_logic():
    full_tools = FakeFullTools()
    adapter = HostSurfaceRuntimeAdapter("code_analyzer", "analysis", full_tools)
    registry = RuntimeRegistry((adapter,))

    status = registry.status("code_analyzer")
    assert status.launchable is True
    assert status.running is False
    assert status.presentation == "host_surface"

    launch = registry.launch("code_analyzer", detached=False)
    assert launch.surface == "analysis"
    assert launch.presentation == "host_surface"
    assert full_tools.running is True

    registry.shutdown("code_analyzer")
    assert full_tools.running is False


# Runtime-adapter contract regression: a class entry point is a constructor,
# not a ready-to-use adapter instance. The actual Code Analyzer MI-01 package
# exports this shape; prior PAH status polling raised "missing self" (HTTP 500).
def test_runtime_registration_realizes_class_and_factory_before_status():
    direct = RuntimeRegistry((DemoRuntime,))
    assert isinstance(direct.get("demo"), DemoRuntime)
    assert direct.status("demo").available is True

    factory = RuntimeRegistry((lambda: DemoRuntime(),))
    assert isinstance(factory.get("demo"), DemoRuntime)
    assert factory.status("demo").available is True


def test_entry_point_discovery_returns_instantiated_runtime(monkeypatch):
    from pah import runtime as runtime_module

    class EntryPoint:
        name = "code_analyzer"
        def load(self):
            return DemoRuntime

    class EntryPoints:
        def select(self, *, group):
            assert group == "pah.runtimes"
            return [EntryPoint()]

    monkeypatch.setattr(runtime_module.metadata, "entry_points", lambda: EntryPoints())
    registry = RuntimeRegistry()
    adapters = registry.discover_entry_points()
    assert len(adapters) == 1
    assert adapters[0] is registry.get("demo")
    assert isinstance(adapters[0], DemoRuntime)
    assert registry.status("demo").available is True
    assert registry.snapshot()["discovery_errors"] == []


def test_invalid_constructor_is_recorded_and_does_not_register_a_class(monkeypatch):
    from pah import runtime as runtime_module

    class NeedsConfig:
        module_id = "code_analyzer"
        def __init__(self, *, config):
            self.config = config
        def status(self, *, context=None):
            return {"module_id": self.module_id, "available": True}

    class EntryPoint:
        name = "code_analyzer"
        def load(self):
            return NeedsConfig

    monkeypatch.setattr(runtime_module.metadata, "entry_points", lambda: {"pah.runtimes": [EntryPoint()]})
    registry = RuntimeRegistry()
    assert registry.discover_entry_points() == ()
    assert registry.get("code_analyzer") is None
    errors = registry.snapshot()["discovery_errors"]
    assert len(errors) == 1
    assert errors[0]["entry_point"] == "code_analyzer"


def test_bad_status_is_reported_without_crashing_other_modules(caplog):
    class Broken:
        module_id = "code_analyzer"
        def status(self, *, context=None):
            raise RuntimeError("provider offline")

    registry = RuntimeRegistry((Broken(), DemoRuntime()))
    snapshot = registry.snapshot()
    statuses = {item["module_id"]: item for item in snapshot["runtimes"]}
    assert statuses["code_analyzer"]["available"] is False
    assert statuses["code_analyzer"]["launchable"] is False
    assert statuses["code_analyzer"]["metadata"]["runtime_error"] == "RuntimeError"
    assert "provider offline" in statuses["code_analyzer"]["message"]
    assert statuses["demo"]["available"] is True
    assert "Runtime status failed for module code_analyzer" in caplog.text


def test_factory_cannot_return_a_class_instead_of_an_instance():
    with pytest.raises(RuntimeRegistryError, match="uninstantiated class"):
        RuntimeRegistry((lambda: DemoRuntime,))


def test_status_failure_keeps_workflow_http_available(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    from pah import create_app
    from pah import runtime as runtime_module

    class Broken:
        module_id = "code_analyzer"
        def status(self, *, context=None):
            raise ValueError("unavailable status provider")

    class EntryPoint:
        name = "code_analyzer"
        def load(self):
            return Broken

    monkeypatch.setattr(runtime_module.metadata, "entry_points", lambda: {"pah.runtimes": [EntryPoint()]})
    app = create_app(state_dir=tmp_path / "pah-state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        modules = client.get("/api/orchestration/modules")
        workflow = client.get("/api/orchestration/code-analysis")
    assert modules.status_code == 200
    assert workflow.status_code == 200
    assert workflow.get_json()["ok"] is True


def test_real_code_analyzer_factory_uses_bound_status_in_pah_registry(tmp_path):
    pytest.importorskip("code_analyzer.integrations.pah")
    from code_analyzer.integrations.pah import create_runtime_adapter

    root = tmp_path / "source"
    root.mkdir()
    context = ModuleContext(project_root=root, working_root=root, resources={"repository": root})
    registry = RuntimeRegistry((create_runtime_adapter,))
    adapter = registry.get("code_analyzer")
    assert adapter.module_id == "code_analyzer"
    assert adapter.status.__self__ is adapter
    result = registry.status("code_analyzer", context)
    assert result.module_id == "code_analyzer"
    assert not result.metadata.get("runtime_error")
