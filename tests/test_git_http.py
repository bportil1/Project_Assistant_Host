from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("flask")

from pah import create_app


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git executable is required")


def make_bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], text=True, capture_output=True, check=True)
    return remote


def test_git_http_defaults_local_only_and_remote_routes_require_explicit_permission(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    remote = make_bare_remote(tmp_path)

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        opened = client.post("/api/workspace/open", json={"path": str(project)})
        assert opened.status_code == 200
        assert opened.get_json()["git"]["local_only"] is True

        client.post("/api/git/init", json={})
        added = client.post("/api/git/remotes", json={"name": "origin", "url": str(remote)})
        assert added.status_code == 200
        assert added.get_json()["remotes"][0]["name"] == "origin"

        blocked = client.post("/api/git/fetch", json={"remote": "origin"})
        assert blocked.status_code == 400
        assert "Manual Remote" in blocked.get_json()["error"]

        enabled = client.post("/api/git/connectivity", json={"mode": "manual_remote"})
        assert enabled.status_code == 200
        assert enabled.get_json()["remote_enabled"] is True

        fetched = client.post("/api/git/fetch", json={"remote": "origin"})
        assert fetched.status_code == 200
        assert fetched.get_json()["remote_enabled"] is True

        page = client.get("/git")
        assert page.status_code == 200
        assert b"MANUAL REMOTE" in page.data
        assert b"Remotes" in page.data


def test_opening_another_workspace_resets_remote_permission(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir(); second.mkdir()
    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client.post("/api/workspace/open", json={"path": str(first)})
        client.post("/api/git/connectivity", json={"mode": "manual_remote"})
        assert client.get("/api/git/status").get_json()["remote_enabled"] is True

        opened = client.post("/api/workspace/open", json={"path": str(second)})
        assert opened.get_json()["git"]["local_only"] is True
        assert opened.get_json()["git"]["remote_enabled"] is False
