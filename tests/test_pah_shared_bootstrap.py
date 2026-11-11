"""The PAH_Shared offline setup fallback must not require any package index."""
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from pah import lifecycle
from pah.shared_bootstrap import (
    SharedBootstrapError,
    _source_version,
    bootstrap_pah_shared,
    declared_constraints,
    satisfies_all,
)


def _required_project(root: Path, *, spec: str = ">=0.3,<0.4") -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "project-assistant-host"\n'
        f'dependencies = ["Flask>=3", "pah-shared{spec}"]\n', encoding="utf-8"
    )


def test_declared_host_and_pypique_requirements(tmp_path: Path):
    _required_project(tmp_path)
    py = tmp_path / "modules" / "pypique" / "pyproject.toml"
    py.parent.mkdir(parents=True)
    py.write_text('[project.optional-dependencies]\nfull=["pah-shared>=0.3,<0.4"]\n', encoding="utf-8")
    assert declared_constraints(tmp_path) == (">=0.3,<0.4",)


def test_version_checks_and_unsupported_specs():
    assert satisfies_all("0.3.0", (">=0.3,<0.4",))
    assert not satisfies_all("0.2.9", (">=0.3,<0.4",))
    assert not satisfies_all("0.4.0", (">=0.3,<0.4",))
    assert satisfies_all("0.3.1", (">=0.3,<0.4", "!=0.3.0"))
    with pytest.raises(SharedBootstrapError, match="Unsupported"):
        satisfies_all("0.3.0", ("~=0.3",))


def test_vendor_snapshot_is_actual_0_3_package():
    vendor = Path(__file__).resolve().parents[1] / "vendor" / "PAH_Shared"
    assert _source_version(vendor) == "0.3.0"
    assert (vendor / "src" / "pah_shared" / "static" / "matrix_editor.mjs").is_file()
    assert (vendor / "src" / "pah_shared" / "table_view.py").is_file()


def test_missing_local_package_installs_vendor_offline_first(tmp_path: Path, monkeypatch):
    _required_project(tmp_path)
    local_vendor = tmp_path / "vendor" / "PAH_Shared"
    local_vendor.mkdir(parents=True)
    (local_vendor / "pyproject.toml").write_text(
        '[project]\nname="pah-shared"\nversion="0.3.0"\n', encoding="utf-8"
    )
    installed = [None, "0.3.0"]
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: installed.pop(0))
    commands = []

    def fake_run(args, **kwargs):
        commands.append(([str(a) for a in args], kwargs))
        return subprocess.CompletedProcess(args, 0)

    assert bootstrap_pah_shared(tmp_path, Path("/venv/python"), run=fake_run) == "0.3.0"
    assert len(commands) == 1
    assert commands[0][0] == [
        "/venv/python", "-m", "pip", "install", "--no-index",
        "--no-deps", "--no-build-isolation", "-e", str(local_vendor),
    ]
    assert commands[0][1]["cwd"] == tmp_path


def test_matching_installation_does_not_reinstall(tmp_path: Path, monkeypatch):
    _required_project(tmp_path)
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: "0.3.0")
    bootstrap_pah_shared(tmp_path, Path("/venv/python"), run=lambda *_a, **_k: pytest.fail("unexpected pip"))


def test_explicit_local_override_wrong_version_blocks_install(tmp_path: Path, monkeypatch):
    _required_project(tmp_path)
    path = tmp_path / "custom"
    path.mkdir()
    (path / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.4.0"\n')
    monkeypatch.setenv("PAH_SHARED_SOURCE", str(path))
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: None)
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
        bootstrap_pah_shared(tmp_path, Path("/venv/python"), run=lambda *_a, **_k: pytest.fail("unexpected pip"))


def test_no_requirement_leaves_existing_installs_untouched(tmp_path: Path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="project-assistant-host"\n')
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: pytest.fail("no requirement"))
    assert bootstrap_pah_shared(tmp_path, Path("/venv/python"), run=lambda *_a, **_k: pytest.fail("no install")) is None


def test_setup_installs_shared_before_host(monkeypatch, tmp_path: Path):
    _required_project(tmp_path)
    events = []

    def fake_run(args, **kwargs):
        events.append(str(args[-1]))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(lifecycle, "_run", fake_run)
    monkeypatch.setattr(lifecycle, "bootstrap_pah_shared", lambda root, python, *, run: events.append("shared"))
    monkeypatch.setattr(lifecycle, "PYTHON_COMPONENTS", lifecycle.PYTHON_COMPONENTS[:1])
    monkeypatch.setattr(lifecycle, "_component_present", lambda root, component: True)
    lifecycle.install_python_components(tmp_path, Path("/venv/python"))
    assert events == ["wheel", "shared", "."]


def test_prefers_existing_sibling_checkout_to_vendored_fallback(tmp_path: Path, monkeypatch):
    (tmp_path / "PAH").mkdir()
    _required_project(tmp_path / "PAH")
    sibling = tmp_path / "PAH_Shared"
    sibling.mkdir()
    (sibling / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.3.1"\n')
    vendor = tmp_path / "PAH" / "vendor" / "PAH_Shared"
    vendor.mkdir(parents=True)
    (vendor / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.3.0"\n')
    installed = [None, "0.3.1"]
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: installed.pop(0))
    calls = []
    assert bootstrap_pah_shared(tmp_path / "PAH", Path("/venv/python"),
                                run=lambda args, **kw: calls.append(args)) == "0.3.1"
    assert Path(calls[0][-1]) == sibling


def test_conflicting_host_pypique_ranges_report_error(tmp_path: Path, monkeypatch):
    _required_project(tmp_path)
    py = tmp_path / "modules" / "pypique" / "pyproject.toml"
    py.parent.mkdir(parents=True)
    py.write_text('[project.optional-dependencies]\nfull=["pah-shared>=0.4,<0.5"]\n')
    vendor = tmp_path / "vendor" / "PAH_Shared"
    vendor.mkdir(parents=True)
    (vendor / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.3.0"\n')
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: None)
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
        bootstrap_pah_shared(tmp_path, Path("/venv/python"),
                             run=lambda *_a, **_k: pytest.fail("conflicting versions must not install"))
