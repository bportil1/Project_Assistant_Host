from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pah.core.git import GitError, LocalGitService


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git executable is required")


def git(project: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=project, text=True, capture_output=True, check=True)
    return proc.stdout.strip()


def configure_identity(project: Path) -> None:
    git(project, "config", "user.name", "PAH Test")
    git(project, "config", "user.email", "pah-test@example.invalid")


def make_bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], text=True, capture_output=True, check=True)
    return remote


def test_git_service_is_opt_in_local_first_and_remote_permission_resets(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)

    status = service.status()
    assert status["git_available"] is True
    assert status["is_repository"] is False
    assert status["local_only"] is True
    assert status["remote_enabled"] is False
    assert not (project / ".git").exists()

    service.init()
    remote = make_bare_remote(tmp_path)
    service.add_remote("origin", str(remote))
    assert service.status()["remotes"][0]["name"] == "origin"

    with pytest.raises(GitError, match="Manual Remote"):
        service.fetch("origin")
    with pytest.raises(GitError, match="Manual Remote"):
        service.push("origin")
    with pytest.raises(GitError, match="Manual Remote"):
        service.clone(str(remote), tmp_path / "clone")
    with pytest.raises(GitError, match="Manual Remote"):
        service.update_submodules("recorded")

    enabled = service.set_connectivity("manual_remote")
    assert enabled["remote_enabled"] is True
    assert enabled["local_only"] is False

    other = tmp_path / "private-project"
    other.mkdir()
    service.bind(other)
    assert service.connectivity_mode == "local_only"
    assert service.status()["local_only"] is True


def test_local_git_init_stage_commit_history_and_branch_switch(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)

    initialized = service.init()
    assert initialized["is_repository"] is True
    assert (project / ".git").exists()
    assert git(project, "remote") == ""

    configure_identity(project)
    (project / "notes.txt").write_text("first\n", encoding="utf-8")

    status = service.status()
    change = next(item for item in status["changes"] if item["path"] == "notes.txt")
    assert change["untracked"] is True

    staged = service.stage(["notes.txt"])
    change = next(item for item in staged["changes"] if item["path"] == "notes.txt")
    assert change["staged"] is True
    assert "first" in service.diff(path="notes.txt", staged=True)["diff"]

    committed = service.commit("Add notes")
    assert committed["changes"] == []
    assert service.history()[0]["subject"] == "Add notes"

    current = service.branches()["current"]
    git(project, "branch", "alternate")
    switched = service.switch_branch("alternate")
    assert switched["branch"] == "alternate"
    if current:
        service.switch_branch(current)


def test_local_git_unstage_before_first_commit(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)
    service.init()
    (project / "draft.txt").write_text("draft\n", encoding="utf-8")
    service.stage(["draft.txt"])
    status = service.unstage(["draft.txt"])
    item = next(row for row in status["changes"] if row["path"] == "draft.txt")
    assert item["untracked"] is True
    assert item["staged"] is False


def test_remote_configuration_is_local_and_manual_remote_sync_works_with_local_bare_repo(tmp_path: Path):
    remote = make_bare_remote(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)
    service.init()
    configure_identity(project)

    (project / "README.md").write_text("one\n", encoding="utf-8")
    service.stage(["README.md"])
    service.commit("Initial")

    configured = service.add_remote("origin", str(remote))
    assert configured["local_only"] is True
    assert git(project, "remote") == "origin"
    assert configured["remotes"][0]["fetch_url"] == str(remote)

    service.set_connectivity("manual_remote")
    pushed = service.push("origin", set_upstream=True)
    assert pushed["tracking"]["upstream"].startswith("origin/")
    assert pushed["tracking"]["ahead"] == 0
    assert pushed["tracking"]["behind"] == 0

    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], text=True, capture_output=True, check=True)
    configure_identity(other)
    (other / "README.md").write_text("two\n", encoding="utf-8")
    git(other, "add", "README.md")
    git(other, "commit", "-m", "Remote change")
    git(other, "push")

    fetched = service.fetch("origin")
    assert fetched["tracking"]["behind"] == 1
    pulled = service.pull("origin")
    assert pulled["tracking"]["behind"] == 0
    assert (project / "README.md").read_text(encoding="utf-8") == "two\n"

    clone_dest = tmp_path / "service-clone"
    clone_result = service.clone(str(remote), clone_dest)
    assert clone_result["destination"] == str(clone_dest.resolve())
    assert (clone_dest / ".git").exists()

    removed = service.remove_remote("origin")
    assert removed["remotes"] == []


def test_remote_pull_is_fast_forward_only_and_blocked_with_local_changes(tmp_path: Path):
    remote = make_bare_remote(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)
    service.init()
    configure_identity(project)
    (project / "file.txt").write_text("one\n", encoding="utf-8")
    service.stage(["file.txt"])
    service.commit("Initial")
    service.add_remote("origin", str(remote))
    service.set_connectivity("manual_remote")
    service.push("origin", set_upstream=True)

    (project / "file.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(GitError, match="working tree has local changes"):
        service.pull("origin")


def test_git_rejects_unknown_local_branch_empty_commit_and_bad_remote_inputs(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)
    service.init()

    with pytest.raises(GitError, match="existing local branches"):
        service.switch_branch("does-not-exist")
    with pytest.raises(GitError, match="cannot be empty"):
        service.commit("   ")
    with pytest.raises(GitError, match="Remote name"):
        service.add_remote("bad remote", "example")
    with pytest.raises(GitError, match="cannot begin"):
        service.add_remote("origin", "--upload-pack=oops")


def test_remote_comparison_is_local_and_reports_cached_relation(tmp_path: Path):
    remote = make_bare_remote(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service = LocalGitService(project)
    service.init()
    configure_identity(project)
    (project / "paper.tex").write_text("one\n", encoding="utf-8")
    service.stage(["paper.tex"])
    service.commit("Initial")
    service.add_remote("overleaf", str(remote))

    before = service.remote_comparison("overleaf")
    assert before["state"] == "not_fetched"

    service.set_connectivity("manual_remote")
    service.push("overleaf", set_upstream=True)
    service.fetch("overleaf")
    current = service.remote_comparison("overleaf")
    assert current["state"] == "up_to_date"
    assert current["ahead"] == 0
    assert current["behind"] == 0

    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], text=True, capture_output=True, check=True)
    configure_identity(other)
    (other / "paper.tex").write_text("two\n", encoding="utf-8")
    git(other, "add", "paper.tex")
    git(other, "commit", "-m", "Remote edit")
    git(other, "push")

    service.fetch("overleaf")
    behind = service.remote_comparison("overleaf")
    assert behind["state"] == "behind"
    assert behind["behind"] == 1


def test_conflict_path_detection_recognizes_unmerged_statuses():
    changes = [
        {"path": "paper.tex", "status": "UU", "index_status": "U", "worktree_status": "U"},
        {"path": "notes.txt", "status": " M", "index_status": " ", "worktree_status": "M"},
    ]
    assert LocalGitService._conflict_paths(changes) == ["paper.tex"]
