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


def test_pah071_version_is_reported():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    assert 'version = "0.7.1"' in pyproject
    assert '"version": "0.7.1"' in app


def test_pah071_visual_identity_stylesheets_are_loaded_after_legacy_css():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    expected = ["pah.css", "pah-identity.css", "pah-workspace.css", "pah-tools.css"]
    positions = [html.index(name) for name in expected]
    assert positions == sorted(positions)
    for name in expected[1:]:
        assert (ROOT / "pah" / "web" / "static" / name).exists()


def test_pah071_standalone_modules_load_shared_visual_identity():
    analyzer_app = (ROOT / "modules" / "code_analyzer" / "code_analyzer" / "web" / "app.py").read_text(encoding="utf-8")
    analyzer_html = (ROOT / "modules" / "code_analyzer" / "code_analyzer" / "web" / "templates" / "report.html").read_text(encoding="utf-8")
    documents_html = (ROOT / "modules" / "tech_documents" / "tech_documents" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    references_html = (ROOT / "modules" / "reference_manager" / "reference_manager" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    research_search_html = (ROOT / "modules" / "reference_manager" / "modules" / "paper_searcher" / "paper_searcher" / "web" / "static" / "index.html").read_text(encoding="utf-8")

    assert '"pah-module-theme.css"' in analyzer_app
    assert '"pah-compat.css"' in analyzer_app
    assert 'class="pah-module"' in analyzer_html
    for html in [documents_html, references_html, research_search_html]:
        assert "pah-module-theme.css" in html
        assert "pah-compat.css" in html
        assert 'class="pah-module"' in html
