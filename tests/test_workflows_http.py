from pathlib import Path

import pytest

pytest.importorskip("flask")
pytest.importorskip("code_analyzer")
pytest.importorskip("tech_documents")

from pah import create_app


def test_pah05_cross_module_http_workflows(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text(
        "def alpha(x):\n    return beta(x)\n\ndef beta(x):\n    return x * 2\n",
        encoding="utf-8",
    )
    (project / "notes.md").write_text("# Notes\n", encoding="utf-8")

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        assert client.post("/api/workspace/open", json={"path": str(project)}).status_code == 200
        assert client.post("/api/analyzer/analyze", json={}).status_code == 200
        functions = client.get("/api/analyzer/functions").get_json()["functions"]
        alpha = next(row for row in functions if row["name"] == "alpha")

        diagram = client.post(
            "/api/workflows/diagram/entity",
            json={"entity_id": alpha["id"], "target": "docs/alpha.diagram"},
        )
        assert diagram.status_code == 200
        assert (project / "docs" / "alpha.diagram").exists()
        assert "flowchart" in diagram.get_json()["mermaid"]

        scaffold = client.post(
            "/api/workflows/docs/scaffold",
            json={"kind": "entity", "entity_id": alpha["id"], "target": "docs/alpha.md"},
        )
        assert scaffold.status_code == 200
        assert "main.alpha" in (project / "docs" / "alpha.md").read_text(encoding="utf-8")

        snippet = client.post(
            "/api/documents/code-snippet",
            json={"entity_id": alpha["id"], "target": "notes.md", "include_source": True},
        ).get_json()["snippet"]
        assert "/PAH-CODE-REF" in snippet
        refreshed = client.post(
            "/api/workflows/code/refresh",
            json={"target": "notes.md", "content": "# Notes\n\n" + snippet},
        )
        assert refreshed.status_code == 200
        assert refreshed.get_json()["refreshed"] == 1

        diagram_source = (project / "docs" / "alpha.diagram").read_text(encoding="utf-8")
        embedded = client.post(
            "/api/workflows/diagram/document-snippet",
            json={"diagram_path": "docs/alpha.diagram", "content": diagram_source, "target": "notes.md"},
        )
        assert embedded.status_code == 200
        assert "PAH-DIAGRAM-REF" in embedded.get_json()["snippet"]

        linked_content = "# Notes\n\n" + snippet + "\n" + embedded.get_json()["snippet"]
        (project / "notes.md").write_text(linked_content, encoding="utf-8")
        links = client.post(
            "/api/workflows/links",
            json={"entity_id": alpha["id"], "document_path": "notes.md", "document_content": linked_content},
        ).get_json()
        assert "notes.md" in links["entity_used_in"]
        assert links["document"]["diagrams"][0]["path"] == "docs/alpha.diagram"
