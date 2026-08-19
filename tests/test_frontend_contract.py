from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pah05_workflow_controls_exist_and_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    for element_id in [
        "generateDependencyDiagram",
        "generateEntityDocs",
        "generateFileDocs",
        "generateProjectDocs",
        "refreshCodeReferencesButton",
        "entityUsage",
        "referenceUsage",
        "documentLinks",
        "diagramDocumentTarget",
        "insertDiagramDocument",
    ]:
        assert f'id="{element_id}"' in html
        assert f"$('{element_id}')" in js


def test_pah05_routes_are_present():
    source = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    for route in [
        "/api/workflows/diagram/entity",
        "/api/workflows/diagram/document-snippet",
        "/api/workflows/docs/scaffold",
        "/api/workflows/code/refresh",
        "/api/workflows/links",
    ]:
        assert route in source


def test_pah06_full_tool_modes_exist_and_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    for mode in ["workspace", "analysis", "documents", "references"]:
        assert f'data-mode="{mode}"' in html
    for element_id in [
        "analysisMode",
        "documentsMode",
        "referencesMode",
        "analysisToolFrame",
        "documentsToolFrame",
        "referencesToolFrame",
        "openFullAnalysis",
        "openFullDocuments",
        "openFullReferences",
    ]:
        assert f'id="{element_id}"' in html
    assert "async function setMode(mode)" in js
    assert "/api/full-tools/status" in js
    assert "/api/full-tools/return" in js


def test_pah06_full_tool_routes_are_present():
    source = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    assert "/api/full-tools/status" in source
    assert "/api/full-tools/refresh" in source
    assert "/api/full-tools/return" in source
    assert "FullToolManager" in source


def test_pah07_detachable_tool_controls_exist_and_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    for tool in ["analysis", "documents", "references"]:
        assert f'data-tool-detach="{tool}"' in html
    assert 'id="terminalDetach"' in html
    # Detach behavior is now routed through the generic window-surface controller.
    for function_name in [
        "detachSurface",
        "reattachSurface",
        "pollDetachedTerminal",
    ]:
        assert f"function {function_name}" in js or f"async function {function_name}" in js
    assert "isSurfaceDetached(mode)" in js
    assert "isSurfaceDetached('terminal')" in js


def test_pah_reported_versions_match():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    version_line = next(line for line in pyproject.splitlines() if line.startswith("version = "))
    version = version_line.split('"', 2)[1]
    assert f'"version": "{version}"' in app


def test_pah071_visual_identity_stylesheets_are_loaded_after_legacy_css():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    expected = ["pah.css", "pah-identity.css", "pah-workspace.css", "pah-tools.css"]
    positions = [html.index(name) for name in expected]
    assert positions == sorted(positions)
    for name in expected[1:]:
        assert (ROOT / "pah" / "web" / "static" / name).exists()


