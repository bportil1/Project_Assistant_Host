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
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root)
    py = tmp_path / "pyPIQUE" / "pyproject.toml"
    py.parent.mkdir(parents=True)
    py.write_text('[project.optional-dependencies]\nfull=["pah-shared>=0.3,<0.4"]\n', encoding="utf-8")
    assert declared_constraints(root) == (">=0.3,<0.4",)


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


def test_missing_local_package_installs_sibling_offline_first(tmp_path: Path, monkeypatch):
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root)
    local_vendor = tmp_path / "PAH_Shared"
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

    assert bootstrap_pah_shared(root, Path("/venv/python"), run=fake_run) == "0.3.0"
    assert len(commands) == 1
    assert commands[0][0] == [
        "/venv/python", "-m", "pip", "install", "--no-index",
        "--no-deps", "--no-build-isolation", "-e", str(local_vendor),
    ]
    assert commands[0][1]["cwd"] == root


def test_matching_installation_without_source_is_not_authoritative(tmp_path: Path, monkeypatch):
    _required_project(tmp_path)
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: "0.3.0")
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
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
    shared = tmp_path.parent / "PAH_Shared"
    shared.mkdir(exist_ok=True)
    (shared / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.3.0"\n')
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
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root)
    py = tmp_path / "pyPIQUE" / "pyproject.toml"
    py.parent.mkdir(parents=True)
    py.write_text('[project.optional-dependencies]\nfull=["pah-shared>=0.4,<0.5"]\n')
    vendor = tmp_path / "vendor" / "PAH_Shared"
    vendor.mkdir(parents=True)
    (vendor / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.3.0"\n')
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: None)
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
        bootstrap_pah_shared(root, Path("/venv/python"),
                             run=lambda *_a, **_k: pytest.fail("conflicting versions must not install"))


def _graph_source(root: Path, name: str = "PAH_Shared") -> Path:
    source = root.parent / name
    static = source / "src" / "pah_shared" / "static"
    static.mkdir(parents=True)
    (source / "pyproject.toml").write_text(
        '[project]\nname="pah-shared"\nversion="0.4.0"\n', encoding="utf-8"
    )
    for asset in ("interactive_graph_view.mjs", "interactive_graph_view.css"):
        (static / asset).write_text("graph asset", encoding="utf-8")
    return source


def test_0_4_same_version_reinstalls_local_source_to_refresh_graph_assets(tmp_path, monkeypatch):
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root, spec=">=0.4,<0.5")
    source = _graph_source(root)
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: "0.4.0")
    monkeypatch.setattr("pah.shared_bootstrap._installed_missing_graph_assets", lambda *_: ())
    commands = []

    def run(args, **kw):
        commands.append((args, kw))
        return subprocess.CompletedProcess(args, 0)

    assert bootstrap_pah_shared(root, Path("/venv/python"), run=run) == "0.4.0"
    assert len(commands) == 1
    assert commands[0][0][-2:] == ["-e", source]
    assert "--no-index" in commands[0][0]
    assert commands[0][1]["cwd"] == root


def test_shared_checkout_without_graph_assets_is_not_accepted(tmp_path, monkeypatch):
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root, spec=">=0.4,<0.5")
    source = _graph_source(root)
    (source / "src/pah_shared/static/interactive_graph_view.mjs").unlink()
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: "0.4.0")
    with pytest.raises(SharedBootstrapError, match="incomplete.*interactive_graph_view.mjs"):
        bootstrap_pah_shared(root, Path("/venv/python"),
                             run=lambda *_a, **_k: pytest.fail("cannot install broken source"))


def test_matching_old_wheel_without_graph_assets_fails_closed(tmp_path, monkeypatch):
    _required_project(tmp_path, spec=">=0.4,<0.5")
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: "0.4.0")
    monkeypatch.setattr("pah.shared_bootstrap._installed_missing_graph_assets",
                        lambda *_: ("interactive_graph_view.mjs",))
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
        bootstrap_pah_shared(tmp_path, Path("/venv/python"),
                             run=lambda *_a, **_k: pytest.fail("no source to install"))


def test_explicit_source_override_is_authoritative(tmp_path, monkeypatch):
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root, spec=">=0.4,<0.5")
    source = _graph_source(root)
    (source / "pyproject.toml").write_text('[project]\nname="pah-shared"\nversion="0.3.0"\n')
    monkeypatch.setenv("PAH_SHARED_SOURCE", str(source))
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: "0.4.0")
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
        bootstrap_pah_shared(root, Path("/venv/python"),
                             run=lambda *_a, **_k: pytest.fail("bad override cannot be bypassed"))


def test_all_checked_out_module_constraints_are_honored(tmp_path, monkeypatch):
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root, spec=">=0.4,<0.5")
    _graph_source(root)
    module = tmp_path / "ML_Lab"
    module.mkdir(parents=True)
    (module / "pyproject.toml").write_text(
        '[project.optional-dependencies]\nui=["pah-shared>=0.3,<0.4"]\n'
    )
    monkeypatch.setattr("pah.shared_bootstrap._installed_version", lambda *_: None)
    assert declared_constraints(root) == (">=0.4,<0.5", ">=0.3,<0.4")
    with pytest.raises(SharedBootstrapError, match="no compatible local source"):
        bootstrap_pah_shared(root, Path("/venv/python"),
                             run=lambda *_a, **_k: pytest.fail("conflicting module extra"))


def test_code_analyzer_requirements_txt_participates_in_constraints(tmp_path):
    root = tmp_path / "PAH"
    root.mkdir()
    _required_project(root, spec=">=0.4,<0.5")
    path = tmp_path / "Code_Repository_Cataloguer" / "requirements.txt"
    path.parent.mkdir(parents=True)
    path.write_text("pah-shared>=0.2,<0.4\n")
    assert declared_constraints(root) == (">=0.4,<0.5", ">=0.2,<0.4")
