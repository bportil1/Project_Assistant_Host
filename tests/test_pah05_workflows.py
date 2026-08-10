from pathlib import Path

from pah.integrations import (
    ArtifactLinkIndex,
    code_document_snippet,
    diagram_document_snippet,
    entity_dependency_diagram,
    entity_scaffold,
    extract_code_markers,
    file_scaffold,
    project_scaffold,
    refresh_code_references,
    reference_document_snippet,
)


ENTITY = {
    "id": "function:src/demo.py:1:alpha",
    "node_type": "function",
    "name": "alpha",
    "qualified_name": "demo.alpha",
    "path": "src/demo.py",
    "metadata": {
        "line_start": 1,
        "line_end": 2,
        "signature": "alpha(x)",
        "docstring": "Double x.",
        "source_code": "def alpha(x):\n    return x * 2",
    },
}


def test_refreshable_code_reference_round_trip():
    snippet = code_document_snippet(ENTITY, "docs/method.md", include_source=True)
    markers = extract_code_markers(snippet)
    assert len(markers) == 1
    assert markers[0]["id"] == ENTITY["id"]
    assert markers[0]["mode"] == "source"
    assert markers[0]["bounded"] is True

    changed = {**ENTITY, "metadata": {**ENTITY["metadata"], "line_start": 10, "line_end": 12, "source_code": "def alpha(x):\n    return x * 3"}}
    result = refresh_code_references(snippet, "docs/method.md", lambda attrs: changed if attrs.get("id") == ENTITY["id"] else None)
    assert result["refreshed"] == 1
    assert "return x * 3" in result["content"]
    assert "lines 10–12" in result["content"]


def test_dependency_diagram_is_human_editable():
    deps = {
        "incoming": [{"relationship_type": "call", "other": {"id": "f:caller", "node_type": "function", "qualified_name": "demo.caller"}}],
        "outgoing": [{"relationship_type": "call", "other": {"id": "f:beta", "node_type": "function", "qualified_name": "demo.beta"}}],
    }
    source = entity_dependency_diagram(ENTITY, deps)
    assert "@direction LR" in source
    assert "demo.caller" in source
    assert "demo.alpha [service]" in source
    assert "demo.beta" in source
    assert "->" in source


def test_documentation_scaffolds_use_analyzer_facts():
    deps = {"incoming": [], "outgoing": []}
    entity_doc = entity_scaffold(ENTITY, deps)
    assert "demo.alpha" in entity_doc
    assert "alpha(x)" in entity_doc
    assert "Double x." in entity_doc

    file_doc = file_scaffold("src/demo.py", [ENTITY])
    assert "src/demo.py" in file_doc
    assert "demo.alpha" in file_doc

    project_doc = project_scaffold({"project_name": "Demo", "summary": {"python_files": 1, "functions": 1}}, [ENTITY])
    assert "Demo — Technical Overview" in project_doc
    assert "Python files: 1" in project_doc


def test_artifact_link_index_tracks_reverse_usage(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    code = code_document_snippet(ENTITY, "docs/method.md", include_source=False)
    paper = {"PaperID": "P-1", "BibKey": "smith2026", "Title": "Paper"}
    ref = reference_document_snippet(paper, "docs/method.md", kind="citation")
    (tmp_path / "docs" / "method.md").write_text(code + "\n" + ref, encoding="utf-8")

    index = ArtifactLinkIndex(tmp_path)
    data = index.index()
    assert data["summary"]["documents_with_links"] == 1
    assert index.entity_usage(ENTITY) == ["docs/method.md"]
    assert index.paper_usage("P-1") == ["docs/method.md"]
    inspected = index.inspect_content("docs/method.md", (tmp_path / "docs" / "method.md").read_text())
    assert inspected["code"][0]["id"] == ENTITY["id"]
    assert inspected["references"][0]["paper_id"] == "P-1"


def test_diagram_document_snippet_is_traceable_and_indexed(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    snippet = diagram_document_snippet("docs/diagrams/demo.diagram", "docs/overview.md", "flowchart LR\n  A --> B")
    assert "PAH-DIAGRAM-REF" in snippet
    assert "```mermaid" in snippet
    (tmp_path / "docs" / "overview.md").write_text(snippet, encoding="utf-8")
    inspected = ArtifactLinkIndex(tmp_path).inspect_content("docs/overview.md", snippet)
    assert inspected["diagrams"] == [{"path": "docs/diagrams/demo.diagram"}]
