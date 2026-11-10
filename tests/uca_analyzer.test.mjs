import test from 'node:test';
import assert from 'node:assert/strict';
import {readAnalyzerStatus,readAnalyzerFunctions,readAnalyzerEntity,readAnalyzerDependencies} from '../pah/web/static/uca-analyzer-contract.mjs';
test('rejects missing or malformed analyzer status',()=>{
 assert.throws(()=>readAnalyzerStatus({ok:true,available:true,analyzed:true}));
 assert.equal(readAnalyzerStatus({ok:true,available:true,analyzed:true,stale:false,generation:4}).generation,4);
});
test('bounds list and rejects malformed list',()=>{
 assert.throws(()=>readAnalyzerFunctions({ok:true,functions:{},stale:false}));
 const rows=readAnalyzerFunctions({ok:true,functions:Array.from({length:240},(_,i)=>({id:String(i),path:'a.py'})),stale:false});
 assert.equal(rows.length,200);
});
test('requires matching entity ID and stale indicator',()=>{
 const valid={ok:true,stale:true,entity:{id:'a',path:'a.py',node_type:'function',metadata:{line_start:3}}};
 assert.equal(readAnalyzerEntity(valid,'a').start,3);
 assert.throws(()=>readAnalyzerEntity(valid,'b'));
});
test('requires dependency list pair',()=>{
 assert.deepEqual(readAnalyzerDependencies({ok:true,incoming:[1],outgoing:[1,2]}),{incoming:1,outgoing:2});
 assert.throws(()=>readAnalyzerDependencies({ok:true,incoming:[],outgoing:null}));
});
