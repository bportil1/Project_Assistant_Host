"""Read-only, descriptor-safe, bounded verification of user-selected source spans."""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
from pah.labs.source_evidence import _read_verified_source, SourceEvidenceError


def verified_selection(repository_root, project_id, relative_path, start_line, end_line):
    if not isinstance(project_id, str) or not project_id or len(project_id) > 1024:
        raise SourceEvidenceError("Active project is required")
    if not isinstance(relative_path, str) or not relative_path or len(relative_path) > 1024:
        raise SourceEvidenceError("Invalid source path")
    parts = relative_path.split('/')
    if (relative_path.startswith('/') or any(part in ('', '.', '..') for part in parts)
            or '\\' in relative_path or '\x00' in relative_path or '%' in relative_path
            or ':' in relative_path or PurePosixPath(relative_path).as_posix() != relative_path):
        raise SourceEvidenceError("Source path must be canonical and repository-relative")
    if (type(start_line) is not int or type(end_line) is not int or start_line < 1
            or end_line < start_line or end_line - start_line > 79):
        raise SourceEvidenceError("Invalid source range")
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise SourceEvidenceError("Repository root is not a directory")
    data = _read_verified_source(root, relative_path)
    if b'\x00' in data:
        raise SourceEvidenceError("Binary source is unsupported")
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise SourceEvidenceError("Source is not UTF-8") from exc
    if end_line > len(text.splitlines()):
        raise SourceEvidenceError("Selected line is not present in source")
    return {'schema':'pah.uca-source-revision@1', 'project_id':project_id,
            'relative_path':relative_path, 'start_line':start_line, 'end_line':end_line,
            'source_sha256':hashlib.sha256(data).hexdigest()}
