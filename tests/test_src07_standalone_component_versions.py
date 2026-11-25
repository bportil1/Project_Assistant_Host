"""SRC-07: standalone repositories are not Git submodules of PAH."""
from pathlib import Path
import subprocess

import pytest

from pah.component_versions import ComponentVersionError, ComponentVersionManager, component_version_snapshot
from pah.components import GitComponent
from pah.lifecycle import _editable_install_command


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def standalone_fixture(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    source = tmp_path / "component"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "local@example.invalid")
    git(source, "config", "user.name", "Local")
    (source / "README.md").write_text("one\n")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "one")
    git(source, "remote", "add", "origin", str(remote))
    git(source, "push", "-u", "origin", "main")
    host = tmp_path / "host"
    host.mkdir()
    git(host, "init", "-b", "main")
    git(host, "config", "user.email", "local@example.invalid")
    git(host, "config", "user.name", "Local")
    (host / "README.md").write_text("host\n")
    git(host, "add", "README.md")
    git(host, "commit", "-m", "host")
    component = GitComponent(key="component", label="Component", path="../component")
    return host, source, remote, component


def test_clean_standalone_repository_is_current_and_has_no_parent_pin(tmp_path):
    host, _, _, component = standalone_fixture(tmp_path)
    item = component_version_snapshot(host, component)
    assert item["status"] == "current"
    assert item["pinned"] is None
    assert item["checked_out"] == item["remote_head"]
    assert item["recordable"] is False
    assert item["restorable"] is False
    summary = ComponentVersionManager(host, components=(component,)).snapshot()["summary"]
    assert summary["actionable"] == 0


def test_standalone_remote_behind_and_ahead_are_reported(tmp_path):
    host, source, remote, component = standalone_fixture(tmp_path)
    upstream = tmp_path / "upstream"
    subprocess.run(["git", "clone", str(remote), str(upstream)], check=True, capture_output=True)
    git(upstream, "checkout", "main")
    git(upstream, "config", "user.email", "local@example.invalid")
    git(upstream, "config", "user.name", "Local")
    (upstream / "README.md").write_text("two\n")
    git(upstream, "add", "README.md")
    git(upstream, "commit", "-m", "two")
    git(upstream, "push", "origin", "main")
    git(source, "fetch", "origin", "main")
    assert component_version_snapshot(host, component)["status"] == "update_available"
    (source / "local.txt").write_text("new\n")
    git(source, "add", "local.txt")
    git(source, "commit", "-m", "local")
    assert component_version_snapshot(host, component)["status"] == "diverged"
    # Neither a snapshot nor an update-eligibility check mutates the checkout.
    assert (source / "local.txt").read_text() == "new\n"


def test_standalone_panel_has_no_gitlink_controls_or_pinned_column():
    root = Path(__file__).resolve().parents[1]
    html = (root / "pah/web/templates/index.html").read_text()
    js = (root / "pah/web/static/pah.js").read_text()
    assert "<th>PAH pinned</th>" not in html
    for unused in ("componentVersionsRestore", "componentVersionsRecord", "componentVersionsCommitMessage"):
        assert unused not in html
        assert unused not in js
    assert "/api/components/update" in js
    assert "/api/components/fetch" in js
    assert "standalone repositories" in html.lower()


def test_version_dialog_selected_install_reuses_prepared_venv():
    command = _editable_install_command(Path("/tmp/pah-venv/bin/python"), "../ML_Lab[ui]")
    assert "--no-build-isolation" in command
    assert command[-1] == "../ML_Lab[ui]"


def test_legacy_gitlink_actions_refuse_standalone_checkouts_without_modification(tmp_path):
    host, source, _, component = standalone_fixture(tmp_path)
    manager = ComponentVersionManager(host, components=(component,))
    before = git(source, "rev-parse", "HEAD")
    with pytest.raises(ComponentVersionError, match="standalone repository"):
        manager.restore_pinned([component.key])
    with pytest.raises(ComponentVersionError, match="standalone repository"):
        manager.record([component.key], message="not relevant")
    assert git(source, "rev-parse", "HEAD") == before