def test_pah071_standalone_modules_load_shared_visual_identity():
    analyzer_app = (ROOT / "modules" / "code_analyzer" / "code_analyzer" / "web" / "app.py").read_text(encoding="utf-8")
    analyzer_html = (ROOT / "modules" / "code_analyzer" / "code_analyzer" / "web" / "templates" / "report.html").read_text(encoding="utf-8")
    documents_html = (ROOT / "modules" / "tech_documents" / "tech_documents" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    references_html = (ROOT / "modules" / "reference_manager" / "reference_manager" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    research_search_html = (ROOT / "modules" / "reference_manager" / "modules" / "paper_searcher" / "paper_searcher" / "web" / "static" / "index.html").read_text(encoding="utf-8")

    assert '"pah-module-theme.css"' in analyzer_app
    assert '"pah-compat.css"' in analyzer_app
    assert 'class="pah-module"' in analyzer_html
    for html in [documents_html, references_html, research_search_html]:
        assert "pah-module-theme.css" in html
        assert "pah-compat.css" in html
        assert 'class="pah-module"' in html


def test_pah08_collapsible_workspace_panes_are_generic_and_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    css = (ROOT / "pah" / "web" / "static" / "pah.css").read_text(encoding="utf-8")

    for pane_id, toggle_id in [
        ("projectPane", "projectPaneToggle"),
        ("contextPane", "contextPaneToggle"),
        ("terminalPanel", "terminalToggle"),
    ]:
        assert f'id="{pane_id}"' in html
        assert f'id="{toggle_id}"' in html

    for function_name in ["renderPaneState", "setPaneCollapsed", "togglePane", "renderWorkspacePanes"]:
        assert f"function {function_name}" in js

    assert "project-pane-collapsed" in css
    assert "context-pane-collapsed" in css
    assert "setPaneCollapsed('terminal', true" in js
    assert "setPaneCollapsed('terminal', false" in js


def test_pah_current_version_is_reported():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    assert 'version = "0.8.7"' in pyproject
    assert '"version": "0.8.7"' in app


def test_pah081_compact_service_launchers_are_wired():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    css = (ROOT / "pah" / "web" / "static" / "pah.css").read_text(encoding="utf-8")

    for menu_id in ["analysisMenu", "documentsMenu", "referencesMenu", "toolsMenu"]:
        assert f'id="{menu_id}"' in html
        assert f'data-menu-toggle="{menu_id}"' in html

    for tool in ["analysis", "documents", "references"]:
        assert f'data-service-tool="{tool}" data-service-action="open"' in html
        assert f'data-tool-detach="{tool}"' in html
        assert f'data-tool-reload="{tool}"' in html

    for pane in ["project", "context", "terminal"]:
        assert f'data-pane-target="{pane}"' in html
        assert f'data-pane-indicator="{pane}"' in html

    for element_id in ["toolsMenuToggle", "toolsTerminalWindow", "toolsEnvironment", "toolsEnvironmentStatus"]:
        assert f'id="{element_id}"' in html

    assert 'id="envButton"' not in html
    assert "function closeServiceMenus" in js
    assert "function toggleServiceMenu" in js
    assert "async function reloadTool" in js
    assert "[data-pane-target]" in js
    assert ".service-menu" in css
    assert ".service-menu.hidden" in css


def test_pah081_full_tool_status_strips_do_not_duplicate_launcher_actions():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    for mode_id in ["analysisMode", "documentsMode", "referencesMode"]:
        start = html.index(f'id="{mode_id}"')
        end = html.index('</section>', start)
        section = html[start:end]
        assert 'data-tool-detach=' not in section
        assert 'data-tool-reload=' not in section


def test_pah082_generic_window_surface_controller_replaces_tool_specific_detach_state():
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")

    for surface in ["analysis", "documents", "references", "terminal"]:
        assert f"{surface}: {{kind:" in js

    for contract in [
        "const windowSurfaceConfig",
        "function surfaceWindow",
        "function isSurfaceDetached",
        "function surfacePresentationState",
        "async function openWindowSurface",
        "async function detachSurface",
        "async function reattachSurface",
        "async function handleSurfaceWindowClosed",
        "function ensureWindowSurfaceWatch",
    ]:
        assert contract in js

    assert "if (name === 'workspace')" in js
    assert "await setMode('workspace');" in js

    for legacy in [
        "detachedWindows",
        "detachedWatch",
        "terminalDetached",
        "function detachTool",
        "function reattachTool",
        "function detachTerminal",
        "function reattachTerminal",
    ]:
        assert legacy not in js


def test_pah082_terminal_uses_shared_window_controller_but_preserves_single_pty_transfer():
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")

    assert "if (!isSurfaceDetached('terminal')) state.terminalPoll = setInterval(pollTerminal, 300);" in js
    assert "if (!state.terminalId || isSurfaceDetached('terminal')) return;" in js
    assert "popup._pahTerminalPoll" in js
    assert "state.terminalPoll = state.terminalId ? setInterval(pollTerminal, 300) : null;" in js
    assert "writeDetachedTerminalShell(popup)" in js


def test_pah083_layout_preferences_are_local_persistent_and_resizable():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    css = (ROOT / "pah" / "web" / "static" / "pah.css").read_text(encoding="utf-8")

    for handle_id, pane in [
        ("projectPaneResize", "project"),
        ("contextPaneResize", "context"),
        ("terminalPaneResize", "terminal"),
    ]:
        assert f'id="{handle_id}"' in html
        assert f'data-resize-pane="{pane}"' in html

    assert 'id="toolsResetLayout"' in html
    assert "const LAYOUT_STORAGE_KEY = 'pah.workspace.layout.v1'" in js
    for function_name in [
        "loadLayoutPreferences",
        "persistLayoutPreferences",
        "setLayoutPaneSize",
        "applyLayoutSizes",
        "beginPaneResize",
        "resetWorkspaceLayout",
        "restoreLastMode",
    ]:
        assert f"function {function_name}" in js or f"async function {function_name}" in js

    assert "window.localStorage.setItem(LAYOUT_STORAGE_KEY" in js
    assert "--project-pane-expanded-width" in css
    assert "--context-pane-expanded-width" in css
    assert ".workspace-layout.project-pane-collapsed { --project-pane-width: 34px; }" in css
    assert ".workspace-layout.context-pane-collapsed { --context-pane-width: 34px; }" in css
    assert "--terminal-pane-height" in css
    assert ".pane-resize-handle" in css


def test_pah083_layout_shortcuts_and_detached_windows_remain_ephemeral():
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")

    for code in ["KeyP", "KeyO", "KeyK", "KeyE"]:
        assert f"event.code === '{code}'" in js
    assert "event.ctrlKey && event.altKey" in js
    assert "focusWorkspaceEditor" in js

    start = js.index("function persistLayoutPreferences()")
    end = js.index("function effectiveLayoutMax", start)
    persistence_block = js[start:end]
    assert "surfaceWindows" not in persistence_block
    assert "screenX" not in persistence_block
    assert "screenY" not in persistence_block


def test_pah083_aesthetic_hotfix_keeps_tool_heading_single_line_and_terminal_clipped():
    css = (ROOT / "pah" / "web" / "static" / "pah.css").read_text(encoding="utf-8")

    assert ".analysis-heading > div:first-child" in css
    assert "flex-wrap: nowrap;" in css
    assert ".analysis-heading .badge" in css
    assert "text-overflow: ellipsis;" in css
    assert ".terminal-panel.collapsed .terminal-output" in css
    assert ".terminal-panel.collapsed .terminal-input-row { display: none; }" in css


def test_pah084_research_search_is_optional_companion_surface_under_references():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    full_tools = (ROOT / "pah" / "full_tools.py").read_text(encoding="utf-8")

    assert 'id="referencesResearchSearch"' in html
    assert 'data-service-tool="research_search" data-service-action="open"' in html
    assert 'data-mode="research_search"' not in html
    assert "research_search: {kind: 'companion'" in js
    assert "dockable: false" in js
    assert "async function prepareCompanionSurface" in js
    assert "config.kind === 'companion'" in js
    assert '"/api/research-search/launch"' in app
    assert "def research_search_status" in full_tools
    assert "def launch_research_search" in full_tools
    assert '"owner": "references"' in full_tools
    assert '"window_only": True' in full_tools


def test_pah084_research_search_uses_existing_reference_manager_launch_contract():
    full_tools = (ROOT / "pah" / "full_tools.py").read_text(encoding="utf-8")
    reference_route = (
        ROOT / "modules" / "reference_manager" / "reference_manager" / "web" / "routes" / "research_search_routes.py"
    ).read_text(encoding="utf-8")

    assert '/api/research-search/launch' in reference_route
    assert 'self._servers["references"].url.rstrip("/") + "/api/research-search/launch"' in full_tools
    assert 'modules" / "paper_searcher"' in full_tools


def test_pah085_local_git_remains_compact_optional_and_detachable():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    git_html = (ROOT / "pah" / "web" / "templates" / "git.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    core = (ROOT / "pah" / "core" / "git.py").read_text(encoding="utf-8")

    assert 'id="toolsGitGroup"' in html
    assert 'id="gitMenu"' in html
    assert 'id="gitMenuToggle"' not in html
    assert 'class="mode-launcher git-launcher"' not in html
    assert 'id="gitDialog"' in html
    assert 'id="gitFrame"' in html
    assert 'data-mode="git"' not in html
    assert "git: {kind: 'local'" in js
    assert "async function refreshGitStatus" in js
    assert "async function enableLocalGit" in js
    assert "openWindowSurface('git')" in js
    assert "detachSurface('git')" in js
    assert 'LOCAL ONLY' in git_html
    assert '/api/git/status' in app
    assert '/api/git/init' in app
    assert 'class LocalGitService' in core


def test_pah086_remote_git_is_explicit_backend_guarded_and_nested_under_tools():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    git_html = (ROOT / "pah" / "web" / "templates" / "git.html").read_text(encoding="utf-8")
    git_js = (ROOT / "pah" / "web" / "static" / "git.js").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    core = (ROOT / "pah" / "core" / "git.py").read_text(encoding="utf-8")

    assert '<details id="toolsGitGroup"' in html
    assert '<summary><span>Git</span>' in html
    assert 'id="gitMenuToggle"' not in html
    assert 'data-git-tab="remotes"' in git_html
    assert 'id="gitEnableRemote"' in git_html
    assert 'id="gitDisableRemote"' in git_html
    assert "badge.textContent = remoteEnabled ? 'MANUAL REMOTE' : 'LOCAL ONLY'" in git_js
    assert "setConnectivity('manual_remote')" in git_js
    assert "setConnectivity('local_only')" in git_js
    assert "Pull · FF only" in git_html
    assert "Update Tracked Branches" in git_html

    for route in [
        "/api/git/connectivity",
        "/api/git/remotes",
        "/api/git/fetch",
        "/api/git/pull",
        "/api/git/push",
        "/api/git/clone",
        "/api/git/submodules/update",
    ]:
        assert route in app

    assert 'CONNECTIVITY_LOCAL = "local_only"' in core
    assert 'CONNECTIVITY_REMOTE = "manual_remote"' in core
    assert "def _require_remote_enabled" in core
    assert "self._require_remote_enabled()" in core
    assert '["pull", "--ff-only"' in core
    assert '["submodule", "update", "--init", "--recursive", "--remote", "--merge"]' in core
    assert "self._connectivity_mode = self.CONNECTIVITY_LOCAL" in core


def test_pah087_overleaf_import_is_documents_side_transient_and_local_first():
    html = (ROOT / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    app = (ROOT / "pah" / "app.py").read_text(encoding="utf-8")
    overleaf = (ROOT / "pah" / "integrations" / "overleaf.py").read_text(encoding="utf-8")

    assert 'id="documentsOverleafImport"' in html
    assert 'id="overleafDialog"' in html
    assert 'id="overleafZipFile"' in html
    assert 'id="overleafGitUrl"' in html
    assert 'data-mode="overleaf"' not in html
    for function_name in [
        "openOverleafDialog",
        "importOverleafZip",
        "cloneOverleafGit",
        "renderOverleafImportResult",
    ]:
        assert f"function {function_name}" in js or f"async function {function_name}" in js
    assert "/api/overleaf/import-zip" in app
    assert "/api/overleaf/clone" in app
    assert "git_service.clone(" in app
    assert "zipfile.ZipFile" in overleaf
    assert '"acquisition_mode": "zip"' in overleaf
    assert "git init" not in overleaf.lower()
