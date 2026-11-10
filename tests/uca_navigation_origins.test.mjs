import test from 'node:test';
import assert from 'node:assert/strict';
import {fromVerifiedSourceRevision, createNavigationBus} from '../pah/web/static/uca-navigation-contract.mjs';
const host={workspace_id:'ws',project_id:'ws',repository_root:'/repo',repository_id:'repo-'+'a'.repeat(64),context_token:'token',context_revision:2};
const data={ok:true,selection:{schema:'pah.uca-source-revision@1',project_id:'ws',relative_path:'src/a.py',source_sha256:'b'.repeat(64),start_line:2,end_line:2}};
test('editor and analyzer selections retain source revision and project',()=>{
 for (const producer of ['editor','code_analyzer']) {
  const s=fromVerifiedSourceRevision(data,{producer,workspace:'ws',repository:'/repo'},host);
  assert.equal(s.producer,producer);assert.equal(s.source_sha256,data.selection.source_sha256);
  const bus=createNavigationBus(['ws','/repo']);const event=bus.publish(s);
  assert.equal(bus.consume(event,producer),false);assert.equal(bus.consume(event,'pypique'),true);
 }
});
test('rejects fabricated source or wrong project',()=>{
 for(const change of [{source_sha256:''},{project_id:'other'},{relative_path:'../bad'},{start_line:0}])
  assert.throws(()=>fromVerifiedSourceRevision({...data,selection:{...data.selection,...change}},
    {producer:'editor',workspace:'ws',repository:'/repo'},host));
 assert.throws(()=>fromVerifiedSourceRevision(data,{producer:'external',workspace:'ws',repository:'/repo'},host));
});
