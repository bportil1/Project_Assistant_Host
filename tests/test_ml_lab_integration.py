from __future__ import annotations

from pathlib import Path

import pytest


def test_ml_lab_component_is_registered_for_setup_and_entry_point_discovery():
    from pah.components import GIT_COMPONENTS, PYTHON_COMPONENTS

    python = {item.key: item for item in PYTHON_COMPONENTS}
    component = python["ml_lab"]
    assert component.path == "modules/ml_lab"
    assert component.install_spec == "modules/ml_lab[ui]"
    assert component.pah_entry_points == (("pah.modules", "ml_lab"), ("pah.runtimes", "ml_lab"))
    assert component.compatibility_tests == ("tests/test_pah_integration.py",)

    git = {item.key: item for item in GIT_COMPONENTS}
    assert git["ml_lab"].path == "modules/ml_lab"


def test_ml_lab_launcher_is_docked_in_pah_shell():
    root = Path(__file__).resolve().parents[1]
    template = (root / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    script = (root / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    assert 'id="openMlLab"' in template
    assert 'id="mlLabMode"' in template
    assert 'id="mlLabToolFrame"' in template
    assert "openMlLab()" in script
    assert "/api/orchestration/ml-lab" in script
    assert "/api/orchestration/modules/ml_lab/launch" in script


def test_ml_lab_orchestration_endpoint_degrades_cleanly_without_installed_module(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        response = client.get("/api/orchestration/ml-lab")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["lab"]["lab_id"] == "ml_lab"
        assert payload["runtime"]["module_id"] == "ml_lab"
        assert "artifacts" in payload
