"""MI-05: PAH must not commandeer a module's project manager."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from pah.runtime import HostSurfaceRuntimeAdapter, RuntimeRegistry, register_host_surface_fallbacks


def test_existing_entry_points_are_authoritative():
    registry = RuntimeRegistry()
    existing = SimpleNamespace(module_id="tech_documents", status=lambda **kw: {})
    registry.register(existing)
    added = register_host_surface_fallbacks(registry, object())
    assert registry.get("tech_documents") is existing
    assert added == ("code_analyzer", "reference_manager")
    assert isinstance(registry.get("code_analyzer"), HostSurfaceRuntimeAdapter)
    assert isinstance(registry.get("reference_manager"), HostSurfaceRuntimeAdapter)


def test_document_app_factory_does_not_replace_owner_engine(monkeypatch):
    from pah import hosted_compat

    owner_app = object()
    owner_engine = object()
    module = SimpleNamespace(app=owner_app, engine=owner_engine)
    monkeypatch.setattr(hosted_compat.importlib, "import_module", lambda name: module)
    assert hosted_compat.document_workbench_app() is owner_app
    assert module.engine is owner_engine


def test_full_tools_never_mutates_running_document_or_analysis_on_bind(tmp_path, monkeypatch):
    pytest.importorskip("werkzeug")
    import pah.full_tools as full

    class FakeServer:
        def __init__(self):
            self.app = None
            self.calls = 0
            self.url = "http://127.0.0.1:9999/"
            self.running = False

        def start(self, app):
            self.app = app
            self.calls += 1
            self.running = True

        def stop(self):
            self.running = False

    manager = full.FullToolManager(state_dir=tmp_path)
    manager._servers = {name: FakeServer() for name in ("analysis", "documents", "references")}
    owner_app = object()
    monkeypatch.setattr(full, "document_workbench_app", lambda: owner_app)
    # Analyzer WSGI wrapper remains outside the module-owned object.
    monkeypatch.setattr(full, "code_analyzer_app", lambda root, on_analysis=None: (lambda env, start: None))

    root_a, root_b = tmp_path / "repo-a", tmp_path / "repo-b"
    root_a.mkdir(); root_b.mkdir()
    manager.bind_workspace(root_a)
    manager.bind_document_root(root_a)
    manager.start("documents")
    assert manager._servers["documents"].app is owner_app
    manager.start("analysis")
    assert manager.status()["tools"]["analysis"]["bound_workspace"] == str(root_a)
    manager.bind_workspace(root_b)
    manager.bind_document_root(root_b)
    manager.start("analysis")
    manager.start("documents")
    assert manager._servers["analysis"].calls == 1
    assert manager._servers["documents"].calls == 1
    assert manager.status()["tools"]["analysis"]["selection_differs"]
    assert manager.status()["tools"]["documents"]["bound_workspace"] is None
    assert manager.status()["tools"]["documents"]["suggested_document_root"] == str(root_b)

    manager.stop("analysis")
    manager.start("analysis")
    assert manager._servers["analysis"].calls == 2
    assert manager.status()["tools"]["analysis"]["bound_workspace"] == str(root_b)


def test_source_has_no_engine_subclass_or_hidden_workbench_project_controls():
    text = (Path(__file__).resolve().parents[1] / "pah" / "full_tools.py").read_text(encoding="utf-8")
    assert "class WorkspaceDocumentEngine" not in text
    assert "web_app.engine" not in text
    assert "#newProjectBtn" not in text
    assert "manager._document_root" not in text


def test_profile_switch_cannot_implicitly_stop_a_running_surface():
    source = (Path(__file__).resolve().parents[1] / "pah" / "app.py").read_text(encoding="utf-8")
    profile_manager = source.split("    def start_enabled_full_tools() -> None:", 1)[1].split(
        "    def full_tools_status_with_profile() -> dict:", 1
    )[0]
    assert "full_tools.stop(surface)" not in profile_manager
    assert "unregister_module_runtime(module_id)" not in profile_manager


def test_discovered_runtime_instance_record_is_not_overwritten_by_hosted_ui():
    source = (Path(__file__).resolve().parents[1] / "pah" / "app.py").read_text(encoding="utf-8")
    assert 'runtime_registry.get(module_id), HostSurfaceRuntimeAdapter' in source


def test_hosted_callback_cannot_update_analyzer_from_previous_workspace():
    source = (Path(__file__).resolve().parents[1] / "pah" / "app.py").read_text(encoding="utf-8")
    callback = source.split("    def sync_hosted_code_analyzer(engine, event: str) -> None:", 1)[1].split(
        "    full_tools.set_analysis_change_callback", 1
    )[0]
    assert "if not full_tools.analysis_bound_to(workspaces.root):" in callback
    assert callback.index("analysis_bound_to") < callback.index("synchronize_from_engine")
