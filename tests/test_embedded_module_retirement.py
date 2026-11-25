"""Safety regression: source ownership never destroys dirty embedded worktrees."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "retire_embedded_modules.py"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


@pytest.fixture
def legacy_host(tmp_path: Path) -> Path:
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    (host / "pah").mkdir()
    (host / "pah" / "components.py").write_text("# owner\n", encoding="utf8")
    (host / ".gitignore").write_text("/modules/\n", encoding="utf8")
    (host / "scripts").mkdir()
    shutil.copy2(SCRIPT, host / "scripts" / "retire_embedded_modules.py")
    git(host, "init", "-q")
    git(host, "config", "user.email", "test@example.invalid")
    git(host, "config", "user.name", "Test")
    git(host, "add", ".gitignore", "pah", "scripts")
    git(host, "commit", "-qm", "initial")
    # A synthetic valid gitlink is sufficient for testing index semantics;
    # actual dirty/untracked files exercise the recovery behavior separately.
    oid = git(host, "rev-parse", "HEAD")
    git(host, "update-index", "--add", "--cacheinfo", f"160000,{oid},modules/code_analyzer")
    git(host, "commit", "-qm", "embedded gitlink")
    target = host / "modules" / "code_analyzer"
    target.mkdir(parents=True)
    (target / "source.py").write_text("original\nlocal uncommitted change\n", encoding="utf8")
    (target / "new-untracked.dat").write_bytes(b"valuable local work\n")
    (host / "modules" / "hsqa_dbn").mkdir()
    (host / "modules" / "hsqa_dbn" / "scratch.log").write_text("retain\n", encoding="utf8")
    return host


def run_script(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(root / "scripts" / "retire_embedded_modules.py"), *args],
                          cwd=root, text=True, capture_output=True)


def test_dry_run_is_non_destructive(legacy_host: Path):
    before = git(legacy_host, "ls-files", "--stage", "--", "modules")
    result = run_script(legacy_host)
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert git(legacy_host, "ls-files", "--stage", "--", "modules") == before
    assert (legacy_host / "modules/code_analyzer/new-untracked.dat").exists()
    assert not list(legacy_host.parent.glob("*_embedded_module_recovery_*"))


def test_explicit_retirement_backs_up_all_content_and_untracks_only_gitlinks(legacy_host: Path):
    outside = legacy_host.parent / "Code_Repository_Cataloguer"
    outside.mkdir()
    (outside / "separate.py").write_text("do not touch", encoding="utf8")
    result = run_script(legacy_host, "--apply")
    assert result.returncode == 0, result.stderr
    assert git(legacy_host, "ls-files", "--stage", "--", "modules") == ""
    assert git(legacy_host, "diff", "--cached", "--name-only") == "modules/code_analyzer"
    assert list((legacy_host / "modules").iterdir()) == []
    copies = list(legacy_host.parent.glob("*_embedded_module_recovery_*"))
    assert len(copies) == 1
    recovered = copies[0]
    assert (recovered / "modules/code_analyzer/new-untracked.dat").read_bytes() == b"valuable local work\n"
    assert "local uncommitted change" in (recovered / "modules/code_analyzer/source.py").read_text()
    assert (recovered / "modules/hsqa_dbn/scratch.log").read_text() == "retain\n"
    assert (outside / "separate.py").read_text() == "do not touch"
    assert "modules/code_analyzer" not in git(legacy_host, "status", "--porcelain", "--untracked-files=all").split("?? ")
    # Repeated applications are read-only no-ops, not destructive.
    second = run_script(legacy_host, "--apply")
    assert second.returncode == 0
    assert "Already retired" in second.stdout


def test_apply_rejects_unexpected_tracked_file(legacy_host: Path):
    git(legacy_host, "add", "-f", "--", "modules/hsqa_dbn/scratch.log")
    result = run_script(legacy_host, "--apply")
    assert result.returncode != 0
    assert "Unexpected tracked module files" in result.stderr
    assert (legacy_host / "modules/hsqa_dbn/scratch.log").exists()
    assert git(legacy_host, "ls-files", "--stage", "--", "modules")


def test_apply_refuses_old_gitmodules_until_patch_is_applied(legacy_host: Path):
    (legacy_host / ".gitmodules").write_text('[submodule "modules/code_analyzer"]\n')
    result = run_script(legacy_host, "--apply")
    assert result.returncode != 0
    assert ".gitmodules still exists" in result.stderr
    assert (legacy_host / "modules/code_analyzer/new-untracked.dat").exists()


def test_host_patch_has_no_owned_gitlinks_or_readd_scripts():
    assert not (ROOT / ".gitmodules").exists()
    assert "/modules/" in (ROOT / ".gitignore").read_text()
    assert not (ROOT / "scripts/add_submodules.sh").exists()
    assert not (ROOT / "scripts/add_ml_lab_submodule.sh").exists()


def test_standalone_dependency_repair_refuses_host_embedded_module_paths():
    """The old pyPIQUE pin helper cannot make a hidden PAH/modules edit."""
    helper = ROOT / "scripts" / "repair_pypique_shared_dependency.py"
    result = subprocess.run(
        [sys.executable, str(helper), "--pypique", str(ROOT / "modules" / "pypique"), "--apply"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Refusing to modify a path inside PAH" in result.stderr
