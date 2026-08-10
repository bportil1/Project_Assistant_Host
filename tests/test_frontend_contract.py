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
