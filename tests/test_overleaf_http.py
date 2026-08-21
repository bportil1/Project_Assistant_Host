from __future__ import annotations

import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("flask")

from pah import create_app


def zip_bytes(files: dict[str, str]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return buffer


def test_overleaf_zip_http_import_does_not_require_or_enable_remote_git(tmp_path: Path):
    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    destination = tmp_path / "imported"
    archive = zip_bytes({"main.tex": r"\documentclass{article}\begin{document}x\end{document}", "refs.bib": "@book{x}"})

    with app.test_client() as client:
        response = client.post(
            "/api/overleaf/import-zip",
            data={"destination": str(destination), "archive": (archive, "source.zip")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["acquisition_mode"] == "zip"
        assert data["local_only"] is True
        assert data["remote_enabled"] is False
        assert data["project"]["likely_main"] == "main.tex"
        assert not (destination / ".git").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable is required")
def test_overleaf_git_clone_reuses_manual_remote_permission(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init"], cwd=source, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "PAH Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "pah@example.invalid"], cwd=source, check=True)
    (source / "main.tex").write_text(r"\documentclass{article}\begin{document}x\end{document}", encoding="utf-8")
    subprocess.run(["git", "add", "main.tex"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=source, text=True, capture_output=True, check=True)
    remote = tmp_path / "overleaf.git"
    subprocess.run(["git", "clone", "--bare", str(source), str(remote)], text=True, capture_output=True, check=True)

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    destination = tmp_path / "clone"
    with app.test_client() as client:
        blocked = client.post("/api/overleaf/clone", json={"url": str(remote), "destination": str(destination)})
        assert blocked.status_code == 400
        assert "Manual Remote" in blocked.get_json()["error"]
        assert not destination.exists()

        enabled = client.post("/api/git/connectivity", json={"mode": "manual_remote"})
        assert enabled.status_code == 200
        cloned = client.post("/api/overleaf/clone", json={"url": str(remote), "destination": str(destination)})
        assert cloned.status_code == 200
        data = cloned.get_json()
        assert data["acquisition_mode"] == "git"
        assert data["remote_enabled"] is True
        assert data["project"]["likely_main"] == "main.tex"
        assert (destination / ".git").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable is required")
def test_overleaf_sync_is_explicit_reports_freshness_and_blocks_unsafe_push_pull(tmp_path: Path):
    project = tmp_path / "paper"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "PAH Test"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "pah@example.invalid"], cwd=project, check=True)
    (project / "main.tex").write_text(r"\documentclass{article}\begin{document}x\end{document}", encoding="utf-8")
    (project / "refs.bib").write_text("@book{x, title={X}}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=project, text=True, capture_output=True, check=True)

    remote = tmp_path / "overleaf.git"
    subprocess.run(["git", "init", "--bare", str(remote)], text=True, capture_output=True, check=True)
    subprocess.run(["git", "remote", "add", "overleaf", str(remote)], cwd=project, check=True)
    subprocess.run(["git", "push", "-u", "overleaf", "HEAD"], cwd=project, text=True, capture_output=True, check=True)

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        opened = client.post("/api/workspace/open", json={"path": str(project)})
        assert opened.status_code == 200

        initial = client.get("/api/overleaf/status").get_json()
        assert initial["selected_remote"] == "overleaf"
        assert initial["comparison"]["state"] == "up_to_date"
        assert initial["comparison_fresh"] is False
        assert initial["project"]["bib_files"] == ["refs.bib"]

        blocked = client.post("/api/overleaf/fetch", json={"remote": "overleaf"})
        assert blocked.status_code == 400
        assert "Manual Remote" in blocked.get_json()["error"]

        client.post("/api/git/connectivity", json={"mode": "manual_remote"})
        fetched = client.post("/api/overleaf/fetch", json={"remote": "overleaf"})
        assert fetched.status_code == 200
        fetch_data = fetched.get_json()
        assert fetch_data["comparison_fresh"] is True
        assert fetch_data["sync_events"]["last_fetch_at"]

        other = tmp_path / "other"
        subprocess.run(["git", "clone", str(remote), str(other)], text=True, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "PAH Test"], cwd=other, check=True)
        subprocess.run(["git", "config", "user.email", "pah@example.invalid"], cwd=other, check=True)
        (other / "main.tex").write_text(r"\documentclass{article}\begin{document}remote\end{document}", encoding="utf-8")
        subprocess.run(["git", "add", "main.tex"], cwd=other, check=True)
        subprocess.run(["git", "commit", "-m", "Remote edit"], cwd=other, text=True, capture_output=True, check=True)
        subprocess.run(["git", "push"], cwd=other, text=True, capture_output=True, check=True)

        behind = client.post("/api/overleaf/fetch", json={"remote": "overleaf"})
        assert behind.status_code == 200
        assert behind.get_json()["comparison"]["state"] == "behind"

        unsafe_push = client.post("/api/overleaf/push", json={"remote": "overleaf"})
        assert unsafe_push.status_code == 400
        assert "behind/diverged" in unsafe_push.get_json()["error"]

        (project / "local-note.txt").write_text("dirty\n", encoding="utf-8")
        dirty_pull = client.post("/api/overleaf/pull", json={"remote": "overleaf"})
        assert dirty_pull.status_code == 400
        assert "working tree has local changes" in dirty_pull.get_json()["error"]
        (project / "local-note.txt").unlink()

        pulled = client.post("/api/overleaf/pull", json={"remote": "overleaf"})
        assert pulled.status_code == 200
        pull_data = pulled.get_json()
        assert pull_data["comparison"]["state"] == "up_to_date"
        assert pull_data["comparison_fresh"] is True
        assert pull_data["sync_events"]["last_pull_at"]
