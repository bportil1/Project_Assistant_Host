"""Regression contract: PAH never treats embedded Git modules as source owners."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pah import lifecycle
from pah.components import GIT_COMPONENTS, PYTHON_COMPONENTS
from pah.shared_bootstrap import declared_constraints


def test_registry_targets_only_standalone_source_owners(tmp_path: Path):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    for component in PYTHON_COMPONENTS:
        location = (host / component.path).resolve()
        if component.key == "pah":
            assert location == host
        else:
            assert location != host and host not in location.parents
    for component in GIT_COMPONENTS:
        location = (host / component.path).resolve()
        assert location != host and host not in location.parents


def test_missing_standalone_checkout_fails_before_installs(tmp_path: Path, monkeypatch):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pyproject.toml").write_text('[project]\nname="project-assistant-host"\n')
    calls = []
    monkeypatch.setattr(lifecycle, "_run", lambda *args, **kw: calls.append(args))
    with pytest.raises(lifecycle.LifecycleError, match="Code Analyzer"):
        lifecycle.install_python_components(host, Path("/unused/python"))
    assert calls == []


def test_forged_standalone_symlink_back_to_host_is_refused(tmp_path: Path, monkeypatch):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pyproject.toml").write_text('[project]\nname="project-assistant-host"\n')
    (host / "modules").mkdir()
    (host / "modules" / "code_analyzer").mkdir()
    (host / "modules" / "code_analyzer" / "pyproject.toml").write_text('[project]\n')
    (tmp_path / "Code_Repository_Cataloguer").symlink_to(host / "modules" / "code_analyzer")
    monkeypatch.setattr(lifecycle, "PYTHON_COMPONENTS", PYTHON_COMPONENTS[:2])
    with pytest.raises(lifecycle.LifecycleError, match="source must not resolve inside PAH"):
        lifecycle.preflight_standalone_sources(host)


def test_stale_embedded_constraint_is_never_consulted(tmp_path: Path):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pyproject.toml").write_text(
        '[project]\ndependencies=["pah-shared>=0.4,<0.5"]\n'
    )
    legacy = host / "modules" / "pypique" / "pyproject.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('[project.optional-dependencies]\nfull=["pah-shared>=0.2,<0.3"]\n')
    assert declared_constraints(host) == (">=0.4,<0.5",)


def test_default_update_never_runs_any_submodule_git_command(tmp_path: Path, monkeypatch):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / ".git").mkdir()
    calls = []

    def fake_run(args, **kwargs):
        calls.append([str(x) for x in args])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle, "_run", fake_run)
    monkeypatch.setattr(lifecycle, "_reenter_update", lambda *args, **kwargs: 0)
    assert lifecycle.update(host) == 0
    assert calls == [["git", "-c", "submodule.recurse=false", "pull", "--ff-only"]]


def test_no_pull_update_runs_setup_without_submodule_sync(tmp_path: Path, monkeypatch):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / ".git").mkdir()
    calls = []
    monkeypatch.setattr(lifecycle, "ensure_submodules", lambda *_: pytest.fail("no submodule operations"))

    def fake_run(args, **kwargs):
        calls.append([str(x) for x in args])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle, "_run", fake_run)
    assert lifecycle.update(host, no_pull=True) == 0
    assert len(calls) == 1
    assert "setup" in calls[0] and "--skip-submodules" in calls[0]
    assert all("submodule" not in c[:2] for c in calls)


def test_host_does_not_ship_code_analyzer_namespace_overlay():
    host = Path(__file__).resolve().parents[1]
    assert not any((host / "code_analyzer").rglob("*.py"))


def test_host_dirty_check_ignores_legacy_submodule_worktrees(tmp_path: Path, monkeypatch):
    captured = []
    monkeypatch.setattr(lifecycle, "_is_git_repo", lambda *_: True)

    def fake_output(root, args, **kw):
        captured.append(args)
        return ""

    monkeypatch.setattr(lifecycle, "_git_output", fake_output)
    assert lifecycle._host_dirty(tmp_path) == []
    assert "--ignore-submodules=all" in captured[0]
