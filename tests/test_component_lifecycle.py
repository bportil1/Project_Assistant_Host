from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from pah.components import BROWSER_ASSETS, GIT_COMPONENTS, PYTHON_COMPONENTS, GitComponent
from pah.lifecycle import (
    LifecycleError,
    _asset_present,
    _component_present,
    advance_latest_modules,
    doctor_report,
    preflight_latest_modules,
)


def test_component_registry_covers_nested_modules_and_browser_assets():
    components = {component.key: component for component in PYTHON_COMPONENTS}
    assert components["code_analyzer"].install_spec.endswith("[web]")
    assert components["tech_documents"].install_spec.endswith("[web]")
    assert components["reference_manager"].install_spec.endswith("[web]")
    assert components["paper_searcher"].path == "modules/reference_manager/modules/paper_searcher"

    git_components = {component.key: component for component in GIT_COMPONENTS}
    assert git_components["code_analyzer"].default_branch == "main"
    assert git_components["paper_searcher"].path == "modules/reference_manager/modules/paper_searcher"

    assets = {asset.key: asset for asset in BROWSER_ASSETS}
    assert assets["pah_ace"].script == "scripts/vendor_ace.py"
    assert assets["pah_xterm"].script == "scripts/vendor_xterm.py"
    assert assets["workbench_ace"].script.endswith("modules/tech_documents/scripts/vendor_ace.py")
    assert assets["workbench_reveal"].script.endswith("modules/tech_documents/scripts/vendor_reveal.py")


