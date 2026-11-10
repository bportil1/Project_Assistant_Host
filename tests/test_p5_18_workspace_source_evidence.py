from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest


def test_read_only_verified_preview_and_no_editor(tmp_path):
    pytest.importorskip("flask")
    from pah.app import create_app
    app = create_app(state_dir=tmp_path / "state")
    app.testing = True
    client = app.test_client()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "hello.py").write_text("print('<script>')\nprint('second')\n")
    opened = client.post('/api/workspace/open', json={'path': str(root)})
    assert opened.status_code == 200
    project_id = client.get('/api/workspace').json.get('active_workspace_id')
    assert project_id
    evidence = {
        'producer_module': 'pypique', 'finding_id': 'finding-1',
        'project_id': project_id, 'relative_path': 'hello.py',
        'start_line': 1, 'end_line': 2,
        'source_sha256': hashlib.sha256((root / 'hello.py').read_bytes()).hexdigest(),
    }
    url = '/api/orchestration/code-analysis/source-evidence/preview'
    response = client.post(url, json=evidence)
    assert response.status_code == 200, response.json
    assert response.json['evidence']['mode'] == 'read_only'
    assert '<script>' in response.json['evidence']['excerpt']
    assert (root / 'hello.py').read_text().startswith('print(')
    assert client.post(url, json={**evidence, 'project_id': 'another'}).status_code == 409
    (root / 'hello.py').write_text('different\n')
    assert client.post(url, json=evidence).status_code == 409


def test_workspace_preview_requires_json_and_same_origin(tmp_path):
    pytest.importorskip('flask')
    from pah.app import create_app
    app = create_app(state_dir=tmp_path / 'state')
    app.testing = True
    client = app.test_client()
    url = '/api/orchestration/code-analysis/source-evidence/preview'
    assert client.post(url, data='x').status_code == 415
    assert client.post(url, json={}, headers={'Origin':'https://untrusted.example'}).status_code == 403
    assert client.post(url, json={}).status_code == 409


def test_ui_is_read_only():
    base = Path(__file__).resolve().parents[1] / 'pah' / 'web'
    html = (base / 'templates' / 'index.html').read_text()
    js = (base / 'static' / 'source-evidence.js').read_text()
    assert 'sourceEvidencePreviewPanel' in html
    assert 'source-evidence.js' in html
    assert 'textContent = evidence.excerpt' in js
    assert 'editor.open' not in js.lower()
    assert "method: 'PUT'" not in js
