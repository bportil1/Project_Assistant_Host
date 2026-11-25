import test from 'node:test';
import assert from 'node:assert/strict';
import {
  InteractiveGraphContractError,validateInteractiveGraphView,interactiveGraphLayout,
  interactiveGraphTrace,interactiveLayerOverview,interactiveGraphRows,mountInteractiveGraph
} from '../src/pah_shared/static/interactive_graph_view.mjs';

function example() {
  return {schema:'pah-shared.graph-view@1',view_id:'source-tree',source_revision:'sha256:original',
    graph_role:'source_structure',title:'<img src=x onerror=alert(1)>',
    nodes:[{id:'root',label:'<script>bad</script>',kind:'object',group:'0'},
      {id:'child',label:'child',kind:'leaf',group:'1'},
      {id:'other',label:'other',kind:'leaf',group:'1'}],
    edges:[{id:'child-edge',source:'root',target:'child',directed:true,traceable:true},
      {id:'association',source:'child',target:'other',directed:false,traceable:false,label:'non-ancestral display trace'}],
    display:{layout:'layers',coverage:{scope:'exhaustive',total_nodes:3,total_edges:2}},
    overlays:{nodes:{child:{status:'measured',metrics:[{name:'entropy',unit:'bits',estimator:'empirical',status:'measured',value:0.7,support:20}]}},edges:{}}
  };
}
function mutate(fn){const model=example();fn(model);return model;}
class FakeElement {
  constructor(name,document){this.name=name;this.ownerDocument=document;this.attrs={};this.children=[];this.listeners={};this.text='';this.parent=null;this.style={};}
  setAttribute(name,value){this.attrs[name]=String(value);}
  getAttribute(name){return this.attrs[name]??null;}
  appendChild(child){this.children.push(child);child.parent=this;return child;}
  replaceChildren(...children){this.children=children;for(const child of children)child.parent=this;}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  fire(name,overrides={}){const event={key:undefined,button:0,pointerId:0,clientX:0,clientY:0,deltaY:-50,
    target:this,preventDefault(){this.defaultPrevented=true;},stopPropagation(){},...overrides};
    for(const fn of this.listeners[name]??[])fn(event);return event;}
  getBoundingClientRect(){return {left:0,top:0,width:1000,height:580};}
  setPointerCapture(){}
  closest(){return this.name==='g' && (this.attrs['data-node-id']||this.attrs['data-edge-id'])?this:null;}
  set textContent(value){this.text=String(value);this.children=[];}
  get textContent(){return this.text;}
}
const doc={createElementNS(_ns,name){return new FakeElement(name,doc);}};
function mount(view=example(),options={}){const root=new FakeElement('div',doc);
  return {root,viewer:mountInteractiveGraph(root,view,{document:doc,...options})};}
function gather(item,predicate,out=[]){if(predicate(item))out.push(item);for(const child of item.children??[])gather(child,predicate,out);return out;}
const byNode=(root,id)=>gather(root,n=>n.attrs?.['data-node-id']===id)[0];
const byEdge=(root,id)=>gather(root,n=>n.attrs?.['data-edge-id']===id)[0];

