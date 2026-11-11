import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, dirname} from 'node:path';
import {revealAceSource} from '../pah/web/static/uca-ace-source-target.mjs';

const ace = {require(name) {
  assert.equal(name, 'ace/range');
  return {Range: class Range {constructor(sr,sc,er,ec) {
    this.start = {row:sr,column:sc}; this.end = {row:er,column:ec};
  }}};
}};
function stub(lines = 300) {
  const markers = new Map(), calls = [];
  let nextId = 10;
  const session = {
    getLength: () => lines,
    getLine: () => 'const example = true;',
    addMarker: (range, css, type, inFront) => {
      const id = nextId++; markers.set(id, {range, css, type, inFront}); return id;
    },
    removeMarker: id => {markers.delete(id); calls.push(['remove',id]);},
  };
  const editor = {
    session, getSession: () => session,
    gotoLine: (...args) => calls.push(['goto',...args]),
    scrollToLine: (...args) => calls.push(['scroll',...args]),
    resize: (...args) => calls.push(['resize',...args]),
  };
  return {session, editor, markers, calls};
}

test('one-based SAT line 125 reveals Ace row 124 and highlights it', () => {
  const {editor,markers,calls} = stub();
  const marker = revealAceSource(editor,ace,{start_line:125,end_line:125});
  assert.equal(marker.id,10);
  assert.deepEqual(calls.filter(c=>c[0]==='goto')[0],['goto',125,0,true]);
  assert.deepEqual(calls.filter(c=>c[0]==='scroll')[0].slice(0,4),['scroll',124,true,true]);
  assert.equal(markers.get(10).range.start.row,124);
  assert.equal(markers.get(10).range.end.row,124);
  assert.equal(markers.get(10).css,'pah-uca-source-highlight');
  assert.equal(markers.get(10).type,'fullLine');
});
test('multi-line finding highlights inclusive span', () => {
  const {editor, markers} = stub();
  const marker = revealAceSource(editor,ace,{start_line:20,end_line:23});
  assert.equal(markers.get(marker.id).range.start.row,19);
  assert.equal(markers.get(marker.id).range.end.row,22);
});
test('new selection clears previous marker, including across editor sessions', () => {
  const first=stub(), second=stub();
  const old = revealAceSource(first.editor,ace,{start_line:30,end_line:30});
  const next = revealAceSource(second.editor,ace,{start_line:10,end_line:11},old);
  assert.equal(first.markers.size,0);
  assert.equal(second.markers.has(next.id),true);
});
test('out of range or invalid locations do not move or mark the editor', () => {
  for (const selection of [{start_line:0,end_line:1},{start_line:10,end_line:9},
      {start_line:301,end_line:301},{start_line:1,end_line:90},
      {start_line:1.5,end_line:2}]) {
    const {editor,markers,calls}=stub();
    assert.throws(()=>revealAceSource(editor,ace,selection),/line range/);
    assert.equal(markers.size,0);
    assert.equal(calls.length,0);
  }
});
test('a goto error leaves no orphaned marker', () => {
  const {editor,markers}=stub();
  editor.gotoLine=()=>{throw Error('layout failed');};
  assert.throws(()=>revealAceSource(editor,ace,{start_line:2,end_line:2}),/layout failed/);
  assert.equal(markers.size,0);
});
test('PAH only reveals after current-disk hash and editor-scope checks', () => {
  const here=dirname(fileURLToPath(import.meta.url));
  const js=readFileSync(resolve(here,'../pah/web/static/pah.js'),'utf8');
  const handler=js.slice(js.indexOf("window.addEventListener('pah:uca-navigate-editor'"));
  assert.ok(handler.indexOf('hash !== selection.source_sha256')>=0);
  assert.ok(handler.indexOf('hash !== selection.source_sha256') < handler.indexOf('revealAceSource('));
  assert.match(handler, /if \(!stillCurrent\(\) \|\| editor\.session !== tab\.editorSession \|\| tab\.dirty\) return;/);
  assert.match(js,/clearUcaSourceMarker\(\)/);
  assert.match(js,/sourceSha256: data.source_sha256/);
  assert.match(js,/let hash = tab.sourceSha256/);
});
