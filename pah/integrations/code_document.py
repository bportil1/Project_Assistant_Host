from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import Any, Callable


class CodeDocumentBridgeError(ValueError):
    pass


_MD_BLOCK_RE = re.compile(
    r"(?P<block><!--\s*PAH-CODE-REF\s+(?P<attrs>.*?)\s*-->\s*\n(?P<body>.*?)<!--\s*/PAH-CODE-REF\s*-->)",
    re.DOTALL | re.IGNORECASE,
)
_TEX_BLOCK_RE = re.compile(
    r"(?P<block>^%\s*PAH-CODE-REF\s+(?P<attrs>.*?)\s*$\n(?P<body>.*?)^%\s*/PAH-CODE-REF\s*$)",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)
_ATTR_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)=(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^\s]+)")


def _line_text(metadata: dict[str, Any]) -> str:
    start = metadata.get("line_start")
    end = metadata.get("line_end")
    if not start:
        return ""
    if end and end != start:
        return f"lines {start}–{end}"
    return f"line {start}"


def _attrs(entity: dict[str, Any], include_source: bool) -> dict[str, str]:
    metadata = dict(entity.get("metadata") or {})
    start = metadata.get("line_start")
    end = metadata.get("line_end") or start
    values = {
        "id": str(entity.get("id") or ""),
        "path": str(entity.get("path") or ""),
        "entity": str(entity.get("qualified_name") or entity.get("name") or entity.get("id") or "code entity"),
        "mode": "source" if include_source else "reference",
    }
    if start:
        values["lines"] = f"{start}-{end}"
    return values


def _quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_marker_attributes(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, raw in _ATTR_RE.findall(str(text or "")):
        try:
            value = shlex.split(raw)[0] if raw[:1] in {'"', "'"} else raw
        except Exception:
            value = raw.strip('"\'')
        result[key.lower()] = value
    return result


def code_document_snippet(entity: dict[str, Any], target_path: str, *, include_source: bool = False) -> str:
    """Create a bounded, refreshable code reference for Markdown or LaTeX.

    The block remains readable outside PAH, but stores the stable analyzer entity
    id plus insertion mode so PAH can refresh it later after explicit analysis.
    """
    target_suffix = PurePosixPath(str(target_path)).suffix.lower()
    if target_suffix not in {".md", ".markdown", ".tex"}:
        raise CodeDocumentBridgeError("Code references can only target Markdown or LaTeX files.")

    metadata = dict(entity.get("metadata") or {})
    qualified = str(entity.get("qualified_name") or entity.get("name") or entity.get("id") or "code entity")
    source_path = str(entity.get("path") or "")
    line_text = _line_text(metadata)
    source = str(metadata.get("source_code") or "").rstrip()
    location = source_path + (f", {line_text}" if line_text else "")
    attrs = _attrs(entity, include_source)
    marker_attrs = " ".join(f"{key}={_quote(value)}" for key, value in attrs.items())

    if target_suffix in {".md", ".markdown"}:
        body = [f"<!-- PAH-CODE-REF {marker_attrs} -->", f"**`{qualified}`** — `{location}`"]
        if include_source and source:
            body.extend(["", "```python", source, "```"])
        body.append("<!-- /PAH-CODE-REF -->")
        return "\n".join(body) + "\n"

    escaped_qualified = qualified.replace("_", r"\_")
    escaped_location = location.replace("_", r"\_")
    body = [f"% PAH-CODE-REF {marker_attrs}", rf"\texttt{{{escaped_qualified}}} (\texttt{{{escaped_location}}})"]
    if include_source and source:
        body.extend([r"\begin{verbatim}", source, r"\end{verbatim}"])
    body.append("% /PAH-CODE-REF")
    return "\n".join(body) + "\n"


def extract_code_markers(content: str) -> list[dict[str, Any]]:
    """Return PAH code-link metadata from new bounded and legacy markers."""
    text = str(content or "")
    rows: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for regex in (_MD_BLOCK_RE, _TEX_BLOCK_RE):
        for match in regex.finditer(text):
            attrs = parse_marker_attributes(match.group("attrs"))
            rows.append({**attrs, "bounded": True, "start": match.start(), "end": match.end()})
            occupied.append((match.start(), match.end()))

    legacy = re.compile(r"(?:<!--|%)\s*PAH-CODE-REF\s+(?P<attrs>.*?)(?:-->)?$", re.IGNORECASE | re.MULTILINE)
    for match in legacy.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        attrs = parse_marker_attributes(match.group("attrs"))
        rows.append({**attrs, "bounded": False, "start": match.start(), "end": match.end()})
    rows.sort(key=lambda row: int(row.get("start", 0)))
    return rows


def refresh_code_references(
    content: str,
    target_path: str,
    resolver: Callable[[dict[str, str]], dict[str, Any] | None],
) -> dict[str, Any]:
    """Refresh bounded code-reference blocks from current analyzer entities.

    ``resolver`` receives the stored marker attributes and returns the current
    serialized analyzer entity or ``None`` when it cannot be resolved. Legacy
    unbounded markers are left untouched because their generated-body extent is
    unknowable without risking user-authored text.
    """
    suffix = PurePosixPath(str(target_path)).suffix.lower()
    if suffix not in {".md", ".markdown", ".tex"}:
        raise CodeDocumentBridgeError("Code-reference refresh supports Markdown and LaTeX only.")
    regex = _MD_BLOCK_RE if suffix in {".md", ".markdown"} else _TEX_BLOCK_RE
    text = str(content or "")
    refreshed = 0
    unresolved: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        nonlocal refreshed
        attrs = parse_marker_attributes(match.group("attrs"))
        entity = resolver(attrs)
        if entity is None:
            unresolved.append(attrs)
            return match.group("block")
        refreshed += 1
        return code_document_snippet(
            entity,
            target_path,
            include_source=str(attrs.get("mode", "reference")).lower() == "source",
        ).rstrip("\n")

    updated = regex.sub(replace, text)
    return {
        "content": updated,
        "refreshed": refreshed,
        "unresolved": unresolved,
        "legacy_count": sum(1 for row in extract_code_markers(text) if not row.get("bounded")),
    }
