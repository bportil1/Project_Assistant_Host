from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_workspace_nav_removed_without_reordering():
    html = (ROOT / 'pah/web/templates/index.html').read_text()
    assert 'data-mode="workspace"' not in html
    assert html.index('data-mode="uca"') < html.index('data-mode="documents"') < html.index('data-mode="references"')
    assert 'id="workspaceMode"' in html  # internal editor/docking still present

def test_unified_mode_default_and_editor_save():
    js = (ROOT / 'pah/web/static/pah.js').read_text()
    assert "mode: 'uca'" in js
    assert "lastMode: 'uca'" in js
    assert "saved.lastMode === 'workspace' ? 'uca'" in js
    assert "['workspace', 'uca'].includes(state.mode)" in js
