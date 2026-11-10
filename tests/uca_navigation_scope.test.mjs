import test from 'node:test';
import assert from 'node:assert/strict';
import {validateHostScope,bindHostIdentity,fromVerifiedEvidence} from '../pah/web/static/uca-navigation-contract.mjs';
const host={schema:'pah.uca-navigation-scope@1',workspace_id:'ws',project_id:'ws',repository_id:'repo-'+'a'.repeat(64),repository_root:'/repo',context_token:'abc',context_revision:3};
const finding={schema:'pah.source-evidence@1',mode:'read_only',producer_module:'pypique',project_id:'ws',relative_path:'src/a.py',source_sha256:'b'.repeat(64),start_line:2,end_line:4};
test('accepts matching host identity',()=>{
 const value=validateHostScope(host,'ws','/repo');
 const bound=bindHostIdentity(fromVerifiedEvidence(finding,{workspace:'ws',repository:'/repo'}),value);
 assert.equal(bound.repository_id,host.repository_id);
 assert.equal(bound.project_id,host.project_id);
});
test('rejects stale host workspace and repository',()=>{
 assert.throws(()=>validateHostScope(host,'other','/repo'));
 assert.throws(()=>validateHostScope(host,'ws','/other'));
 assert.throws(()=>validateHostScope({...host,project_id:'other'},'ws','/repo'));
 assert.throws(()=>validateHostScope({...host,repository_id:'local-path'},'ws','/repo'));
});
test('rejects cross-project finding and malformed host revision',()=>{
 assert.throws(()=>bindHostIdentity(fromVerifiedEvidence({...finding,project_id:'other'},{workspace:'ws',repository:'/repo'}),host));
 assert.throws(()=>validateHostScope({...host,context_revision:NaN},'ws','/repo'));
});
