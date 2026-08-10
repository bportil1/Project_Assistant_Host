from __future__ import annotations

import re
from typing import Any


class AnalysisDiagramBridgeError(ValueError):
    pass


def _clean_label(value: Any) -> str:
    text = " ".join(str(value or "").split()).replace("->", "→")
    return text or "unknown"


def _kind(node: dict[str, Any] | None, *, focal: bool = False) -> str:
    if focal:
        return "service"
    if not node:
        return "interface"
    node_type = str(node.get("node_type") or "").lower()
    node_id = str(node.get("id") or "")
    if node_id.startswith("external:") or node_type in {"external", "library"}:
        return "interface"
    if node_type == "class":
        return "custom"
    if node_type == "module":
        return "service"
    return "default"


def _node_text(node: dict[str, Any] | None, *, focal: bool = False) -> str:
    if not node:
        return "unknown"
    return _clean_label(node.get("qualified_name") or node.get("name") or node.get("id")) + f" [{_kind(node, focal=focal)}]"


def entity_dependency_diagram(
    entity: dict[str, Any],
    dependencies: dict[str, Any],
    *,
    direction: str = "LR",
    preset: str = "architecture",
) -> str:
    """Create a small editable .diagram view centered on one analyzer entity."""
    if not entity:
        raise AnalysisDiagramBridgeError("An analyzed entity is required.")
    focal_label = _clean_label(entity.get("qualified_name") or entity.get("name") or entity.get("id"))
    lines = [f"@direction {direction}", f"@preset {preset}", ""]
    relation_notes: list[str] = []

    incoming = dependencies.get("incoming") or []
    outgoing = dependencies.get("outgoing") or []
    seen_edges: set[tuple[str, str]] = set()

    # Explicit focal declaration keeps its semantic kind even if first seen as a target.
    lines.append(f"{focal_label} [service]")
    metadata = dict(entity.get("metadata") or {})
    location = str(entity.get("path") or "")
    if metadata.get("line_start"):
        location += f":{metadata.get('line_start')}"
    if location:
        lines.append(f"  :: source {location}")
    lines.append("")

    for row in incoming:
        other = dict(row.get("other") or {})
        source = _clean_label(other.get("qualified_name") or other.get("name") or other.get("id"))
        edge = (source, focal_label)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        lines.append(f"{_node_text(other)} -> {focal_label} [service]")
        relation_notes.append(f"incoming {row.get('relationship_type')}: {source}")

    for row in outgoing:
        other = dict(row.get("other") or {})
        target = _clean_label(other.get("qualified_name") or other.get("name") or other.get("id"))
        edge = (focal_label, target)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        lines.append(f"{focal_label} [service] -> {_node_text(other)}")
        relation_notes.append(f"outgoing {row.get('relationship_type')}: {target}")

    if not seen_edges:
        lines.append(f"// No incoming or outgoing analyzer relationships were found for {focal_label}.")
    if relation_notes:
        lines.extend(["", "// Analyzer relationship types:"] + [f"// {note}" for note in relation_notes])
    return "\n".join(lines).rstrip() + "\n"


def suggested_diagram_path(entity: dict[str, Any]) -> str:
    name = str(entity.get("qualified_name") or entity.get("name") or "entity")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-") or "entity"
    return f"docs/diagrams/{slug}_dependencies.diagram"
