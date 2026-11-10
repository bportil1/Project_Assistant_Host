import test from 'node:test';
import assert from 'node:assert/strict';
import {createEditorDock} from '../pah/web/static/uca-editor-dock.mjs';

function setup() {
  const home = {children: []};
  const mount = {children: []};
  function move(parent, child, before = null) {
    if (child.parentNode) {
      const old = child.parentNode.children;
      old.splice(old.indexOf(child), 1);
    }
    const index = before ? parent.children.indexOf(before) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, child);
    child.parentNode = parent;
  }
  for (const p of [home, mount]) {
    p.appendChild = child => move(p, child);
    p.insertBefore = (child, before) => move(p, child, before);
  }
  const source = {ownerDocument: {createComment: () => ({})}};
  const after = {};
  home.appendChild(source); home.appendChild(after);
  // In a browser Node.nextSibling is maintained by DOM; this fake exposes it.
  Object.defineProperty(source, 'nextSibling', {get: () => {
    const list = source.parentNode?.children || [];
    return list[list.indexOf(source)+1] || null;
  }});
  const original = home.insertBefore;
  home.insertBefore = (child,before) => original(child,before);
  const dock = createEditorDock({source,mount});
  const anchor = home.children[0];
  Object.defineProperty(anchor,'nextSibling',{get: () => { const list=home.children; return list[list.indexOf(anchor)+1] || null; }});
  return {dock,home,mount,source,after,anchor};
}

test('editor is moved, never cloned, and restored in original order', () => {
  const {dock,home,mount,source,after,anchor}=setup();
  assert.equal(dock.sync(true),true);
  assert.equal(dock.sync(true),false);
  assert.equal(mount.children[0],source);
  assert.equal(dock.sync(false),true);
  assert.deepEqual(home.children,[anchor,source,after]);
  assert.equal(dock.sync(false),false);
});
test('source owner or mount changed externally fails closed', () => {
  const {dock,source,mount}=setup();
  const foreign={children:[],appendChild(child){this.children.push(child);child.parentNode=this;}};
  foreign.appendChild(source);
  assert.throws(() => dock.dock(),/another controller/);
  mount.appendChild(source); // restore into expected home for the positive test
});
test('missing anchors fail instead of constructing a second editor', () => {
  assert.throws(() => createEditorDock({source:null,mount:{}}),/missing/);
});
