from __future__ import annotations

from pathlib import Path
import subprocess

from pah.component_versions import ComponentVersionManager, component_version_snapshot
from pah.components import GitComponent


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def _configure(path: Path) -> None:
    _git(path, "config", "user.email", "tests@example.com")
    _git(path, "config", "user.name", "PAH Tests")


def _host_with_submodule(tmp_path: Path) -> tuple[Path, Path, Path, GitComponent, str, str]:
    remote = tmp_path / "module.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _configure(seed)
    (seed / "value.txt").write_text("one\n", encoding="utf-8")
    _git(seed, "add", "value.txt")
    _git(seed, "commit", "-m", "one")
    first = _git(seed, "rev-parse", "HEAD")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-u", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

    host = tmp_path / "host"
    host.mkdir()
    _git(host, "init", "-b", "main")
    _configure(host)
    (host / "README.md").write_text("host\n", encoding="utf-8")
    _git(host, "add", "README.md")
    _git(host, "commit", "-m", "host")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", str(remote), "modules/demo"],
        cwd=host,
        check=True,
        text=True,
        capture_output=True,
    )
    _git(host, "commit", "-am", "pin demo")
    module = host / "modules" / "demo"
    _configure(module)

    collaborator = tmp_path / "collaborator"
    subprocess.run(["git", "clone", str(remote), str(collaborator)], check=True, text=True, capture_output=True)
    _configure(collaborator)
    (collaborator / "value.txt").write_text("two\n", encoding="utf-8")
    _git(collaborator, "add", "value.txt")
    _git(collaborator, "commit", "-m", "two")
    _git(collaborator, "push")
    latest = _git(collaborator, "rev-parse", "HEAD")

    component = GitComponent(key="demo", label="Demo", path="modules/demo")
    return host, module, remote, component, first, latest


def test_component_status_distinguishes_pinned_checkout_and_explicit_remote_fetch(tmp_path: Path):
    host, module, _, component, first, latest = _host_with_submodule(tmp_path)
    manager = ComponentVersionManager(host, components=(component,))

    before = manager.snapshot()["components"][0]
    assert before["pinned"] == first
    assert before["checked_out"] == first
    # Remote tracking refs are intentionally not refreshed by a local snapshot.
    assert before["remote_head"] == first
    assert before["status"] == "current"
    assert manager.snapshot()["last_fetch_at"] is None

    fetched = manager.fetch(["demo"])
    item = fetched["components"][0]
    assert item["remote_head"] == latest
    assert item["status"] == "update_available"
    assert item["behind"] == 1
    assert fetched["last_fetch_at"]


def test_update_then_record_turns_checked_out_revision_into_new_parent_pin(tmp_path: Path):
    host, module, _, component, first, latest = _host_with_submodule(tmp_path)
    manager = ComponentVersionManager(host, components=(component,))
    manager.fetch(["demo"])

    updated = manager.update(["demo"], run_tests=False)
    item = updated["components"][0]
    assert _git(module, "rev-parse", "HEAD") == latest
    assert item["checked_out"] == latest
    assert item["pinned"] == first
    assert item["status"] == "pinned_mismatch"
    assert item["recordable"] is True

    recorded = manager.record(["demo"], message="Record demo component")
    item = recorded["components"][0]
    assert item["pinned"] == latest
    assert item["checked_out"] == latest
    assert item["status"] == "current"
    assert recorded["commits"]
    assert _git(host, "log", "-1", "--pretty=%s") == "Record demo component"


def test_restore_pinned_reverts_unrecorded_component_update(tmp_path: Path):
    host, module, _, component, first, latest = _host_with_submodule(tmp_path)
    manager = ComponentVersionManager(host, components=(component,))
    manager.fetch(["demo"])
    manager.update(["demo"], run_tests=False)
    assert _git(module, "rev-parse", "HEAD") == latest

    restored = manager.restore_pinned(["demo"])
    item = restored["components"][0]
    assert _git(module, "rev-parse", "HEAD") == first
    assert item["checked_out"] == first
    assert item["pinned"] == first
    assert item["status"] == "update_available"


def test_dirty_component_is_reported_without_being_modified(tmp_path: Path):
    host, module, _, component, _, _ = _host_with_submodule(tmp_path)
    (module / "local.txt").write_text("private local work\n", encoding="utf-8")

    item = component_version_snapshot(host, component)
    assert item["status"] == "modified_worktree"
    assert item["dirty"] is True
    assert item["recordable"] is False


