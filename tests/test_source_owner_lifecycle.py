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
            assert location.parent == host.parent
    for component in GIT_COMPONENTS:
        location = (host / component.path).resolve()
        assert location.parent == host.parent
    assert "paper_searcher" not in {item.key for item in PYTHON_COMPONENTS}
    assert "paper_searcher" not in {item.key for item in GIT_COMPONENTS}


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


def test_missing_optional_research_search_companion_does_not_block_preflight(tmp_path: Path, monkeypatch):
    """A real Reference Manager source is required; its nested searcher is not."""
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pyproject.toml").write_text('[project]\nname="project-assistant-host"\n')
    for component in PYTHON_COMPONENTS:
        if component.key == "pah":
            continue
        source = (host / component.path).resolve()
        source.mkdir(parents=True)
        (source / "pyproject.toml").write_text('[project]\nname="fixture"\n')
    monkeypatch.setattr(lifecycle, "declared_constraints", lambda *_: ())
    assert not (tmp_path / "Research_Paper_Repository_Manager" / "modules" / "paper_searcher").exists()
    lifecycle.preflight_standalone_sources(host)


def test_nested_optional_source_is_refused_even_when_marked_optional(tmp_path: Path, monkeypatch):
    from pah.components import PythonComponent

    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pyproject.toml").write_text('[project]\nname="project-assistant-host"\n')
    fake_nested = PythonComponent(
        key="bad", label="Bad nested source", path="../Other_Repo/modules/nested",
        install_spec="../Other_Repo/modules/nested", imports=(), required=False,
    )
    monkeypatch.setattr(lifecycle, "PYTHON_COMPONENTS", (PYTHON_COMPONENTS[0], fake_nested))
    monkeypatch.setattr(lifecycle, "declared_constraints", lambda *_: ())
    with pytest.raises(lifecycle.LifecycleError, match="source must be a sibling checkout"):
        lifecycle.preflight_standalone_sources(host)


def test_optional_search_absent_from_install_and_latest_module_registries():
    assert all("paper_searcher" != entry.key for entry in PYTHON_COMPONENTS)
    assert all("paper_searcher" != entry.key for entry in GIT_COMPONENTS)
    assert all("/modules/" not in entry.path for entry in (*PYTHON_COMPONENTS, *GIT_COMPONENTS))


def test_setup_installs_only_standalone_distributions_not_search_companion(tmp_path: Path, monkeypatch):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pyproject.toml").write_text('[project]\nname="project-assistant-host"\n')
    for component in PYTHON_COMPONENTS:
        if component.key == "pah":
            continue
        source = (host / component.path).resolve()
        source.mkdir(parents=True)
        (source / "pyproject.toml").write_text('[project]\nname="fixture"\n')
    monkeypatch.setattr(lifecycle, "declared_constraints", lambda *_: ())
    monkeypatch.setattr(lifecycle, "bootstrap_pah_shared", lambda *args, **kwargs: None)
    monkeypatch.setattr(lifecycle, "_code_analyzer_api_status", lambda *args, **kwargs: (True, None))
    commands = []

    def fake_run(args, **kwargs):
        commands.append(tuple(map(str, args)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle, "_run", fake_run)
    lifecycle.install_python_components(host, Path("/fake/python"))
    installs = [entry for entry in commands if "install" in entry]
    assert len(installs) == len(PYTHON_COMPONENTS) + 1  # pip tools + each managed source
    assert not any("paper_searcher" in " ".join(entry) for entry in installs)
    assert not any("/modules/" in " ".join(entry) for entry in installs)
