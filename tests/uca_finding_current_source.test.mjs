import test from 'node:test';
import assert from 'node:assert/strict';
import {candidateFinding, eligibleFinding} from '../pah/web/static/uca-pypique-contract.mjs';
import {fromVerifiedSourceRevision} from '../pah/web/static/uca-navigation-contract.mjs';

const candidate = {schema:'pypique.source-location-candidate@1',project_id:'workspace-A',relative_path:'src/app.py',start_line:17,end_line:17};
const row = {status:'unavailable',reason:'missing_verified_source_sha256', locator:null,candidate};

test('missing scan-time hash preserves a navigation candidate but not verified status',()=>{
  assert.equal(candidateFinding(row,'workspace-A'),true);
  assert.equal(eligibleFinding(row,'workspace-A'),false);
  assert.equal(candidateFinding(row,'workspace-B'),false);
});
test('path escapes and missing lines cannot become candidates',()=>{
  for (const relative_path of ['../secrets.py','/etc/passwd','src/../evil.py','src\\app.py','src//app.py']) {
    assert.equal(candidateFinding({...row,candidate:{...candidate,relative_path}},'workspace-A'),false);
  }
  assert.equal(candidateFinding({...row,candidate:{...candidate,start_line:0}},'workspace-A'),false);
});
test('current-file navigation establishes only current-source identity, never scan-time equivalence',()=>{
  const host={schema:'pah.uca-navigation-scope@1',workspace_id:'workspace-A',project_id:'workspace-A',repository_root:'/repo',repository_id:'repo-'+('a'.repeat(64)),context_token:'x',context_revision:3};
  const result={ok:true,selection:{schema:'pah.uca-source-revision@1',project_id:'workspace-A',relative_path:'src/app.py',start_line:17,end_line:17,source_sha256:'b'.repeat(64)}};
  const selection=fromVerifiedSourceRevision(result,{producer:'pypique',workspace:'workspace-A',repository:'/repo'},host);
  assert.equal(selection.source_origin,'current_location_only');
  assert.equal(selection.producer,'pypique');
  assert.equal(selection.source_sha256,'b'.repeat(64));
  assert.throws(()=>fromVerifiedSourceRevision(result,{producer:'intruder',workspace:'workspace-A',repository:'/repo'},host));
});

test('findings pane includes and selects historical findings with source candidates', async()=>{
  const saved={document:globalThis.document,window:globalThis.window,fetch:globalThis.fetch,Option:globalThis.Option,CustomEvent:globalThis.CustomEvent};
  try {
    class Element {
      constructor(){this.events={};this.children=[];this.disabled=false;this.hidden=false;this.textContent='';this.style={};this.value='';}
      addEventListener(k,fn){this.events[k]=fn;}
      replaceChildren(...children){this.children=children;}
      add(child){this.children.push(child);}
      insertAdjacentElement(_,element){ if(this.id==='ucaFindingSelect' && element.id) byId.set(element.id,element); }
      async fire(k){return this.events[k]?.({});}
    }
    const byId=new Map();
    for (const id of ['ucaFindingLoad','ucaFindingView','ucaFindingPrev','ucaFindingNext','ucaFindingPage',
      'ucaFindingSelect','ucaFindingStatus','ucaFindingPreviewStatus','ucaFindingExcerpt','researchWorkspaceSelect',
      'workspacePath','openWorkspace']) {const el=new Element();el.id=id;byId.set(id,el);}
    byId.get('ucaFindingView').value='all';
    byId.get('researchWorkspaceSelect').value='workspace-A';
    byId.get('workspacePath').value='/repo';
    const events=[];const handlers={};
    globalThis.document={querySelector:()=>new Element(),getElementById:id=>byId.get(id)||null,createElement:tag=>new Element()};
    globalThis.window={addEventListener:(k,fn)=>{handlers[k]=fn;},dispatchEvent:event=>{events.push(event);handlers[event.type]?.(event);}};
    globalThis.Option=class {constructor(text,value){this.text=text;this.value=value;}};
    globalThis.CustomEvent=class {constructor(type,{detail}){this.type=type;this.detail=detail;}};
    globalThis.fetch=async()=>({ok:true,json:async()=>({ok:true,projection:{schema:'pypique.source-evidence-projections@1',project_id:'workspace-A',total:1,offset:0,results:[{...row,provider:'semgrep',finding_id:'f-1',summary:{file_path:'src/app.py',line:17,severity:'HIGH',message:'Detected issue',cwes:['CWE-79']}}]}})});
    await import('../pah/web/static/uca-pypique-findings.mjs?candidate_test='+Date.now());
    await byId.get('ucaFindingLoad').fire('click');
    assert.equal(byId.get('ucaFindingSelect').disabled,false);
    assert.equal(byId.get('ucaFindingSelect').children.length,2);
    assert.match(byId.get('ucaFindingStatus').textContent,/1 current-source candidates/);
    byId.get('ucaFindingSelect').value='0';
    await byId.get('ucaFindingSelect').fire('change');
    assert.match(byId.get('ucaFindingDetails').textContent,/CWE-79/);
    assert.equal(byId.get('ucaFindingOpenCurrent').hidden,false);
    await byId.get('ucaFindingOpenCurrent').fire('click');
    const request=events.find(e=>e.type==='pah:uca-source-selection-request');
    assert.deepEqual(request.detail,{producer:'pypique',relative_path:'src/app.py',start_line:17,end_line:17});
  } finally {Object.assign(globalThis,saved);}
});
