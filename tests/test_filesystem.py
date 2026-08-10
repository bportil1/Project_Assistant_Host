from pathlib import Path

import pytest

from pah.core.filesystem import FileSystemError, FileSystemService


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
