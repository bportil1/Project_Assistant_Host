from __future__ import annotations

import hashlib
import os
from pathlib import Path
import pytest

from pah.labs.source_evidence import SourceEvidenceError, SourceEvidenceLocator, read_source_evidence


def locator(path: str, content: bytes, **updates):
    values = dict(producer_module="pypique", finding_id="sat-001", project_id="project-a",
                  relative_path=path, start_line=2, end_line=3,
                  source_sha256=hashlib.sha256(content).hexdigest())
    values.update(updates)
    return SourceEvidenceLocator.from_mapping(values)


def test_exact_read_only_excerpt(tmp_path):
    data = b"alpha\nbeta\ngamma\ndelta\n"
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    source.write_bytes(data)
    result = read_source_evidence(repository_root=tmp_path, active_project_id="project-a",
                                  locator=locator("src/example.py", data))
    assert result["excerpt"] == "beta\ngamma"
    assert result["mode"] == "read_only"
    assert source.read_bytes() == data


def test_rejects_stale_and_project_mismatch(tmp_path):
    source = tmp_path / "example.py"
    source.write_bytes(b"first\nsecond\nthird\n")
    ref = locator("example.py", source.read_bytes())
    with pytest.raises(SourceEvidenceError, match="different project"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-b", locator=ref)
    source.write_bytes(b"first\nchanged\nthird\n")
    with pytest.raises(SourceEvidenceError, match="stale"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-a", locator=ref)


@pytest.mark.parametrize("path", ["../secret.py", "/etc/passwd", "x/../y", "x//y", "C:/file", "x\\y"])
def test_rejects_invalid_paths(path):
    with pytest.raises(SourceEvidenceError):
        locator(path, b"a")


def test_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_bytes(b"one\ntwo\nthree\n")
    (root / "linked.py").symlink_to(outside)
    with pytest.raises(SourceEvidenceError, match="escapes"):
        read_source_evidence(repository_root=root, active_project_id="project-a",
                             locator=locator("linked.py", outside.read_bytes()))


def test_rejects_invalid_span_and_unsupported_producer(tmp_path):
    with pytest.raises(SourceEvidenceError, match="span"):
        locator("example.py", b"a", start_line=1, end_line=82)
    with pytest.raises(SourceEvidenceError, match="pyPIQUE"):
        locator("example.py", b"a", producer_module="other")
    with pytest.raises(SourceEvidenceError, match="start_line"):
        locator("example.py", b"a", start_line=True)


def test_missing_line_and_binary_source(tmp_path):
    source = tmp_path / "example.py"
    source.write_bytes(b"one\ntwo\n")
    with pytest.raises(SourceEvidenceError, match="line range"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-a",
                             locator=locator("example.py", source.read_bytes()))
    source.write_bytes(b"one\x00\ntwo\nthree\n")
    with pytest.raises(SourceEvidenceError, match="Binary"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-a",
                             locator=locator("example.py", source.read_bytes()))


def test_rejects_internal_symlink_even_if_target_inside_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "source.py").write_text("one\ntwo\nthree\n")
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(SourceEvidenceError, match="unavailable|outside"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-a",
                             locator=locator("link/source.py", (real / "source.py").read_bytes()))


def test_rejects_replaced_leaf_symlink_at_open(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    original = root / "file.py"
    content = b"one\ntwo\nthree\n"
    original.write_bytes(content)
    outside = tmp_path / "outside.py"
    outside.write_bytes(content)
    real_open = os.open
    swapped = False

    def swap_before_leaf_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "file.py" and "dir_fd" in kwargs and not swapped:
            swapped = True
            original.unlink()
            original.symlink_to(outside)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_before_leaf_open)
    with pytest.raises(SourceEvidenceError, match="unavailable|outside"):
        read_source_evidence(repository_root=root, active_project_id="project-a",
                             locator=locator("file.py", content))
    assert swapped


def test_rejects_directory_as_source(tmp_path):
    (tmp_path / "source.py").mkdir()
    with pytest.raises(SourceEvidenceError, match="regular file|unavailable"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-a",
                             locator=locator("source.py", b"whatever"))


def test_rejects_in_place_modification_during_read(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    content = b"one\ntwo\nthree\n"
    source.write_bytes(content)
    real_read = os.read
    changed = False

    def mutate_after_first_read(fd, count):
        nonlocal changed
        result = real_read(fd, count)
        if not changed and result:
            changed = True
            source.write_bytes(b"altered\ncontent\n")
        return result

    monkeypatch.setattr(os, "read", mutate_after_first_read)
    with pytest.raises(SourceEvidenceError, match="changed during inspection"):
        read_source_evidence(repository_root=tmp_path, active_project_id="project-a",
                             locator=locator("source.py", content))
    assert changed
