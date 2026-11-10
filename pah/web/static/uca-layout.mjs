import {PANES, defaultLayout, normalizeLayout, withPane, withWidth, layoutKey} from './uca-layout-state.mjs';
import {createEditorDock} from './uca-editor-dock.mjs';

const root = document.getElementById('ucaMode');
if (root) {
  const storagePrefix = 'pah.uca.layout.v1:';
  const scopeLabel = document.getElementById('ucaScope');
  const notice = document.getElementById('ucaLayoutNotice');
  const selector = document.getElementById('researchWorkspaceSelect');
  const path = document.getElementById('workspacePath');
  let scope = null;
  let current = defaultLayout();
  const dock = createEditorDock({
    source: document.querySelector('#workspaceMode > .main-pane'),
    mount: document.getElementById('ucaEditorMount'),
  });
  let ucaActive = !root.classList.contains('hidden');
  function syncEditor() {
    dock.sync(ucaActive && current.visible.includes('editor'));
    if (ucaActive && current.visible.includes('editor')) {
      window.requestAnimationFrame(() => window.dispatchEvent(new Event('pah:uca-editor-layout')));
    }
  }
  const key = () => layoutKey(selector?.value || '', path?.value || '');
  function save() {
    if (!scope) return;
    try { window.localStorage.setItem(storagePrefix + scope, JSON.stringify(current)); }
    catch (_) { notice.textContent = 'Layout preferences are session-only: browser storage unavailable.'; }
  }
  function render() {
    for (const name of PANES) {
      const pane = root.querySelector(`[data-uca-pane="${name}"]`);
      const checked = root.querySelector(`[data-uca-toggle="${name}"]`);
      const width = root.querySelector(`[data-uca-width="${name}"]`);
      pane.hidden = !current.visible.includes(name);
      pane.style.flexGrow = String(current.widths[name]);
      pane.style.flexBasis = '0';
      checked.checked = !pane.hidden;
      width.value = String(current.widths[name]);
    }
    syncEditor();
    const selected = current.visible.length;
    notice.textContent = `${selected} pane${selected === 1 ? '' : 's'} visible. Editor docked when selected; SAT and analyzer integration follow in UCA-04/05.`;
  }
  function updateScope() {
    const next = key();
    if (scope === next) return;
    scope = next;
    current = defaultLayout();
    if (scope) {
      try { current = normalizeLayout(JSON.parse(window.localStorage.getItem(storagePrefix + scope) || 'null')); }
      catch (_) { current = defaultLayout(); }
    }
    scopeLabel.textContent = scope ? 'Layout scoped to the selected research workspace and repository' : 'Select a research workspace and repository to persist layout';
    render();
  }
  for (const input of root.querySelectorAll('[data-uca-toggle]')) {
    input.addEventListener('change', () => {
      const name = input.dataset.ucaToggle;
      const requested = withPane(current, name, input.checked);
      if (!requested.visible.includes(name) && input.checked || requested.visible.length === 1 && !input.checked && current.visible.length === 1) {
        notice.textContent = 'At least one pane must remain visible.';
      }
      current = requested;
      save(); render();
    });
  }
  for (const input of root.querySelectorAll('[data-uca-width]')) {
    input.addEventListener('input', () => { current = withWidth(current, input.dataset.ucaWidth, input.value); save(); render(); });
  }
  document.getElementById('ucaReset')?.addEventListener('click', () => { current = defaultLayout(); save(); render(); });
  selector?.addEventListener('change', updateScope);
  path?.addEventListener('change', updateScope);
  // PAH updates workspace identity asynchronously; checking on mode entry prevents
  // carrying a layout across project switches not reflected by a change event.
  document.querySelector('[data-mode="uca"]')?.addEventListener('click', () => queueMicrotask(updateScope));
  window.addEventListener('pah:uca-mode', event => {
    ucaActive = event.detail?.active === true;
    syncEditor();
  });
  window.addEventListener('beforeunload', () => dock.restore());
  updateScope();
}
