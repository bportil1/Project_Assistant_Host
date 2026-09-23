from pathlib import Path

import pytest

pytest.importorskip("flask")

from pah import create_app


def test_http_workspace_edit_and_health(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('ok')\n")
    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        assert client.get("/api/health").get_json()["ok"] is True
        opened = client.post("/api/workspace/open", json={"path": str(project)})
        assert opened.status_code == 200
        file_data = client.get("/api/file", query_string={"path": "main.py"}).get_json()
        assert file_data["language"] == "python"
        saved = client.put("/api/file", json={"path": "main.py", "content": "print('changed')\n"})
        assert saved.status_code == 200
        assert (project / "main.py").read_text() == "print('changed')\n"


def test_research_workspace_api_maps_document_root_without_replacing_repository_root(tmp_path: Path):
    repo = tmp_path / "repo"
    research = tmp_path / "research"
    documents = research / "thesis" / "overleaf"
    repo.mkdir()
    documents.mkdir(parents=True)

    app = create_app(state_dir=tmp_path / "state-workspaces")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        created = client.post(
            "/api/research-workspaces",
            json={"id": "hsqa-thesis", "name": "HSQA Thesis", "activate": True},
        )
        assert created.status_code == 200

        assert client.put(
            "/api/shared-roots/hsqa-repo",
            json={"name": "HSQA Repository", "role": "repository", "path": str(repo)},
        ).status_code == 200
        assert client.put(
            "/api/shared-roots/research-projects",
            json={"name": "Research Projects", "path": str(research)},
        ).status_code == 200

        mapped_repo = client.put(
            "/api/research-workspaces/hsqa-thesis/resources/repository",
            json={"root_id": "hsqa-repo"},
        )
        assert mapped_repo.status_code == 200
        mapped_docs = client.put(
            "/api/research-workspaces/hsqa-thesis/resources/documents",
            json={"root_id": "research-projects", "relative_path": "thesis/overleaf"},
        )
        assert mapped_docs.status_code == 200

        state = client.get("/api/workspace").get_json()
        assert state["root"] == str(repo.resolve())
        assert state["workspace_id"] == "hsqa-thesis"
        assert state["resources"]["documents"]["path"] == str(documents.resolve())

        catalog = client.get("/api/research-workspaces").get_json()
        assert catalog["active_workspace_id"] == "hsqa-thesis"
        assert {item["id"] for item in catalog["shared_roots"]} >= {"hsqa-repo", "research-projects"}
