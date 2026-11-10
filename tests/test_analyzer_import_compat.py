"""Offline public-import regression tests for Code Analyzer integration."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pah.integrations.analyzer import AnalyzerIntegration, AnalyzerIntegrationError
from pah.lifecycle import _code_analyzer_api_status


def test_missing_root_reexport_uses_public_api_module(monkeypatch):
    package = ModuleType("code_analyzer")
    package.__file__ = "/local/code_analyzer/__init__.py"
    api = ModuleType("code_analyzer.api")
    class Facade:
        pass
    api.CodeAnalyzer = Facade
    seen = []

    def importer(name):
        seen.append(name)
        return {"code_analyzer": package, "code_analyzer.api": api}[name]

    monkeypatch.setattr("pah.integrations.analyzer.importlib.import_module", importer)
    adapter = AnalyzerIntegration()
    assert adapter._load_class() is Facade
    assert adapter.status()["available"] is True
    assert seen == ["code_analyzer", "code_analyzer.api"]


def test_incompatible_package_reports_actual_origin(monkeypatch, tmp_path):
    package = ModuleType("code_analyzer")
    package.__file__ = "/bad/site-packages/code_analyzer/__init__.py"

    def importer(name):
        if name == "code_analyzer":
            return package
        raise ModuleNotFoundError("No module named 'code_analyzer.api'")

    monkeypatch.setattr("pah.integrations.analyzer.importlib.import_module", importer)
    adapter = AnalyzerIntegration()
    adapter.bind(tmp_path)
    status = adapter.status()
    assert status["available"] is False
    assert "/bad/site-packages/code_analyzer" in status["import_error"]
    with pytest.raises(AnalyzerIntegrationError, match="incompatible with PAH"):
        adapter.analyze()


def test_namespace_package_is_reported_without_guessing_paths(monkeypatch):
    package = ModuleType("code_analyzer")
    package.__path__ = ["/tmp/empty_code_analyzer"]

    def importer(name):
        if name == "code_analyzer":
            return package
        raise ImportError("no api module")

    monkeypatch.setattr("pah.integrations.analyzer.importlib.import_module", importer)
    assert "/tmp/empty_code_analyzer" in AnalyzerIntegration().status()["import_error"]


def test_existing_root_facade_is_preferred(monkeypatch):
    package = ModuleType("code_analyzer")
    class Facade:
        pass
    package.CodeAnalyzer = Facade
    monkeypatch.setattr(
        "pah.integrations.analyzer.importlib.import_module",
        lambda name: package if name == "code_analyzer" else pytest.fail("unneeded fallback"),
    )
    assert AnalyzerIntegration()._load_class() is Facade


def test_doctor_api_check_rejects_importable_incompatible_package(tmp_path: Path):
    package = tmp_path / "code_analyzer"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    ok, detail = _code_analyzer_api_status(Path(sys.executable), root=tmp_path)
    assert ok is False
    assert "CodeAnalyzer is unavailable" in (detail or "")
    assert "import origin" in (detail or "")


def test_doctor_api_check_accepts_real_public_facade_and_web(tmp_path: Path):
    package = tmp_path / "code_analyzer"
    web = package / "web"
    web.mkdir(parents=True)
    (package / "__init__.py").write_text("class CodeAnalyzer: pass\n", encoding="utf-8")
    (web / "__init__.py").write_text("", encoding="utf-8")
    (web / "app.py").write_text("def create_app(): pass\n", encoding="utf-8")
    ok, detail = _code_analyzer_api_status(Path(sys.executable), root=tmp_path)
    assert ok is True
    assert detail is None


def test_browser_status_preserves_diagnostic_from_server():
    source = (Path(__file__).resolve().parents[1] / "pah/web/static/pah.js").read_text(encoding="utf-8")
    assert "state.analyzer.importError = typeof data.import_error" in source
    assert "Code Analyzer import failed:" in source
