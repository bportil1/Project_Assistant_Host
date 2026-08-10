from pathlib import Path

import pytest

pytest.importorskip("flask")
pytest.importorskip("reference_manager")

from pah import create_app


def test_reference_http_surface_and_document_bridge(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("# Notes\n", encoding="utf-8")

    library = tmp_path / "library"
    library.mkdir()

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        assert client.post("/api/workspace/open", json={"path": str(project)}).status_code == 200
        selected = client.post("/api/references/library", json={"path": str(library)})
        assert selected.status_code == 200
        assert selected.get_json()["configured"] is True

        imported = client.post(
            "/api/references/bibtex/import",
            json={"content": "@article{x2026, title={Example Paper}, author={A. Author}, year={2026}}"},
        )
        assert imported.status_code == 200

        papers = client.get("/api/references/papers").get_json()["papers"]
        assert len(papers) == 1
        paper = papers[0]
        assert paper["BibKey"] == "x2026"

        snippet = client.post(
            "/api/references/document-snippet",
            json={"paper_id": paper["PaperID"], "target": "notes.md", "kind": "citation"},
        )
        assert snippet.status_code == 200
        assert "[@x2026]" in snippet.get_json()["snippet"]

        saved = client.put(
            "/api/references/paper",
            json={"paper_id": paper["PaperID"], "status": "Read", "notes": "Reviewed"},
        )
        assert saved.get_json()["paper"]["Status"] == "Read"
        health = client.get("/api/health").get_json()
        assert health["version"] == "0.5.0"
        assert health["references"]["available"] is True
