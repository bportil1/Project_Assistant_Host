"""Ensure Quality Impact analysis uses the common read-only table engine."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quality_impact_table_is_shared_component():
    js = (ROOT / 'pah/web/static/pah.js').read_text()
    assert "mountTable(host,snapshot" in js
    assert "import('/pah-shared/table_component.mjs')" in js
    portion = js[js.index('function qiTable(holder'):js.index('function renderQualityImpactPanel')]
    assert "qiElement('table'" not in portion
    assert "data_scope:'complete'" in portion


def test_shared_asset_route_is_allowlisted():
    source = (ROOT / 'pah/app.py').read_text()
    assert '@app.get("/pah-shared/<asset>")' in source
    assert 'static_asset(asset).read_bytes()' in source
