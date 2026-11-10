// UCA-11: offline behavioral acceptance of the *actual* UCA browser controller.
// No network, browser, source mutation, or installed module dependency.
import test from 'node:test';
import assert from 'node:assert/strict';

const tick = () => new Promise(resolve => setImmediate(resolve));
const host = (workspace='ws', repository='/repo') => ({
  schema:'pah.uca-navigation-scope@1', workspace_id:workspace, project_id:workspace,
  repository_root:repository, repository_id:'repo-'+'a'.repeat(64),
  context_token:'token-'+workspace, context_revision:1,
});
const result = (workspace='ws') => ({ok:true,selection:{
  schema:'pah.uca-source-revision@1', project_id:workspace,
  relative_path:'src/a.py',source_sha256:'b'.repeat(64),start_line:3,end_line:3,
}});
const response = body => ({ok:true,json:async()=>body});
const deferred = () => {
  let resolve;
  const promise = new Promise(r=>{resolve=r;});
  return {promise, resolve};
};

async function installController(fetchImplementation) {
  const original = {document:globalThis.document,window:globalThis.window,
    fetch:globalThis.fetch, CustomEvent:globalThis.CustomEvent};
  const listeners = new Map();
  const windowListeners = new Map();
  const workspace = {value:'ws',listeners:new Map(),addEventListener(type,cb){this.listeners.set(type,cb);},
    change(value){this.value=value;this.listeners.get('change')?.();}};
  const repository = {value:'/repo',listeners:new Map(),addEventListener(type,cb){this.listeners.set(type,cb);},
    change(value){this.value=value;this.listeners.get('change')?.();}};
  const root = {classList:{contains:()=>false}};
  globalThis.document = {
    getElementById(id){return ({ucaMode:root,researchWorkspaceSelect:workspace,
      workspacePath:repository,openWorkspace:null})[id]??null;},
  };
  globalThis.window = {
    addEventListener(name,cb){(windowListeners.get(name)||windowListeners.set(name,[]).get(name)).push(cb);},
    dispatchEvent(event){for(const cb of windowListeners.get(event.type)||[])cb(event);},
  };
  globalThis.CustomEvent = class {constructor(type,{detail}={}){this.type=type;this.detail=detail;}};
  globalThis.fetch=fetchImplementation;
  // Each test gets a new module instance, and therefore isolated bus/epoch state.
  await import('../pah/web/static/uca-navigation.mjs?acceptance='+Math.random());
  const captured=[];
  for(const pane of ['editor','pypique','code_analyzer'])
    window.addEventListener('pah:uca-navigate-'+pane,e=>captured.push({pane,selection:e.detail.selection}));
  const emit = (type,detail) => window.dispatchEvent(new CustomEvent(type,{detail}));
  const restore=()=>{for(const key of Object.keys(original)){
    if(original[key]===undefined)delete globalThis[key];else globalThis[key]=original[key];
  }};
  return {workspace,repository,captured,emit,restore};
}

// Global DOM fakes are necessarily serialized across tests.
test('switching projects during pending verification discards the old navigation', {concurrency:false},async()=>{
  const pending=deferred();let sourceCalled=false;
  const env=await installController(async url=>{
    if(url.includes('/scope'))return pending.promise;
    sourceCalled=true;return response(result());
  });
  try {
    env.emit('pah:uca-source-selection-request',{
      producer:'editor',relative_path:'src/a.py',start_line:3,end_line:3});
    env.workspace.change('other');
    pending.resolve(response({ok:true,scope:host()}));
    await tick();await tick();
    assert.equal(sourceCalled,false);
    assert.deepEqual(env.captured,[]);
  }finally{env.restore();}
});

test('rejecting stale source verification publishes no cross-pane navigation', {concurrency:false},async()=>{
  const env=await installController(async url=>url.includes('/scope')
    ? response({ok:true,scope:host()})
    : ({ok:false,json:async()=>({ok:false,error:'Source fingerprint mismatch'})}));
  try {
    env.emit('pah:uca-source-selection-request',{
      producer:'code_analyzer',relative_path:'src/a.py',start_line:3,end_line:3});
    await tick();await tick();
    assert.deepEqual(env.captured,[]);
  }finally{env.restore();}
});

test('verified editor selection dispatches once to other panes, never echoes to editor', {concurrency:false},async()=>{
  const env=await installController(async url=>url.includes('/scope')
    ? response({ok:true,scope:host()}) : response(result()));
  try {
    env.emit('pah:uca-source-selection-request',{
      producer:'editor',relative_path:'src/a.py',start_line:3,end_line:3});
    await tick();await tick();
    assert.deepEqual(env.captured.map(e=>e.pane),['pypique','code_analyzer']);
    assert.ok(env.captured.every(e=>e.selection.source_sha256==='b'.repeat(64)));
  }finally{env.restore();}
});

test('switching repository during pending source verification invalidates response', {concurrency:false},async()=>{
  const pending=deferred();
  const env=await installController(async url=>url.includes('/scope')
    ? response({ok:true,scope:host()}) : pending.promise);
  try {
    env.emit('pah:uca-source-selection-request',{
      producer:'editor',relative_path:'src/a.py',start_line:3,end_line:3});
    await tick();
    env.repository.change('/second');
    pending.resolve(response(result()));
    await tick();await tick();
    assert.deepEqual(env.captured,[]);
  }finally{env.restore();}
});
