"""P5-18: producer-owned bounded finding selection and read-only UI wiring."""
from pathlib import Path
from unittest.mock import patch
import pytest


def test_selection_contract_source():
    base = Path(__file__).resolve().parents[1] / "pah"
    app = (base / "app.py").read_text()
    ui = (base / "web/static/source-evidence.js").read_text()
    html = (base / "web/templates/index.html").read_text()
    assert 'project_findings_evidence(str(root), project_id=project_id, view=view, limit=100)' in app
    assert 'workspaces.is_module_enabled("pypique")' in app
    assert 'sourceEvidenceFindingSelect' in html
    assert "verify.click()" in ui
    assert "clearFindings('Workspace changed." in ui


def test_local_http_findings_requires_project_and_provider(tmp_path):
    flask = pytest.importorskip('flask')
    from pah.app import create_app
    app = create_app(state_dir=tmp_path / 'state')
    app.testing = True
    c = app.test_client()
    url = '/api/orchestration/code-analysis/source-evidence/findings'
    assert c.get(url).status_code == 409
    assert c.get(url + '?view=unsupported').status_code == 409  # scope first
