// UCA-03: move the existing PAH editor DOM, never clone it or its Ace session.
// The original editor controller remains authoritative for saves and dirty tabs.
export function createEditorDock({source, mount}) {
  if (!source || !mount || !source.parentNode) throw new Error('UCA editor docking anchors are missing');
  const home = source.parentNode;
  const anchor = source.ownerDocument.createComment('UCA editor home');
  home.insertBefore(anchor, source);
  let docked = false;
  function dock() {
    if (docked) return false;
    if (source.parentNode !== home) throw new Error('Editor was moved by another controller');
    mount.appendChild(source);
    docked = true;
    return true;
  }
  function restore() {
    if (!docked) return false;
    if (source.parentNode !== mount) throw new Error('Editor docking location was changed externally');
    home.insertBefore(source, anchor.nextSibling);
    docked = false;
    return true;
  }
  return {dock, restore, sync: active => active ? dock() : restore(), get docked() { return docked; }};
}
