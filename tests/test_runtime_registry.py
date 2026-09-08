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