def test_component_version_panel_and_routes_are_exposed():
    root = Path(__file__).resolve().parents[1]
    template = (root / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    script = (root / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    app_source = (root / "pah" / "app.py").read_text(encoding="utf-8")

    assert 'id="toolsComponentVersions"' in template
    assert 'id="componentVersionsDialog"' in template
    assert 'id="componentVersionsRows"' in template
    assert "/api/components/status" in script
    assert "/api/components/fetch" in script
    assert "/api/components/update" in script
    assert "/api/components/restore-pinned" in script
    assert "/api/components/test" in script
    assert "/api/components/record" in script
    assert '@app.get("/api/components/status")' in app_source
    assert '@app.post("/api/components/update")' in app_source


def test_doctor_reports_managed_component_revisions_without_fetching(tmp_path: Path):
    from pah.lifecycle import doctor_report

    report = doctor_report(tmp_path)
    assert "component_versions" in report
    assert isinstance(report["component_versions"], list)


def _host_with_nested_submodule(tmp_path: Path):
    child_remote = tmp_path / "child.git"
    parent_remote = tmp_path / "parent.git"
    subprocess.run(["git", "init", "--bare", str(child_remote)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "--bare", str(parent_remote)], check=True, capture_output=True, text=True)

    child_seed = tmp_path / "child-seed"
    child_seed.mkdir()
    _git(child_seed, "init", "-b", "main")
    _configure(child_seed)
    (child_seed / "child.txt").write_text("one\n", encoding="utf-8")
    _git(child_seed, "add", "child.txt")
    _git(child_seed, "commit", "-m", "child one")
    child_first = _git(child_seed, "rev-parse", "HEAD")
    _git(child_seed, "remote", "add", "origin", str(child_remote))
    _git(child_seed, "push", "-u", "origin", "main")
    _git(child_remote, "symbolic-ref", "HEAD", "refs/heads/main")

    parent_seed = tmp_path / "parent-seed"
    parent_seed.mkdir()
    _git(parent_seed, "init", "-b", "main")
    _configure(parent_seed)
    (parent_seed / "parent.txt").write_text("parent\n", encoding="utf-8")
    _git(parent_seed, "add", "parent.txt")
    _git(parent_seed, "commit", "-m", "parent base")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", str(child_remote), "modules/child"],
        cwd=parent_seed,
        check=True,
        text=True,
        capture_output=True,
    )
    _git(parent_seed, "commit", "-am", "pin child")
    parent_first = _git(parent_seed, "rev-parse", "HEAD")
    _git(parent_seed, "remote", "add", "origin", str(parent_remote))
    _git(parent_seed, "push", "-u", "origin", "main")
    _git(parent_remote, "symbolic-ref", "HEAD", "refs/heads/main")

    host = tmp_path / "host-nested"
    host.mkdir()
    _git(host, "init", "-b", "main")
    _configure(host)
    (host / "README.md").write_text("host\n", encoding="utf-8")
    _git(host, "add", "README.md")
    _git(host, "commit", "-m", "host")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", str(parent_remote), "modules/parent"],
        cwd=host,
        check=True,
        text=True,
        capture_output=True,
    )
    # Clone nested child into the parent checkout before recording host.
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "update", "--init", "--recursive"],
        cwd=host,
        check=True,
        text=True,
        capture_output=True,
    )
    _git(host, "commit", "-am", "pin parent")
    parent_checkout = host / "modules" / "parent"
    child_checkout = parent_checkout / "modules" / "child"
    _configure(parent_checkout)
    _configure(child_checkout)

    collaborator = tmp_path / "child-collaborator"
    subprocess.run(["git", "clone", str(child_remote), str(collaborator)], check=True, text=True, capture_output=True)
    _configure(collaborator)
    (collaborator / "child.txt").write_text("two\n", encoding="utf-8")
    _git(collaborator, "add", "child.txt")
    _git(collaborator, "commit", "-m", "child two")
    _git(collaborator, "push")
    child_latest = _git(collaborator, "rev-parse", "HEAD")

    parent_component = GitComponent(key="parent", label="Parent", path="modules/parent")
    child_component = GitComponent(key="child", label="Child", path="modules/parent/modules/child")
    return host, parent_checkout, child_checkout, parent_component, child_component, parent_first, child_first, child_latest


def test_nested_update_auto_includes_parent_and_record_commits_parent_then_host(tmp_path: Path):
    host, parent, child, parent_component, child_component, parent_first, child_first, child_latest = _host_with_nested_submodule(tmp_path)
    manager = ComponentVersionManager(host, components=(parent_component, child_component))

    manager.fetch(["child"])
    updated = manager.update(["child"], run_tests=False)
    assert updated["requested_keys"] == ["child"]
    assert updated["expanded_keys"] == ["parent", "child"]
    assert _git(child, "rev-parse", "HEAD") == child_latest
    assert component_version_snapshot(host, child_component)["pinned"] == child_first

    recorded = manager.record(["child"], message="Record nested versions")
    assert len(recorded["commits"]) == 2
    parent_after = _git(parent, "rev-parse", "HEAD")
    assert parent_after != parent_first
    assert component_version_snapshot(host, child_component)["pinned"] == child_latest
    assert component_version_snapshot(host, parent_component)["pinned"] == parent_after
