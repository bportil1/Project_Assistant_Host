// UCA-02: pure layout rules, testable without a browser or PAH runtime.
export const PANES = Object.freeze(['editor', 'pypique', 'analyzer']);
const DEFAULT_WIDTHS = Object.freeze({editor: 34, pypique: 33, analyzer: 33});
export function defaultLayout() { return {visible: [...PANES], widths: {...DEFAULT_WIDTHS}}; }
export function normalizeLayout(value) {
  const layout = defaultLayout();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return layout;
  if (Array.isArray(value.visible)) {
    const visible = PANES.filter(name => value.visible.includes(name));
    if (visible.length) layout.visible = visible;
  }
  if (value.widths && typeof value.widths === 'object') {
    for (const name of PANES) {
      const number = value.widths[name];
      if (typeof number === 'number' && Number.isFinite(number)) layout.widths[name] = Math.min(70, Math.max(15, Math.round(number)));
    }
  }
  return layout;
}
export function withPane(layout, name, show) {
  if (!PANES.includes(name)) throw new TypeError('Unknown pane');
  const current = normalizeLayout(layout);
  const next = current.visible.filter(value => value !== name);
  if (show) next.push(name);
  if (!next.length) return current; // At least one visible pane.
  return normalizeLayout({...current, visible: next});
}
export function withWidth(layout, name, width) {
  if (!PANES.includes(name) || !Number.isFinite(Number(width))) throw new TypeError('Invalid pane width');
  const current = normalizeLayout(layout);
  return normalizeLayout({...current, widths: {...current.widths, [name]: Number(width)}});
}
export function layoutKey(workspaceId, repositoryRoot) {
  // Keep distinct logical workspaces/repositories from overwriting each other's preferences.
  if (typeof workspaceId !== 'string' || !workspaceId.trim()) return null;
  if (typeof repositoryRoot !== 'string' || !repositoryRoot.trim()) return null;
  return JSON.stringify([workspaceId, repositoryRoot]);
}

// Resize a *pair* without changing the sum of weights or jumping other panes.
// No global 100%-sum assumption: hidden panes keep their previous preferences.
export function resizeAdjacent(layout, left, right, fraction) {
  if (!PANES.includes(left) || !PANES.includes(right) || left === right ||
      !Number.isFinite(fraction)) throw new TypeError('Invalid adjacent resize');
  const current=normalizeLayout(layout);
  const total=current.widths[left]+current.widths[right];
  const lower=Math.max(15,total-70);
  const upper=Math.min(70,total-15);
  const leftWeight=Math.min(upper,Math.max(lower,Math.round(total*fraction)));
  return normalizeLayout({...current,widths:{...current.widths,
    [left]:leftWeight,[right]:total-leftWeight}});
}
