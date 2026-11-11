"""The editor and UCA source verifier must fingerprint identical file bytes."""
import hashlib
from pathlib import Path

from pah.core.filesystem import FileSystemService


def test_editor_read_exposes_raw_byte_digest_without_changing_universal_newlines(tmp_path: Path):
    original = b"first\r\nsecond\r\nthird\n"
    (tmp_path / "example.py").write_bytes(original)
    result = FileSystemService(tmp_path).read_text("example.py")
    assert result["content"] == "first\nsecond\nthird\n"
    assert result["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["source_sha256"] != hashlib.sha256(result["content"].encode()).hexdigest()


def test_editor_read_digest_updates_when_disk_changes(tmp_path: Path):
    path = tmp_path / "example.py"
    path.write_bytes(b"one\r\n")
    fs = FileSystemService(tmp_path)
    before = fs.read_text("example.py")
    path.write_bytes(b"two\r\n")
    after = fs.read_text("example.py")
    assert before["source_sha256"] != after["source_sha256"]
    assert after["source_sha256"] == hashlib.sha256(b"two\r\n").hexdigest()
