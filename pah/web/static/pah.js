(() => {
  const $ = id => document.getElementById(id);
  const editor = $('editor');
  const highlightCode = $('highlightCode');
  const highlightLayer = $('highlightLayer');

  const state = {
    workspace: null,
    tabs: [],
    active: null,
    selectedTree: null,
    terminalId: null,
    terminalPoll: null,
    analyzer: {
      available: false,
      analyzed: false,
      stale: false,
      generation: 0,
      summary: null,
      overview: null,
      functions: [],
      selectedId: null,
      selectedEntity: null,
    },
    documents: {
      available: false,
      compilers: {latexmk: false, tectonic: false},
      files: [],
      normalizedDiagram: null,
    },
    references: {
      available: false,
      configured: false,
      libraryRoot: null,
      summary: null,
      papers: [],
      statuses: [],
      topics: [],
      selected: null,
    },
    mode: 'workspace',
    git: {git_available: false, workspace: null, is_repository: false, repository_root: null, branch: null, detached: false, head: null, changes: [], staged_count: 0, unstaged_count: 0, untracked_count: 0, submodules: [], remotes: [], tracking: null, connectivity_mode: 'local_only', local_only: true, remote_enabled: false},
    overleaf: {lastImport: null, sync: null},
    fullTools: {
      analysis: {available: false, url: null, error: null},
      documents: {available: false, url: null, error: null},
      references: {available: false, url: null, error: null},
      research_search: {available: false, url: null, error: null, owner: 'references', window_only: true},
    },
    surfaceWindows: {
      analysis: {popup: null},
      documents: {popup: null},
      references: {popup: null},
      research_search: {popup: null},
      git: {popup: null},
      terminal: {popup: null},
    },
    surfaceWindowWatch: null,
    panes: {
      project: {collapsed: false},
      context: {collapsed: false},
      terminal: {collapsed: false},
    },
    layout: {
      projectWidth: 265,
      contextWidth: 360,
      terminalHeight: 250,
      lastMode: 'workspace',
    },
  };

  async function api(url, options = {}) {
    const response = await fetch(url, {
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
      ...options,
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  }

  async function apiForm(url, formData) {
    const response = await fetch(url, {method: 'POST', body: formData});
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  }

  function toast(message, error = false) {
    const el = $('toast');
    el.textContent = message;
    el.classList.toggle('error', error);
    el.classList.add('show');
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove('show'), 2400);
  }

  function activeTab() { return state.tabs.find(tab => tab.path === state.active) || null; }
  function basename(path) { return String(path || '').split('/').pop(); }
  function parentPath(path) { const parts = String(path || '').split('/'); parts.pop(); return parts.join('/'); }
  function fmt(value, digits = 3) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : String(value ?? '');
  }
  function setText(id, text) { $(id).textContent = text; }
  function clearElement(id) { $(id).replaceChildren(); }

  // ---------------------------------------------------------------------------
  // Local workspace-layout preferences
  // ---------------------------------------------------------------------------
  const LAYOUT_STORAGE_KEY = 'pah.workspace.layout.v1';
  const layoutDefaults = Object.freeze({
    projectWidth: 265,
    contextWidth: 360,
    terminalHeight: 250,
    lastMode: 'workspace',
  });
  const layoutSizeConfig = Object.freeze({
    project: {stateKey: 'projectWidth', targetId: 'workspaceMode', cssVar: '--project-pane-expanded-width', min: 180, max: 480},
    context: {stateKey: 'contextWidth', targetId: 'workspaceMode', cssVar: '--context-pane-expanded-width', min: 260, max: 560},
    terminal: {stateKey: 'terminalHeight', targetId: 'app', cssVar: '--terminal-pane-height', min: 120, max: 520},
  });

  function clampNumber(value, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) return min;
    return Math.min(max, Math.max(min, number));
  }

  function loadLayoutPreferences() {
    let saved = null;
    try {
      saved = JSON.parse(window.localStorage.getItem(LAYOUT_STORAGE_KEY) || 'null');
    } catch (_) {
      saved = null;
    }
    if (!saved || typeof saved !== 'object') return;

    for (const name of Object.keys(state.panes)) {
      if (typeof saved.panes?.[name] === 'boolean') state.panes[name].collapsed = saved.panes[name];
    }
    for (const [name, config] of Object.entries(layoutSizeConfig)) {
      const savedValue = saved.sizes?.[config.stateKey];
      if (Number.isFinite(Number(savedValue))) {
        state.layout[config.stateKey] = clampNumber(savedValue, config.min, config.max);
      }
    }
    if (['workspace', 'analysis', 'documents', 'references'].includes(saved.lastMode)) {
      state.layout.lastMode = saved.lastMode;
    }
  }

  function persistLayoutPreferences() {
    const payload = {
      version: 1,
      panes: Object.fromEntries(Object.entries(state.panes).map(([name, pane]) => [name, Boolean(pane.collapsed)])),
      sizes: {
        projectWidth: Math.round(state.layout.projectWidth),
        contextWidth: Math.round(state.layout.contextWidth),
        terminalHeight: Math.round(state.layout.terminalHeight),
      },
      lastMode: state.layout.lastMode,
    };
    try {
      window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(payload));
    } catch (_) {
      // Layout persistence is a convenience only; PAH must remain usable when
      // browser storage is disabled or unavailable.
    }
  }

  function effectiveLayoutMax(name, config) {
    if (name === 'terminal') return Math.min(config.max, Math.max(config.min, window.innerHeight - 180));
    const width = $('workspaceMode')?.getBoundingClientRect().width || window.innerWidth;
    const minimumEditor = window.innerWidth <= 850 ? 300 : (window.innerWidth <= 1150 ? 330 : 360);
    const otherName = name === 'project' ? 'context' : 'project';
    const otherConfig = layoutSizeConfig[otherName];
    const otherPanel = $(paneConfig?.[otherName]?.panelId);
    const otherHiddenByCss = otherPanel ? window.getComputedStyle(otherPanel).display === 'none' : false;
    const otherWidth = (state.panes[otherName].collapsed || otherHiddenByCss)
      ? 34
      : Number(state.layout[otherConfig.stateKey] || layoutDefaults[otherConfig.stateKey]);
    return Math.min(config.max, Math.max(config.min, width - otherWidth - minimumEditor));
  }

  function setLayoutPaneSize(name, value, {persist = false} = {}) {
    const config = layoutSizeConfig[name];
    if (!config) return;
    const max = effectiveLayoutMax(name, config);
    const size = clampNumber(value, config.min, max);
    state.layout[config.stateKey] = size;
    $(config.targetId)?.style.setProperty(config.cssVar, `${Math.round(size)}px`);
    if (persist) persistLayoutPreferences();
  }

  function applyLayoutSizes() {
    for (const [name, config] of Object.entries(layoutSizeConfig)) {
      setLayoutPaneSize(name, state.layout[config.stateKey], {persist: false});
    }
  }

  function beginPaneResize(name, event) {
    const config = layoutSizeConfig[name];
    if (!config || state.panes[name]?.collapsed) return;
    if (name === 'terminal' && isSurfaceDetached('terminal')) return;
    event.preventDefault();

    const startX = event.clientX;
    const startY = event.clientY;
    const startSize = Number(state.layout[config.stateKey]);
    const cursorClass = name === 'terminal' ? 'pane-resizing-row' : 'pane-resizing-column';
    document.body.classList.add(cursorClass);

    const onMove = moveEvent => {
      let delta = 0;
      if (name === 'project') delta = moveEvent.clientX - startX;
      else if (name === 'context') delta = startX - moveEvent.clientX;
      else delta = startY - moveEvent.clientY;
      setLayoutPaneSize(name, startSize + delta, {persist: false});
    };
    const onUp = () => {
      document.body.classList.remove(cursorClass);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      persistLayoutPreferences();
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, {once: true});
  }

  function resetWorkspaceLayout() {
    state.layout.projectWidth = layoutDefaults.projectWidth;
    state.layout.contextWidth = layoutDefaults.contextWidth;
    state.layout.terminalHeight = layoutDefaults.terminalHeight;
    for (const pane of Object.values(state.panes)) pane.collapsed = false;
    renderWorkspacePanes();
    applyLayoutSizes();
    persistLayoutPreferences();
    closeServiceMenus();
    toast('Workspace layout reset');
  }

  async function focusWorkspaceEditor() {
    if (state.mode !== 'workspace') await setMode('workspace');
    const tab = activeTab();
    if (tab) editor.focus();
    else $('workspacePath')?.focus();
  }

  async function restoreLastMode() {
    const mode = state.layout.lastMode;
    if (mode === 'workspace' || !state.workspace) return;
    await setMode(mode);
  }

  // ---------------------------------------------------------------------------
  // Flexible workspace pane state
  // ---------------------------------------------------------------------------
  const paneConfig = {
    project: {
      panelId: 'projectPane',
      toggleId: 'projectPaneToggle',
      layoutId: 'workspaceMode',
      layoutClass: 'project-pane-collapsed',
      expandedText: '‹',
      collapsedText: '›',
      expandedTitle: 'Collapse project tree',
      collapsedTitle: 'Show project tree',
    },
    context: {
      panelId: 'contextPane',
      toggleId: 'contextPaneToggle',
      layoutId: 'workspaceMode',
      layoutClass: 'context-pane-collapsed',
      expandedText: '›',
      collapsedText: '‹',
      expandedTitle: 'Collapse project tools',
      collapsedTitle: 'Show project tools',
    },
    terminal: {
      panelId: 'terminalPanel',
      toggleId: 'terminalToggle',
      layoutId: 'app',
      layoutClass: 'terminal-collapsed',
      expandedText: 'Hide',
      collapsedText: 'Show',
      expandedTitle: 'Collapse terminal',
      collapsedTitle: 'Show terminal',
    },
  };

  function renderPaneState(name) {
    const config = paneConfig[name];
    const pane = state.panes[name];
    if (!config || !pane) return;
    const panel = $(config.panelId);
    const toggle = $(config.toggleId);
    const layout = $(config.layoutId);
    if (panel) panel.classList.toggle('collapsed', pane.collapsed);
    if (layout && config.layoutClass) layout.classList.toggle(config.layoutClass, pane.collapsed);
    if (toggle) {
      toggle.textContent = pane.collapsed ? config.collapsedText : config.expandedText;
      toggle.title = pane.collapsed ? config.collapsedTitle : config.expandedTitle;
      toggle.setAttribute('aria-expanded', String(!pane.collapsed));
    }
    const indicator = document.querySelector(`[data-pane-indicator="${name}"]`);
    if (indicator) {
      indicator.textContent = (name === 'terminal' && isSurfaceDetached('terminal')) ? 'Detached' : (pane.collapsed ? 'Collapsed' : 'Shown');
    }
  }

  function setPaneCollapsed(name, collapsed, {persist = true} = {}) {
    if (!state.panes[name]) return;
    state.panes[name].collapsed = Boolean(collapsed);
    renderPaneState(name);
    if (persist) persistLayoutPreferences();
  }

  function togglePane(name) {
    if (!state.panes[name]) return;
    setPaneCollapsed(name, !state.panes[name].collapsed);
  }

  function renderWorkspacePanes() {
    for (const name of Object.keys(paneConfig)) renderPaneState(name);
  }

  // ---------------------------------------------------------------------------
  // Compact service/tool launcher menus
  // ---------------------------------------------------------------------------
  function setServiceMenuOpen(menuId, open) {
    const menu = $(menuId);
    if (!menu) return;
    menu.classList.toggle('hidden', !open);
    const toggle = document.querySelector(`[data-menu-toggle="${menuId}"]`);
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.classList.toggle('menu-open', open);
    }
  }

  function closeServiceMenus(exceptId = null) {
    document.querySelectorAll('.service-menu').forEach(menu => {
      if (menu.id !== exceptId) {
        setServiceMenuOpen(menu.id, false);
        menu.querySelectorAll('details[open]').forEach(detail => detail.removeAttribute('open'));
      }
    });
  }

  function toggleServiceMenu(menuId) {
    const menu = $(menuId);
    if (!menu) return;
    const willOpen = menu.classList.contains('hidden');
    closeServiceMenus(menuId);
    setServiceMenuOpen(menuId, willOpen);
    if (willOpen && menuId === 'toolsMenu') refreshGitStatus().catch(() => {});
  }
  function functionLabel(id) {
    const item = state.analyzer.functions.find(row => row.id === id);
    return item ? (item.qualified_name || item.name) : id;
  }

  // ---------------------------------------------------------------------------
  // Generic dock / detach window controller
  // ---------------------------------------------------------------------------
  const windowSurfaceConfig = {
    analysis: {kind: 'hosted', title: 'Code Analyzer', width: 1220, height: 820},
    documents: {kind: 'hosted', title: 'Document Workbench', width: 1220, height: 820},
    references: {kind: 'hosted', title: 'Reference Manager', width: 1220, height: 820},
    research_search: {kind: 'companion', title: 'Research Search', width: 1280, height: 900, dockable: false},
    git: {kind: 'local', title: 'Git', width: 1180, height: 820, dockable: true, url: '/git', dialogId: 'gitDialog', frameId: 'gitFrame'},
    terminal: {kind: 'terminal', title: 'PAH Terminal', width: 980, height: 620},
  };

  function toolFrameId(tool) {
    return `${tool}ToolFrame`;
  }

  function toolStatusId(tool) {
    return `${tool}ToolStatus`;
  }

  function surfaceConfig(name) {
    return windowSurfaceConfig[name] || null;
  }

  function rawSurfaceWindow(name) {
    return state.surfaceWindows[name]?.popup || null;
  }

  function surfaceWindow(name) {
    const popup = rawSurfaceWindow(name);
    if (!popup || popup.closed) return null;
    return popup;
  }

  function isSurfaceDetached(name) {
    return Boolean(surfaceWindow(name));
  }

  function surfacePresentationState(name) {
    const config = surfaceConfig(name);
    if (!config) return 'closed';
    if (isSurfaceDetached(name)) return 'detached';
    if (name === 'terminal') return state.panes.terminal.collapsed ? 'collapsed' : 'docked';
    if (config.kind === 'local') return $(config.dialogId)?.open ? 'docked' : 'closed';
    return state.mode === name ? 'docked' : 'closed';
  }

  function renderWindowSurfaceState() {
    for (const tool of ['analysis', 'documents', 'references']) {
      const detached = surfacePresentationState(tool) === 'detached';
      const modeButton = document.querySelector(`.mode-button[data-mode="${tool}"]`);
      if (modeButton) {
        modeButton.classList.toggle('detached', detached);
        const info = state.fullTools[tool] || {};
        modeButton.title = detached
          ? `Focus detached ${tool} window`
          : (info.available ? `Open full ${tool} workspace` : (info.error || `${tool} module unavailable`));
      }
      const detachButton = document.querySelector(`[data-tool-detach="${tool}"]`);
      if (detachButton) {
        detachButton.textContent = detached ? 'Focus Window' : 'Open in New Window';
        detachButton.disabled = !(state.fullTools[tool]?.available);
      }
    }

    const researchSearchInfo = state.fullTools.research_search || {};
    const researchSearchDetached = surfacePresentationState('research_search') === 'detached';
    const researchSearchButton = $('referencesResearchSearch');
    const researchSearchStatus = $('researchSearchMenuStatus');
    if (researchSearchButton) {
      researchSearchButton.disabled = !researchSearchInfo.available;
      const label = researchSearchButton.querySelector('span:first-child');
      if (label) label.textContent = researchSearchDetached ? 'Focus Research Search' : 'Research Search';
      researchSearchButton.title = researchSearchInfo.available
        ? (researchSearchDetached ? 'Focus the existing Research Search window' : 'Open Research Search in a separate window')
        : (researchSearchInfo.error || 'Research Search unavailable');
    }
    if (researchSearchStatus) {
      researchSearchStatus.textContent = researchSearchDetached
        ? 'Detached'
        : (researchSearchInfo.available ? 'Open' : 'Unavailable');
    }

    const gitState = surfacePresentationState('git');
    const gitOpen = $('gitOpenSurface');
    const gitWindow = $('gitOpenWindow');
    if (gitOpen) {
      const label = gitOpen.querySelector('span:first-child');
      const meta = gitOpen.querySelector('.service-menu-meta');
      if (label) label.textContent = gitState === 'detached' ? 'Focus Git' : 'Open Git';
      if (meta) meta.textContent = gitState === 'detached' ? 'Detached' : (gitState === 'docked' ? 'Open' : 'Open');
      gitOpen.disabled = !state.workspace;
    }
    if (gitWindow) {
      const label = gitWindow.querySelector('span:first-child');
      const meta = gitWindow.querySelector('.service-menu-meta');
      if (label) label.textContent = gitState === 'detached' ? 'Focus Git Window' : 'Open in New Window';
      if (meta) meta.textContent = gitState === 'detached' ? 'Detached' : 'Detach';
      gitWindow.disabled = !state.workspace;
    }

    const terminalIsDetached = surfacePresentationState('terminal') === 'detached';
    const terminalButton = $('terminalDetach');
    if (terminalButton) terminalButton.textContent = terminalIsDetached ? 'Focus window' : 'Detach';
    const terminalWindowButton = $('toolsTerminalWindow');
    if (terminalWindowButton) {
      const label = terminalWindowButton.querySelector('span:first-child');
      const meta = terminalWindowButton.querySelector('.service-menu-meta');
      if (label) label.textContent = terminalIsDetached ? 'Focus Terminal Window' : 'Terminal Window';
      if (meta) meta.textContent = terminalIsDetached ? 'Detached' : 'Open';
    }
    $('terminalPanel')?.classList.toggle('detached', terminalIsDetached);
    renderPaneState('terminal');
  }

  function popupFeatures(width = 1220, height = 820) {
    const left = Math.max(0, Math.round((window.screenX || 0) + 80));
    const top = Math.max(0, Math.round((window.screenY || 0) + 70));
    return `popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`;
  }

  function writeDetachedHostedShell(popup, tool, url) {
    const config = surfaceConfig(tool);
    const title = config?.title || tool;
    popup.document.open();
    const dockable = config?.dockable !== false;
    const returnLabel = dockable ? 'Reattach' : 'Close';
    const contextLabel = dockable ? 'Detached from PAH' : 'PAH companion service';
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PAH — ${title}</title><style>html,body{margin:0;height:100%;background:#111318;color:#d9dee7;font-family:Inter,system-ui,sans-serif}body{display:grid;grid-template-rows:36px minmax(0,1fr)}header{display:flex;align-items:center;gap:10px;padding:4px 8px;background:#171a21;border-bottom:1px solid #303642;font-size:12px}header strong{flex:0 0 auto}header span{flex:1;color:#8993a3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}button{background:#252b35;color:#d9dee7;border:1px solid #303642;border-radius:5px;padding:4px 9px;cursor:pointer}button:hover{background:#303744}iframe{width:100%;height:100%;border:0;background:#fff}</style></head><body><header><strong>${title}</strong><span>${contextLabel}</span><button id="reattachButton">${returnLabel}</button></header><iframe id="detachedFrame" title="${title}"></iframe></body></html>`);
    popup.document.close();
    const frame = popup.document.getElementById('detachedFrame');
    const separator = url.includes('?') ? '&' : '?';
    frame.src = `${url}${separator}pahDetached=${Date.now()}`;
    popup.document.getElementById('reattachButton').onclick = () => reattachSurface(tool, {activate: dockable});
    popup.focus();
  }

  async function syncReturnedTool(mode) {
    if (!['analysis', 'documents', 'references'].includes(mode)) return;
    try {
      await api('/api/full-tools/return', {method: 'POST', body: JSON.stringify({mode})});
    } catch (error) {
      toast(`Full-tool sync warning: ${error.message}`, true);
    }
    await refreshTree().catch(() => {});
    await refreshCleanTabsFromDisk();
    await refreshAnalyzerStatus().catch(() => {});
    await refreshReferenceStatus().catch(() => {});
  }

  async function prepareHostedSurface(name, popup) {
    await refreshFullTools();
    const info = state.fullTools[name];
    if (!info?.available || !info.url) {
      popup.close();
      toast(info?.error || `${name} module is unavailable.`, true);
      return false;
    }
    state.surfaceWindows[name].popup = popup;
    writeDetachedHostedShell(popup, name, info.url);
    const frame = $(toolFrameId(name));
    if (frame) {
      frame.src = 'about:blank';
      delete frame.dataset.toolUrl;
    }
    if (state.mode === name) await setMode('workspace');
    return true;
  }

  async function prepareCompanionSurface(name, popup) {
    if (name !== 'research_search') return false;
    try {
      const data = await api('/api/research-search/launch', {method: 'POST', body: '{}'});
      const url = data.url || state.fullTools.research_search?.url;
      if (!url) throw new Error('Research Search did not provide a launch URL.');
      state.fullTools.research_search = {
        ...(state.fullTools.research_search || {}),
        available: true,
        url,
        error: null,
        owner: data.owner || 'references',
        window_only: true,
      };
      state.surfaceWindows[name].popup = popup;
      writeDetachedHostedShell(popup, name, url);
      if (!data.already_running) toast('Research Search started');
      return true;
    } catch (error) {
      popup.close();
      toast(`Unable to launch Research Search: ${error.message}`, true);
      return false;
    }
  }

  async function prepareLocalSurface(name, popup) {
    const config = surfaceConfig(name);
    if (!config || config.kind !== 'local' || !state.workspace) {
      popup.close();
      if (!state.workspace) toast('Open a workspace first', true);
      return false;
    }
    state.surfaceWindows[name].popup = popup;
    const dialog = $(config.dialogId);
    if (dialog?.open) dialog.close();
    writeDetachedHostedShell(popup, name, config.url);
    return true;
  }

  async function prepareTerminalSurface(popup) {
    if (!state.workspace) {
      popup.close();
      toast('Open a workspace first', true);
      return false;
    }
    if (!state.terminalId) await startTerminal();
    state.surfaceWindows.terminal.popup = popup;
    clearInterval(state.terminalPoll);
    state.terminalPoll = null;
    writeDetachedTerminalShell(popup);
    setPaneCollapsed('terminal', true, {persist: false});
    return true;
  }

  async function detachSurface(name) {
    const config = surfaceConfig(name);
    if (!config) return;
    const existing = surfaceWindow(name);
    if (existing) { existing.focus(); return; }

    // Open synchronously from the click event so browser popup blocking does not
    // turn a normal detach action into a silent failure.
    const popup = window.open('', `pah-detached-${name}`, popupFeatures(config.width, config.height));
    if (!popup) {
      toast('The browser blocked the detached window. Allow popups for this local PAH site.', true);
      return;
    }
    popup.document.title = `PAH — Preparing ${config.title}`;

    let prepared = false;
    if (config.kind === 'hosted') prepared = await prepareHostedSurface(name, popup);
    else if (config.kind === 'companion') prepared = await prepareCompanionSurface(name, popup);
    else if (config.kind === 'local') prepared = await prepareLocalSurface(name, popup);
    else if (config.kind === 'terminal') prepared = await prepareTerminalSurface(popup);
    if (!prepared) return;

    renderWindowSurfaceState();
    ensureWindowSurfaceWatch();
  }

  async function activateDockedSurface(name) {
    const config = surfaceConfig(name);
    if (!config) return;
    if (config.kind === 'hosted') {
      await setMode(name);
      return;
    }
    if (config.kind === 'companion') {
      await detachSurface(name);
      return;
    }
    if (config.kind === 'local') {
      if (!state.workspace) return toast('Open a workspace first', true);
      const dialog = $(config.dialogId);
      const frame = $(config.frameId);
      if (frame && (!frame.src || frame.src.endsWith('about:blank'))) frame.src = `${config.url}?pah=${Date.now()}`;
      if (dialog && !dialog.open) dialog.showModal();
      renderWindowSurfaceState();
      return;
    }
    if (name === 'terminal') {
      setPaneCollapsed('terminal', false);
      $('terminalInput')?.focus();
    }
  }

  async function reattachSurface(name, {activate = true, expand = true, closeWindow = true} = {}) {
    const config = surfaceConfig(name);
    if (!config) return;
    const popup = rawSurfaceWindow(name);

    if (config.kind === 'terminal') {
      if (popup && popup._pahTerminalPoll) popup.clearInterval(popup._pahTerminalPoll);
      clearInterval(state.terminalPoll);
      state.terminalPoll = state.terminalId ? setInterval(pollTerminal, 300) : null;
      if (expand) setPaneCollapsed('terminal', false, {persist: false});
    }

    state.surfaceWindows[name].popup = null;
    if (closeWindow && popup && !popup.closed) popup.close();
    renderWindowSurfaceState();

    if (config.kind === 'hosted') await syncReturnedTool(name);
    if (activate) await activateDockedSurface(name);
  }

  async function handleSurfaceWindowClosed(name) {
    const popup = rawSurfaceWindow(name);
    if (!popup || !popup.closed) return;
    await reattachSurface(name, {activate: false, expand: false, closeWindow: false});
  }

  function ensureWindowSurfaceWatch() {
    if (state.surfaceWindowWatch) return;
    state.surfaceWindowWatch = window.setInterval(() => {
      for (const name of Object.keys(windowSurfaceConfig)) {
        handleSurfaceWindowClosed(name).catch(() => {});
      }
    }, 700);
  }

  function refreshDetachedSurface(name) {
    const popup = surfaceWindow(name);
    const info = state.fullTools[name];
    if (!popup || !info?.available || !info.url) return;
    const frame = popup.document.getElementById('detachedFrame');
    if (!frame) return;
    const separator = info.url.includes('?') ? '&' : '?';
    frame.src = `${info.url}${separator}pahDetached=${Date.now()}`;
  }

  async function openWindowSurface(name, {detached = false} = {}) {
    closeServiceMenus();
    // Workspace is a normal docked PAH mode, not a detachable service surface.
    // Route it directly through setMode so the Workspace button always returns
    // from Analysis/Documents/References to the editor workspace.
    if (name === 'workspace') {
      await setMode('workspace');
      return;
    }
    const config = surfaceConfig(name);
    if (!config) return;
    if (detached || config.kind === 'companion') {
      await detachSurface(name);
      return;
    }
    if (isSurfaceDetached(name)) {
      surfaceWindow(name)?.focus();
      return;
    }
    await activateDockedSurface(name);
  }

  async function reloadTool(tool) {
    closeServiceMenus();
    await refreshFullTools();
    const info = state.fullTools[tool];
    if (!info?.available || !info.url) {
      toast(info?.error || `${tool} module is unavailable.`, true);
      return;
    }
    if (isSurfaceDetached(tool)) refreshDetachedSurface(tool);
    else loadToolFrame(tool, true);
  }

  function renderFullToolStatus() {
    for (const tool of ['analysis', 'documents', 'references']) {
      const info = state.fullTools[tool] || {};
      const button = document.querySelector(`.mode-button[data-mode="${tool}"]`);
      if (button) {
        button.classList.toggle('unavailable', !info.available);
        button.title = info.available ? `Open full ${tool} workspace` : (info.error || `${tool} module unavailable`);
      }
      document.querySelectorAll(`[data-service-tool="${tool}"], [data-tool-detach="${tool}"], [data-tool-reload="${tool}"]`).forEach(action => {
        action.disabled = !info.available;
      });
      const status = $(toolStatusId(tool));
      if (status) {
        if (info.available) {
          if (tool === 'analysis' && info.bound_workspace) status.textContent = info.bound_workspace;
          else if (tool === 'documents' && info.bound_workspace) status.textContent = info.bound_workspace;
          else if (tool === 'references' && info.library_root) status.textContent = info.library_root;
          else status.textContent = 'Ready';
          if (isSurfaceDetached(tool)) status.textContent += ' · detached';
        } else {
          status.textContent = info.error || 'Module unavailable';
        }
      }
    }
    const researchSearchInfo = state.fullTools.research_search || {};
    const researchSearchAction = $('referencesResearchSearch');
    if (researchSearchAction) researchSearchAction.disabled = !researchSearchInfo.available;
    renderWindowSurfaceState();
  }

  async function refreshFullTools({reloadActive = false} = {}) {
    try {
      const data = await api('/api/full-tools/status');
      state.fullTools = {...state.fullTools, ...(data.tools || {})};
      renderFullToolStatus();
      if (reloadActive) {
        for (const tool of ['analysis', 'documents', 'references']) {
          if (isSurfaceDetached(tool)) refreshDetachedSurface(tool);
        }
      }
      if (reloadActive && state.mode !== 'workspace' && !isSurfaceDetached(state.mode)) loadToolFrame(state.mode, true);
    } catch (error) {
      for (const tool of ['analysis', 'documents', 'references', 'research_search']) {
        state.fullTools[tool] = {available: false, url: null, error: error.message};
      }
      renderFullToolStatus();
    }
  }

  function renderGitLauncher() {
    const info = state.git || {};
    const branch = $('gitMenuBranch');
    const status = $('gitMenuStatus');
    const tracking = $('gitMenuTracking');
    const init = $('gitInitRepository');
    if (branch) {
      if (!state.workspace) branch.textContent = 'No workspace';
      else if (!info.git_available) branch.textContent = 'Git unavailable';
      else if (!info.is_repository) branch.textContent = 'Not enabled';
      else branch.textContent = info.branch || (info.detached ? 'Detached HEAD' : 'Local repository');
    }
    if (status) {
      if (!info.git_available) status.textContent = 'Unavailable';
      else status.textContent = info.remote_enabled ? 'Manual remote' : 'Local only';
    }
    if (tracking) {
      const track = info.tracking || null;
      if (track?.upstream) {
        const ahead = Number.isInteger(track.ahead) ? track.ahead : '?';
        const behind = Number.isInteger(track.behind) ? track.behind : '?';
        tracking.textContent = `${track.upstream} · ↑${ahead} ↓${behind}`;
      } else {
        const count = (info.remotes || []).length;
        tracking.textContent = count ? `${count} remote${count === 1 ? '' : 's'}` : 'No remote configured';
      }
    }
    if (init) {
      init.disabled = !state.workspace || !info.git_available || info.is_repository;
      const meta = init.querySelector('.service-menu-meta');
      if (meta) meta.textContent = info.is_repository ? 'Enabled' : 'git init';
    }
    $('toolsGitGroup')?.classList.toggle('unavailable', Boolean(state.workspace && !info.git_available));
    const dialogStatus = $('gitDialogStatus');
    if (dialogStatus) {
      const mode = info.remote_enabled ? 'manual remote' : 'local only';
      dialogStatus.textContent = info.is_repository
        ? `${info.branch || 'local'} · ${(info.changes || []).length} changes · ${mode}`
        : mode;
    }
    renderWindowSurfaceState();
  }

  async function refreshGitStatus() {
    try {
      const data = await api('/api/git/status');
      state.git = data;
    } catch (error) {
      state.git = {...state.git, git_available: false, is_repository: false, error: error.message};
    }
    renderGitLauncher();
    renderOverleafConnectivity();
    return state.git;
  }

  async function enableLocalGit() {
    closeServiceMenus();
    if (!state.workspace) return toast('Open a workspace first', true);
    if (!window.confirm('Enable Local Git for this workspace? This creates a local .git repository only and does not configure or contact a remote.')) return;
    try {
      const data = await api('/api/git/init', {method: 'POST', body: '{}'});
      state.git = data;
      renderGitLauncher();
      toast('Local Git enabled for this workspace');
      await openWindowSurface('git');
      const frame = $('gitFrame');
      if (frame) frame.src = `/git?pah=${Date.now()}`;
    } catch (error) {
      toast(error.message, true);
    }
  }

  window._pahGitHost = {
    hasDirtyBuffers: () => state.tabs.some(tab => tab.dirty),
    statusChanged: () => refreshGitStatus(),
    worktreeChanged: async () => {
      await refreshTree().catch(() => {});
      await refreshCleanTabsFromDisk();
      await refreshAnalyzerStatus().catch(() => {});
      await refreshDocumentStatus().catch(() => {});
      await refreshReferenceStatus().catch(() => {});
      await refreshGitStatus().catch(() => {});
    },
    openWorkspacePath: async path => {
      await openWorkspace(path);
    },
  };

  // ---------------------------------------------------------------------------
  // Overleaf project import (Documents-side convenience)
  // ---------------------------------------------------------------------------
  function renderOverleafConnectivity() {
    const badge = $('overleafGitConnectivity');
    const enable = $('overleafEnableRemote');
    const clone = $('overleafCloneGit');
    const available = state.git?.git_available !== false;
    const enabled = available && Boolean(state.git?.remote_enabled);
    if (badge) {
      badge.textContent = available ? (enabled ? 'MANUAL REMOTE' : 'LOCAL ONLY') : 'GIT UNAVAILABLE';
      badge.classList.toggle('remote', enabled);
    }
    if (enable) {
      enable.textContent = enabled ? 'Manual Remote Enabled' : 'Enable Manual Remote';
      enable.disabled = !available || enabled;
    }
    if (clone) clone.disabled = !available || !enabled;
  }

  async function openOverleafDialog() {
    closeServiceMenus();
    await refreshGitStatus();
    renderOverleafConnectivity();
    $('overleafDialog')?.showModal();
  }

  async function enableOverleafManualRemote() {
    if (state.git?.remote_enabled) return;
    const ok = window.confirm('Enable Manual Remote Git for this PAH session? This permits Overleaf Git clone/sync only when you explicitly click a remote action. Credentials remain with Git/your credential helper.');
    if (!ok) return;
    const data = await api('/api/git/connectivity', {method: 'POST', body: JSON.stringify({mode: 'manual_remote'})});
    state.git = {...state.git, ...data};
    renderGitLauncher();
    renderOverleafConnectivity();
    toast('Manual Remote enabled for this workspace session.');
  }

  function appendOverleafSummaryCell(holder, label, value, {wide = false, code = false} = {}) {
    const cell = document.createElement('div');
    if (wide) cell.className = 'wide';
    const caption = document.createElement('span');
    caption.textContent = label;
    const content = document.createElement(code ? 'code' : 'strong');
    content.textContent = String(value ?? '—');
    content.title = content.textContent;
    cell.append(caption, content);
    holder.appendChild(cell);
  }

  function renderOverleafImportResult(data) {
    state.overleaf.lastImport = data;
    const result = $('overleafImportResult');
    const holder = $('overleafImportSummary');
    holder.replaceChildren();
    const project = data.project || {};
    const counts = project.counts || {};
    appendOverleafSummaryCell(holder, 'TeX files', counts.tex || 0);
    appendOverleafSummaryCell(holder, 'BibTeX files', counts.bib || 0);
    appendOverleafSummaryCell(holder, 'Figures', counts.figures || 0);
    appendOverleafSummaryCell(holder, 'Support files', counts.support || 0);
    appendOverleafSummaryCell(holder, 'Likely main document', project.likely_main || 'Not detected', {wide: true, code: true});
    appendOverleafSummaryCell(holder, 'Local project directory', data.destination || project.root || '—', {wide: true, code: true});
    if ((project.bib_files || []).length) {
      appendOverleafSummaryCell(holder, 'Detected bibliography', project.bib_files.join(', '), {wide: true, code: true});
    }
    $('overleafImportMode').textContent = data.acquisition_mode === 'git' ? 'Git-backed' : 'Local ZIP';
    result.classList.remove('hidden');
  }

  async function importOverleafZip() {
    const input = $('overleafZipFile');
    const file = input?.files?.[0];
    const destination = $('overleafZipDestination').value.trim();
    if (!file) return toast('Choose an Overleaf source ZIP.', true);
    if (!destination) return toast('Choose a destination directory.', true);
    const button = $('overleafImportZip');
    button.disabled = true;
    button.textContent = 'Importing…';
    try {
      const form = new FormData();
      form.append('archive', file, file.name);
      form.append('destination', destination);
      const data = await apiForm('/api/overleaf/import-zip', form);
      renderOverleafImportResult(data);
      toast('Overleaf source ZIP imported locally.');
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = 'Import ZIP';
    }
  }

  async function cloneOverleafGit() {
    if (!state.git?.remote_enabled) return toast('Enable Manual Remote before cloning an Overleaf Git project.', true);
    const url = $('overleafGitUrl').value.trim();
    const destination = $('overleafGitDestination').value.trim();
    const branch = $('overleafGitBranch').value.trim();
    if (!url || !destination) return toast('Enter the Overleaf Git URL and destination directory.', true);
    if (!window.confirm(`Clone the Overleaf Git project into ${destination}? This is an explicit network-capable Git operation.`)) return;
    const button = $('overleafCloneGit');
    button.disabled = true;
    button.textContent = 'Cloning…';
    try {
      const data = await api('/api/overleaf/clone', {
        method: 'POST',
        body: JSON.stringify({url, destination, branch}),
      });
      renderOverleafImportResult(data);
      toast('Overleaf Git project cloned.');
    } catch (error) {
      toast(error.message, true);
    } finally {
      renderOverleafConnectivity();
      button.textContent = 'Clone Project';
    }
  }

  async function openImportedOverleafProject() {
    const destination = state.overleaf.lastImport?.destination;
    if (!destination) return;
    $('overleafDialog')?.close();
    await openWorkspace(destination);
    toast('Imported project opened in PAH.');
  }

  function overleafRelationLabel(comparison) {
    const stateName = comparison?.state || 'unknown';
    if (stateName === 'up_to_date') return 'Up to date';
    if (stateName === 'ahead') return `Ahead by ${comparison.ahead ?? '?'}`;
    if (stateName === 'behind') return `Behind by ${comparison.behind ?? '?'}`;
    if (stateName === 'diverged') return `Diverged · ↑${comparison.ahead ?? '?'} ↓${comparison.behind ?? '?'}`;
    if (stateName === 'not_fetched') return 'Remote ref not fetched';
    if (stateName === 'detached') return 'Detached HEAD';
    return 'Unknown';
  }

  function renderOverleafSync(data) {
    state.overleaf.sync = data;
    if (data.git) state.git = data.git;
    renderGitLauncher();

    const select = $('overleafSyncRemote');
    const previous = data.selected_remote || select?.value || '';
    if (select) {
      select.replaceChildren();
      const remotes = data.overleaf_remotes || [];
      if (!remotes.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No recognized Overleaf remote';
        select.appendChild(option);
      } else {
        if (!previous && remotes.length > 1) {
          const placeholder = document.createElement('option');
          placeholder.value = '';
          placeholder.textContent = 'Choose an Overleaf remote…';
          select.appendChild(placeholder);
        }
        for (const remote of remotes) {
          const option = document.createElement('option');
          option.value = remote.name;
          option.textContent = `${remote.name} — ${remote.fetch_url || remote.push_url || 'configured remote'}`;
          option.selected = remote.name === previous;
          select.appendChild(option);
        }
        if (!select.value && remotes.length === 1) select.value = remotes[0].name;
      }
    }

    const remoteEnabled = Boolean(data.git?.remote_enabled);
    const connection = $('overleafSyncConnectivity');
    if (connection) {
      connection.textContent = data.git?.git_available === false ? 'GIT UNAVAILABLE' : (remoteEnabled ? 'MANUAL REMOTE' : 'LOCAL ONLY');
      connection.classList.toggle('remote', remoteEnabled);
    }
    const enable = $('overleafSyncEnableRemote');
    if (enable) {
      enable.disabled = data.git?.git_available === false || remoteEnabled;
      enable.textContent = remoteEnabled ? 'Manual Remote Enabled' : 'Enable Manual Remote';
    }

    const holder = $('overleafSyncSummary');
    holder?.replaceChildren();
    const comparison = data.comparison || null;
    appendOverleafSummaryCell(holder, 'Branch', data.git?.branch || '—');
    appendOverleafSummaryCell(holder, 'Overleaf remote', data.selected_remote || 'Not selected');
    appendOverleafSummaryCell(holder, 'Remote relation', overleafRelationLabel(comparison));
    appendOverleafSummaryCell(holder, 'Ahead / behind', comparison?.available ? `↑${comparison.ahead ?? '?'} / ↓${comparison.behind ?? '?'}` : '—');
    appendOverleafSummaryCell(holder, 'Likely main document', data.project?.likely_main || 'Not detected', {wide: true, code: true});
    appendOverleafSummaryCell(holder, 'Unresolved conflicts', (data.git?.conflict_paths || []).length, {wide: false});

    const freshness = $('overleafSyncFreshness');
    const lastFetch = data.sync_events?.last_fetch_at || null;
    if (freshness) freshness.textContent = data.comparison_fresh && lastFetch ? `Fetched ${lastFetch}` : 'Cached · Fetch to verify remote state';

    const warnings = [];
    if (!data.git?.is_repository) warnings.push('The current workspace is not a Git repository. Overleaf Git synchronization is unavailable; ZIP-imported projects can remain local.');
    if (data.git?.is_repository && !(data.overleaf_remotes || []).length) warnings.push('No recognized Overleaf remote was found. Use a remote named “overleaf” or an Overleaf Git URL, configurable under Tools → Git.');
    if ((data.git?.conflict_paths || []).length) warnings.push(`Resolve Git conflicts before synchronization: ${data.git.conflict_paths.join(', ')}`);
    if ((data.git?.changes || []).length) warnings.push('The working tree has local changes. Pull is blocked until those disk changes are committed or otherwise cleaned.');
    if (state.tabs.some(tab => tab.dirty)) warnings.push('PAH has unsaved editor buffers. Save or close them before Pull.');
    if (comparison?.state === 'behind' || comparison?.state === 'diverged') warnings.push('Push is blocked while the cached Overleaf state is behind/diverged. Fetch/Pull and resolve remote changes first.');
    const warning = $('overleafSyncWarning');
    if (warning) {
      warning.textContent = warnings.join(' ');
      warning.classList.toggle('hidden', warnings.length === 0);
    }

    const hasRemote = Boolean(data.selected_remote);
    const networkReady = remoteEnabled && hasRemote && data.git?.is_repository;
    $('overleafSyncFetch').disabled = !networkReady;
    $('overleafSyncPull').disabled = !networkReady || Boolean((data.git?.changes || []).length) || Boolean((data.git?.conflict_paths || []).length) || state.tabs.some(tab => tab.dirty);
    $('overleafSyncPush').disabled = !networkReady || Boolean((data.git?.conflict_paths || []).length) || ['behind', 'diverged'].includes(comparison?.state);

    const ref = data.references || {};
    $('overleafBibReferenceStatus').textContent = ref.configured ? `Library: ${ref.library_root || 'configured'}` : 'Reference library not configured';
    const bibList = $('overleafBibList');
    bibList?.replaceChildren();
    const bibs = data.project?.bib_files || [];
    if (!bibs.length) {
      const empty = document.createElement('div');
      empty.className = 'overleaf-bib-empty';
      empty.textContent = 'No .bib files detected in the current workspace.';
      bibList?.appendChild(empty);
    } else {
      for (const path of bibs) {
        const row = document.createElement('div');
        row.className = 'overleaf-bib-row';
        const code = document.createElement('code');
        code.textContent = path;
        code.title = path;
        const actions = document.createElement('div');
        actions.className = 'overleaf-bib-actions';
        const open = document.createElement('button');
        open.type = 'button';
        open.textContent = 'Open';
        open.onclick = () => openOverleafBib(path).catch(error => toast(error.message, true));
        const importButton = document.createElement('button');
        importButton.type = 'button';
        importButton.textContent = 'Import to References';
        importButton.disabled = !ref.available || !ref.configured;
        importButton.onclick = () => importOverleafBib(path).catch(error => toast(error.message, true));
        actions.append(open, importButton);
        row.append(code, actions);
        bibList?.appendChild(row);
      }
    }

    const menuMeta = $('overleafSyncMenuStatus');
    if (menuMeta) menuMeta.textContent = hasRemote ? overleafRelationLabel(comparison) : 'No remote';
  }

  async function refreshOverleafSync(remote = null) {
    const selected = remote || $('overleafSyncRemote')?.value || '';
    const suffix = selected ? `?remote=${encodeURIComponent(selected)}` : '';
    const data = await api(`/api/overleaf/status${suffix}`);
    renderOverleafSync(data);
    return data;
  }

  async function openOverleafSyncDialog() {
    closeServiceMenus();
    if (!state.workspace) return toast('Open a PAH workspace first.', true);
    await refreshGitStatus();
    $('overleafSyncDialog')?.showModal();
    await refreshOverleafSync();
  }

  async function overleafSyncAction(action) {
    const sync = state.overleaf.sync || {};
    const remote = $('overleafSyncRemote')?.value || sync.selected_remote || '';
    if (!remote) return toast('Choose a recognized Overleaf remote first.', true);
    if (!state.git?.remote_enabled) return toast('Enable Manual Remote before contacting Overleaf.', true);
    if (action === 'pull' && state.tabs.some(tab => tab.dirty)) return toast('Save or close unsaved PAH editor buffers before pulling.', true);
    if (action === 'fetch' && !window.confirm(`Fetch from Overleaf remote “${remote}”?`)) return;
    if (action === 'pull' && !window.confirm(`Pull from Overleaf remote “${remote}” using fast-forward only?`)) return;
    if (action === 'push' && !window.confirm(`Push the current branch to Overleaf remote “${remote}”?`)) return;
    try {
      const data = await api(`/api/overleaf/${action}`, {method: 'POST', body: JSON.stringify({remote})});
      renderOverleafSync(data);
      if (action === 'pull') {
        await refreshCleanTabsFromDisk();
        await refreshTree();
        await refreshAnalyzerStatus().catch(() => {});
        await refreshDocumentStatus().catch(() => {});
      }
      toast(`Overleaf ${action} completed.`);
    } catch (error) {
      toast(error.message, true);
      await refreshOverleafSync(remote).catch(() => {});
    }
  }

  async function openOverleafBib(path) {
    $('overleafSyncDialog')?.close();
    await setMode('workspace');
    await openFile(path);
  }

  async function importOverleafBib(path) {
    if (!window.confirm(`Import BibTeX entries from ${path} into the currently selected Reference Manager library? The document .bib file itself will not be modified.`)) return;
    const data = await api('/api/overleaf/bibtex/import', {method: 'POST', body: JSON.stringify({path})});
    await refreshReferenceStatus().catch(() => {});
    toast(`BibTeX import completed for ${path}.`);
    await refreshOverleafSync($('overleafSyncRemote')?.value || null).catch(() => {});
    return data;
  }

  function loadToolFrame(tool, force = false) {
    if (isSurfaceDetached(tool)) return false;
    const info = state.fullTools[tool];
    const frame = $(toolFrameId(tool));
    if (!frame || !info?.available || !info.url) return false;
    const current = frame.dataset.toolUrl || '';
    if (force || current !== info.url || !frame.src) {
      const separator = info.url.includes('?') ? '&' : '?';
      frame.src = `${info.url}${separator}pah=${Date.now()}`;
      frame.dataset.toolUrl = info.url;
    }
    return true;
  }

  async function refreshCleanTabsFromDisk() {
    let skippedDirty = 0;
    for (const tab of state.tabs) {
      if (tab.dirty) { skippedDirty += 1; continue; }
      try {
        const data = await api(`/api/file?path=${encodeURIComponent(tab.path)}`);
        tab.content = data.content;
        tab.saved = data.content;
        tab.language = data.language;
      } catch (_) {
        // A full tool may have moved/deleted a file. Leave the tab as-is so the
        // user can decide what to do rather than silently discarding content.
      }
    }
    renderTabs();
    showActive();
    if (skippedDirty) toast(`${skippedDirty} unsaved PAH tab${skippedDirty === 1 ? '' : 's'} not refreshed from disk.`);
  }

  async function setMode(mode) {
    if (!['workspace', 'analysis', 'documents', 'references'].includes(mode)) return;
    closeServiceMenus();
    if (mode !== 'workspace' && isSurfaceDetached(mode)) {
      surfaceWindow(mode).focus();
      return;
    }
    const previousMode = state.mode;
    if (previousMode !== 'workspace' && previousMode !== mode) {
      await syncReturnedTool(previousMode);
    }
    if (mode !== 'workspace') {
      await refreshFullTools();
      const info = state.fullTools[mode];
      if (!info?.available) {
        toast(info?.error || `${mode} module is unavailable.`, true);
        return;
      }
      loadToolFrame(mode);
    }
    state.mode = mode;
    state.layout.lastMode = mode;
    persistLayoutPreferences();
    document.querySelectorAll('.mode-button').forEach(button => {
      button.classList.toggle('active', button.dataset.mode === mode);
    });
    $('workspaceMode').classList.toggle('hidden', mode !== 'workspace');
    $('analysisMode').classList.toggle('hidden', mode !== 'analysis');
    $('documentsMode').classList.toggle('hidden', mode !== 'documents');
    $('referencesMode').classList.toggle('hidden', mode !== 'references');
    $('app').classList.toggle('full-mode', mode !== 'workspace');
  }

  // ---------------------------------------------------------------------------
  // Workspace / files / editor
  // ---------------------------------------------------------------------------
  async function loadWorkspaceInfo() {
    const data = await api('/api/workspace');
    state.workspace = data.root;
    if (data.git) state.git = data.git;
    state.overleaf.sync = null;
    if ($('overleafSyncMenuStatus')) $('overleafSyncMenuStatus').textContent = 'Manual';
    $('workspacePath').value = data.root || '';

    const recent = $('recentWorkspaces');
    recent.innerHTML = '<option value="">Recent…</option>';
    for (const path of data.recent || []) {
      const option = document.createElement('option');
      option.value = path;
      option.textContent = path;
      recent.appendChild(option);
    }

    if (data.root) {
      await refreshTree();
      await refreshEnvironment();
      await restartTerminal();
      $('emptyEditor').querySelector('h2').textContent = 'Open a file';
    }
    await refreshAnalyzerStatus();
    await refreshDocumentStatus();
    await refreshReferenceStatus();
    await refreshFullTools({reloadActive: Boolean(data.root)});
    await refreshGitStatus();
  }

  async function openWorkspace(path) {
    if (state.tabs.some(tab => tab.dirty) && !confirm('Open another workspace and discard unsaved editor changes?')) return;
    const data = await api('/api/workspace/open', {method: 'POST', body: JSON.stringify({path})});
    state.workspace = data.root;
    if (data.git) state.git = data.git;
    state.tabs = [];
    state.active = null;
    state.selectedTree = null;
    resetAnalyzerView();
    resetDocumentsView();
    resetReferencesView();
    renderTabs();
    showActive();
    await loadWorkspaceInfo();
    toast(`Opened ${data.root}`);
  }

  function renderTreeNodes(nodes, container) {
    for (const node of nodes) {
      const wrap = document.createElement('div');
      const row = document.createElement('div');
      row.className = `tree-item ${node.type}`;
      row.dataset.path = node.path;
      row.dataset.type = node.type;

      const icon = document.createElement('span');
      icon.className = 'tree-icon';
      icon.textContent = node.type === 'dir' ? '▸' : '·';
      const name = document.createElement('span');
      name.textContent = node.name;
      row.append(icon, name);
      wrap.appendChild(row);

      if (node.type === 'dir') {
        const children = document.createElement('div');
        children.className = 'tree-children';
        children.hidden = true;
        wrap.appendChild(children);
        let loaded = false;

        row.addEventListener('dblclick', async () => {
          try {
            if (!loaded) {
              const data = await api(`/api/tree?path=${encodeURIComponent(node.path)}`);
              renderTreeNodes(data.tree || [], children);
              loaded = true;
            }
            children.hidden = !children.hidden;
            icon.textContent = children.hidden ? '▸' : '▾';
          } catch (error) {
            toast(error.message, true);
          }
        });
      } else {
        row.addEventListener('dblclick', () => openFile(node.path).catch(error => toast(error.message, true)));
      }

      row.addEventListener('click', event => {
        event.stopPropagation();
        document.querySelectorAll('.tree-item.selected').forEach(item => item.classList.remove('selected'));
        row.classList.add('selected');
        state.selectedTree = {path: node.path, type: node.type};
      });
      container.appendChild(wrap);
    }
  }

  async function refreshTree() {
    if (!state.workspace) return;
    const data = await api('/api/tree');
    const tree = $('tree');
    tree.innerHTML = '';
    renderTreeNodes(data.tree || [], tree);
  }

  async function openFile(path) {
    let tab = state.tabs.find(item => item.path === path);
    if (!tab) {
      const data = await api(`/api/file?path=${encodeURIComponent(path)}`);
      tab = {path: data.path, content: data.content, saved: data.content, language: data.language, dirty: false};
      state.tabs.push(tab);
    }
    state.active = tab.path;
    renderTabs();
    showActive();
  }

  function renderTabs() {
    const tabs = $('tabs');
    tabs.innerHTML = '';
    for (const tab of state.tabs) {
      const el = document.createElement('div');
      el.className = `tab ${tab.path === state.active ? 'active' : ''}`;
      el.title = tab.path;
      el.innerHTML = `<span class="name"></span><span class="dirty">${tab.dirty ? '●' : ''}</span><span class="close">×</span>`;
      el.querySelector('.name').textContent = basename(tab.path);
      el.addEventListener('click', event => {
        if (event.target.classList.contains('close')) return;
        state.active = tab.path;
        renderTabs();
        showActive();
      });
      el.querySelector('.close').addEventListener('click', event => {
        event.stopPropagation();
        closeTab(tab.path);
      });
      tabs.appendChild(el);
    }
  }

  function closeTab(path) {
    const tab = state.tabs.find(item => item.path === path);
    if (tab?.dirty && !confirm(`Discard unsaved changes to ${path}?`)) return;
    const index = state.tabs.findIndex(item => item.path === path);
    state.tabs.splice(index, 1);
    if (state.active === path) {
      state.active = state.tabs[Math.max(0, index - 1)]?.path || state.tabs[0]?.path || null;
    }
    renderTabs();
    showActive();
  }

  function showActive() {
    const tab = activeTab();
    const has = Boolean(tab);
    $('editorWrap').classList.toggle('hidden', !has);
    $('emptyEditor').style.display = has ? 'none' : 'grid';
    $('saveButton').disabled = !has;
    $('runButton').disabled = !has || !tab.path.toLowerCase().endsWith('.py');
    if (!has) {
      setText('fileStatus', 'No file open');
      setText('analysisFilePath', 'No file open');
      setText('documentFilePath', 'No file open');
      clearElement('fileEntities');
      refreshDocumentContext();
      refreshReferenceContext();
      return;
    }
    editor.value = tab.content;
    updateHighlight();
    setText('fileStatus', `${tab.path}  •  ${tab.language}`);
    updateCursor();
    refreshAnalyzerFile().catch(error => toast(error.message, true));
    refreshDocumentContext();
    refreshReferenceContext();
  }

  function updateHighlight() {
    const tab = activeTab();
    if (!tab) return;
    highlightCode.innerHTML = window.PAHSyntax.highlight(editor.value, tab.language) + '\n';
    highlightLayer.scrollTop = editor.scrollTop;
    highlightLayer.scrollLeft = editor.scrollLeft;
  }

  function updateCursor() {
    const before = editor.value.slice(0, editor.selectionStart);
    const line = before.split('\n').length;
    const col = before.length - before.lastIndexOf('\n');
    setText('cursorStatus', `Ln ${line}, Col ${col}`);
  }

  async function saveActive() {
    const tab = activeTab();
    if (!tab) return;
    const data = await api('/api/file', {method: 'PUT', body: JSON.stringify({path: tab.path, content: tab.content})});
    tab.saved = tab.content;
    tab.dirty = false;
    if (data.analyzer_stale) markAnalyzerStaleLocal();
    renderTabs();
    await refreshArtifactUsage();
    toast(`Saved ${tab.path}`);
  }

  editor.addEventListener('input', () => {
    const tab = activeTab();
    if (!tab) return;
    tab.content = editor.value;
    tab.dirty = tab.content !== tab.saved;
    renderTabs();
    updateHighlight();
    updateCursor();
  });
  editor.addEventListener('scroll', () => {
    highlightLayer.scrollTop = editor.scrollTop;
    highlightLayer.scrollLeft = editor.scrollLeft;
  });
  editor.addEventListener('keyup', updateCursor);
  editor.addEventListener('click', updateCursor);
  editor.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      saveActive().catch(error => toast(error.message, true));
    }
    if (event.key === 'Tab') {
      event.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      editor.setRangeText('    ', start, end, 'end');
      editor.dispatchEvent(new Event('input'));
    }
  });

  async function fsCreate(kind) {
    if (!state.workspace) return toast('Open a workspace first', true);
    const base = state.selectedTree
      ? (state.selectedTree.type === 'dir' ? state.selectedTree.path : parentPath(state.selectedTree.path))
      : '';
    const name = prompt(`${kind === 'dir' ? 'Folder' : 'File'} path relative to ${base || 'workspace root'}:`, '');
    if (!name) return;
    const path = [base, name].filter(Boolean).join('/');
    await api('/api/fs/create', {method: 'POST', body: JSON.stringify({path, kind})});
    if (kind === 'file' && path.toLowerCase().endsWith('.py')) markAnalyzerStaleLocal();
    await refreshTree();
    await refreshDocumentFiles();
    toast(`Created ${path}`);
  }

  async function fsRename() {
    const selected = state.selectedTree;
    if (!selected) return toast('Select an item first', true);
    const newName = prompt('New name:', basename(selected.path));
    if (!newName) return;
    const data = await api('/api/fs/rename', {method: 'POST', body: JSON.stringify({path: selected.path, new_name: newName})});
    remapOpenPath(selected.path, data.path, selected.type === 'dir');
    state.selectedTree = null;
    await refreshAnalyzerStatus();
    await refreshTree();
    await refreshDocumentFiles();
    toast(`Renamed to ${data.path}`);
  }

  async function fsMove() {
    const selected = state.selectedTree;
    if (!selected) return toast('Select an item first', true);
    const destination = prompt('Move to relative path or directory:', selected.path);
    if (!destination || destination === selected.path) return;
    const data = await api('/api/fs/move', {method: 'POST', body: JSON.stringify({path: selected.path, destination})});
    remapOpenPath(selected.path, data.path, selected.type === 'dir');
    state.selectedTree = null;
    await refreshAnalyzerStatus();
    await refreshTree();
    await refreshDocumentFiles();
    toast(`Moved to ${data.path}`);
  }

  function remapOpenPath(oldPath, newPath, isDir) {
    for (const tab of state.tabs) {
      if (tab.path === oldPath || (isDir && tab.path.startsWith(oldPath + '/'))) {
        const suffix = tab.path.slice(oldPath.length);
        if (state.active === tab.path) state.active = newPath + suffix;
        tab.path = newPath + suffix;
      }
    }
    renderTabs();
    showActive();
  }

  async function fsDelete() {
    const selected = state.selectedTree;
    if (!selected) return toast('Select an item first', true);
    if (!confirm(`Permanently delete ${selected.path}?`)) return;
    await api(`/api/fs?path=${encodeURIComponent(selected.path)}`, {method: 'DELETE'});
    for (const tab of [...state.tabs]) {
      if (tab.path === selected.path || (selected.type === 'dir' && tab.path.startsWith(selected.path + '/'))) {
        tab.dirty = false;
        closeTab(tab.path);
      }
    }
    state.selectedTree = null;
    await refreshAnalyzerStatus();
    await refreshTree();
    await refreshDocumentFiles();
    toast(`Deleted ${selected.path}`);
  }

  // ---------------------------------------------------------------------------
  // Terminal / environment / execution
  // ---------------------------------------------------------------------------
  function stripAnsi(text) {
    return text
      .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, '')
      .replace(/\x1b\[[0-?]*[ -\/]*[@-~]/g, '')
      .replace(/\r(?!\n)/g, '');
  }

  async function startTerminal() {
    if (!state.workspace) return;
    if (state.terminalId) {
      try { await api(`/api/terminal?id=${encodeURIComponent(state.terminalId)}`, {method: 'DELETE'}); } catch (_) {}
    }
    const data = await api('/api/terminal/start', {method: 'POST', body: '{}'});
    state.terminalId = data.id;
    setText('terminalOutput', '');
    clearInterval(state.terminalPoll);
    if (!isSurfaceDetached('terminal')) state.terminalPoll = setInterval(pollTerminal, 300);
  }

  async function pollTerminal() {
    if (!state.terminalId || isSurfaceDetached('terminal')) return;
    try {
      const data = await api(`/api/terminal/read?id=${encodeURIComponent(state.terminalId)}`);
      if (data.output) {
        const output = $('terminalOutput');
        output.textContent += stripAnsi(data.output);
        output.scrollTop = output.scrollHeight;
      }
      if (data.closed) {
        clearInterval(state.terminalPoll);
        state.terminalId = null;
      }
    } catch (_) {}
  }

  async function terminalSend(data) {
    if (!state.terminalId) await startTerminal();
    await api('/api/terminal/input', {method: 'POST', body: JSON.stringify({id: state.terminalId, data})});
  }

  async function pollDetachedTerminal() {
    if (!state.terminalId) return {output: '', closed: true};
    try {
      const data = await api(`/api/terminal/read?id=${encodeURIComponent(state.terminalId)}`);
      if (data.output) {
        const clean = stripAnsi(data.output);
        const output = $('terminalOutput');
        output.textContent += clean;
        output.scrollTop = output.scrollHeight;
        data.output = clean;
      }
      if (data.closed) state.terminalId = null;
      return data;
    } catch (_) {
      return {output: '', closed: false};
    }
  }

  function writeDetachedTerminalShell(popup) {
    popup.document.open();
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PAH — Terminal</title><style>html,body{margin:0;height:100%;background:#0d0f13;color:#d9dee7;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace}body{display:grid;grid-template-rows:36px minmax(0,1fr) 38px}header{display:flex;align-items:center;gap:6px;padding:4px 8px;background:#171a21;border-bottom:1px solid #303642;font-family:Inter,system-ui,sans-serif;font-size:12px}header strong{margin-right:auto}button{background:#252b35;color:#d9dee7;border:1px solid #303642;border-radius:5px;padding:4px 8px;cursor:pointer}button:hover{background:#303744}pre{margin:0;overflow:auto;padding:9px 11px;white-space:pre-wrap;word-break:break-word;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;color:#cbd4c4}div.input{display:flex;align-items:center;gap:7px;padding:4px 9px;border-top:1px solid #252a33}input{flex:1;border:0;outline:none;background:transparent;color:#d9dee7;font:12px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace}</style></head><body><header><strong>PAH Terminal</strong><button id="interrupt">Ctrl+C</button><button id="clear">Clear</button><button id="restart">Restart</button><button id="reattach">Reattach</button></header><pre id="output"></pre><div class="input"><span>›</span><input id="input" autocomplete="off" spellcheck="false" placeholder="Enter terminal command"></div></body></html>`);
    popup.document.close();
    const out = popup.document.getElementById('output');
    out.textContent = $('terminalOutput').textContent;
    out.scrollTop = out.scrollHeight;
    const input = popup.document.getElementById('input');
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        const value = input.value;
        input.value = '';
        terminalSend(value + '\n').catch(error => toast(error.message, true));
      } else if (event.ctrlKey && event.key.toLowerCase() === 'c') {
        event.preventDefault();
        terminalSend('\x03').catch(error => toast(error.message, true));
      }
    });
    popup.document.getElementById('interrupt').onclick = () => terminalSend('\x03').catch(error => toast(error.message, true));
    popup.document.getElementById('clear').onclick = () => { out.textContent = ''; setText('terminalOutput', ''); };
    popup.document.getElementById('restart').onclick = async () => {
      try { await restartTerminal(); out.textContent = ''; } catch (error) { toast(error.message, true); }
    };
    popup.document.getElementById('reattach').onclick = () => reattachSurface('terminal', {activate: true, expand: true});
    popup._pahTerminalPoll = popup.setInterval(async () => {
      const data = await pollDetachedTerminal();
      if (data.output) {
        out.textContent += data.output;
        out.scrollTop = out.scrollHeight;
      }
    }, 300);
    popup.focus();
  }

  async function restartTerminal() {
    if (!state.workspace) return;
    await startTerminal();
  }

  async function refreshEnvironment() {
    if (!state.workspace) return;
    const data = await api('/api/environment');
    const environmentStatus = $('toolsEnvironmentStatus');
    if (environmentStatus) environmentStatus.textContent = data.is_venv ? basename(data.selected) : 'system';
    $('envStatus').textContent = `${data.version}\nInterpreter: ${data.interpreter}\nEnvironment: ${data.selected || 'system'}`;
  }

  async function openEnvironmentDialog() {
    try {
      const data = await api('/api/environment');
      await refreshEnvironment();
      $('envPath').value = data.selected || '.venv';
      $('envDialog').showModal();
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function changeEnvironment(action) {
    try {
      if (action === 'create') {
        await api('/api/environment/create', {method: 'POST', body: JSON.stringify({path: $('envPath').value || '.venv'})});
      } else if (action === 'select') {
        await api('/api/environment/select', {method: 'POST', body: JSON.stringify({path: $('envPath').value})});
      } else {
        await api('/api/environment/select', {method: 'POST', body: JSON.stringify({path: null})});
      }
      await refreshEnvironment();
      await restartTerminal();
      toast('Python environment updated');
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function runActive() {
    const tab = activeTab();
    if (!tab) return;
    await saveActive();
    if (!state.terminalId) await startTerminal();
    const data = await api('/api/run', {
      method: 'POST',
      body: JSON.stringify({path: tab.path, terminal_id: state.terminalId, args: []}),
    });
    state.terminalId = data.terminal_id;
    if (isSurfaceDetached('terminal')) {
      surfaceWindow('terminal')?.focus();
    } else {
      setPaneCollapsed('terminal', false);
    }
    toast(`Running ${basename(tab.path)}`);
  }

  // ---------------------------------------------------------------------------
  // CodeAnalyzer integration
  // ---------------------------------------------------------------------------
  function resetAnalyzerView() {
    state.analyzer = {
      available: false,
      analyzed: false,
      stale: false,
      generation: 0,
      summary: null,
      overview: null,
      functions: [],
      selectedId: null,
      selectedEntity: null,
    };
    clearElement('fileEntities');
    setText('analysisFilePath', 'No file open');
    $('entityDetails').className = 'analysis-placeholder';
    $('entityDetails').textContent = 'Select an analyzed class, function, or method.';
    $('entityActions').classList.add('hidden');
    $('codeDocumentActions').classList.add('hidden');
    $('generateFileDocs').disabled = true;
    $('entityUsage').className = 'analysis-placeholder';
    $('entityUsage').textContent = 'Select an entity to inspect saved document links.';
    $('dependencyResults').className = 'analysis-placeholder';
    $('dependencyResults').textContent = 'Select an entity to inspect incoming and outgoing relationships.';
    $('similarityResults').className = 'analysis-placeholder';
    $('similarityResults').textContent = 'Similarity runs only when requested.';
    $('analysisOverview').className = 'analysis-placeholder';
    $('analysisOverview').textContent = 'Analyze the project to populate repository metrics.';
    $('matrixResults').className = 'analysis-placeholder';
    $('matrixResults').textContent = 'Not computed.';
    $('duplicateResults').className = 'analysis-placeholder';
    $('duplicateResults').textContent = 'Not computed.';
    $('clusterResults').className = 'analysis-placeholder';
    $('clusterResults').textContent = 'Not computed.';
    $('compareTarget').innerHTML = '<option value="">Compare with…</option>';
    $('compareButton').disabled = true;
    updateAnalyzerChrome();
  }

  function markAnalyzerStaleLocal() {
    if (!state.analyzer.analyzed) return;
    state.analyzer.stale = true;
    updateAnalyzerChrome();
  }

  function updateAnalyzerChrome() {
    const badge = $('analyzerBadge');
    badge.className = 'badge muted';
    const button = $('analyzeButton');
    button.disabled = !state.workspace || !state.analyzer.available;
    button.textContent = state.analyzer.analyzed ? 'Re-analyze' : 'Analyze';
    $('generateProjectDocs').disabled = !state.analyzer.analyzed || state.analyzer.stale;

    if (!state.workspace) {
      badge.textContent = 'idle';
      setAnalyzerMessage('Open a workspace to use code analysis.');
      return;
    }
    if (!state.analyzer.available) {
      badge.className = 'badge missing';
      badge.textContent = 'module missing';
      setAnalyzerMessage('CodeAnalyzer is not installed in this PAH environment. Add the code-analyzer submodule and run scripts/setup.sh.', 'error');
      return;
    }
    if (!state.analyzer.analyzed) {
      badge.className = 'badge ready';
      badge.textContent = 'ready';
      setAnalyzerMessage('Analyzer available. Analysis runs only when you request it.');
      return;
    }
    if (state.analyzer.stale) {
      badge.className = 'badge stale';
      badge.textContent = 'stale';
      setAnalyzerMessage('Files changed after the last analysis. Existing results remain visible until you re-analyze.', 'warning');
      return;
    }
    badge.className = 'badge ready';
    badge.textContent = `current · ${state.analyzer.generation}`;
    setAnalyzerMessage('Analysis is current for the open workspace.');
  }

  function setAnalyzerMessage(message, kind = '') {
    const el = $('analyzerMessage');
    el.textContent = message;
    el.className = `analysis-message${kind ? ' ' + kind : ''}`;
  }

  async function refreshAnalyzerStatus() {
    const data = await api('/api/analyzer/status');
    state.analyzer.available = Boolean(data.available);
    state.analyzer.analyzed = Boolean(data.analyzed);
    state.analyzer.stale = Boolean(data.stale);
    state.analyzer.generation = Number(data.generation || 0);
    state.analyzer.summary = data.summary || null;
    if (state.analyzer.analyzed && !state.analyzer.overview) {
      state.analyzer.overview = {summary: data.summary || {}, warnings: [], generation: data.generation, stale: data.stale};
    }
    updateAnalyzerChrome();
    if (state.analyzer.analyzed) {
      await loadAnalyzerFunctions();
      renderAnalyzerOverview();
      await refreshAnalyzerFile();
    }
  }

  async function analyzeProject() {
    const button = $('analyzeButton');
    button.disabled = true;
    button.classList.add('busy');
    button.textContent = 'Analyzing…';
    setAnalyzerMessage('Analyzing Python structure and relationships…');
    try {
      const data = await api('/api/analyzer/analyze', {method: 'POST', body: '{}'});
      state.analyzer.analyzed = true;
      state.analyzer.stale = false;
      state.analyzer.generation = Number(data.generation || state.analyzer.generation + 1);
      state.analyzer.summary = data.summary || {};
      state.analyzer.overview = data;
      state.analyzer.selectedId = null;
      state.analyzer.selectedEntity = null;
      await loadAnalyzerFunctions();
      renderAnalyzerOverview();
      clearRepositoryAnalysisResults();
      await refreshAnalyzerFile();
      updateAnalyzerChrome();
      toast(`Analyzed ${data.project_name || 'project'}`);
    } finally {
      button.classList.remove('busy');
      updateAnalyzerChrome();
    }
  }

  async function loadAnalyzerFunctions() {
    if (!state.analyzer.analyzed) return;
    const data = await api('/api/analyzer/functions');
    state.analyzer.functions = data.functions || [];
    populateCompareTargets();
  }

  function renderAnalyzerOverview() {
    const holder = $('analysisOverview');
    holder.className = '';
    holder.innerHTML = '';
    const summary = state.analyzer.overview?.summary || state.analyzer.summary || {};
    const keys = [
      ['python_files', 'Python files'],
      ['modules', 'Modules'],
      ['classes', 'Classes'],
      ['functions', 'Functions'],
      ['methods', 'Methods'],
      ['relationships', 'Relationships'],
      ['internal_imports', 'Internal imports'],
      ['external_imports', 'External imports'],
    ];
    const grid = document.createElement('div');
    grid.className = 'summary-grid';
    for (const [key, label] of keys) {
      const card = document.createElement('div');
      card.className = 'summary-card';
      card.innerHTML = '<div class="summary-value"></div><div class="summary-label"></div>';
      card.querySelector('.summary-value').textContent = summary[key] ?? 0;
      card.querySelector('.summary-label').textContent = label;
      grid.appendChild(card);
    }
    holder.appendChild(grid);

    const warnings = state.analyzer.overview?.warnings || [];
    if (warnings.length) {
      const list = document.createElement('ul');
      list.className = 'warning-list';
      for (const warning of warnings) {
        const li = document.createElement('li');
        li.textContent = warning;
        list.appendChild(li);
      }
      holder.appendChild(list);
    }
  }

  async function refreshAnalyzerFile() {
    const tab = activeTab();
    setText('analysisFilePath', tab ? tab.path : 'No file open');
    const holder = $('fileEntities');
    holder.replaceChildren();
    $('generateFileDocs').disabled = !tab || !state.analyzer.analyzed || state.analyzer.stale || !tab.path.toLowerCase().endsWith('.py');
    if (!tab || !state.analyzer.analyzed) return;

    const data = await api(`/api/analyzer/file?path=${encodeURIComponent(tab.path)}`);
    const entities = data.entities || [];
    if (!entities.length) {
      const empty = document.createElement('div');
      empty.className = 'analysis-placeholder';
      empty.textContent = tab.path.toLowerCase().endsWith('.py') ? 'No Python entities were extracted from this file.' : 'The active file is not part of the Python analysis catalog.';
      holder.appendChild(empty);
      return;
    }

    const currentStillVisible = entities.some(entity => entity.id === state.analyzer.selectedId);
    if (!currentStillVisible && state.analyzer.selectedEntity?.path !== tab.path) clearSelectedEntity();

    for (const entity of entities) {
      const row = document.createElement('button');
      row.className = `entity-item${entity.id === state.analyzer.selectedId ? ' selected' : ''}`;
      row.type = 'button';
      const line = entity.metadata?.line_start;
      row.innerHTML = '<div class="entity-main"><span class="entity-name"></span><span class="entity-type"></span></div><div class="entity-meta"></div>';
      row.querySelector('.entity-name').textContent = entity.qualified_name || entity.name;
      row.querySelector('.entity-type').textContent = entity.node_type;
      row.querySelector('.entity-meta').textContent = line ? `line ${line}` : (entity.metadata?.line_count ? `${entity.metadata.line_count} lines` : '');
      row.addEventListener('click', () => selectEntity(entity.id).catch(error => toast(error.message, true)));
      holder.appendChild(row);
    }
  }

  function clearSelectedEntity() {
    state.analyzer.selectedId = null;
    state.analyzer.selectedEntity = null;
    $('entityDetails').className = 'analysis-placeholder';
    $('entityDetails').textContent = 'Select an analyzed class, function, or method.';
    $('entityActions').classList.add('hidden');
    $('codeDocumentActions').classList.add('hidden');
    $('entityUsage').className = 'analysis-placeholder';
    $('entityUsage').textContent = 'Select an entity to inspect saved document links.';
    $('dependencyResults').className = 'analysis-placeholder';
    $('dependencyResults').textContent = 'Select an entity to inspect incoming and outgoing relationships.';
    $('similarityResults').className = 'analysis-placeholder';
    $('similarityResults').textContent = 'Similarity runs only when requested.';
    populateCompareTargets();
  }

  async function selectEntity(id) {
    const [entityData, dependencyData] = await Promise.all([
      api(`/api/analyzer/entity?id=${encodeURIComponent(id)}`),
      api(`/api/analyzer/dependencies?id=${encodeURIComponent(id)}`),
    ]);
    state.analyzer.selectedId = id;
    state.analyzer.selectedEntity = entityData.entity;
    renderEntity(entityData.entity);
    renderDependencies(dependencyData);
    populateCompareTargets();
    $('similarityResults').className = 'analysis-placeholder';
    $('similarityResults').textContent = 'Similarity runs only when requested.';
    await refreshAnalyzerFile();
    await refreshArtifactUsage();
  }

  function renderEntity(entity) {
    const holder = $('entityDetails');
    holder.className = 'entity-card';
    holder.innerHTML = '';
    const title = document.createElement('h4');
    title.textContent = entity.qualified_name || entity.name;
    holder.appendChild(title);

    const metadata = entity.metadata || {};
    const kv = document.createElement('div');
    kv.className = 'kv';
    const rows = [
      ['Type', entity.node_type],
      ['File', entity.path || '—'],
      ['Lines', metadata.line_start ? `${metadata.line_start}${metadata.line_end && metadata.line_end !== metadata.line_start ? '–' + metadata.line_end : ''}` : '—'],
      ['Signature', metadata.signature || '—'],
    ];
    for (const [key, value] of rows) {
      const k = document.createElement('div'); k.className = 'key'; k.textContent = key;
      const v = document.createElement('div'); v.textContent = value;
      kv.append(k, v);
    }
    holder.appendChild(kv);

    if (metadata.docstring) {
      const doc = document.createElement('div');
      doc.className = 'small-muted';
      doc.textContent = metadata.docstring;
      holder.appendChild(doc);
    }
    if (metadata.source_code) {
      const source = document.createElement('pre');
      source.textContent = metadata.source_code;
      holder.appendChild(source);
    }

    $('entityActions').classList.remove('hidden');
    $('codeDocumentActions').classList.toggle('hidden', !state.documents.available);
    populateDocumentTargets();
    const similarityAllowed = entity.node_type === 'function' || entity.node_type === 'method';
    $('similarButton').disabled = !similarityAllowed;
    $('generateDependencyDiagram').disabled = !state.documents.available || state.analyzer.stale;
    $('generateEntityDocs').disabled = state.analyzer.stale;
  }

  function renderDependencies(data) {
    const holder = $('dependencyResults');
    holder.className = '';
    holder.innerHTML = '';
    const groups = [
      ['Outgoing', data.outgoing || []],
      ['Incoming', data.incoming || []],
    ];
    for (const [title, rows] of groups) {
      const group = document.createElement('div');
      group.className = 'dep-group';
      const heading = document.createElement('div');
      heading.className = 'dep-title';
      heading.textContent = `${title} (${rows.length})`;
      group.appendChild(heading);
      if (!rows.length) {
        const empty = document.createElement('div');
        empty.className = 'small-muted';
        empty.textContent = 'None';
        group.appendChild(empty);
      } else {
        for (const row of rows) {
          const item = document.createElement('div');
          item.className = 'dep-row';
          const other = document.createElement('span');
          other.textContent = row.other?.qualified_name || row.other?.name || row.other?.id || 'unknown';
          const relation = document.createElement('span');
          relation.className = 'dep-rel';
          relation.textContent = row.relationship_type;
          item.append(other, relation);
          if (row.other?.id && !row.other.id.startsWith('external:')) {
            item.style.cursor = 'pointer';
            item.title = 'Inspect this entity';
            item.addEventListener('click', () => selectEntity(row.other.id).catch(error => toast(error.message, true)));
          }
          group.appendChild(item);
        }
      }
      holder.appendChild(group);
    }
  }

  function populateCompareTargets() {
    const select = $('compareTarget');
    const selected = state.analyzer.selectedId;
    const current = select.value;
    select.innerHTML = '<option value="">Compare with…</option>';
    for (const fn of state.analyzer.functions) {
      if (fn.id === selected) continue;
      const option = document.createElement('option');
      option.value = fn.id;
      option.textContent = fn.qualified_name || fn.name;
      select.appendChild(option);
    }
    if ([...select.options].some(option => option.value === current)) select.value = current;
    const entity = state.analyzer.selectedEntity;
    $('compareButton').disabled = !entity || !['function', 'method'].includes(entity.node_type) || !select.value;
  }

  async function openSelectedEntitySource() {
    const entity = state.analyzer.selectedEntity;
    if (!entity?.path) return;
    await openFile(entity.path);
    const startLine = Number(entity.metadata?.line_start || 1);
    const endLine = Number(entity.metadata?.line_end || startLine);
    const lines = editor.value.split('\n');
    let start = 0;
    for (let i = 0; i < startLine - 1 && i < lines.length; i++) start += lines[i].length + 1;
    let end = start;
    for (let i = startLine - 1; i < endLine && i < lines.length; i++) end += lines[i].length + (i < lines.length - 1 ? 1 : 0);
    editor.focus();
    editor.setSelectionRange(start, Math.max(start, end));
    updateCursor();
  }

  async function computeSimilar() {
    const entity = state.analyzer.selectedEntity;
    if (!entity) return;
    const button = $('similarButton');
    button.disabled = true;
    const holder = $('similarityResults');
    holder.className = 'analysis-placeholder';
    holder.textContent = 'Computing global pairwise similarities…';
    try {
      const data = await api(`/api/analyzer/similar?id=${encodeURIComponent(entity.id)}&limit=8`);
      renderSimilarityNeighbors(data);
    } finally {
      button.disabled = false;
    }
  }

  function renderSimilarityNeighbors(data) {
    const holder = $('similarityResults');
    holder.className = '';
    holder.innerHTML = '';
    const list = document.createElement('div');
    list.className = 'result-list';
    for (const row of data.neighbors || []) {
      const button = document.createElement('button');
      button.className = 'result-row';
      button.type = 'button';
      button.innerHTML = '<div class="entity-main"><span class="entity-name"></span><span class="score"></span></div><div class="result-meta"></div>';
      button.querySelector('.entity-name').textContent = row.qualified_name || row.name;
      button.querySelector('.score').textContent = fmt(row.score, 3);
      button.querySelector('.result-meta').textContent = `${row.path || ''}${row.line_start ? ':' + row.line_start : ''}`;
      button.addEventListener('click', () => selectEntity(row.id).catch(error => toast(error.message, true)));
      list.appendChild(button);
    }
    holder.appendChild(list);
    const note = document.createElement('div');
    note.className = 'small-muted';
    note.textContent = `Mean repository pair similarity: ${fmt(data.summary?.mean_off_diagonal || 0, 3)}`;
    holder.appendChild(note);
  }

  async function compareSelected() {
    const left = state.analyzer.selectedId;
    const right = $('compareTarget').value;
    if (!left || !right) return;
    const holder = $('similarityResults');
    holder.className = 'analysis-placeholder';
    holder.textContent = 'Comparing selected functions…';
    const data = await api('/api/analyzer/compare', {
      method: 'POST',
      body: JSON.stringify({left_id: left, right_id: right}),
    });
    holder.className = '';
    holder.innerHTML = '';
    const top = document.createElement('div');
    top.className = 'analysis-row';
    top.innerHTML = '<div class="entity-main"><span class="entity-name"></span><span class="score"></span></div><div class="result-meta"></div>';
    top.querySelector('.entity-name').textContent = `${functionLabel(left)} ↔ ${functionLabel(right)}`;
    top.querySelector('.score').textContent = fmt(data.score, 3);
    top.querySelector('.result-meta').textContent = `context depth ${data.config?.context_depth ?? 1}`;
    holder.appendChild(top);
    for (const layer of data.layers || []) {
      const row = document.createElement('div');
      row.className = 'dep-row';
      row.innerHTML = `<span>distance ${layer.distance}</span><span class="dep-rel">combined ${fmt(layer.combined_similarity, 3)}</span>`;
      holder.appendChild(row);
    }
  }

  function clearRepositoryAnalysisResults() {
    $('matrixResults').className = 'analysis-placeholder';
    $('matrixResults').textContent = 'Not computed.';
    $('duplicateResults').className = 'analysis-placeholder';
    $('duplicateResults').textContent = 'Not computed.';
    $('clusterResults').className = 'analysis-placeholder';
    $('clusterResults').textContent = 'Not computed.';
  }

  function requireAnalysis() {
    if (!state.analyzer.analyzed) {
      toast('Analyze the project first.', true);
      return false;
    }
    return true;
  }

  async function computeMatrixSummary() {
    if (!requireAnalysis()) return;
    const button = $('matrixButton');
    button.disabled = true;
    setText('matrixResults', 'Computing pairwise matrix…');
    try {
      const data = await api('/api/analyzer/matrix', {method: 'POST', body: JSON.stringify({include_matrix: false})});
      renderMatrixSummary(data);
    } finally { button.disabled = false; }
  }

  function renderMatrixSummary(data) {
    const holder = $('matrixResults');
    holder.className = '';
    holder.innerHTML = '';
    const summary = data.summary || {};
    const rows = [
      ['Functions', summary.function_count ?? 0],
      ['Pairs computed', summary.computed_pair_count ?? 0],
      ['Mean', fmt(summary.mean_off_diagonal ?? 0, 3)],
      ['Maximum', fmt(summary.maximum_off_diagonal ?? 0, 3)],
      ['Minimum', fmt(summary.minimum_off_diagonal ?? 0, 3)],
    ];
    for (const [label, value] of rows) {
      const row = document.createElement('div');
      row.className = 'dep-row';
      row.innerHTML = '<span></span><span class="dep-rel"></span>';
      row.children[0].textContent = label;
      row.children[1].textContent = value;
      holder.appendChild(row);
    }
  }

  async function computeDuplicates() {
    if (!requireAnalysis()) return;
    const button = $('duplicatesButton');
    button.disabled = true;
    const holder = $('duplicateResults');
    holder.className = 'analysis-placeholder';
    holder.textContent = 'Computing duplicate candidates…';
    try {
      const threshold = Number($('duplicateThreshold').value || 0.65);
      const data = await api('/api/analyzer/duplicates', {
        method: 'POST',
        body: JSON.stringify({threshold, limit: 25, include_source: false}),
      });
      renderDuplicates(data);
    } finally { button.disabled = false; }
  }

  function renderDuplicates(data) {
    const holder = $('duplicateResults');
    holder.className = '';
    holder.innerHTML = '';
    const summary = data.summary || {};
    const summaryLine = document.createElement('div');
    summaryLine.className = 'small-muted';
    summaryLine.textContent = `${summary.matching_pair_count ?? 0} pairs ≥ ${fmt(summary.threshold ?? 0, 2)} · coverage ${fmt((summary.duplicate_function_coverage ?? 0) * 100, 1)}%`;
    holder.appendChild(summaryLine);
    const list = document.createElement('div');
    list.className = 'result-list';
    for (const candidate of data.candidates || []) {
      const row = document.createElement('div');
      row.className = 'analysis-row';
      row.innerHTML = '<div class="entity-main"><span class="entity-name"></span><span class="score"></span></div><div class="result-meta"></div>';
      row.querySelector('.entity-name').textContent = `${functionLabel(candidate.left_id)} ↔ ${functionLabel(candidate.right_id)}`;
      row.querySelector('.score').textContent = fmt(candidate.score, 3);
      row.querySelector('.result-meta').textContent = (candidate.explanation || []).slice(0, 2).join(' · ') || `${candidate.shared_factor_count || 0} shared factors`;
      list.appendChild(row);
    }
    holder.appendChild(list);
  }

  async function computeClusters() {
    if (!requireAnalysis()) return;
    const button = $('clustersButton');
    button.disabled = true;
    const holder = $('clusterResults');
    holder.className = 'analysis-placeholder';
    holder.textContent = 'Computing matrix and clusters…';
    try {
      const k = Number($('clusterK').value || 3);
      const data = await api('/api/analyzer/clusters', {method: 'POST', body: JSON.stringify({k})});
      renderClusters(data);
    } finally { button.disabled = false; }
  }

  function renderClusters(data) {
    const holder = $('clusterResults');
    holder.className = '';
    holder.innerHTML = '';
    const intro = document.createElement('div');
    intro.className = 'small-muted';
    intro.textContent = `${data.k} clusters · inertia ${fmt(data.inertia || 0, 3)} · ${data.iterations || 0} iterations`;
    holder.appendChild(intro);
    const list = document.createElement('div');
    list.className = 'result-list';
    for (const cluster of data.clusters || []) {
      const row = document.createElement('div');
      row.className = 'analysis-row';
      row.innerHTML = '<div class="entity-main"><span class="entity-name"></span><span class="score"></span></div><div class="result-meta"></div><div class="factor-list"></div>';
      row.querySelector('.entity-name').textContent = `Cluster ${cluster.cluster}`;
      row.querySelector('.score').textContent = String(cluster.size);
      row.querySelector('.result-meta').textContent = `Representative: ${functionLabel(cluster.representative_id)}`;
      row.querySelector('.factor-list').textContent = (cluster.common_factors || []).slice(0, 5).map(factor => factor.factor).join(' · ');
      list.appendChild(row);
    }
    holder.appendChild(list);
  }

  // ---------------------------------------------------------------------------
  // DocumentEngine integration + PAH-owned code → document bridge
  // ---------------------------------------------------------------------------
  function documentExtension(path) {
    const name = String(path || '').toLowerCase();
    if (name.endsWith('.markdown')) return '.markdown';
    const index = name.lastIndexOf('.');
    return index >= 0 ? name.slice(index) : '';
  }

  function resetDocumentsView() {
    state.documents = {
      available: false,
      compilers: {latexmk: false, tectonic: false},
      files: [],
      normalizedDiagram: null,
    };
    setText('documentFilePath', 'No file open');
    setText('compilerStatus', 'Checking…');
    $('documentResults').className = 'analysis-placeholder';
    $('documentResults').textContent = 'Open Markdown, LaTeX, BibTeX, or .diagram content to use document-aware tools.';
    clearElement('documentFiles');
    $('documentActions').classList.add('hidden');
    $('parseDiagramButton').classList.add('hidden');
    $('normalizeDiagramButton').classList.add('hidden');
    $('compileLatexButton').classList.add('hidden');
    $('refreshCodeReferencesButton').classList.add('hidden');
    $('diagramInsertActions').classList.add('hidden');
    $('diagramDocumentTarget').innerHTML = '<option value="">Choose Markdown document…</option>';
    $('documentLinks').className = 'analysis-placeholder';
    $('documentLinks').textContent = 'Open Markdown or LaTeX to inspect PAH code/reference links.';
    $('documentTarget').innerHTML = '<option value="">Choose document…</option>';
    updateDocumentChrome();
  }

  function setDocumentMessage(message, kind = '') {
    const el = $('documentMessage');
    el.textContent = message;
    el.className = `analysis-message${kind ? ' ' + kind : ''}`;
  }

  function updateDocumentChrome() {
    const badge = $('documentBadge');
    badge.className = 'badge muted';
    if (!state.workspace) {
      badge.textContent = 'docs idle';
      setDocumentMessage('Open a workspace to use document tools.');
      return;
    }
    if (!state.documents.available) {
      badge.className = 'badge missing';
      badge.textContent = 'docs missing';
      setDocumentMessage('DocumentEngine is not installed. Add the tech-documents submodule and run scripts/setup.sh.', 'error');
      return;
    }
    badge.className = 'badge ready';
    badge.textContent = 'docs ready';
    setDocumentMessage('DocumentEngine available. PAH keeps the general editor while the module supplies document-specific operations.');
  }

  async function refreshDocumentStatus() {
    const data = await api('/api/documents/status');
    state.documents.available = Boolean(data.available);
    state.documents.compilers = data.compilers || {latexmk: false, tectonic: false};
    updateDocumentChrome();
    const enabled = Object.entries(state.documents.compilers).filter(([, value]) => value).map(([name]) => name);
    setText('compilerStatus', enabled.length ? `Available: ${enabled.join(', ')}` : 'No LaTeX compiler detected (latexmk or tectonic).');
    if (state.documents.available && state.workspace) await refreshDocumentFiles();
    if (state.analyzer.selectedEntity) $('generateDependencyDiagram').disabled = !state.documents.available || state.analyzer.stale;
    refreshDocumentContext();
  }

  async function refreshDocumentFiles() {
    if (!state.workspace || !state.documents.available) return;
    const data = await api('/api/documents/files');
    state.documents.files = data.files || [];
    const holder = $('documentFiles');
    holder.replaceChildren();
    if (!state.documents.files.length) {
      const empty = document.createElement('div');
      empty.className = 'analysis-placeholder';
      empty.textContent = 'No Markdown, LaTeX, BibTeX, or .diagram files found.';
      holder.appendChild(empty);
    } else {
      for (const item of state.documents.files) {
        const button = document.createElement('button');
        button.className = 'entity-item';
        button.type = 'button';
        button.innerHTML = '<div class="entity-main"><span class="entity-name"></span><span class="entity-type"></span></div><div class="entity-meta"></div>';
        button.querySelector('.entity-name').textContent = item.name;
        button.querySelector('.entity-type').textContent = item.extension.replace('.', '') || 'text';
        button.querySelector('.entity-meta').textContent = item.path;
        button.addEventListener('click', () => openFile(item.path).catch(error => toast(error.message, true)));
        holder.appendChild(button);
      }
    }
    populateDocumentTargets();
    populateReferenceDocumentTargets();
    populateDiagramTargets();
  }

  function populateDocumentTargets() {
    const select = $('documentTarget');
    const current = select.value;
    select.innerHTML = '<option value="">Choose document…</option>';
    for (const item of state.documents.files.filter(row => row.insert_target)) {
      const option = document.createElement('option');
      option.value = item.path;
      option.textContent = item.path;
      select.appendChild(option);
    }
    if ([...select.options].some(option => option.value === current)) select.value = current;
    const canInsert = Boolean(state.analyzer.selectedEntity && select.value && state.documents.available);
    $('insertCodeReference').disabled = !canInsert;
    $('insertCodeSource').disabled = !canInsert;
  }

  function populateDiagramTargets() {
    const select = $('diagramDocumentTarget');
    const current = select.value;
    select.innerHTML = '<option value="">Choose Markdown document…</option>';
    for (const item of state.documents.files.filter(row => ['.md', '.markdown'].includes(row.extension))) {
      const option = document.createElement('option');
      option.value = item.path;
      option.textContent = item.path;
      select.appendChild(option);
    }
    if ([...select.options].some(option => option.value === current)) select.value = current;
    const tab = activeTab();
    $('insertDiagramDocument').disabled = !tab || documentExtension(tab.path) !== '.diagram' || !select.value || !state.documents.available;
  }

  function refreshDocumentContext() {
    const tab = activeTab();
    state.documents.normalizedDiagram = null;
    setText('documentFilePath', tab ? tab.path : 'No file open');
    $('documentActions').classList.add('hidden');
    $('parseDiagramButton').classList.add('hidden');
    $('normalizeDiagramButton').classList.add('hidden');
    $('compileLatexButton').classList.add('hidden');
    $('refreshCodeReferencesButton').classList.add('hidden');
    $('diagramInsertActions').classList.add('hidden');
    renderDocumentLinks(null);

    if (!tab) {
      $('documentResults').className = 'analysis-placeholder';
      $('documentResults').textContent = 'Open a document file to use document-aware tools.';
      return;
    }
    if (!state.documents.available) {
      $('documentResults').className = 'analysis-placeholder';
      $('documentResults').textContent = 'The PAH editor remains available, but DocumentEngine-specific actions require the module.';
      return;
    }

    const extension = documentExtension(tab.path);
    const recognized = ['.md', '.markdown', '.tex', '.bib', '.diagram'].includes(extension);
    if (!recognized) {
      $('documentResults').className = 'analysis-placeholder';
      $('documentResults').textContent = 'The active file is not a document type handled by DocumentEngine.';
      return;
    }

    $('documentActions').classList.remove('hidden');
    $('documentResults').className = 'analysis-placeholder';
    if (extension === '.diagram') {
      $('parseDiagramButton').classList.remove('hidden');
      $('diagramInsertActions').classList.remove('hidden');
      populateDiagramTargets();
      $('documentResults').textContent = 'Parse this .diagram source through DocumentEngine, normalize it, or insert its current Mermaid rendering into Markdown.';
    } else if (extension === '.tex') {
      $('compileLatexButton').classList.remove('hidden');
      $('refreshCodeReferencesButton').classList.remove('hidden');
      $('refreshCodeReferencesButton').disabled = !state.analyzer.analyzed || state.analyzer.stale;
      $('documentResults').textContent = 'Compile this LaTeX source in an isolated build workspace, or refresh bounded PAH code references from current analysis.';
    } else if (extension === '.bib') {
      $('documentResults').textContent = 'BibTeX is editable here; the Refs panel can import the current editor contents into the selected ReferenceManager library.';
    } else {
      $('refreshCodeReferencesButton').classList.remove('hidden');
      $('refreshCodeReferencesButton').disabled = !state.analyzer.analyzed || state.analyzer.stale;
      $('documentResults').textContent = 'Markdown is editable in PAH and can receive or refresh analyzer-backed code references and embedded source blocks.';
    }
    refreshArtifactUsage().catch(error => toast(error.message, true));
  }

  async function parseActiveDiagram() {
    const tab = activeTab();
    if (!tab || documentExtension(tab.path) !== '.diagram') return;
    const button = $('parseDiagramButton');
    button.disabled = true;
    try {
      const data = await api('/api/documents/diagram/parse', {
        method: 'POST',
        body: JSON.stringify({content: tab.content}),
      });
      state.documents.normalizedDiagram = data.normalized_source || null;
      $('normalizeDiagramButton').classList.toggle('hidden', !state.documents.normalizedDiagram);
      const holder = $('documentResults');
      holder.className = 'document-output';
      holder.replaceChildren();
      const kind = document.createElement('div');
      kind.className = 'document-kind';
      kind.textContent = `direction ${data.graph?.direction || '?'} · preset ${data.graph?.preset || '?'}`;
      const label = document.createElement('div');
      label.className = 'small-muted';
      label.textContent = 'Mermaid generated by DocumentEngine:';
      const pre = document.createElement('pre');
      pre.textContent = data.mermaid || '';
      holder.append(kind, label, pre);
    } finally {
      button.disabled = false;
    }
  }

  function useNormalizedDiagram() {
    const tab = activeTab();
    if (!tab || !state.documents.normalizedDiagram) return;
    tab.content = state.documents.normalizedDiagram;
    tab.dirty = tab.content !== tab.saved;
    editor.value = tab.content;
    updateHighlight();
    updateCursor();
    renderTabs();
    toast('Applied normalized .diagram source; save when ready.');
  }

  async function compileActiveLatex() {
    const tab = activeTab();
    if (!tab || documentExtension(tab.path) !== '.tex') return;
    await saveActive();
    const button = $('compileLatexButton');
    button.disabled = true;
    const holder = $('documentResults');
    holder.className = 'analysis-placeholder';
    holder.textContent = 'Compiling LaTeX in an isolated build workspace…';
    try {
      const data = await api('/api/documents/latex/compile', {
        method: 'POST',
        body: JSON.stringify({path: tab.path}),
      });
      holder.className = 'document-output';
      holder.replaceChildren();
      const status = document.createElement('div');
      status.className = data.success ? 'document-kind' : 'small-muted';
      status.textContent = data.success ? 'Compilation succeeded.' : (data.error || 'Compilation failed.');
      holder.appendChild(status);
      if (data.success && data.pdf_name) {
        const link = document.createElement('a');
        link.target = '_blank';
        link.rel = 'noopener';
        link.href = `/api/documents/build?build_id=${encodeURIComponent(data.build_id)}&filename=${encodeURIComponent(data.pdf_name)}`;
        link.textContent = `Open ${data.pdf_name}`;
        holder.appendChild(link);
      }
      if (data.log) {
        const pre = document.createElement('pre');
        pre.textContent = data.log;
        holder.appendChild(pre);
      }
    } finally {
      button.disabled = false;
    }
  }

  async function insertSelectedCode(includeSource) {
    const entity = state.analyzer.selectedEntity;
    const target = $('documentTarget').value;
    if (!entity || !target) return;
    const data = await api('/api/documents/code-snippet', {
      method: 'POST',
      body: JSON.stringify({entity_id: entity.id, target, include_source: includeSource}),
    });

    // Insert into PAH's editor buffer rather than silently writing the file. This
    // respects any unsaved target-document edits and gives the user final control.
    await openFile(target);
    const tab = activeTab();
    const separator = tab.content.trim().length ? '\n\n' : '';
    tab.content = tab.content.replace(/\s*$/, '') + separator + data.snippet;
    tab.dirty = tab.content !== tab.saved;
    editor.value = tab.content;
    updateHighlight();
    updateCursor();
    renderTabs();
    refreshDocumentContext();
    await refreshArtifactUsage();
    toast(includeSource ? 'Inserted refreshable code reference with source; save when ready.' : 'Inserted refreshable code reference; save when ready.');
  }

  // ---------------------------------------------------------------------------
  // PAH 0.5 cross-module workflows
  // ---------------------------------------------------------------------------
  function workflowSlug(value) {
    return String(value || 'artifact').replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '') || 'artifact';
  }

  async function generateDependencyDiagram() {
    const entity = state.analyzer.selectedEntity;
    if (!entity) return;
    if (state.analyzer.stale) return toast('Re-analyze before generating analyzer-backed artifacts.', true);
    if (!state.documents.available) return toast('DocumentEngine is required to validate generated .diagram files.', true);
    const defaultPath = `docs/diagrams/${workflowSlug(entity.qualified_name || entity.name)}_dependencies.diagram`;
    const target = prompt('Create editable dependency diagram at:', defaultPath);
    if (!target) return;
    const data = await api('/api/workflows/diagram/entity', {
      method: 'POST',
      body: JSON.stringify({entity_id: entity.id, target}),
    });
    await refreshTree();
    await refreshDocumentFiles();
    await openFile(data.path);
    toast(`Created ${data.path}`);
  }

  async function generateDocumentationScaffold(kind) {
    if (!state.analyzer.analyzed) return toast('Analyze the project first.', true);
    if (state.analyzer.stale) return toast('Re-analyze before generating analyzer-backed documentation.', true);
    const tab = activeTab();
    const entity = state.analyzer.selectedEntity;
    let defaultPath = 'docs/technical_overview.md';
    const payload = {kind};
    if (kind === 'entity') {
      if (!entity) return toast('Select an analyzed entity first.', true);
      payload.entity_id = entity.id;
      defaultPath = `docs/code/${workflowSlug(entity.qualified_name || entity.name)}.md`;
    } else if (kind === 'file') {
      if (!tab?.path?.toLowerCase().endsWith('.py')) return toast('Open an analyzed Python file first.', true);
      payload.path = tab.path;
      defaultPath = `docs/code/${workflowSlug(basename(tab.path).replace(/\.py$/i, ''))}.md`;
    }
    const target = prompt('Create documentation scaffold at:', defaultPath);
    if (!target) return;
    payload.target = target;
    const data = await api('/api/workflows/docs/scaffold', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await refreshTree();
    if (state.documents.available) await refreshDocumentFiles();
    await openFile(data.path);
    toast(`Created ${kind} documentation scaffold.`);
  }

  async function insertActiveDiagramIntoDocument() {
    const diagramTab = activeTab();
    const target = $('diagramDocumentTarget').value;
    if (!diagramTab || documentExtension(diagramTab.path) !== '.diagram' || !target) return;
    const data = await api('/api/workflows/diagram/document-snippet', {
      method: 'POST',
      body: JSON.stringify({diagram_path: diagramTab.path, content: diagramTab.content, target}),
    });
    await openFile(target);
    const targetTab = activeTab();
    const separator = targetTab.content.trim().length ? '\n\n' : '';
    targetTab.content = targetTab.content.replace(/\s*$/, '') + separator + data.snippet;
    targetTab.dirty = targetTab.content !== targetTab.saved;
    editor.value = targetTab.content;
    updateHighlight();
    updateCursor();
    renderTabs();
    refreshDocumentContext();
    await refreshArtifactUsage();
    toast('Inserted linked Mermaid diagram; save when ready.');
  }

  async function refreshActiveCodeReferences() {
    const tab = activeTab();
    if (!tab || !['.md', '.markdown', '.tex'].includes(documentExtension(tab.path))) return;
    if (state.analyzer.stale) return toast('Re-analyze before refreshing code references.', true);
    const data = await api('/api/workflows/code/refresh', {
      method: 'POST',
      body: JSON.stringify({target: tab.path, content: tab.content}),
    });
    tab.content = data.content;
    tab.dirty = tab.content !== tab.saved;
    editor.value = tab.content;
    updateHighlight();
    updateCursor();
    renderTabs();
    await refreshArtifactUsage();
    const unresolved = (data.unresolved || []).length;
    const legacy = Number(data.legacy_count || 0);
    toast(`Refreshed ${data.refreshed || 0} code block(s)${unresolved ? ` · ${unresolved} unresolved` : ''}${legacy ? ` · ${legacy} legacy marker(s) unchanged` : ''}.`);
  }

  function renderUsageList(holderId, paths, emptyMessage) {
    const holder = $(holderId);
    holder.replaceChildren();
    if (!(paths || []).length) {
      holder.className = 'analysis-placeholder';
      holder.textContent = emptyMessage;
      return;
    }
    holder.className = 'result-list';
    for (const path of paths) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'result-row';
      button.textContent = path;
      button.addEventListener('click', () => openFile(path).catch(error => toast(error.message, true)));
      holder.appendChild(button);
    }
  }

  function renderDocumentLinks(documentData) {
    const holder = $('documentLinks');
    holder.replaceChildren();
    if (!documentData) {
      holder.className = 'analysis-placeholder';
      holder.textContent = 'Open Markdown or LaTeX to inspect PAH code/reference links.';
      return;
    }
    const code = documentData.code || [];
    const refs = documentData.references || [];
    const diagrams = documentData.diagrams || [];
    if (!code.length && !diagrams.length && !refs.length) {
      holder.className = 'analysis-placeholder';
      holder.textContent = 'No PAH code or reference markers in the current document buffer.';
      return;
    }
    holder.className = '';
    const codeTitle = document.createElement('div');
    codeTitle.className = 'dep-title';
    codeTitle.textContent = `Code links (${code.length})`;
    holder.appendChild(codeTitle);
    for (const row of code) {
      const item = document.createElement('div');
      item.className = 'dep-row';
      const name = document.createElement('span');
      name.textContent = row.entity || row.id || row.path || 'code entity';
      const mode = document.createElement('span');
      mode.className = 'dep-rel';
      mode.textContent = row.bounded ? (row.mode || 'reference') : 'legacy';
      item.append(name, mode);
      holder.appendChild(item);
    }
    const diagramTitle = document.createElement('div');
    diagramTitle.className = 'dep-title';
    diagramTitle.textContent = `Diagram links (${diagrams.length})`;
    holder.appendChild(diagramTitle);
    for (const row of diagrams) {
      const item = document.createElement('div');
      item.className = 'dep-row';
      const name = document.createElement('span');
      name.textContent = row.path || 'diagram';
      const kind = document.createElement('span');
      kind.className = 'dep-rel';
      kind.textContent = 'diagram';
      item.append(name, kind);
      item.style.cursor = row.path ? 'pointer' : '';
      if (row.path) item.addEventListener('click', () => openFile(row.path).catch(error => toast(error.message, true)));
      holder.appendChild(item);
    }
    const refTitle = document.createElement('div');
    refTitle.className = 'dep-title';
    refTitle.textContent = `Reference links (${refs.length})`;
    holder.appendChild(refTitle);
    for (const row of refs) {
      const item = document.createElement('div');
      item.className = 'dep-row';
      const name = document.createElement('span');
      name.textContent = row.bibkey || row.title || row.paper_id || 'paper';
      const kind = document.createElement('span');
      kind.className = 'dep-rel';
      kind.textContent = row.paper_id || 'reference';
      item.append(name, kind);
      holder.appendChild(item);
    }
  }

  async function refreshArtifactUsage() {
    if (!state.workspace) return;
    const tab = activeTab();
    const payload = {};
    if (state.analyzer.selectedEntity) payload.entity_id = state.analyzer.selectedEntity.id;
    if (state.references.selected) payload.paper_id = state.references.selected.PaperID;
    if (tab && ['.md', '.markdown', '.tex'].includes(documentExtension(tab.path))) {
      payload.document_path = tab.path;
      payload.document_content = tab.content;
    }
    if (!Object.keys(payload).length) {
      renderUsageList('entityUsage', [], 'Select an entity to inspect saved document links.');
      renderUsageList('referenceUsage', [], 'Select a paper to inspect saved document links.');
      renderDocumentLinks(null);
      return;
    }
    const data = await api('/api/workflows/links', {method: 'POST', body: JSON.stringify(payload)});
    if (payload.entity_id) {
      renderUsageList('entityUsage', data.entity_used_in || [], 'This entity is not referenced by any saved PAH document markers.');
    }
    if (payload.paper_id) {
      renderUsageList('referenceUsage', data.paper_used_in || [], 'This paper is not referenced by any saved PAH document markers.');
    }
    renderDocumentLinks(data.document || null);
  }

  // ---------------------------------------------------------------------------
  // ReferenceManager integration + PAH-owned reference → document bridge
  // ---------------------------------------------------------------------------
  function resetReferencesView() {
    state.references = {
      available: false,
      configured: false,
      libraryRoot: null,
      summary: null,
      papers: [],
      statuses: [],
      topics: [],
      selected: null,
    };
    $('referenceLibraryPath').value = '';
    $('referenceSearch').value = '';
    $('referenceStatusFilter').innerHTML = '<option value="">All statuses</option>';
    $('referenceTopicFilter').innerHTML = '<option value="">All topics</option>';
    clearElement('referencePapers');
    $('referenceDetails').className = 'analysis-placeholder';
    $('referenceDetails').textContent = 'Select a paper to inspect metadata.';
    $('referenceUsage').className = 'analysis-placeholder';
    $('referenceUsage').textContent = 'Select a paper to inspect saved document links.';
    $('referenceEditActions').classList.add('hidden');
    $('referenceToolsResult').className = 'analysis-placeholder';
    $('referenceToolsResult').textContent = 'Open a .bib file to import its current editor contents, or inspect duplicate groups.';
    $('referenceDocumentTarget').innerHTML = '<option value="">Choose Markdown/LaTeX document…</option>';
    updateReferenceChrome();
    refreshReferenceContext();
  }

  function setReferenceMessage(message, kind = '') {
    const el = $('referenceMessage');
    el.textContent = message;
    el.className = `analysis-message${kind ? ' ' + kind : ''}`;
  }

  function referenceSummaryText(summary) {
    if (!summary) return 'Library selected; sync or refresh to inspect papers.';
    const present = Number(summary.file_state_counts?.Present || 0);
    const cited = Number(summary.status_counts?.Cited || 0);
    return `${Number(summary.papers || 0)} papers · ${present} local PDFs · ${Number(summary.bibkey_count || 0)} BibKeys · ${cited} cited`;
  }

  function updateReferenceChrome() {
    const badge = $('referenceBadge');
    badge.className = 'badge muted';
    $('useWorkspaceLibrary').disabled = !state.workspace || !state.references.available;
    $('syncReferenceLibrary').disabled = !state.references.available || !state.references.configured;
    $('setReferenceLibrary').disabled = !state.references.available;
    if (!state.references.available) {
      badge.className = 'badge missing';
      badge.textContent = 'refs missing';
      setReferenceMessage('ReferenceManager is not installed. Add the reference-manager submodule and run scripts/setup.sh.', 'error');
      return;
    }
    if (!state.references.configured) {
      badge.textContent = 'refs idle';
      setReferenceMessage('ReferenceManager available. Choose a paper-library directory; it may be separate from the open code workspace.');
      return;
    }
    badge.className = 'badge ready';
    badge.textContent = 'refs ready';
    setReferenceMessage('Reference library connected. PAH can browse/edit lightweight metadata and insert existing BibKey citations into documents.');
  }

  async function refreshReferenceStatus() {
    const data = await api('/api/references/status');
    state.references.available = Boolean(data.available);
    state.references.configured = Boolean(data.configured);
    state.references.libraryRoot = data.library_root || null;
    state.references.summary = data.summary || null;
    $('referenceLibraryPath').value = state.references.libraryRoot || '';
    setText('referenceSummary', state.references.configured ? referenceSummaryText(state.references.summary) : 'No library selected.');
    updateReferenceChrome();
    if (state.references.available && state.references.configured) {
      await refreshReferencePapers();
    } else {
      clearElement('referencePapers');
    }
    populateReferenceDocumentTargets();
    refreshReferenceContext();
  }

  function replaceSelectOptions(select, values, emptyLabel) {
    const current = select.value;
    select.replaceChildren();
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = emptyLabel;
    select.appendChild(empty);
    for (const value of values || []) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    }
    if ([...select.options].some(option => option.value === current)) select.value = current;
  }

  async function refreshReferencePapers() {
    if (!state.references.available || !state.references.configured) return;
    const params = new URLSearchParams({
      q: $('referenceSearch').value || '',
      status: $('referenceStatusFilter').value || '',
      topic: $('referenceTopicFilter').value || '',
      limit: '500',
    });
    const data = await api(`/api/references/papers?${params.toString()}`);
    state.references.papers = data.papers || [];
    state.references.statuses = data.statuses || [];
    state.references.topics = data.topics || [];
    state.references.summary = data.summary || state.references.summary;
    replaceSelectOptions($('referenceStatusFilter'), state.references.statuses, 'All statuses');
    replaceSelectOptions($('referenceTopicFilter'), state.references.topics, 'All topics');
    setText('referenceSummary', `${referenceSummaryText(state.references.summary)} · showing ${Number(data.matched || 0)}${data.truncated ? '+' : ''}`);

    const holder = $('referencePapers');
    holder.replaceChildren();
    if (!state.references.papers.length) {
      const empty = document.createElement('div');
      empty.className = 'analysis-placeholder';
      empty.textContent = 'No references match the current filters.';
      holder.appendChild(empty);
      return;
    }
    for (const paper of state.references.papers) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `entity-item${state.references.selected?.PaperID === paper.PaperID ? ' selected' : ''}`;
      const main = document.createElement('div');
      main.className = 'entity-main';
      const title = document.createElement('span');
      title.className = 'entity-name';
      title.textContent = paper.Title || paper.Filename || 'Untitled';
      const status = document.createElement('span');
      status.className = 'entity-type';
      status.textContent = paper.Status || '—';
      main.append(title, status);
      const meta = document.createElement('div');
      meta.className = 'entity-meta';
      const author = paper.Authors || '';
      const year = paper.Year || '';
      const topic = paper.Topic || '';
      meta.textContent = [author, year, topic].filter(Boolean).join(' · ');
      button.append(main, meta);
      button.addEventListener('click', () => selectReferencePaper(paper.PaperID).catch(error => toast(error.message, true)));
      holder.appendChild(button);
    }
  }

  async function selectReferencePaper(paperId) {
    const data = await api(`/api/references/paper?id=${encodeURIComponent(paperId)}`);
    state.references.selected = data.paper;
    renderReferenceDetails();
    await refreshReferencePapers();
    await refreshArtifactUsage();
  }

  function renderReferenceDetails() {
    const paper = state.references.selected;
    const holder = $('referenceDetails');
    holder.replaceChildren();
    if (!paper) {
      holder.className = 'analysis-placeholder';
      holder.textContent = 'Select a paper to inspect metadata.';
      $('referenceEditActions').classList.add('hidden');
      $('referenceUsage').className = 'analysis-placeholder';
      $('referenceUsage').textContent = 'Select a paper to inspect saved document links.';
      updateReferenceInsertButtons();
      return;
    }
    holder.className = 'entity-card';
    const title = document.createElement('h4');
    title.textContent = paper.Title || paper.Filename || 'Untitled';
    const kv = document.createElement('div');
    kv.className = 'kv';
    const entries = [
      ['Authors', paper.Authors || '—'],
      ['Year', paper.Year || '—'],
      ['Venue', paper.Venue || '—'],
      ['Topic', paper.Topic || '—'],
      ['BibKey', paper.BibKey || '—'],
      ['DOI', paper.DOI || '—'],
      ['File', paper.FileState || '—'],
    ];
    for (const [key, value] of entries) {
      const k = document.createElement('div'); k.className = 'key'; k.textContent = key;
      const v = document.createElement('div'); v.textContent = value;
      kv.append(k, v);
    }
    holder.append(title, kv);
    if (paper.Abstract) {
      const abstract = document.createElement('div');
      abstract.className = 'reference-abstract';
      abstract.textContent = paper.Abstract;
      holder.appendChild(abstract);
    }
    $('referenceEditActions').classList.remove('hidden');
    $('referenceStatusEdit').value = paper.Status || 'Needs Review';
    $('referenceNotesEdit').value = paper.Notes || '';
    const pdf = $('openReferencePdf');
    pdf.classList.toggle('hidden', !paper.pdf_available);
    if (paper.pdf_available) pdf.href = `/api/references/pdf?id=${encodeURIComponent(paper.PaperID)}`;
    updateReferenceInsertButtons();
  }

  function populateReferenceDocumentTargets() {
    const select = $('referenceDocumentTarget');
    const current = select.value;
    select.innerHTML = '<option value="">Choose Markdown/LaTeX document…</option>';
    for (const item of (state.documents.files || []).filter(row => row.insert_target)) {
      const option = document.createElement('option');
      option.value = item.path;
      option.textContent = item.path;
      select.appendChild(option);
    }
    if ([...select.options].some(option => option.value === current)) select.value = current;
    updateReferenceInsertButtons();
  }

  function updateReferenceInsertButtons() {
    const paper = state.references.selected;
    const target = $('referenceDocumentTarget').value;
    const base = Boolean(paper && target && state.documents.available && state.workspace);
    $('insertReferenceCitation').disabled = !base || !String(paper?.BibKey || '').trim();
    $('insertReferenceNote').disabled = !base;
  }

  function refreshReferenceContext() {
    const tab = activeTab();
    const isBib = Boolean(tab && documentExtension(tab.path) === '.bib');
    $('importActiveBibtex').disabled = !isBib || !state.references.available || !state.references.configured;
    updateReferenceInsertButtons();
  }

  async function chooseReferenceLibrary(useWorkspace = false) {
    const url = useWorkspace ? '/api/references/library/use-workspace' : '/api/references/library';
    const options = {method: 'POST'};
    if (!useWorkspace) options.body = JSON.stringify({path: $('referenceLibraryPath').value});
    const data = await api(url, options);
    state.references.configured = Boolean(data.configured);
    state.references.libraryRoot = data.library_root || null;
    $('referenceLibraryPath').value = state.references.libraryRoot || '';
    state.references.selected = null;
    await refreshReferenceStatus();
    await refreshFullTools();
    if (isSurfaceDetached('references')) refreshDetachedSurface('references');
    else if (state.mode === 'references') loadToolFrame('references', true);
    toast(`Reference library: ${state.references.libraryRoot}`);
  }

  async function syncReferences() {
    const button = $('syncReferenceLibrary');
    button.disabled = true;
    try {
      const data = await api('/api/references/sync', {
        method: 'POST',
        body: JSON.stringify({detect_moves: true, extract_titles: false}),
      });
      await refreshReferenceStatus();
      toast(`Reference sync complete${data.added !== undefined ? ` · ${data.added} added` : ''}`);
    } finally {
      button.disabled = false;
      updateReferenceChrome();
    }
  }

  async function saveSelectedReference() {
    const paper = state.references.selected;
    if (!paper) return;
    const data = await api('/api/references/paper', {
      method: 'PUT',
      body: JSON.stringify({
        paper_id: paper.PaperID,
        status: $('referenceStatusEdit').value,
        notes: $('referenceNotesEdit').value,
      }),
    });
    state.references.selected = data.paper;
    state.references.summary = data.summary || state.references.summary;
    renderReferenceDetails();
    await refreshReferencePapers();
    toast('Reference metadata saved.');
  }

  async function insertSelectedReference(kind) {
    const paper = state.references.selected;
    const target = $('referenceDocumentTarget').value;
    if (!paper || !target) return;
    const data = await api('/api/references/document-snippet', {
      method: 'POST',
      body: JSON.stringify({paper_id: paper.PaperID, target, kind}),
    });
    await openFile(target);
    const tab = activeTab();
    const separator = tab.content.trim().length ? '\n\n' : '';
    tab.content = tab.content.replace(/\s*$/, '') + separator + data.snippet;
    tab.dirty = tab.content !== tab.saved;
    editor.value = tab.content;
    updateHighlight();
    updateCursor();
    renderTabs();
    refreshDocumentContext();
    refreshReferenceContext();
    await refreshArtifactUsage();
    toast(kind === 'citation' ? 'Inserted citation; save when ready.' : 'Inserted reference note; save when ready.');
  }

  async function importActiveBibtex() {
    const tab = activeTab();
    if (!tab || documentExtension(tab.path) !== '.bib') return toast('Open a .bib file first.', true);
    const button = $('importActiveBibtex');
    button.disabled = true;
    try {
      const data = await api('/api/references/bibtex/import', {
        method: 'POST',
        body: JSON.stringify({content: tab.content}),
      });
      const holder = $('referenceToolsResult');
      holder.className = 'document-output';
      holder.replaceChildren();
      const summary = document.createElement('div');
      summary.className = 'document-kind';
      summary.textContent = `${Number(data.entries || 0)} BibTeX entries · ${Number(data.matched || 0)} matched · ${Number(data.created || 0)} created`;
      holder.appendChild(summary);
      await refreshReferenceStatus();
    } finally {
      refreshReferenceContext();
    }
  }

  async function showReferenceDuplicates() {
    const holder = $('referenceToolsResult');
    holder.className = 'analysis-placeholder';
    holder.textContent = 'Checking duplicate groups…';
    const data = await api('/api/references/duplicates');
    holder.className = 'result-list';
    holder.replaceChildren();
    if (!(data.groups || []).length) {
      const empty = document.createElement('div');
      empty.className = 'analysis-placeholder';
      empty.textContent = 'No duplicate groups detected.';
      holder.appendChild(empty);
      return;
    }
    for (const [index, group] of data.groups.entries()) {
      const row = document.createElement('div');
      row.className = 'analysis-row';
      const names = group.map(paper => paper.Title || paper.Filename || paper.PaperID).join(' ↔ ');
      row.textContent = `Group ${index + 1}: ${names}`;
      holder.appendChild(row);
    }
  }

  // ---------------------------------------------------------------------------
  // Event wiring
  // ---------------------------------------------------------------------------
  document.querySelectorAll('.mode-button[data-mode]').forEach(button => {
    button.addEventListener('click', () => openWindowSurface(button.dataset.mode).catch(error => toast(error.message, true)));
  });
  document.querySelectorAll('[data-menu-toggle]').forEach(button => {
    button.addEventListener('click', event => {
      event.stopPropagation();
      toggleServiceMenu(button.dataset.menuToggle);
    });
  });
  document.querySelectorAll('[data-service-action="open"]').forEach(button => {
    button.addEventListener('click', () => openWindowSurface(button.dataset.serviceTool).catch(error => toast(error.message, true)));
  });
  document.querySelectorAll('[data-tool-reload]').forEach(button => {
    button.addEventListener('click', () => reloadTool(button.dataset.toolReload).catch(error => toast(error.message, true)));
  });
  document.querySelectorAll('[data-tool-detach]').forEach(button => {
    button.addEventListener('click', () => {
      closeServiceMenus();
      detachSurface(button.dataset.toolDetach).catch(error => toast(error.message, true));
    });
  });
  document.querySelectorAll('[data-pane-target]').forEach(button => {
    button.addEventListener('click', () => {
      const pane = button.dataset.paneTarget;
      closeServiceMenus();
      if (pane === 'terminal' && isSurfaceDetached('terminal')) {
        surfaceWindow('terminal')?.focus();
        return;
      }
      togglePane(pane);
    });
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.mode-launcher')) closeServiceMenus();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeServiceMenus();
    if (!(event.ctrlKey && event.altKey) || event.metaKey) return;

    if (event.code === 'KeyP') {
      event.preventDefault();
      togglePane('project');
    } else if (event.code === 'KeyO') {
      event.preventDefault();
      togglePane('context');
    } else if (event.code === 'KeyK') {
      event.preventDefault();
      if (isSurfaceDetached('terminal')) surfaceWindow('terminal')?.focus();
      else togglePane('terminal');
    } else if (event.code === 'KeyE') {
      event.preventDefault();
      focusWorkspaceEditor().catch(error => toast(error.message, true));
    }
  });
  $('openFullAnalysis').onclick = () => openWindowSurface('analysis').catch(error => toast(error.message, true));
  $('openFullDocuments').onclick = () => openWindowSurface('documents').catch(error => toast(error.message, true));
  $('openFullReferences').onclick = () => openWindowSurface('references').catch(error => toast(error.message, true));

  $('openWorkspace').onclick = () => openWorkspace($('workspacePath').value).catch(error => toast(error.message, true));
  $('workspacePath').addEventListener('keydown', event => { if (event.key === 'Enter') $('openWorkspace').click(); });
  $('recentWorkspaces').onchange = event => { if (event.target.value) openWorkspace(event.target.value).catch(error => toast(error.message, true)); };

  $('refreshTree').onclick = () => refreshTree().catch(error => toast(error.message, true));
  $('newFile').onclick = () => fsCreate('file').catch(error => toast(error.message, true));
  $('newFolder').onclick = () => fsCreate('dir').catch(error => toast(error.message, true));
  $('renameItem').onclick = () => fsRename().catch(error => toast(error.message, true));
  $('moveItem').onclick = () => fsMove().catch(error => toast(error.message, true));
  $('deleteItem').onclick = () => fsDelete().catch(error => toast(error.message, true));

  $('saveButton').onclick = () => saveActive().catch(error => toast(error.message, true));
  $('runButton').onclick = () => runActive().catch(error => toast(error.message, true));

  $('terminalInput').addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      const value = event.target.value;
      event.target.value = '';
      terminalSend(value + '\n').catch(error => toast(error.message, true));
    } else if (event.ctrlKey && event.key.toLowerCase() === 'c') {
      event.preventDefault();
      terminalSend('\x03').catch(error => toast(error.message, true));
    }
  });
  $('terminalInterrupt').onclick = () => terminalSend('\x03').catch(error => toast(error.message, true));
  $('terminalClear').onclick = () => setText('terminalOutput', '');
  $('terminalRestart').onclick = () => restartTerminal().catch(error => toast(error.message, true));
  $('terminalDetach').onclick = () => detachSurface('terminal').catch(error => toast(error.message, true));
  $('projectPaneToggle').onclick = () => togglePane('project');
  $('contextPaneToggle').onclick = () => togglePane('context');
  $('terminalToggle').onclick = () => togglePane('terminal');
  document.querySelectorAll('[data-resize-pane]').forEach(handle => {
    handle.addEventListener('pointerdown', event => beginPaneResize(handle.dataset.resizePane, event));
    handle.addEventListener('dblclick', () => {
      const name = handle.dataset.resizePane;
      const config = layoutSizeConfig[name];
      if (!config) return;
      setLayoutPaneSize(name, layoutDefaults[config.stateKey], {persist: true});
    });
  });

  $('documentsOverleafImport').onclick = () => openOverleafDialog().catch(error => toast(error.message, true));
  $('documentsOverleafSync').onclick = () => openOverleafSyncDialog().catch(error => toast(error.message, true));
  $('overleafDialogClose').onclick = () => $('overleafDialog')?.close();
  $('overleafImportZip').onclick = () => importOverleafZip();
  $('overleafEnableRemote').onclick = () => enableOverleafManualRemote().catch(error => toast(error.message, true));
  $('overleafCloneGit').onclick = () => cloneOverleafGit();
  $('overleafOpenProject').onclick = () => openImportedOverleafProject().catch(error => toast(error.message, true));
  $('overleafSyncClose').onclick = () => $('overleafSyncDialog')?.close();
  $('overleafSyncEnableRemote').onclick = () => enableOverleafManualRemote().then(() => refreshOverleafSync($('overleafSyncRemote')?.value || null)).catch(error => toast(error.message, true));
  $('overleafSyncRefresh').onclick = () => refreshOverleafSync($('overleafSyncRemote')?.value || null).catch(error => toast(error.message, true));
  $('overleafSyncRemote').onchange = () => refreshOverleafSync($('overleafSyncRemote').value).catch(error => toast(error.message, true));
  $('overleafSyncFetch').onclick = () => overleafSyncAction('fetch');
  $('overleafSyncPull').onclick = () => overleafSyncAction('pull');
  $('overleafSyncPush').onclick = () => overleafSyncAction('push');
  $('overleafSyncOpenGit').onclick = () => openWindowSurface('git').catch(error => toast(error.message, true));

  $('toolsEnvironment').onclick = () => {
    closeServiceMenus();
    openEnvironmentDialog();
  };
  $('toolsTerminalWindow').onclick = () => {
    closeServiceMenus();
    detachSurface('terminal').catch(error => toast(error.message, true));
  };
  $('toolsResetLayout').onclick = resetWorkspaceLayout;
  $('gitOpenSurface').onclick = () => {
    closeServiceMenus();
    openWindowSurface('git').catch(error => toast(error.message, true));
  };
  $('gitOpenWindow').onclick = () => {
    closeServiceMenus();
    detachSurface('git').catch(error => toast(error.message, true));
  };
  $('gitInitRepository').onclick = () => enableLocalGit().catch(error => toast(error.message, true));
  $('gitRefreshStatus').onclick = () => {
    closeServiceMenus();
    refreshGitStatus().catch(error => toast(error.message, true));
  };
  $('gitDialogDetach').onclick = () => detachSurface('git').catch(error => toast(error.message, true));
  $('gitDialogClose').onclick = () => {
    $('gitDialog')?.close();
    renderWindowSurfaceState();
  };
  $('gitDialog')?.addEventListener('close', renderWindowSurfaceState);
  $('createEnv').onclick = () => changeEnvironment('create');
  $('selectEnv').onclick = () => changeEnvironment('select');
  $('systemEnv').onclick = () => changeEnvironment('system');

  $('analyzeButton').onclick = () => analyzeProject().catch(error => toast(error.message, true));
  $('openEntitySource').onclick = () => openSelectedEntitySource().catch(error => toast(error.message, true));
  $('similarButton').onclick = () => computeSimilar().catch(error => toast(error.message, true));
  $('compareTarget').onchange = populateCompareTargets;
  $('compareButton').onclick = () => compareSelected().catch(error => toast(error.message, true));
  $('matrixButton').onclick = () => computeMatrixSummary().catch(error => toast(error.message, true));
  $('duplicatesButton').onclick = () => computeDuplicates().catch(error => toast(error.message, true));
  $('clustersButton').onclick = () => computeClusters().catch(error => toast(error.message, true));
  $('documentTarget').onchange = populateDocumentTargets;
  $('insertCodeReference').onclick = () => insertSelectedCode(false).catch(error => toast(error.message, true));
  $('insertCodeSource').onclick = () => insertSelectedCode(true).catch(error => toast(error.message, true));
  $('generateDependencyDiagram').onclick = () => generateDependencyDiagram().catch(error => toast(error.message, true));
  $('generateEntityDocs').onclick = () => generateDocumentationScaffold('entity').catch(error => toast(error.message, true));
  $('generateFileDocs').onclick = () => generateDocumentationScaffold('file').catch(error => toast(error.message, true));
  $('generateProjectDocs').onclick = () => generateDocumentationScaffold('project').catch(error => toast(error.message, true));
  $('parseDiagramButton').onclick = () => parseActiveDiagram().catch(error => toast(error.message, true));
  $('refreshCodeReferencesButton').onclick = () => refreshActiveCodeReferences().catch(error => toast(error.message, true));
  $('diagramDocumentTarget').onchange = populateDiagramTargets;
  $('insertDiagramDocument').onclick = () => insertActiveDiagramIntoDocument().catch(error => toast(error.message, true));
  $('normalizeDiagramButton').onclick = useNormalizedDiagram;
  $('compileLatexButton').onclick = () => compileActiveLatex().catch(error => toast(error.message, true));
  $('setReferenceLibrary').onclick = () => chooseReferenceLibrary(false).catch(error => toast(error.message, true));
  $('useWorkspaceLibrary').onclick = () => chooseReferenceLibrary(true).catch(error => toast(error.message, true));
  $('syncReferenceLibrary').onclick = () => syncReferences().catch(error => toast(error.message, true));
  $('saveReferencePaper').onclick = () => saveSelectedReference().catch(error => toast(error.message, true));
  $('referenceDocumentTarget').onchange = updateReferenceInsertButtons;
  $('insertReferenceCitation').onclick = () => insertSelectedReference('citation').catch(error => toast(error.message, true));
  $('insertReferenceNote').onclick = () => insertSelectedReference('note').catch(error => toast(error.message, true));
  $('importActiveBibtex').onclick = () => importActiveBibtex().catch(error => toast(error.message, true));
  $('referenceDuplicates').onclick = () => showReferenceDuplicates().catch(error => toast(error.message, true));
  $('referenceStatusFilter').onchange = () => refreshReferencePapers().catch(error => toast(error.message, true));
  $('referenceTopicFilter').onchange = () => refreshReferencePapers().catch(error => toast(error.message, true));
  let referenceSearchTimer = null;
  $('referenceSearch').addEventListener('input', () => {
    clearTimeout(referenceSearchTimer);
    referenceSearchTimer = setTimeout(() => refreshReferencePapers().catch(error => toast(error.message, true)), 180);
  });

  document.querySelectorAll('.analysis-tab').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.analysis-tab').forEach(item => item.classList.toggle('active', item === button));
      const tab = button.dataset.analysisTab;
      $('analysisContext').classList.toggle('hidden', tab !== 'context');
      $('analysisRepository').classList.toggle('hidden', tab !== 'repository');
      $('analysisDocuments').classList.toggle('hidden', tab !== 'documents');
      $('analysisReferences').classList.toggle('hidden', tab !== 'references');
      $('analyzeButton').style.display = ['documents', 'references'].includes(tab) ? 'none' : '';
      if (tab === 'documents') {
        refreshDocumentStatus().catch(error => toast(error.message, true));
      } else if (tab === 'references') {
        refreshReferenceStatus().catch(error => toast(error.message, true));
      }
    });
  });

  window.addEventListener('beforeunload', event => {
    if (state.tabs.some(tab => tab.dirty)) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  window.addEventListener('unload', () => {
    for (const key of ['analysis', 'documents', 'references', 'git', 'terminal']) {
      const popup = surfaceWindow(key);
      if (popup) popup.close();
    }
  });

  resetAnalyzerView();
  resetDocumentsView();
  resetReferencesView();
  loadLayoutPreferences();
  renderWorkspacePanes();
  renderGitLauncher();
  renderOverleafConnectivity();
  applyLayoutSizes();
  window.addEventListener('resize', applyLayoutSizes);
  (async () => {
    try {
      await loadWorkspaceInfo();
      await restoreLastMode();
    } catch (error) {
      toast(error.message, true);
    }
  })();
})();