def test_component_and_asset_readiness_are_path_based(tmp_path: Path):
    component = next(item for item in PYTHON_COMPONENTS if item.key == "paper_searcher")
    component_root = tmp_path / component.path
    component_root.mkdir(parents=True)
    assert not _component_present(tmp_path, component)
    (component_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert _component_present(tmp_path, component)

    asset = next(item for item in BROWSER_ASSETS if item.key == "pah_xterm")
    assert not _asset_present(tmp_path, asset)
    for marker in asset.markers:
        path = tmp_path / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    assert _asset_present(tmp_path, asset)


def test_doctor_json_shape_explains_missing_fragments(tmp_path: Path):
    report = doctor_report(tmp_path)
    assert report["ok"] is False
    assert report["venv"]["ok"] is False
    assert {item["key"] for item in report["components"]} >= {
        "pah",
        "code_analyzer",
        "tech_documents",
        "reference_manager",
        "paper_searcher",
    }
    assert {item["key"] for item in report["assets"]} >= {
        "pah_ace",
        "pah_xterm",
        "workbench_ace",
        "workbench_reveal",
    }
    json.dumps(report)


def test_public_lifecycle_scripts_route_through_one_python_coordinator():
    root = Path(__file__).resolve().parents[1]
    setup = (root / "scripts" / "setup.sh").read_text(encoding="utf-8")
    update = (root / "scripts" / "update.sh").read_text(encoding="utf-8")
    doctor = (root / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    vendor = (root / "scripts" / "vendor_assets.py").read_text(encoding="utf-8")
    lifecycle = (root / "pah" / "lifecycle.py").read_text(encoding="utf-8")

    assert "pah.lifecycle" in setup
    assert "pah.lifecycle" in update
    assert "pah.lifecycle" in doctor
    assert "from pah.lifecycle import main" in vendor
    assert "--latest-modules" in lifecycle
    assert "--skip-tests" in lifecycle


def test_setup_submodule_step_accepts_source_archives(tmp_path: Path, capsys):
    from pah.lifecycle import ensure_submodules

    (tmp_path / ".gitmodules").write_text("[submodule \"x\"]\n\tpath = modules/x\n", encoding="utf-8")
    ensure_submodules(tmp_path)
    output = capsys.readouterr().out
    assert "Source archive detected" in output


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def _configure_repo(path: Path) -> None:
    _git(path, "config", "user.email", "tests@example.com")
    _git(path, "config", "user.name", "PAH Tests")


def _remote_with_detached_worktree(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _configure_repo(seed)
    (seed / "value.txt").write_text("one\n", encoding="utf-8")
    _git(seed, "add", "value.txt")
    _git(seed, "commit", "-m", "one")
    first = _git(seed, "rev-parse", "HEAD")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-u", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

    root = tmp_path / "host"
    root.mkdir()
    work = root / "module"
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True, text=True)
    _configure_repo(work)
    _git(work, "checkout", "--detach", first)

    collaborator = tmp_path / "collaborator"
    subprocess.run(["git", "clone", str(remote), str(collaborator)], check=True, capture_output=True, text=True)
    _configure_repo(collaborator)
    (collaborator / "value.txt").write_text("two\n", encoding="utf-8")
    _git(collaborator, "add", "value.txt")
    _git(collaborator, "commit", "-m", "two")
    _git(collaborator, "push")
    latest = _git(collaborator, "rev-parse", "HEAD")
    return root, work, latest


def test_latest_module_update_switches_clean_detached_checkout_and_fast_forwards(tmp_path: Path):
    root, work, latest = _remote_with_detached_worktree(tmp_path)
    component = GitComponent(key="demo", label="Demo", path="module")

    snapshots = preflight_latest_modules(root, (component,))
    assert snapshots[0]["detached"] is True
    report = advance_latest_modules(root, (component,))

    assert _git(work, "branch", "--show-current") == "main"
    assert _git(work, "rev-parse", "HEAD") == latest
    assert (work / "value.txt").read_text(encoding="utf-8") == "two\n"
    assert report["components"][0]["changed"] is True


def test_latest_module_preflight_blocks_dirty_repository_before_changes(tmp_path: Path):
    root, work, _ = _remote_with_detached_worktree(tmp_path)
    component = GitComponent(key="demo", label="Demo", path="module")
    (work / "local.txt").write_text("unsaved\n", encoding="utf-8")

    with pytest.raises(LifecycleError, match="working tree is dirty"):
        preflight_latest_modules(root, (component,))


def test_latest_module_preflight_blocks_unexpected_feature_branch(tmp_path: Path):
    root, work, _ = _remote_with_detached_worktree(tmp_path)
    component = GitComponent(key="demo", label="Demo", path="module")
    _git(work, "checkout", "-b", "feature")

    with pytest.raises(LifecycleError, match="expected 'main'"):
        preflight_latest_modules(root, (component,))


def test_recommended_graphviz_and_quarto_tools_have_automatic_installers():
    from pah.components import SYSTEM_TOOLS

    tools = {tool.key: tool for tool in SYSTEM_TOOLS}
    assert tools["graphviz"].auto_install is True
    assert tools["graphviz"].installer == "package"
    assert tools["graphviz"].package_name == "graphviz"
    assert tools["quarto"].auto_install is True
    assert tools["quarto"].installer == "quarto_release"
    assert tools["latex"].auto_install is False


def test_quarto_release_asset_selection_is_platform_package_specific():
    from pah.lifecycle import _select_quarto_asset

    release = {
        "assets": [
            {"name": "quarto-1.2.3-linux-amd64.deb", "browser_download_url": "https://example.invalid/a.deb"},
            {"name": "quarto-1.2.3-linux-arm64.deb", "browser_download_url": "https://example.invalid/b.deb"},
            {"name": "quarto-1.2.3-linux-amd64.rpm", "browser_download_url": "https://example.invalid/a.rpm"},
        ]
    }
    assert _select_quarto_asset(release, manager="apt", arch="amd64")["name"].endswith("amd64.deb")
    assert _select_quarto_asset(release, manager="dnf", arch="amd64")["name"].endswith("amd64.rpm")


def test_optional_system_tool_provisioning_can_install_graphviz_and_quarto(monkeypatch, tmp_path: Path):
    import pah.lifecycle as lifecycle

    installed: set[str] = set()
    monkeypatch.setattr(lifecycle, "_package_manager", lambda: "apt")
    monkeypatch.setattr(lifecycle.shutil, "which", lambda command: f"/usr/bin/{command}" if command in installed else None)

    def fake_package(package: str, **kwargs):
        assert package == "graphviz"
        installed.add("dot")

    def fake_quarto(**kwargs):
        installed.add("quarto")

    monkeypatch.setattr(lifecycle, "_install_package", fake_package)
    monkeypatch.setattr(lifecycle, "_install_quarto", fake_quarto)

    assert lifecycle.provision_system_tools(tmp_path) == []
    assert installed == {"dot", "quarto"}


def test_optional_system_tool_failure_does_not_raise(monkeypatch, tmp_path: Path):
    import pah.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "_package_manager", lambda: "apt")
    monkeypatch.setattr(lifecycle.shutil, "which", lambda command: None)
    monkeypatch.setattr(lifecycle, "_install_package", lambda *args, **kwargs: (_ for _ in ()).throw(LifecycleError("apt unavailable")))
    monkeypatch.setattr(lifecycle, "_install_quarto", lambda **kwargs: (_ for _ in ()).throw(LifecycleError("network unavailable")))

    failures = lifecycle.provision_system_tools(tmp_path)
    assert any("Graphviz" in failure for failure in failures)
    assert any("Quarto" in failure for failure in failures)


def _init_simple_repo(path: Path, *, filename: str = "pyproject.toml") -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _configure_repo(path)
    (path / filename).write_text("[project]\nname='fixture'\nversion='0.0.0'\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")


def test_fresh_clone_recursive_submodule_bootstrap_includes_nested_research_search(tmp_path: Path, monkeypatch):
    from pah.lifecycle import ensure_submodules

    sources = tmp_path / "sources"
    paper = sources / "paper_searcher"
    _init_simple_repo(paper)
    (paper / "run.py").write_text("print('search')\n", encoding="utf-8")
    _git(paper, "add", "run.py")
    _git(paper, "commit", "-m", "runner")

    reference = sources / "reference_manager"
    _init_simple_repo(reference)
    _git(reference, "-c", "protocol.file.allow=always", "submodule", "add", str(paper), "modules/paper_searcher")
    _git(reference, "commit", "-am", "nested search module")

    analyzer = sources / "code_analyzer"
    documents = sources / "tech_documents"
    _init_simple_repo(analyzer)
    _init_simple_repo(documents)

    host_source = sources / "host"
    _init_simple_repo(host_source)
    for source, destination in (
        (analyzer, "modules/code_analyzer"),
        (documents, "modules/tech_documents"),
        (reference, "modules/reference_manager"),
    ):
        _git(host_source, "-c", "protocol.file.allow=always", "submodule", "add", str(source), destination)
    _git(host_source, "commit", "-am", "host modules")

    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", "--no-recurse-submodules", str(host_source), str(checkout)], check=True, capture_output=True, text=True)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")

    ensure_submodules(checkout)

    assert (checkout / "modules/code_analyzer/pyproject.toml").is_file()
    assert (checkout / "modules/tech_documents/pyproject.toml").is_file()
    assert (checkout / "modules/reference_manager/pyproject.toml").is_file()
    assert (checkout / "modules/reference_manager/modules/paper_searcher/run.py").is_file()
    status = _git(checkout, "submodule", "status", "--recursive")
    assert "modules/reference_manager/modules/paper_searcher" in status


