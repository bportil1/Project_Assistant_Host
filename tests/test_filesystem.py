from pathlib import Path

import pytest

from pah.core.filesystem import FileConflictError, FileSystemError, FileSystemService


def test_file_crud_and_path_safety(tmp_path: Path):
    fs = FileSystemService(tmp_path)
    fs.create("src", "dir")
    fs.create("src/a.py", "file")
    fs.write_text("src/a.py", "print('hello')\n")
    assert fs.read_text("src/a.py")["content"] == "print('hello')\n"
    renamed = fs.rename("src/a.py", "b.py")
    assert renamed["path"] == "src/b.py"
    moved = fs.move("src/b.py", "b.py")
    assert moved["path"] == "b.py"
    fs.delete("b.py")
    assert not (tmp_path / "b.py").exists()
    with pytest.raises(FileSystemError):
        fs.resolve("../outside")


def test_tree_ignores_dot_git(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / "main.py").write_text("pass\n")
    tree = FileSystemService(tmp_path).tree()
    assert [item["name"] for item in tree] == ["main.py"]


def test_list_directory_is_shallow_and_keeps_all_root_entries(tmp_path: Path):
    # A very large nested directory must not prevent later root entries from appearing.
    huge = tmp_path / "results"
    huge.mkdir()
    for index in range(50):
        sub = huge / f"trial_{index}"
        sub.mkdir()
        for inner in range(20):
            (sub / f"value_{inner}.txt").write_text("x")
    (tmp_path / "utils").mkdir()
    (tmp_path / "main.py").write_text("pass\n")
    (tmp_path / "run_hsqa.slurm").write_text("#!/bin/bash\n")

    fs = FileSystemService(tmp_path)
    root_names = [item["name"] for item in fs.list_directory()]

    assert "results" in root_names
    assert "utils" in root_names
    assert "main.py" in root_names
    assert "run_hsqa.slurm" in root_names
    # Shallow listing should not recursively populate nested children.
    results_item = next(item for item in fs.list_directory() if item["name"] == "results")
    assert "children" not in results_item


def test_list_directory_supports_nested_paths_and_hides_git(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("pass\n")
    (src / ".git").mkdir()

    items = FileSystemService(tmp_path).list_directory("src")
    assert [item["name"] for item in items] == ["a.py"]


def test_editor_save_rejects_stale_revision_without_clobbering_external_change(tmp_path: Path):
    fs = FileSystemService(tmp_path)
    path = tmp_path / "paper.md"
    path.write_bytes(b"original\r\n")
    original = fs.read_text("paper.md")
    path.write_text("from second instance\n", encoding="utf-8")

    with pytest.raises(FileConflictError, match="changed on disk"):
        fs.write_text("paper.md", "first instance edit\n", expected_sha256=original["source_sha256"])
    assert path.read_text() == "from second instance\n"


def test_editor_save_returns_new_revision_for_successive_saves(tmp_path: Path):
    fs = FileSystemService(tmp_path)
    (tmp_path / "notes.txt").write_text("one\n")
    first = fs.read_text("notes.txt")
    second = fs.write_text("notes.txt", "two\n", expected_sha256=first["source_sha256"])
    third = fs.write_text("notes.txt", "three\n", expected_sha256=second["source_sha256"])
    assert third["source_sha256"] == fs.read_text("notes.txt")["source_sha256"]
    assert not list(tmp_path.glob(".notes.txt.pah-*.tmp"))


def test_write_conflict_is_consistent_across_independent_services(tmp_path: Path):
    (tmp_path / "model.json").write_text('{"version":1}')
    a, b = FileSystemService(tmp_path), FileSystemService(tmp_path)
    a_version = a.read_text("model.json")["source_sha256"]
    b_version = b.read_text("model.json")["source_sha256"]
    a.write_text("model.json", '{"version":2}', expected_sha256=a_version)
    with pytest.raises(FileConflictError):
        b.write_text("model.json", '{"version":3}', expected_sha256=b_version)
