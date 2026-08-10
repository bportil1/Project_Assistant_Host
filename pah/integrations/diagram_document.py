from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


class DiagramDocumentBridgeError(ValueError):
    pass


def _quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def diagram_document_snippet(diagram_path: str, target_path: str, mermaid: str) -> str:
    """Embed a DocumentEngine-rendered diagram in Markdown with source traceability."""
    suffix = PurePosixPath(str(target_path)).suffix.lower()
    if suffix not in {".md", ".markdown"}:
        raise DiagramDocumentBridgeError("PAH 0.5 diagram insertion currently targets Markdown files only.")
    source = str(diagram_path or "").strip()
    if not source.lower().endswith(".diagram"):
        raise DiagramDocumentBridgeError("Diagram source must be a .diagram file.")
    graph = str(mermaid or "").strip()
    if not graph:
        raise DiagramDocumentBridgeError("DocumentEngine did not produce Mermaid output for this diagram.")
    return (
        f"<!-- PAH-DIAGRAM-REF path={_quote(source)} -->\n"
        "```mermaid\n"
        f"{graph}\n"
        "```\n"
        "<!-- /PAH-DIAGRAM-REF -->\n"
    )
