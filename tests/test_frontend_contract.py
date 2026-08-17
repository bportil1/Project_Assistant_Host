from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pah05_workflow_controls_exist_and_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    for element_id in [
        "generateDependencyDiagram",
        "generateEntityDocs",
        "generateFileDocs",
        "generateProjectDocs",
        "refreshCodeReferencesButton",
        "entityUsage",
        "referenceUsage",
        "documentLinks",
        "diagramDocumentTarget",
        "insertDiagramDocument",
    ]:
        assert f'id="{element_id}"' in html
        assert f"$('{element_id}')" in js


def test_pah05_routes_are_present():
    source = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    for route in [
        "/api/workflows/diagram/entity",
        "/api/workflows/diagram/document-snippet",
        "/api/workflows/docs/scaffold",
        "/api/workflows/code/refresh",
        "/api/workflows/links",
    ]:
        assert route in source


def test_pah06_full_tool_modes_exist_and_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    for mode in ["workspace", "analysis", "documents", "references"]:
        assert f'data-mode="{mode}"' in html
    for element_id in [
        "analysisMode",
        "documentsMode",
        "referencesMode",
        "analysisToolFrame",
        "documentsToolFrame",
        "referencesToolFrame",
        "openFullAnalysis",
        "openFullDocuments",
        "openFullReferences",
    ]:
        assert f'id="{element_id}"' in html
    assert "async function setMode(mode)" in js
    assert "/api/full-tools/status" in js
    assert "/api/full-tools/return" in js


def test_pah06_full_tool_routes_are_present():
    source = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    assert "/api/full-tools/status" in source
    assert "/api/full-tools/refresh" in source
    assert "/api/full-tools/return" in source
    assert "FullToolManager" in source


def test_pah07_detachable_tool_controls_exist_and_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    for tool in ["analysis", "documents", "references"]:
        assert f'data-tool-detach="{tool}"' in html
    assert 'id="terminalDetach"' in html
    for function_name in [
        "detachTool",
        "reattachTool",
        "detachTerminal",
        "reattachTerminal",
        "pollDetachedTerminal",
    ]:
        assert f"function {function_name}" in js or f"async function {function_name}" in js
    assert "isToolDetached(mode)" in js
    assert "state.terminalDetached" in js


def test_pah07_version_is_reported():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    assert 'version = "0.7.0"' in pyproject
    assert '"version": "0.7.0"' in app
