// UCA layout controller: reusable PAH editor/tree, genuine pane dividers, local windows.
import {PANES, defaultLayout, normalizeLayout, withPane, withWidth, resizeAdjacent, layoutKey} from './uca-layout-state.mjs';
import {createEditorDock} from './uca-editor-dock.mjs';

const root = document.getElementById('ucaMode');
if (root) {
  const requested = new URLSearchParams(window.location.search).get('uca_pane');
  const standalone = PANES.includes(requested) ? requested : null;
  if (standalone) {
    document.documentElement.dataset.ucaStandalone = standalone;
    root.dataset.ucaStandalone = standalone;
    document.title = `${standalone === 'editor' ? 'Source editor' : standalone === 'pypique' ? 'pyPIQUE' : 'Code Analyzer'} — PAH`;
  }
  const storagePrefix = 'pah.uca.layout.v1:';
  const scopeLabel = document.getElementById('ucaScope');
  const notice = document.getElementById('ucaLayoutNotice');
  const selector = document.getElementById('researchWorkspaceSelect');
  const path = document.getElementById('workspacePath');
  const grid = document.getElementById('ucaGrid');
  const explorerMount = document.getElementById('ucaExplorerDock');
  const explorerToggle = document.getElementById('ucaExplorerToggle');
  const editorDock = createEditorDock({
    source: document.querySelector('#workspaceMode > .main-pane'),
    mount: document.getElementById('ucaEditorMount'),
  });
  // Reuse the original tree, file actions and event handlers. Do not clone the
  // explorer: its controller owns the selected file and authorized operations.
  const treeDock = createEditorDock({
    source: document.querySelector('#workspaceMode > #projectPane'),
    mount: explorerMount,
  });
  let current = defaultLayout();
  let explorerVisible = true;
  let scope = Symbol('uninitialized');
  let ucaActive = !root.classList.contains('hidden');
  const windows = new Map();
  let watchWindows = null;
  const key = () => layoutKey(selector?.value || '', path?.value || '');

  function shownPanes() {
    return (standalone ? [standalone] : current.visible.filter(name => !windows.has(name)));
  }
  function save() {
    if (!scope || standalone) return;
    try { window.localStorage.setItem(storagePrefix + scope, JSON.stringify(current)); }
    catch (_) { notice.textContent = 'Layout preferences cannot be saved in this browser.'; }
  }
  function syncDocks() {
    const visible = shownPanes();
    editorDock.sync(ucaActive && visible.includes('editor'));
    const showExplorer = ucaActive && explorerVisible && (!standalone || standalone === 'editor');
    treeDock.sync(showExplorer);
    explorerMount.hidden = !showExplorer;
    explorerToggle?.setAttribute('aria-pressed', String(explorerVisible));
    if (showExplorer && document.getElementById('projectPane')?.classList.contains('collapsed')) {
      document.getElementById('projectPaneToggle')?.click();
    }
    if (ucaActive && visible.includes('editor')) {
      window.requestAnimationFrame(() => window.dispatchEvent(new Event('pah:uca-editor-layout')));
    }
  }
  function renderWidths() {
    for (const name of PANES) {
      const pane = root.querySelector(`[data-uca-pane="${name}"]`);
      const width = root.querySelector(`[data-uca-width="${name}"]`);
      pane.style.flexGrow = String(current.widths[name]);
      pane.style.flexBasis = '0px';
      if (width) width.value = String(current.widths[name]);
    }
    window.requestAnimationFrame(() => {
      if (ucaActive && shownPanes().includes('editor')) window.dispatchEvent(new Event('pah:uca-editor-layout'));
    });
  }
  function gripBetween(leftName, rightName) {
    const grip = document.createElement('div');
    grip.className = 'uca-grip';
    grip.dataset.ucaGrip = `${leftName}-${rightName}`;
    grip.tabIndex = 0;
    grip.setAttribute('role', 'separator');
    grip.setAttribute('aria-orientation', 'vertical');
    grip.setAttribute('aria-label', `Resize ${leftName} and ${rightName} panes`);
    let drag = null;
    grip.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      const left = root.querySelector(`[data-uca-pane="${leftName}"]`);
      const right = root.querySelector(`[data-uca-pane="${rightName}"]`);
      const leftWidth = left.getBoundingClientRect().width;
      const rightWidth = right.getBoundingClientRect().width;
      const sum = leftWidth + rightWidth;
      if (sum < 1) return;
      drag = {x:event.clientX, width:leftWidth, sum};
      grip.setPointerCapture(event.pointerId);
      grip.classList.add('dragging');
      event.preventDefault();
    });
    grip.addEventListener('pointermove', event => {
      if (!drag) return;
      current = resizeAdjacent(current, leftName, rightName, (drag.width + event.clientX - drag.x) / drag.sum);
      save(); renderWidths();
    });
    const release = () => {drag = null; grip.classList.remove('dragging');};
    grip.addEventListener('pointerup', release);
    grip.addEventListener('pointercancel', release);
    grip.addEventListener('lostpointercapture', release);
    grip.addEventListener('keydown', event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      const left = current.widths[leftName], right = current.widths[rightName];
      current = resizeAdjacent(current, leftName, rightName,
        left / (left+right) + (event.key === 'ArrowRight' ? 0.04 : -0.04));
      save(); renderWidths();
      event.preventDefault();
    });
    return grip;
  }
  function render() {
    const visible = shownPanes();
    for (const name of PANES) {
      const pane = root.querySelector(`[data-uca-pane="${name}"]`);
      pane.hidden = !visible.includes(name);
      const toggle = root.querySelector(`[data-uca-toggle="${name}"]`);
      if (toggle) toggle.checked = current.visible.includes(name);
      for (const button of root.querySelectorAll(`[data-uca-detach="${name}"]`)) {
        button.textContent = windows.has(name) ? `↙ Reattach ${name}` : `↗ ${name === 'analyzer' ? 'Analyzer' : name === 'editor' ? 'Editor' : 'pyPIQUE'}`;
      }
    }
    for (const grip of grid.querySelectorAll('[data-uca-grip]')) grip.remove();
    for (let i=1; i<visible.length; i++) {
      const right = root.querySelector(`[data-uca-pane="${visible[i]}"]`);
      grid.insertBefore(gripBetween(visible[i-1], visible[i]), right);
    }
    renderWidths();
    syncDocks();
    if (standalone) {
      notice.textContent = 'Separate PAH window: editor sessions and unsaved changes are not shared with the main window. Save before switching windows.';
    } else if (!visible.length) {
      notice.textContent = 'All selected panes are in separate windows. Reattach one using its button above.';
    } else {
      notice.textContent = `${visible.length} pane${visible.length===1?'':'s'} in this window. Drag dividers or use arrow keys to resize.`;
    }
  }
  function updateScope() {
    const next = key();
    if (scope === next) return;
    scope = next;
    current = standalone ? {...defaultLayout(),visible:[standalone]} : defaultLayout();
    if (scope && !standalone) {
      try { current = normalizeLayout(JSON.parse(window.localStorage.getItem(storagePrefix + scope) || 'null')); }
      catch (_) { current = defaultLayout(); }
    }
    scopeLabel.textContent = scope ? 'Layout scoped to selected research workspace and repository' : 'Select a research workspace and repository';
    render();
  }
  for (const input of root.querySelectorAll('[data-uca-toggle]')) {
    input.addEventListener('change', () => {
      if (standalone) return;
      const next = withPane(current, input.dataset.ucaToggle, input.checked);
      if (next.visible.length === current.visible.length && !input.checked && current.visible.length === 1) {
        notice.textContent = 'At least one pane must remain selected.';
      }
      current = next; save(); render();
    });
  }
  // Hidden range controls remain for keyboard/test compatibility. Users resize
  // by the visible, wide dividers instead of fighting three independent sliders.
  for (const input of root.querySelectorAll('[data-uca-width]')) {
    input.addEventListener('input', () => {current=withWidth(current,input.dataset.ucaWidth,input.value);save();renderWidths();});
  }
  document.getElementById('ucaReset')?.addEventListener('click', () => {current=defaultLayout();save();render();});
  explorerToggle?.addEventListener('click', () => {explorerVisible=!explorerVisible;syncDocks();});
  document.getElementById('ucaCloseWindow')?.addEventListener('click', () => window.close());
  if (standalone) {
    document.getElementById('ucaCloseWindow').hidden = false;
    document.getElementById('ucaReset').hidden = true;
  } else {
    for (const button of root.querySelectorAll('[data-uca-detach]')) {
      button.addEventListener('click', () => {
        const name = button.dataset.ucaDetach;
        if (windows.has(name)) {
          windows.get(name).close(); windows.delete(name); render(); return;
        }
        const popupUrl = new URL(window.location.href);
        popupUrl.searchParams.set('uca_pane',name);
        popupUrl.hash = '';
        const popup = window.open(popupUrl.toString(), `pah_uca_${name}`, 'popup=yes,width=1100,height=780');
        if (!popup) {notice.textContent='Browser blocked the local pane window. Allow popups for PAH.';return;}
        windows.set(name,popup);
        if (!watchWindows) watchWindows = window.setInterval(() => {
          let changed = false;
          for (const [pane, win] of windows) if (win.closed) { windows.delete(pane); changed=true; }
          if (changed) render();
          if (!windows.size) {clearInterval(watchWindows);watchWindows=null;}
        },650);
        render();
      });
    }
  }
  selector?.addEventListener('change', updateScope);
  path?.addEventListener('change', updateScope);
  document.querySelector('[data-mode="uca"]')?.addEventListener('click', () => queueMicrotask(updateScope));
  window.addEventListener('pah:uca-mode', event => {ucaActive=event.detail?.active===true;syncDocks();});
  window.addEventListener('beforeunload', () => {
    editorDock.restore(); treeDock.restore();
    for (const popup of windows.values()) if (!popup.closed) popup.close();
    if (watchWindows) clearInterval(watchWindows);
  });
  updateScope();
}
