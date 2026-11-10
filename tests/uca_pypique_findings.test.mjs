import test from 'node:test';
import assert from 'node:assert/strict';
import {readProjection, eligibleFinding, checkedEvidence} from '../pah/web/static/uca-pypique-contract.mjs';
const loc={producer_module:'pypique',project_id:'p',relative_path:'src/a.py',source_sha256:'a'.repeat(64),start_line:2,end_line:3};
const finding={status:'ready_for_pah_verification',locator:loc};
test('valid producer projection and eligible finding',()=>{
  assert.equal(readProjection({schema:'pypique.source-evidence-projections@1',project_id:'p',total:1,offset:0,results:[finding]}).results.length,1);
  assert.equal(eligibleFinding(finding,'p'),true);
});
test('rejects incomplete or forged evidence',()=>{
  for (const change of [{source_sha256:''},{relative_path:'../secret'},{relative_path:'src/%2e/a'}, {project_id:'other'}, {start_line:0}, {end_line:1}, {relative_path:'src\\x'}])
    assert.equal(eligibleFinding({...finding, locator:{...loc,...change}},'p'),false);
  assert.equal(eligibleFinding({...finding,status:'unavailable'},'p'),false);
});
test('requires matching read-only source response',()=>{
  const valid={ok:true,evidence:{...loc,schema:'pah.source-evidence@1',mode:'read_only',excerpt:'source line'}};
  assert.equal(checkedEvidence(valid,loc).excerpt,'source line');
  for (const change of [{source_sha256:'b'.repeat(64)}, {start_line:1}, {project_id:'q'}, {mode:'editable'}])
    assert.throws(()=>checkedEvidence({ok:true,evidence:{...valid.evidence,...change}},loc),/does not match/);
});
test('accepts paginated finding collections beyond the old 100-finding cap',()=>{
  const data={schema:'pypique.source-evidence-projections@1',project_id:'p',total:1200,offset:200,results:Array(200).fill(finding)};
  assert.equal(readProjection(data).results.length,200);
  assert.throws(()=>readProjection({...data,total:300}));
  assert.throws(()=>readProjection({...data,offset:-1}));
  assert.throws(()=>readProjection({...data,schema:'wrong'}));
});
