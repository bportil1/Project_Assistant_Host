import test from 'node:test';
import assert from 'node:assert/strict';
import {readProviderNavigation,providerOverlap,NAV_SCHEMA} from '../pah/web/static/uca-provider-navigation-contract.mjs';
const sha='a'.repeat(64);
const valid=()=>({ok:true,project_id:'p',snapshot:{schema:NAV_SCHEMA,language:'atlas',provider_id:'atlas',relative_path:'a.as',source_sha256:sha,source_revision_verified:true,capabilities:{structural:true,semantic:false},diagnostics:[],items:[{id:'n',name:'Operation',kind:'operation',relative_path:'a.as',start_line:2,end_line:3,parent_id:null}]}});
test('validates provider result and preserves declared confidence',()=>{
 const s=readProviderNavigation(valid(),'p','a.as'); assert.equal(s.items[0].kind,'operation'); assert.equal(s.capabilities.semantic,false);
});
test('rejects mismatched scope and incompatible schema',()=>{
 assert.throws(()=>readProviderNavigation(valid(),'wrong','a.as'));
 const x=valid();x.snapshot.schema='unknown';assert.throws(()=>readProviderNavigation(x,'p','a.as'));
});
test('rejects duplicate nodes and impossible spans',()=>{
 const a=valid();a.snapshot.items.push({...a.snapshot.items[0]});assert.throws(()=>readProviderNavigation(a,'p','a.as'));
 const b=valid();b.snapshot.items[0].end_line=1;assert.throws(()=>readProviderNavigation(b,'p','a.as'));
});
test('matches only exact path and revision',()=>{
 const s=readProviderNavigation(valid(),'p','a.as');
 assert.equal(providerOverlap(s,{relative_path:'a.as',source_sha256:sha,start_line:3,end_line:4}).length,1);
 assert.equal(providerOverlap(s,{relative_path:'a.as',source_sha256:'b'.repeat(64),start_line:3,end_line:4}).length,0);
});
