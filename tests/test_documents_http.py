from pathlib import Path

import pytest

pytest.importorskip("flask")
pytest.importorskip("tech_documents")
pytest.importorskip("code_analyzer")

from pah import create_app


def test_document_and_code_bridge_http_surface(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("def hello(name):\n    return f'Hello {name}'\n", encoding="utf-8")
    (project / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (project / "architecture.diagram").write_text("A -> B\n", encoding="utf-8")

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        assert client.post("/api/workspace/open", json={"path": str(project)}).status_code == 200
        status = client.get("/api/documents/status").get_json()
        assert status["available"] is True

        files = client.get("/api/documents/files").get_json()["files"]
        assert any(row["path"] == "notes.md" for row in files)

        parsed = client.post("/api/documents/diagram/parse", json={"content": "A -> B\n"}).get_json()
        assert "flowchart" in parsed["mermaid"]

        client.post("/api/analyzer/analyze", json={})
        functions = client.get("/api/analyzer/functions").get_json()["functions"]
        hello = next(row for row in functions if row["name"] == "hello")
        snippet = client.post(
            "/api/documents/code-snippet",
            json={"entity_id": hello["id"], "target": "notes.md", "include_source": True},
        ).get_json()["snippet"]
        assert "PAH-CODE-REF" in snippet
        assert "```python" in snippet
