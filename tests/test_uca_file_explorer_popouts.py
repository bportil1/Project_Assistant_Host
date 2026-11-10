from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_same_tree_docked_without_restoring_workspace_navigation():
    html=(ROOT/'pah/web/templates/index.html').read_text()
    layout=(ROOT/'pah/web/static/uca-layout.mjs').read_text()
    assert 'data-mode="workspace"' not in html
    assert 'id="ucaExplorerToggle"' in html and 'id="ucaExplorerDock"' in html
    assert 'source: document.querySelector(\'#workspaceMode > #projectPane\')' in layout
    assert 'mount: explorerMount' in layout
    assert 'createEditorDock' in layout

def test_detachment_is_local_and_retains_editor_host():
    js=(ROOT/'pah/web/static/uca-layout.mjs').read_text()
    assert "popupUrl.searchParams.set('uca_pane',name)" in js
    assert 'popup = window.open(' in js
    assert 'editorDock.restore(); treeDock.restore()' in js
    assert 'renderWidths();' in js

def test_no_global_finding_count_cap_on_host():
    app=(ROOT/'pah/app.py').read_text()
    assert 'limit=200, offset=offset' in app
    assert 'limit=100' not in app[app.index('def code_analysis_source_evidence_findings():'):app.index('def code_analysis_source_evidence_preview():')]
    assert 'Invalid finding page offset' in app
