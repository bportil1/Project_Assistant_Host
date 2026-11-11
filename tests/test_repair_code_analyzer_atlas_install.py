"""Offline checks for the opt-in Code Analyzer/UCA-12 install repair."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).parents[1] / "scripts" / "repair_code_analyzer_atlas_install.py"
spec = importlib.util.spec_from_file_location("repair_code_analyzer_atlas_install", SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def test_missing_u12_file_is_detected(tmp_path):
    assert "code_analyzer/language_providers/inventory.py" in repair.source_problems(tmp_path)


def test_full_source_has_no_missing_files(tmp_path):
    for rel in repair.REQUIRED_FILES:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    assert repair.source_problems(tmp_path) == []


def test_probe_runs_in_target_python_and_pah_directory(tmp_path, monkeypatch):
    observed = {}
    def fake_run(cmd, **kw):
        observed.update(cmd=cmd, kw=kw)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "origin": "/test"}), stderr="")
    monkeypatch.setattr(repair.subprocess, "run", fake_run)
    ok, report = repair.probe_install(Path("/some/python"), tmp_path)
    assert ok and report["origin"] == "/test"
    assert observed["cmd"][:2] == ["/some/python", "-c"]
    assert observed["kw"]["cwd"] == str(tmp_path)


def test_offline_install_never_uses_index_or_editable(tmp_path, monkeypatch):
    observed = {}
    def fake_run(cmd, **kw):
        observed["cmd"] = cmd
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(repair.subprocess, "run", fake_run)
    assert repair.install_source(Path("/python"), tmp_path, tmp_path) == 0
    command = observed["cmd"]
    assert "--no-index" in command and "--no-deps" in command
    assert "--no-build-isolation" in command and "--force-reinstall" in command
    assert "-e" not in command and str(tmp_path) == command[-1]


def test_probe_does_not_claim_unparseable_output_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout="Oops", stderr="details"))
    ok, report = repair.probe_install(Path("/python"), tmp_path)
    assert not ok and "error" in report


def test_probe_script_requires_both_provider_inventory_and_navigation():
    assert 'from code_analyzer.language_providers.inventory import atlas_files' in repair.PROBE
    assert 'from code_analyzer.language_providers.navigation import build_navigation_snapshot' in repair.PROBE
    assert 'from code_analyzer.web.atlas_routes import register_atlas_routes' in repair.PROBE


def test_main_uses_venv_entry_point_not_resolved_system_python(tmp_path, monkeypatch):
    """Regression: venv/bin/python may symlink to /usr/bin/python3.12."""
    root = tmp_path / "host"
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    # A symlink should remain the subprocess command even if its target is elsewhere.
    (venv / "bin" / "python").symlink_to(Path(__import__("sys").executable))
    source = tmp_path / "cataloguer"
    for rel in repair.REQUIRED_FILES:
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# placeholder\n")
    monkeypatch.setattr(repair.sys, "prefix", str(venv))
    invocations = []

    def fake_probe(python, cwd):
        invocations.append(("probe", python, cwd))
        return True, {"ok": True, "python": str(python)}

    def fake_install(python, source_path, cwd):
        invocations.append(("install", python, cwd))
        return 0

    monkeypatch.setattr(repair, "probe_install", fake_probe)
    monkeypatch.setattr(repair, "install_source", fake_install)
    assert repair.main(["--pah-root", str(root), "--source", str(source), "--repair"]) == 0
    assert len(invocations) == 3
    for _, invoked_python, invoked_cwd in invocations:
        assert invoked_python == venv / "bin" / "python"
        assert invoked_cwd == root
        assert invoked_python.resolve() != invoked_python


def test_main_refuses_nonvenv_invocations_before_install(tmp_path, monkeypatch):
    root = tmp_path / "host"
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    (venv / "bin" / "python").symlink_to(Path(__import__("sys").executable))
    monkeypatch.setattr(repair.sys, "prefix", str(tmp_path / "wrong_env"))
    monkeypatch.setattr(repair, "install_source", lambda *a: (_ for _ in ()).throw(AssertionError("should not install")))
    assert repair.main(["--pah-root", str(root), "--source", str(tmp_path), "--repair"]) == 2


def test_preflight_rejects_missing_foundational_contract_even_with_u12(tmp_path):
    """Regression for the observed successful reinstall that omitted contracts.py."""
    for rel in repair.REQUIRED_FILES:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# placeholder\n")
    (tmp_path / "code_analyzer/language_providers/contracts.py").unlink()
    assert repair.source_problems(tmp_path) == [
        "code_analyzer/language_providers/contracts.py"
    ]


def test_preflight_checks_uca07_08_09_and_12():
    required = set(repair.REQUIRED_FILES)
    assert {
        "code_analyzer/language_providers/contracts.py",
        "code_analyzer/language_providers/registry.py",
        "code_analyzer/language_providers/python_provider.py",
        "code_analyzer/language_providers/atlas_provider.py",
        "code_analyzer/language_providers/_atlas_engine/analysis.py",
        "code_analyzer/language_providers/navigation.py",
        "code_analyzer/language_providers/inventory.py",
        "code_analyzer/web/atlas_routes.py",
    }.issubset(required)


def test_import_probe_checks_contracts_and_registry_before_browser():
    assert "from code_analyzer.language_providers.contracts import CONTRACT_VERSION" in repair.PROBE
    assert "from code_analyzer.language_providers.registry import default_registry" in repair.PROBE
    assert "from code_analyzer.language_providers.atlas_provider import AtlasLanguageProvider" in repair.PROBE


def test_missing_contracts_block_reinstall_before_pip(tmp_path, monkeypatch):
    root = tmp_path / "host"
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    (venv / "bin" / "python").symlink_to(Path(__import__("sys").executable))
    source = tmp_path / "cataloguer"
    for rel in repair.REQUIRED_FILES:
        if rel.endswith("/contracts.py"):
            continue
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# placeholder\n")
    monkeypatch.setattr(repair.sys, "prefix", str(venv))
    monkeypatch.setattr(repair, "probe_install", lambda *args: (False, {"ok": False}))
    monkeypatch.setattr(repair, "install_source", lambda *args: (_ for _ in ()).throw(AssertionError("pip should not run")))
    assert repair.main(["--pah-root", str(root), "--source", str(source), "--repair"]) == 2
