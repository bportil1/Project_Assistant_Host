"""Read-only, exact-source evidence resolver for the PAH Code Analysis Lab.

P5-18 does not infer evidence coordinates, perform SAT, or edit source files.
The producer must supply explicit coordinates and a source SHA-256; the caller
must supply the currently authorized repository root and verify project identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Mapping

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_LINES = 80
_MAX_RESULT_BYTES = 24 * 1024


class SourceEvidenceError(ValueError):
    """Invalid, unauthorized, stale, or unsupported source evidence."""


@dataclass(frozen=True)
class SourceEvidenceLocator:
    producer_module: str
    finding_id: str
    project_id: str
    relative_path: str
    start_line: int
    end_line: int
    source_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "SourceEvidenceLocator":
        if not isinstance(value, Mapping):
            raise SourceEvidenceError("Evidence locator must be a mapping")
        required = ("producer_module", "finding_id", "project_id", "relative_path", "source_sha256")
        values = {}
        for key in required:
            raw = value.get(key)
            if not isinstance(raw, str) or not raw.strip() or len(raw) > 1024:
                raise SourceEvidenceError(f"Invalid evidence {key}")
            values[key] = raw.strip()
        for key in ("start_line", "end_line"):
            raw = value.get(key)
            if type(raw) is not int or raw < 1:
                raise SourceEvidenceError(f"Invalid evidence {key}")
            values[key] = raw
        if values["producer_module"] != "pypique":
            raise SourceEvidenceError("P5-18 only accepts explicit pyPIQUE evidence")
        path = values["relative_path"]
        parsed = PurePosixPath(path)
        if (path.startswith("/") or "\\" in path or "\x00" in path or
                not parsed.parts or any(p in (".", "..") for p in path.split("/")) or
                parsed.as_posix() != path or ":" in parsed.parts[0]):
            raise SourceEvidenceError("Source path must be a canonical repository-relative POSIX path")
        if values["end_line"] < values["start_line"] or values["end_line"] - values["start_line"] + 1 > _MAX_LINES:
            raise SourceEvidenceError("Evidence span exceeds bounded source preview")
        if not _SHA256.fullmatch(values["source_sha256"]):
            raise SourceEvidenceError("Source SHA-256 must be lowercase hex")
        return cls(**values)


def _read_verified_source(root: Path, relative_path: str) -> bytes:
    """Read through anchored descriptors, never through a resolved pathname.

    Every child component is opened relative to its already-open parent using
    O_NOFOLLOW. The final descriptor is inspected before reading, so replacing
    a pathname with a symlink cannot redirect the read outside the repository.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise SourceEvidenceError("Secure source inspection requires POSIX descriptor-relative opens")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = None
    try:
        descriptor = os.open(root, directory_flags)
        for component in relative_path.split("/")[:-1]:
            child = os.open(component, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(relative_path.split("/")[-1], file_flags, dir_fd=descriptor)
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise SourceEvidenceError("Evidence source must be a regular file")
            if before.st_size > _MAX_FILE_BYTES:
                raise SourceEvidenceError("Evidence source exceeds preview file-size limit")
            chunks = []
            total = 0
            while True:
                part = os.read(file_descriptor, min(65536, _MAX_FILE_BYTES + 1 - total))
                if not part:
                    break
                total += len(part)
                if total > _MAX_FILE_BYTES:
                    raise SourceEvidenceError("Evidence source exceeds preview file-size limit")
                chunks.append(part)
            after = os.fstat(file_descriptor)
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise SourceEvidenceError("Evidence source changed during inspection")
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    except OSError as error:
        raise SourceEvidenceError("Evidence source escapes the authorized repository or is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_source_evidence(*, repository_root: str | Path, active_project_id: str,
                         locator: SourceEvidenceLocator) -> dict[str, object]:
    """Verify the source and provide a bounded excerpt; no filesystem writes.

    The calling PAH service authorizes the repository root.  This function
    independently checks project isolation and containment but does not decide
    which users are authorized for a PAH workspace.
    """
    if not active_project_id or locator.project_id != active_project_id:
        raise SourceEvidenceError("Evidence belongs to a different project")
    # Validate even dataclass values constructed directly rather than via parser.
    locator = SourceEvidenceLocator.from_mapping(vars(locator))
    try:
        root = Path(repository_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise SourceEvidenceError("Repository root must be a directory")
    except (OSError, RuntimeError) as error:
        raise SourceEvidenceError("Authorized repository root is unavailable") from error
    data = _read_verified_source(root, locator.relative_path)
    digest = hashlib.sha256(data).hexdigest()
    if digest != locator.source_sha256:
        raise SourceEvidenceError("Evidence is stale: source SHA-256 changed")
    if b"\x00" in data:
        raise SourceEvidenceError("Binary source is not supported")
    try:
        contents = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceEvidenceError("Source is not UTF-8") from error
    lines = contents.splitlines()
    if locator.end_line > len(lines):
        raise SourceEvidenceError("Evidence line range exceeds source length")
    excerpt = "\n".join(lines[locator.start_line - 1:locator.end_line])
    if len(excerpt.encode("utf-8")) > _MAX_RESULT_BYTES:
        raise SourceEvidenceError("Evidence excerpt exceeds preview byte limit")
    return {
        "schema": "pah.source-evidence@1",
        "mode": "read_only",
        "producer_module": locator.producer_module,
        "finding_id": locator.finding_id,
        "project_id": locator.project_id,
        "relative_path": locator.relative_path,
        "start_line": locator.start_line,
        "end_line": locator.end_line,
        "source_sha256": digest,
        "excerpt": excerpt,
    }
