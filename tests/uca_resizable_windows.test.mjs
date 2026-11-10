import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultLayout,resizeAdjacent,withPane} from '../pah/web/static/uca-layout-state.mjs';
import {eligibleRelay} from '../pah/web/static/uca-window-navigation-contract.mjs';

test('adjacent drag preserves other pane and pair total',()=>{
  const base=defaultLayout();
  const next=resizeAdjacent(base,'editor','pypique',0.7);
  assert.equal(next.widths.analyzer,base.widths.analyzer);
  assert.equal(next.widths.editor+next.widths.pypique,67);
  assert.ok(next.widths.editor>base.widths.editor);
});
test('drag clamps to feasible paired widths and rejects invalid panes',()=>{
  const base=defaultLayout();
  for (const f of [-5,10]) {
    const next=resizeAdjacent(base,'editor','pypique',f);
    assert.ok(next.widths.editor>=15&&next.widths.pypique>=15);
    assert.equal(next.widths.editor+next.widths.pypique,67);
  }
  assert.throws(()=>resizeAdjacent(base,'editor','editor',0.5));
  assert.throws(()=>resizeAdjacent(base,'editor','pypique',NaN));
  const pair=withPane(base,'analyzer',false);
  assert.equal(resizeAdjacent(pair,'editor','pypique',0.3).visible.length,2);
});
const selected={schema:'pah.source-selection@1',producer:'pypique',project_id:'ws',workspace:'ws',repository:'/repos/a',
  workspace_id:'ws',repository_id:'repo-'+ 'a'.repeat(64),context_token:'tk',context_revision:3,
  relative_path:'src/test.py',source_sha256:'b'.repeat(64),start_line:1,end_line:1};
test('window relay rejects different workspaces, unsafe paths and unverified identity',()=>{
  assert.equal(eligibleRelay(selected,'ws','/repos/a'),true);
  for(const change of [{relative_path:'../secret'}, {source_sha256:'bad'}, {project_id:'other'},
    {repository_id:'repo-other'},{context_revision:-1},{end_line:0}])
    assert.equal(eligibleRelay({...selected,...change},'ws','/repos/a'),false);
  assert.equal(eligibleRelay(selected,'other','/repos/a'),false);
  assert.equal(eligibleRelay(selected,'ws','/repos/b'),false);
});
