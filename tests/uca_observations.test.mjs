import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeObservations,scopeIdentity} from '../pah/web/static/uca-observation-contract.mjs';
const payload={ok:true,sources:[{owner:'code_analyzer',jobs:[{job_id:'j1',label:'Analyze',state:'succeeded'}]},{owner:'unknown-owner',jobs:[{job_id:'j2',state:'succeeded'}]}]};
test('observations retain producer ownership but never imply artifact parity',()=>{
 const result=summarizeObservations(payload);
 assert.equal(result.rows.length,1);assert.equal(result.rows[0].owner,'code_analyzer');
 assert.equal(result.rows[0].state,'succeeded');assert.equal(result.artifactVerification,'unverified');
});
test('unavailable feed fails closed',()=>{
 assert.throws(()=>summarizeObservations({ok:false,sources:[]}));
 assert.throws(()=>summarizeObservations({ok:true,sources:{}}));
});
test('bounded results and unknown states',()=>{
 const jobs=Array.from({length:35},(_,i)=>({job_id:`j${i}`,state:'custom'}));
 const value=summarizeObservations({ok:true,sources:[{owner:'pypique',jobs}]});
 assert.equal(value.rows.length,30);assert.equal(value.truncated,true);assert.equal(value.rows[0].state,'unknown');
});
test('workspace scope must be server-authoritative',()=>{
 const obj={ok:true,scope:{project_id:'p',repository_id:'r',context_token:'c',revision:1}};
 assert.match(scopeIdentity(obj),/^p/);
 assert.throws(()=>scopeIdentity({ok:true,scope:{project_id:'p'}}));
});