test('validates domain-neutral source identity, mixed directed display links and detached copy',()=>{
  const input=example(),model=validateInteractiveGraphView(input);
  assert.equal(model.nodes[0].label,input.nodes[0].label);
  assert.equal(model.edges[1].directed,false);
  input.nodes[0].label='mutated';
  assert.equal(model.nodes[0].label,'<script>bad</script>');
  assert.equal(model.overlays.nodes.child.metrics[0].value,.7);
});
test('rejects invalid IDs, dangling links, unknown roles/coverage and missing explicit direction',()=>{
  for(const update of [
    x=>x.schema='pah-shared.graph@1', x=>x.view_id='', x=>x.source_revision='',
    x=>x.nodes[1].id='root',x=>x.edges[0].id=x.edges[1].id,
    x=>x.edges[0].target='missing',x=>delete x.edges[0].directed,
    x=>x.display.coverage.scope='silent',x=>x.display.coverage.total_nodes=2,
    x=>x.display.coverage.total_edges=4,x=>x.display.layout='unknown',
    x=>x.nodes[0].position={x:NaN,y:1},
    x=>{x.display.layout='recorded';},
    x=>{x.overlays.nodes.nope={status:'pending',metrics:[]};},
    x=>{x.overlays.nodes.child.metrics[0].value=NaN;},
    x=>{x.overlays.nodes.child.metrics[0].support=-1;},
    x=>{x.overlays.nodes.child.metrics[0].status='pending';},
    x=>{x.edges[1].traceable='yes';},
  ]) assert.throws(()=>validateInteractiveGraphView(mutate(update)),InteractiveGraphContractError);
});
test('partial input must declare sampled/filtered/page coverage with original counts',()=>{
  const m=mutate(x=>{x.nodes.pop();x.edges.pop();x.display.coverage={scope:'filtered',total_nodes:500,total_edges:1000};});
  assert.equal(validateInteractiveGraphView(m).display.coverage.total_nodes,500);
  m.display.coverage.scope='exhaustive';
  assert.throws(()=>validateInteractiveGraphView(m),InteractiveGraphContractError);
});
test('overlay zero is a measured value; unavailable is not zero',()=>{
  const m=mutate(x=>{x.overlays.nodes.child.metrics[0].value=0;x.overlays.nodes.root={status:'unavailable',metrics:[{name:'variance',value:null,status:'unavailable'}]};});
  assert.equal(validateInteractiveGraphView(m).overlays.nodes.child.metrics[0].value,0);
  assert.equal(validateInteractiveGraphView(m).overlays.nodes.root.metrics[0].value,null);
});
test('deterministic layering follows explicit group, not inferred ancestry',()=>{
  const first=interactiveGraphLayout(example()),second=interactiveGraphLayout(example());
  assert.deepEqual([...first],[...second]);
  assert.equal(first.get('child').y,first.get('other').y);
  assert.ok(first.get('root').y < first.get('child').y);
});
test('recorded and cyclic circular positions are presentation only',()=>{
  const m=mutate(x=>{x.display.layout='recorded';x.nodes.forEach((n,i)=>n.position={x:i*2,y:i});});
  assert.deepEqual(interactiveGraphLayout(m).get('other'),{x:4,y:2});
  const cycle=mutate(x=>{x.display.layout='circular';x.edges=[...x.edges,{id:'cycle',source:'other',target:'root',directed:true}];x.display.coverage.total_edges++;});
  assert.equal(interactiveGraphLayout(cycle).size,3);
});
test('recorded source traces follow only explicit directed traceable edges',()=>{
  const m=example();
  assert.deepEqual([...interactiveGraphTrace(m,'root').nodes].sort(),['child','root']);
  assert.deepEqual([...interactiveGraphTrace(m,'root').edges],['child-edge']);
  assert.deepEqual([...interactiveGraphTrace(m,'child',{context:true}).nodes].sort(),['child','root']);
  assert.deepEqual([...interactiveGraphTrace(m,'nope').nodes],[]);
});
test('layer overview preserves source totals and marks collapsed summaries',()=>{
  const m=example(),summary=interactiveLayerOverview(m);
  assert.equal(summary.coverage.scope,'collapsed');
  assert.equal(summary.coverage.total_nodes,3);
  assert.equal(summary.coverage.rendered_nodes,2);
  assert.equal(summary.edges.length,1);
  assert.equal(m.nodes[0].id,'root');
});
test('selection emits IDs plus view and source revision; inspector remains owner-controlled',()=>{
  const selections=[];const {viewer,root}=mount(example(),{onSelect:x=>selections.push(x)});
  assert.equal(viewer.select('node','child'),true);
  assert.deepEqual(selections[0],{view_id:'source-tree',source_revision:'sha256:original',graph_role:'source_structure',kind:'node',id:'child'});
  assert.equal(viewer.select('edge','association'),true);
  assert.equal(viewer.select('node','absent'),false);
  assert.equal(byEdge(root,'association').getAttribute('role'),'button');
  assert.equal(viewer.selection.id,'association');
});
test('DOM labels are text, not HTML, including owner-controlled source strings',()=>{
  const {root,viewer}=mount();
  assert.equal(root.children[0].getAttribute('role'),'group');
  assert.equal(byNode(root,'root').children[1].text,'<script>bad</script>');
  assert.ok(!gather(root,n=>n.name==='script').length);
  assert.equal(byNode(root,'child').getAttribute('data-overlay-status'),'measured');
  assert.match(root.children[0].getAttribute('aria-label'),/exhaustive view/);
  assert.equal(viewer.coverage.rendered_nodes,3);
});
test('explicit mixed direction arrows appear only for directed edges',()=>{
  const {root}=mount();
  assert.equal(gather(byEdge(root,'child-edge'),n=>n.name==='polygon').length,1);
  assert.equal(gather(byEdge(root,'association'),n=>n.name==='polygon').length,0);
});
test('keyboard node/edge activation and keyboard pan work',()=>{
  const events=[];const {viewer,root}=mount(example(),{onSelect:e=>events.push(e)});
  byNode(root,'root').fire('keydown',{key:'Enter'});
  assert.equal(events[0].kind,'node');
  byEdge(root,'association').fire('keydown',{key:' '});
  assert.equal(events[1].id,'association');
  const start=viewer.camera.x;
  root.children[0].fire('keydown',{key:'ArrowLeft'});
  assert.ok(viewer.camera.x>start);
});
test('fit, wheel, zoom and pointer panning are bounded and callback-driven',()=>{
  const frames=[];const {root,viewer}=mount(example(),{onViewportChange:x=>frames.push(x)});
  const zoom=viewer.camera.zoom;
  root.children[0].fire('wheel',{deltaY:-1});
  assert.ok(viewer.camera.zoom>zoom);
  assert.throws(()=>viewer.zoom(NaN),InteractiveGraphContractError);
  const x=viewer.camera.x;
  root.children[0].fire('pointerdown',{pointerId:3,clientX:10,clientY:10});
  root.children[0].fire('pointermove',{pointerId:3,clientX:30,clientY:10});
  assert.equal(viewer.camera.x,x+20);
  assert.ok(frames.length>=3);
});
test('clear selection when revision or view changes; no stale callbacks on update',()=>{
  const {viewer}=mount();viewer.select('node','root');
  const next=mutate(x=>{x.source_revision='sha256:changed';});
  viewer.update(next,{preserveSelection:true});
  assert.equal(viewer.selection,null);
  assert.equal(viewer.coverage.total_nodes,3);
});
test('same revision can preserve explicit valid selected ID, otherwise clears',()=>{
  const {viewer}=mount();viewer.select('node','child');
  viewer.update(example(),{preserveSelection:true});assert.equal(viewer.selection.id,'child');
  viewer.update(example());assert.equal(viewer.selection,null);
});
test('table selection bridge uses original node/edge IDs and source revisions',()=>{
  const rows=interactiveGraphRows(example());
  assert.equal(rows.nodes[1].overlay_status,'measured');
  assert.equal(rows.edges[1].directed,false);
  assert.equal(rows.source_revision,'sha256:original');
  assert.deepEqual(rows.nodes[1].metrics[0].value,0.7);
  const {viewer}=mount();assert.equal(viewer.select('node',rows.nodes[1].id),true);
});
test('oversized graphs automatically show labeled groups and provide paged drill-down',()=>{
  const m=example();m.nodes=[];m.edges=[];m.overlays={nodes:{},edges:{}};
  for(let i=0;i<520;i++)m.nodes.push({id:`n${i}`,label:`node ${i}`,group:'level-0',kind:'data'});
  m.display.coverage={scope:'exhaustive',total_nodes:520,total_edges:0};
  const {root,viewer}=mount(m);
  assert.equal(viewer.coverage.scope,'collapsed');
  assert.match(viewer.viewDescription,/Layer overview/);
  byNode(root,'summary:level-0').fire('click');
  assert.equal(viewer.coverage.scope,'page');
  assert.equal(viewer.coverage.rendered_nodes,12);
  viewer.nextPage();assert.equal(viewer.coverage.rendered_nodes,12);
  viewer.previousPage();assert.equal(viewer.coverage.rendered_nodes,12);
  viewer.context();assert.equal(viewer.coverage.scope,'collapsed');
});
test('dense graphs do not silently draw only part of the supplied edges',()=>{
  const m=example();m.edges=[];
  for(let i=0;i<1000;i++)m.edges.push({id:`e${i}`,source:'root',target:i%2?'child':'other',directed:i%2===1});
  m.display.coverage.total_edges=1000;
  const {viewer}=mount(m);assert.equal(viewer.coverage.scope,'collapsed');
  assert.equal(viewer.coverage.total_edges,1000);
});
test('external table selection may recenter a node without changing source objects',()=>{
  const {viewer}=mount();
  const before=viewer.camera.x;
  viewer.select('node','child',{recenter:true});
  assert.notEqual(viewer.camera.x,before);
  assert.equal(viewer.selection.id,'child');
});
test('destroy removes view and disallows update; no automatic fetch or storage',()=>{
  const {viewer,root}=mount();viewer.destroy();viewer.destroy();
  assert.equal(root.children.length,0);
  assert.throws(()=>viewer.update(example()),InteractiveGraphContractError);
});
