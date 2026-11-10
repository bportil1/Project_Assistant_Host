import test from 'node:test';
import assert from 'node:assert/strict';
import {createNavigationBus,fromVerifiedEvidence} from '../pah/web/static/uca-navigation-contract.mjs';
const src={schema:'pah.source-evidence@1',mode:'read_only',producer_module:'pypique',project_id:'pr',relative_path:'src/a.py',source_sha256:'a'.repeat(64),start_line:3,end_line:5};
const scope={workspace:'ws',repository:'/repo'};
test('requires verified read-only evidence and safe identity',()=>{
 const result=fromVerifiedEvidence(src,scope);
 assert.equal(result.schema,'pah.source-selection@1');
 for(const change of [{mode:'editable'},{relative_path:'../a'},{source_sha256:''},{start_line:0},{project_id:''}])
   assert.throws(()=>fromVerifiedEvidence({...src,...change},scope));
});
test('delivers each navigation to separate consumers once',()=>{
 const bus=createNavigationBus(['ws','/repo']);const selection=fromVerifiedEvidence(src,scope);
 const event=bus.publish(selection);
 assert.equal(bus.consume(event,'pypique'),false);
 assert.equal(bus.consume(event,'editor'),true);
 assert.equal(bus.consume(event,'editor'),false);
 assert.equal(bus.consume(event,'code_analyzer'),true);
});
test('switching repository rejects pending events',()=>{
 const bus=createNavigationBus(['ws','/repo']);const old=bus.publish(fromVerifiedEvidence(src,scope));
 bus.switchScope(['ws','/another']);assert.equal(bus.consume(old,'editor'),false);
 assert.throws(()=>bus.publish(fromVerifiedEvidence(src,scope)));
});
test('rejects stale or spoofed navigation events',()=>{
 const bus=createNavigationBus(['ws','/repo']);const event=bus.publish(fromVerifiedEvidence(src,scope));
 assert.equal(bus.consume({...event},'editor'),false);
 assert.equal(bus.consume(event,'unknown'),false);
});
