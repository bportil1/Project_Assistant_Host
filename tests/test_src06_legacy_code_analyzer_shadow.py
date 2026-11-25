"""SRC-06: no host-owned Code Analyzer namespace may eclipse the standalone package."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from pah import lifecycle


def test_untracked_legacy_code_analyzer_is_preserved_in_sibling_recovery(tmp_path):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    legacy = host / "code_analyzer"
    (legacy / "language_providers").mkdir(parents=True)
    (legacy / "language_providers" / "local.txt").write_text("user work", encoding="utf8")
    (legacy / "__pycache__").mkdir()
    (legacy / "__pycache__" / "api.pyc").write_bytes(b"cache")

    preserved = lifecycle.preserve_legacy_code_analyzer_shadow(host)

    assert preserved is not None
    assert preserved.parent == tmp_path / "Project_Assistant_Host_legacy_import_recovery"
    assert (preserved / "language_providers/local.txt").read_text() == "user work"
    assert (preserved / "__pycache__/api.pyc").read_bytes() == b"cache"
    assert not legacy.exists()
    assert lifecycle.preserve_legacy_code_analyzer_shadow(host) is None


def test_an_unrelated_legacy_path_is_not_overwritten(tmp_path):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    legacy = host / "code_analyzer"
    legacy.mkdir()
    recovery = tmp_path / "Project_Assistant_Host_legacy_import_recovery"
    (recovery / "code_analyzer_20261125T000000Z-000").mkdir(parents=True)
    destination = lifecycle.preserve_legacy_code_analyzer_shadow(host)
    assert destination is not None and destination.name.endswith("-000")
    assert (recovery / "code_analyzer_20261125T000000Z-000").exists()


def test_symlink_and_regular_file_are_refused(tmp_path):
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    original = tmp_path / "important"
    original.mkdir()
    shadow = host / "code_analyzer"
    shadow.symlink_to(original, target_is_directory=True)
    with pytest.raises(lifecycle.LifecycleError, match="symlink"):
        lifecycle.preserve_legacy_code_analyzer_shadow(host)
    assert shadow.is_symlink() and original.is_dir()
    shadow.unlink()
    shadow.write_text("important", encoding="utf8")
    with pytest.raises(lifecycle.LifecycleError, match="non-directory"):
        lifecycle.preserve_legacy_code_analyzer_shadow(host)
    assert shadow.read_text() == "important"


def test_nested_git_checkout_is_not_relocated(tmp_path):
    host = tmp_path / "Project_Assistant_Host"
    (host / "code_analyzer" / ".git").mkdir(parents=True)
    with pytest.raises(lifecycle.LifecycleError, match="Git checkout"):
        lifecycle.preserve_legacy_code_analyzer_shadow(host)
    assert (host / "code_analyzer" / ".git").is_dir()


def test_tracked_host_files_block_relocation(tmp_path):
    import subprocess
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    subprocess.run(["git", "init", "-q", str(host)], check=True)
    legacy = host / "code_analyzer"
    legacy.mkdir()
    (legacy / "legacy.py").write_text("tracked", encoding="utf8")
    subprocess.run(["git", "add", "-f", "code_analyzer/legacy.py"], cwd=host, check=True)
    with pytest.raises(lifecycle.LifecycleError, match="tracked"):
        lifecycle.preserve_legacy_code_analyzer_shadow(host)
    assert (legacy / "legacy.py").read_text() == "tracked"


def test_git_apply_deleted_host_files_allow_safe_untracked_migration(tmp_path):
    """Deletion in working tree may precede staging in Git's index."""
    import subprocess
    host = tmp_path / "Project_Assistant_Host"
    host.mkdir()
    subprocess.run(["git", "init", "-q", str(host)], check=True)
    legacy = host / "code_analyzer"
    legacy.mkdir()
    historical = legacy / "old_provider.py"
    historical.write_text("tracked", encoding="utf8")
    subprocess.run(["git", "add", "-f", "code_analyzer/old_provider.py"], cwd=host, check=True)
    historical.unlink()  # git apply deleted the old file, but index is not staged
    (legacy / "user_data.txt").write_text("preserve me", encoding="utf8")

    backup = lifecycle.preserve_legacy_code_analyzer_shadow(host)
    assert backup is not None
    assert (backup / "user_data.txt").read_text() == "preserve me"
    assert not legacy.exists()
    # The historical deletion remains in Git's index, for staging by the owner.
    index = subprocess.run(["git", "ls-files", "--", "code_analyzer"],
                           cwd=host, text=True, capture_output=True, check=True)
    assert "code_analyzer/old_provider.py" in index.stdout


def test_setup_moves_import_shadow_before_code_analyzer_install(tmp_path, monkeypatch):
    root = tmp_path / "Project_Assistant_Host"
    root.mkdir()
    (root / "code_analyzer").mkdir()
    (root / "code_analyzer" / "legacy.txt").write_text("kept", encoding="utf8")
    (root / "pyproject.toml").write_text('[project]\nname="host"\n', encoding="utf8")
    components = (lifecycle.PYTHON_COMPONENTS[0], lifecycle.PYTHON_COMPONENTS[1])
    for component in components[1:]:
        source = (root / component.path).resolve()
        source.mkdir(parents=True)
        (source / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf8")
    monkeypatch.setattr(lifecycle, "PYTHON_COMPONENTS", components)
    monkeypatch.setattr(lifecycle, "declared_constraints", lambda *_: ())
    monkeypatch.setattr(lifecycle, "bootstrap_pah_shared", lambda *_a, **_k: None)
    monkeypatch.setattr(lifecycle, "_code_analyzer_api_status", lambda *_a, **_k: (True, None))
    calls = []

    def fake_run(args, **kwargs):
        args = [str(value) for value in args]
        if "-e" in args and "Code_Repository_Cataloguer" in args[-1]:
            assert not (root / "code_analyzer").exists()
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(lifecycle, "_run", fake_run)
    lifecycle.install_python_components(root, Path("/fake/venv/bin/python"))
    assert not (root / "code_analyzer").exists()
    assert any("Code_Repository_Cataloguer" in cmd[-1] for cmd in calls)
    assert list((tmp_path / "Project_Assistant_Host_legacy_import_recovery").rglob("legacy.txt"))


def test_host_gitignore_prevents_reintroducing_shadow():
    root = Path(__file__).resolve().parents[1]
    assert "/code_analyzer/" in (root / ".gitignore").read_text(encoding="utf8")
