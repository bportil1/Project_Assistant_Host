from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .code_document import extract_code_markers, parse_marker_attributes


_DIAGRAM_RE = re.compile(r'<!--\s*PAH-DIAGRAM-REF\s+(?P<attrs>.*?)\s*-->', re.IGNORECASE)
_REF_RE = re.compile(r"(?:<!--|%)\s*PAH-REF\s+(?P<attrs>.*?)(?:-->)?$", re.IGNORECASE | re.MULTILINE)
_DOCUMENT_EXTENSIONS = {".md", ".markdown", ".tex"}
_IGNORED_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}


class ArtifactLinkIndex:
    """PAH-owned traceability index over explicit document markers."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def inspect_content(path: str, content: str) -> dict[str, Any]:
        code = []
        for row in extract_code_markers(content):
            code.append({
                "id": row.get("id", ""),
                "path": row.get("path", ""),
                "entity": row.get("entity", ""),
                "mode": row.get("mode", "legacy" if not row.get("bounded") else "reference"),
                "bounded": bool(row.get("bounded")),
            })
        diagrams = []
        for match in _DIAGRAM_RE.finditer(str(content or "")):
            attrs = parse_marker_attributes(match.group("attrs"))
            diagrams.append({"path": attrs.get("path", "")})
        refs = []
        for match in _REF_RE.finditer(str(content or "")):
            attrs = parse_marker_attributes(match.group("attrs"))
            refs.append({
                "paper_id": attrs.get("paper_id", ""),
                "bibkey": attrs.get("bibkey", ""),
                "title": attrs.get("title", ""),
            })
        return {"path": path, "code": code, "diagrams": diagrams, "references": refs}

    def _documents(self) -> list[Path]:
        rows: list[Path] = []
        for directory, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [name for name in dirnames if name not in _IGNORED_DIRS]
            base = Path(directory)
            for filename in filenames:
                path = base / filename
                if path.suffix.lower() in _DOCUMENT_EXTENSIONS:
                    rows.append(path)
        return sorted(rows)

    def index(self) -> dict[str, Any]:
        documents = []
        code_reverse: dict[str, list[str]] = {}
        code_fallback: dict[str, list[str]] = {}
        reference_reverse: dict[str, list[str]] = {}
        for path in self._documents():
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            relative = path.relative_to(self.root).as_posix()
            row = self.inspect_content(relative, content)
            if row["code"] or row["diagrams"] or row["references"]:
                documents.append(row)
            for link in row["code"]:
                if link.get("id"):
                    code_reverse.setdefault(str(link["id"]), []).append(relative)
                fallback = f"{link.get('path', '')}::{link.get('entity', '')}"
                code_fallback.setdefault(fallback, []).append(relative)
            for link in row["references"]:
                if link.get("paper_id"):
                    reference_reverse.setdefault(str(link["paper_id"]), []).append(relative)

        return {
            "documents": documents,
            "code": {key: sorted(set(value)) for key, value in code_reverse.items()},
            "code_fallback": {key: sorted(set(value)) for key, value in code_fallback.items()},
            "references": {key: sorted(set(value)) for key, value in reference_reverse.items()},
            "summary": {
                "documents_with_links": len(documents),
                "code_entities_referenced": len(code_reverse) + len(code_fallback),
                "papers_referenced": len(reference_reverse),
                "diagram_references": sum(len(row.get("diagrams") or []) for row in documents),
            },
        }

    def entity_usage(self, entity: dict[str, Any]) -> list[str]:
        data = self.index()
        entity_id = str(entity.get("id") or "")
        if entity_id and entity_id in data["code"]:
            return data["code"][entity_id]
        key = f"{entity.get('path', '')}::{entity.get('qualified_name') or entity.get('name') or ''}"
        return data["code_fallback"].get(key, [])

    def paper_usage(self, paper_id: str) -> list[str]:
        return self.index()["references"].get(str(paper_id or ""), [])