def test_host_update_cleanliness_ignores_untracked_patch_files_but_blocks_tracked_edits(tmp_path: Path):
    from pah.lifecycle import _host_dirty, _host_untracked

    _init_simple_repo(tmp_path)
    (tmp_path / "PAH_update.patch").write_text("patch artifact\n", encoding="utf-8")
    assert _host_dirty(tmp_path) == []
    assert "PAH_update.patch" in _host_untracked(tmp_path)

    (tmp_path / "pyproject.toml").write_text("changed\n", encoding="utf-8")
    assert _host_dirty(tmp_path)


def test_setup_orchestrates_full_chain_and_optional_tool_failure_is_nonfatal(monkeypatch, tmp_path: Path):
    import pah.lifecycle as lifecycle

    calls: list[str] = []
    fake_python = tmp_path / ".venv/bin/python"

    monkeypatch.setattr(lifecycle, "_python_ok", lambda: True)
    monkeypatch.setattr(lifecycle, "ensure_submodules", lambda root: calls.append("submodules"))
    monkeypatch.setattr(lifecycle, "ensure_venv", lambda root: calls.append("venv") or fake_python)
    monkeypatch.setattr(lifecycle, "install_python_components", lambda root, python: calls.append("python"))
    monkeypatch.setattr(lifecycle, "provision_assets", lambda root, python, force=False: calls.append("assets") or [])
    monkeypatch.setattr(
        lifecycle,
        "provision_system_tools",
        lambda root: calls.append("system-tools") or ["Quarto: offline"],
    )
    monkeypatch.setattr(lifecycle, "doctor_report", lambda root: calls.append("doctor") or {"ok": True})
    monkeypatch.setattr(lifecycle, "print_doctor", lambda report: None)

    assert lifecycle.setup(tmp_path) == 0
    assert calls == ["submodules", "venv", "python", "assets", "system-tools", "doctor"]
