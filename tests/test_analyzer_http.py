from pathlib import Path

import pytest

pytest.importorskip("flask")
pytest.importorskip("code_analyzer")

from pah import create_app


def test_analyzer_http_surface(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text(
        "def one(x):\n    return two(x)\n\ndef two(x):\n    return x + 1\n",
        encoding="utf-8",
    )

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        assert client.post("/api/workspace/open", json={"path": str(project)}).status_code == 200
        status = client.get("/api/analyzer/status").get_json()
        assert status["available"] is True
        assert status["analyzed"] is False

        analyzed = client.post("/api/analyzer/analyze", json={}).get_json()
        assert analyzed["summary"]["functions"] == 2

        functions = client.get("/api/analyzer/functions").get_json()["functions"]
        one = next(row for row in functions if row["name"] == "one")
        two = next(row for row in functions if row["name"] == "two")

        entities = client.get("/api/analyzer/file", query_string={"path": "main.py"}).get_json()["entities"]
        assert any(row["id"] == one["id"] for row in entities)

        deps = client.get("/api/analyzer/dependencies", query_string={"id": one["id"]}).get_json()
        assert any(row["target_id"] == two["id"] for row in deps["outgoing"])

        similar = client.get("/api/analyzer/similar", query_string={"id": one["id"], "limit": 1}).get_json()
        assert similar["neighbors"][0]["id"] == two["id"]

        saved = client.put("/api/file", json={"path": "main.py", "content": "def one(x):\n    return x\n"}).get_json()
        assert saved["analyzer_stale"] is True
        assert client.get("/api/analyzer/status").get_json()["stale"] is True
