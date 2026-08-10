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
