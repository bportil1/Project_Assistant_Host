/**
 * SU-02 — opt-in, offline interactive scientific graph view.
 *
 * Presentation/controller routines adapted from pyPIQUE's
 * src/pique_py/static/model_explorer.js (layout, layerOverview, camera fit/zoom,
 * source tracing, pointer navigation and bounded layer drill-down), with
 * keyboard/edge selection patterns from static/concluded_graph.js.
 * pyPIQUE: MIT license, copyright (c) 2019 Montana State University
 * Software Engineering Labs. See THIRD_PARTY_NOTICES_GRAPH.md.
 *
 * No pyPIQUE scientific interpretation, data loading, persistence or inference.
 * This does NOT alter the existing graph@1 or hierarchy@1 contracts.
 */
export class InteractiveGraphContractError extends Error {
  constructor(message) { super(message); this.name = 'InteractiveGraphContractError'; }
}
const fail = message => { throw new InteractiveGraphContractError(message); };
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const string = (value, name, max=240, required=true) => {
  if (typeof value !== 'string' || value.length > max || (required && !value)) fail(`${name}: expected ${required?'nonempty ':''}string <= ${max}`);
  return value;
};
const number = value => typeof value === 'number' && Number.isFinite(value);
const limits = Object.freeze({nodes:5000,edges:15000,renderNodes:450,renderEdges:850,groups:300,metrics:16});
const SVG_NS = 'http://www.w3.org/2000/svg';
function el(doc,name,attrs={},text=null) {
  const item = doc.createElementNS(SVG_NS,name);
  for (const [key,value] of Object.entries(attrs)) item.setAttribute(key,String(value));
  if (text !== null) item.textContent = text;
  return item;
}
const copy = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));

/** Validate a separate *presentation* view; IDs refer to owner-owned objects. */
export function validateInteractiveGraphView(input) {
  if (!record(input) || input.schema !== 'pah-shared.graph-view@1') fail('Unsupported interactive graph schema');
  const view_id = string(input.view_id,'view_id',128);
  const source_revision = string(input.source_revision,'source_revision',240);
  const graph_role = string(input.graph_role,'graph_role',96);
  const title = string(input.title ?? '', 'title',240,false);
  if (!Array.isArray(input.nodes) || input.nodes.length > limits.nodes) fail('Node array missing or exceeds 5000');
  if (!Array.isArray(input.edges) || input.edges.length > limits.edges) fail('Edge array missing or exceeds 15000');
  const ids = new Set(), edgeIds = new Set(), groups = new Set();
  const nodes=input.nodes.map((n,i)=>{
    if (!record(n)) fail(`nodes[${i}] must be an object`);
    const id=string(n.id,`nodes[${i}].id`,128);
    if (ids.has(id)) fail(`Duplicate node ID ${id}`);
    ids.add(id);
    const label=string(n.label ?? id,`nodes[${i}].label`,240,false);
    const kind=string(n.kind ?? '',`nodes[${i}].kind`,96,false);
    const group=string(n.group ?? kind ?? '',`nodes[${i}].group`,96,false);
    groups.add(group);
    let position=null;
    if (n.position !== undefined && n.position !== null) {
      if (!record(n.position) || !number(n.position.x) || !number(n.position.y)) fail(`nodes[${i}].position must have finite x/y`);
      position={x:n.position.x,y:n.position.y};
    }
    return {id,label,kind,group,position};
  });
  if(groups.size>limits.groups) fail('Too many display groups');
  const edges=input.edges.map((e,i)=>{
    if (!record(e)) fail(`edges[${i}] must be an object`);
    const id=string(e.id,`edges[${i}].id`,128);
    if(edgeIds.has(id)) fail(`Duplicate edge ID ${id}`);
    edgeIds.add(id);
    const source=string(e.source,`edges[${i}].source`,128),target=string(e.target,`edges[${i}].target`,128);
    if(!ids.has(source)||!ids.has(target)) fail(`Dangling edge ${id}`);
    if(typeof e.directed!=='boolean') fail(`edges[${i}].directed must be explicit boolean`);
    if(e.traceable!==undefined && typeof e.traceable!=='boolean') fail(`edges[${i}].traceable must be boolean`);
    return {id,source,target,directed:e.directed,traceable:e.traceable===true,
      label:string(e.label??'',`edges[${i}].label`,240,false),kind:string(e.kind??'',`edges[${i}].kind`,96,false)};
  });
  if(!record(input.display)) fail('display must be an object');
  const layout=input.display.layout;
  if(!['layers','recorded','circular'].includes(layout)) fail('display.layout must be layers, recorded, or circular');
  if(layout==='recorded' && nodes.some(n=>!n.position)) fail('Recorded layout requires all node positions');
  const coverage=input.display.coverage;
  if(!record(coverage)) fail('display.coverage is required');
  const scope=coverage.scope;
  if(!['exhaustive','sampled','filtered','collapsed','page'].includes(scope)) fail('Unknown coverage scope');
  const total_nodes=coverage.total_nodes,total_edges=coverage.total_edges;
  if(!Number.isSafeInteger(total_nodes)||total_nodes<nodes.length || !Number.isSafeInteger(total_edges)||total_edges<edges.length) fail('Invalid source coverage totals');
  if(scope==='exhaustive' && (total_nodes!==nodes.length || total_edges!==edges.length)) fail('Exhaustive scope must account for all nodes/edges');
  const seed=coverage.seed === undefined?null:coverage.seed;
  if(seed!==null && !(typeof seed==='string' || Number.isSafeInteger(seed))) fail('coverage.seed must be string or safe integer');
  const overlays=input.overlays ?? {nodes:{},edges:{}};
  if(!record(overlays) || !record(overlays.nodes??{}) || !record(overlays.edges??{})) fail('overlays must contain node and edge maps');
  const validateOverlays=(values,known,prefix)=>{
    const validated=Object.create(null);
    for(const [id,entry] of Object.entries(values??{})) {
      if(!known.has(id)) fail(`Unknown ${prefix} overlay ID ${id}`);
      if(!record(entry) || !Array.isArray(entry.metrics) || entry.metrics.length>limits.metrics) fail(`Invalid overlay ${prefix} ${id}`);
      const status=string(entry.status ?? 'unavailable',`overlay status ${id}`,48);
      if(!['measured','pending','unavailable','insufficient_support'].includes(status)) fail(`Invalid overlay status ${id}`);
      validated[id]={status,metrics:entry.metrics.map((m,index)=>{
        if(!record(m)) fail(`Invalid metric ${id}[${index}]`);
        const name=string(m.name,`metric name ${id}`,96),unit=string(m.unit??'',`metric unit ${id}`,48,false);
        const estimator=string(m.estimator??'',`metric estimator ${id}`,128,false);
        const metricStatus=string(m.status??status,`metric status ${id}`,48);
        if(!['measured','pending','unavailable','insufficient_support'].includes(metricStatus)) fail('Invalid metric status');
        if(!(m.value===null || number(m.value))) fail('Metric value must be finite number or null');
        if(metricStatus!=='measured' && m.value!==null) fail('Unavailable metric cannot have a numeric value');
        if(m.support!==undefined && m.support!==null && (!Number.isSafeInteger(m.support)||m.support<0)) fail('Invalid metric support');
        return {name,unit,estimator,status:metricStatus,value:m.value,support:m.support??null};
      })};
    }
    return validated;
  };
  // Cloned detached model: caller mutation never changes a mounted view.
  return {schema:'pah-shared.graph-view@1',view_id,source_revision,graph_role,title,nodes,edges,
    display:{layout,coverage:{scope,total_nodes,total_edges,seed}},
    overlays:{nodes:validateOverlays(overlays.nodes,ids,'node'),edges:validateOverlays(overlays.edges,edgeIds,'edge')}};
}

/** Adapted from pyPIQUE's layer layout; tiers are explicit *display groups*. */
export function interactiveGraphLayout(view) {
  const model = validateInteractiveGraphView(view);
  if(model.display.layout==='recorded') return new Map(model.nodes.map(n=>[n.id,{...n.position}]));
  if(model.display.layout==='circular') {
    const count=Math.max(1,model.nodes.length);
    return new Map(model.nodes.slice().sort((a,b)=>a.id.localeCompare(b.id)).map((n,i)=>[
      n.id,{x:550+Math.cos(2*Math.PI*i/count)*Math.max(160,count*3),y:320+Math.sin(2*Math.PI*i/count)*Math.max(160,count*3)}]));
  }
  const groups = new Map();
  for(const node of model.nodes) {if(!groups.has(node.group)) groups.set(node.group,[]);groups.get(node.group).push(node);}
  const types=[...groups.keys()].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  const gapX=205, bandGap=185;
  const maxColumns=Math.max(1,...types.map(type=>groups.get(type).length));
  const centerX=145+(maxColumns-1)*gapX/2;
  const positions=new Map();
  types.forEach((type,i)=>{
    const items=groups.get(type).slice().sort((a,b)=>a.id.localeCompare(b.id,undefined,{numeric:true}));
    const left=centerX-(items.length-1)*gapX/2;
    items.forEach((node,col)=>positions.set(node.id,{x:left+col*gapX,y:95+i*bandGap}));
  });
  return positions;
}

/** The graph-trace algorithm is ported from pyPIQUE's traceSources/traceInContext.
 * Only edges explicitly opted into provenance tracing are traversed. */
export function interactiveGraphTrace(input, selectedId, {context=false}={}) {
  const model=validateInteractiveGraphView(input),known=new Set(model.nodes.map(n=>n.id));
  if(!known.has(selectedId)) return {nodes:new Set(),edges:new Set()};
  const forward=new Map(),reverse=new Map();
  for(const edge of model.edges) {
    if(!edge.traceable || !edge.directed) continue;
    if(!forward.has(edge.source)) forward.set(edge.source,[]);
    forward.get(edge.source).push({neighbor:edge.target,edgeId:edge.id});
    if(!reverse.has(edge.target)) reverse.set(edge.target,[]);
    reverse.get(edge.target).push({neighbor:edge.source,edgeId:edge.id});
  }
  const nodes=new Set(),edges=new Set(),stack=[selectedId];
  while(stack.length){const id=stack.pop();if(nodes.has(id))continue;nodes.add(id);
    for(const item of forward.get(id)??[]){edges.add(item.edgeId);stack.push(item.neighbor);}}
  if(context){const seen=new Set(),ancestors=[selectedId];
    while(ancestors.length){const id=ancestors.pop();if(seen.has(id))continue;seen.add(id);
      for(const item of reverse.get(id)??[]){nodes.add(item.neighbor);edges.add(item.edgeId);ancestors.push(item.neighbor);}}}
  return {nodes,edges};
}

/** pyPIQUE's layerOverview, generalized: summaries are explicitly display-only. */
export function interactiveLayerOverview(input) {
  const model=validateInteractiveGraphView(input),groups=new Map();
  for(const node of model.nodes){if(!groups.has(node.group))groups.set(node.group,[]);groups.get(node.group).push(node);}
  const summary=[...groups].map(([group,items])=>({id:`summary:${group}`,label:`${group||'ungrouped'} · ${items.length} nodes`,kind:'display_summary',group,count:items.length}));
  const present=new Set(summary.map(n=>n.id)),byId=new Map(model.nodes.map(n=>[n.id,n]));
  const pairCounts=new Map();
  for(const edge of model.edges){const a=byId.get(edge.source).group,b=byId.get(edge.target).group;
    if(a===b)continue;
    const key=JSON.stringify([a,b,edge.directed]);pairCounts.set(key,(pairCounts.get(key)??0)+1);}
  return {nodes:summary,edges:[...pairCounts].map(([key,count],index)=>{const [a,b,directed]=JSON.parse(key);
    return {id:`summary-edge:${index}`,source:`summary:${a}`,target:`summary:${b}`,directed,traceable:false,kind:'display_summary',label:`${count} recorded edges`,count};}),
    coverage:{scope:'collapsed',total_nodes:model.display.coverage.total_nodes,total_edges:model.display.coverage.total_edges,
      rendered_nodes:summary.length,rendered_edges:pairCounts.size},summary_ids:present};
}

function bounds(positions) {
  if(!positions.size) return {left:0,right:1000,top:0,bottom:600};
  let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
  for(const p of positions.values()) {left=Math.min(left,p.x);right=Math.max(right,p.x);top=Math.min(top,p.y);bottom=Math.max(bottom,p.y);}
  return {left:left-120,right:right+120,top:top-75,bottom:bottom+75};
}
function validDimensions(width,height) {
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<320||width>4096||height<240||height>4096) fail('Invalid view dimensions');
}

/**
 * Mount an opt-in scientific viewer. No DOM is touched until explicit mount.
 * API intentionally resembles pyPIQUE's mount/update/fit/zoom/overview/context.
 * A view can be displayed without scientific observations or metrics.
 */
export function mountInteractiveGraph(container,input,{document=container?.ownerDocument,width=1000,height=580,
  onSelect=()=>{},onViewportChange=()=>{}}={}) {
  if(!container||typeof container.replaceChildren!=='function'||!document?.createElementNS) fail('DOM container required');
  if(typeof onSelect!=='function'||typeof onViewportChange!=='function') fail('Event callbacks must be functions');
  validDimensions(width,height);
  let model=validateInteractiveGraphView(input),selected=null,dragging=null,destroyed=false;
  let manualOverview=false,groupFocus=null,groupPage=0,focusOnly=false;
  const PAGE_SIZE=12;
  let camera={x:0,y:0,zoom:1};
  let lastCoverage=null;
  const svg=el(document,'svg',{viewBox:`0 0 ${width} ${height}`,role:'group',tabindex:'0',
    'aria-label':model.title || 'Interactive scientific graph',class:'pah-interactive-graph'});
  container.replaceChildren(svg);
  const ids=()=>({nodes:new Set(model.nodes.map(n=>n.id)),edges:new Set(model.edges.map(e=>e.id))});
  function notifyViewport() {if(destroyed)return;onViewportChange({view_id:model.view_id,source_revision:model.source_revision,camera:{...camera},coverage:copy(lastCoverage)});}
  function visibleGraph() {
    if(manualOverview && !selected) return interactiveLayerOverview(model);
    const nodes=model.nodes,edges=model.edges;
    let visibleNodes=nodes, visibleEdges=edges,scope=model.display.coverage.scope;
    if(groupFocus!==null) {
      const main=nodes.filter(n=>n.group===groupFocus).slice(groupPage*PAGE_SIZE,(groupPage+1)*PAGE_SIZE);
      const base=new Set(main.map(n=>n.id)),neighbor=[];
      for(const edge of edges){if(base.has(edge.source) && !base.has(edge.target)) neighbor.push(edge.target);
        if(base.has(edge.target) && !base.has(edge.source)) neighbor.push(edge.source);}
      const keep=new Set([...base,...[...new Set(neighbor)].sort().slice(0,72)]);
      visibleNodes=nodes.filter(n=>keep.has(n.id));
      visibleEdges=edges.filter(e=>keep.has(e.source)&&keep.has(e.target)&&(base.has(e.source)||base.has(e.target)));
      scope='page';
    } else if(focusOnly && selected?.kind==='node') {
      const traced=interactiveGraphTrace(model,selected.id);
      visibleNodes=nodes.filter(n=>traced.nodes.has(n.id));visibleEdges=edges.filter(e=>traced.edges.has(e.id));scope='filtered';
    }
    if(visibleNodes.length>limits.renderNodes || visibleEdges.length>limits.renderEdges) {
      // A large graph is *not* truncated invisibly. Use a labelled layer overview,
      // then page into real nodes, as pyPIQUE's explorer does.
      const summary=interactiveLayerOverview(model);
      return {...summary,automaticOverview:true};
    }
    return {nodes:visibleNodes,edges:visibleEdges,
      coverage:{scope,total_nodes:model.display.coverage.total_nodes,total_edges:model.display.coverage.total_edges,
        rendered_nodes:visibleNodes.length,rendered_edges:visibleEdges.length}};
  }
  function positionsFor(current) {
    if(current.summary_ids){const groups=[...new Set(current.nodes.map(n=>n.group))].sort();
      return new Map(current.nodes.map(n=>[n.id,{x:400,y:100+groups.indexOf(n.group)*155}]));}
    // Fast validated layout of the visible subset without requiring a new scientific object.
    if(model.display.layout==='recorded') return new Map(current.nodes.map(n=>[n.id,{...n.position}]));
    if(model.display.layout==='circular') {const ordered=current.nodes.slice().sort((a,b)=>a.id.localeCompare(b.id));
      return new Map(ordered.map((n,i)=>[n.id,{x:500+Math.cos(2*Math.PI*i/Math.max(1,ordered.length))*Math.max(160,ordered.length*3),
        y:290+Math.sin(2*Math.PI*i/Math.max(1,ordered.length))*Math.max(160,ordered.length*3)}]));}
    const groups=new Map();for(const n of current.nodes){if(!groups.has(n.group))groups.set(n.group,[]);groups.get(n.group).push(n);}
    const tiers=[...groups.keys()].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
    const max=Math.max(1,...tiers.map(t=>groups.get(t).length));
    const center=145+(max-1)*205/2,positions=new Map();
    tiers.forEach((t,i)=>{const items=groups.get(t).slice().sort((a,b)=>a.id.localeCompare(b.id,undefined,{numeric:true}));
      const left=center-(items.length-1)*205/2;items.forEach((n,j)=>positions.set(n.id,{x:left+j*205,y:95+i*185}));});
    return positions;
  }
  function draw(){
    if(destroyed)return;
    svg.replaceChildren();
    const current=visibleGraph(),positions=positionsFor(current);
    lastCoverage=current.coverage;
    svg.setAttribute('aria-label',`${model.title||'Scientific graph'}; ${current.coverage.scope} view showing ${current.coverage.rendered_nodes} nodes and ${current.coverage.rendered_edges} edges of ${current.coverage.total_nodes} nodes and ${current.coverage.total_edges} edges`);
    const group=el(document,'g',{transform:`translate(${camera.x} ${camera.y}) scale(${camera.zoom})`});
    svg.appendChild(group);
    const trace=selected?.kind==='node' ? interactiveGraphTrace(model,selected.id,{context:!focusOnly}):{nodes:new Set(),edges:new Set()};
    const hasTrace=selected?.kind==='node' && !current.summary_ids;
    const byId=new Map(positions);
    const edgeLayer=el(document,'g',{'data-layer':'edges'});
    for(const edge of current.edges){const a=byId.get(edge.source),b=byId.get(edge.target);if(!a||!b)continue;
      const active=selected?.kind==='edge'&&selected.id===edge.id;
      const path=el(document,'g',{'data-edge-id':edge.id,'data-overlay-status':model.overlays.edges[edge.id]?.status??'unavailable',role:'button',tabindex:'0',
        'aria-label':`Edge ${edge.label||edge.id}: ${edge.source} ${edge.directed?'to':'associated with'} ${edge.target}`,
        class:`pah-ig-edge${active?' is-selected':''}${hasTrace&&!trace.edges.has(edge.id)?' is-dimmed':''}`});
      const loop=edge.source===edge.target || (a.x===b.x&&a.y===b.y);
      const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;
      const ux=loop?0:dx/len,uy=loop?1:dy/len;
      // Directional endpoint and arrowhead reflect the actual drawn relation,
      // not a blanket down-arrow that would falsely reverse upward links.
      const start={x:a.x+ux*28,y:a.y+uy*28};
      const end=loop?{x:a.x,y:a.y-23}:{x:b.x-ux*28,y:b.y-uy*28};
      const d=loop
        ? `M ${a.x} ${a.y-23} C ${a.x-55} ${a.y-85}, ${a.x+55} ${a.y-85}, ${a.x} ${a.y-23}`
        : `M ${start.x} ${start.y} C ${start.x} ${(start.y+end.y)/2}, ${end.x} ${(start.y+end.y)/2}, ${end.x} ${end.y}`;
      path.appendChild(el(document,'path',{d,fill:'none',class:'pah-ig-edge-line'}));
      if(edge.directed) {
        const bx=end.x-ux*10,by=end.y-uy*10;
        path.appendChild(el(document,'polygon',{points:`${end.x},${end.y} ${bx-uy*5},${by+ux*5} ${bx+uy*5},${by-ux*5}`,class:'pah-ig-arrow-head'}));
      }
      path.appendChild(el(document,'title',{},edge.label||edge.id));
      const choose=()=>{if(current.summary_ids)return;select('edge',edge.id);};
      path.addEventListener('click',event=>{event.stopPropagation?.();choose();});
      path.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault?.();choose();}});
      edgeLayer.appendChild(path);
    }
    group.appendChild(edgeLayer);
    const nodeLayer=el(document,'g',{'data-layer':'nodes'});
    for(const node of current.nodes){const p=positions.get(node.id);if(!p)continue;
      const active=selected?.kind==='node' && selected.id===node.id;
      const status=model.overlays.nodes[node.id]?.status ?? 'unavailable';
      const button=el(document,'g',{transform:`translate(${p.x} ${p.y})`,role:'button',tabindex:'0',
        'data-node-id':node.id,'data-overlay-status':status,
        'aria-label':`Node ${node.label}; ${node.group}; analysis ${status}`,
        class:`pah-ig-node${active?' is-selected':''}${hasTrace&&!trace.nodes.has(node.id)?' is-dimmed':''}`});
      button.appendChild(el(document,'rect',{x:-82,y:-23,width:164,height:46,rx:8,class:'pah-ig-node-bg'}));
      button.appendChild(el(document,'text',{'text-anchor':'middle',y:5,class:'pah-ig-node-label'},
        node.label.length>25?node.label.slice(0,22)+'…':node.label));
      button.appendChild(el(document,'title',{},`${node.id} (${node.kind||node.group})`));
      const choose=()=>{
        if(current.summary_ids){if(current.automaticOverview||manualOverview){groupFocus=node.group;groupPage=0;manualOverview=false;selected=null;fit();}return;}
        select('node',node.id);
      };
      button.addEventListener('click',event=>{event.stopPropagation?.();choose();});
      button.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault?.();choose();}});
      nodeLayer.appendChild(button);
    }
    group.appendChild(nodeLayer);
  }
  function fit(){if(destroyed)return;const current=visibleGraph(),area=bounds(positionsFor(current));
    const w=Math.max(1,area.right-area.left),h=Math.max(1,area.bottom-area.top);
    const tall=height/h*.87;
    const zoom=w>width*3?Math.min(1.15,Math.max(.35,tall)):
      Math.min(2,Math.max(.04,Math.min(width/w,height/h)*.94));
    camera={zoom,x:width/2-(area.left+area.right)/2*zoom,y:height/2-(area.top+area.bottom)/2*zoom};draw();notifyViewport();}
  function zoom(factor,anchorX=width/2,anchorY=height/2){
    if(destroyed)return;
    if(!number(factor)||factor<=0||!number(anchorX)||!number(anchorY)) fail('Invalid zoom argument');
    const next=Math.max(.025,Math.min(6,camera.zoom*factor)),ratio=next/camera.zoom;
    camera.x=anchorX-(anchorX-camera.x)*ratio;camera.y=anchorY-(anchorY-camera.y)*ratio;
    camera.zoom=next;draw();notifyViewport();}
  function select(kind,id,{recenter=false}={}){
    if(destroyed)return false;
    const known=ids();if(!['node','edge'].includes(kind)||!known[`${kind}s`].has(id))return false;
    manualOverview=false;groupFocus=null;focusOnly=false;
    selected={kind,id};
    if(recenter){
      const current=visibleGraph(),positions=positionsFor(current);
      const point=kind==='node'?positions.get(id):(()=>{const edge=model.edges.find(e=>e.id===id);
        const a=positions.get(edge.source),b=positions.get(edge.target);
        return a&&b?{x:(a.x+b.x)/2,y:(a.y+b.y)/2}:null;})();
      if(point){camera.x=width/2-point.x*camera.zoom;camera.y=height/2-point.y*camera.zoom;}
    }
    draw();if(recenter)notifyViewport();
    onSelect({view_id:model.view_id,source_revision:model.source_revision,graph_role:model.graph_role,kind,id});
    return true;
  }
  const svgPoint=event=>{const rect=svg.getBoundingClientRect?.()??{left:0,top:0,width,height};
    return {x:(event.clientX-rect.left)*width/Math.max(1,rect.width),y:(event.clientY-rect.top)*height/Math.max(1,rect.height)};};
  svg.addEventListener('wheel',event=>{event.preventDefault?.();const at=svgPoint(event);zoom(event.deltaY<0?1.18:1/1.18,at.x,at.y);},{passive:false});
  svg.addEventListener('pointerdown',event=>{if(event.button!==0 || event.target?.closest?.('.pah-ig-node, .pah-ig-edge'))return;
    dragging={pointer:event.pointerId,last:svgPoint(event)};svg.setPointerCapture?.(event.pointerId);});
  svg.addEventListener('pointermove',event=>{if(!dragging||dragging.pointer!==event.pointerId)return;
    const next=svgPoint(event);camera.x+=next.x-dragging.last.x;camera.y+=next.y-dragging.last.y;dragging.last=next;draw();notifyViewport();});
  ['pointerup','pointercancel','lostpointercapture'].forEach(name=>svg.addEventListener(name,()=>{dragging=null;}));
  svg.addEventListener('keydown',event=>{
    if(event.target!==svg)return;
    if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){
      event.preventDefault?.();camera.x+=event.key==='ArrowLeft'?45:event.key==='ArrowRight'?-45:0;
      camera.y+=event.key==='ArrowUp'?45:event.key==='ArrowDown'?-45:0;draw();notifyViewport();}
  });
  fit();
  return {
    get svg(){return svg;},get selection(){return selected?{...selected}:null;},
    get coverage(){return copy(lastCoverage);},get camera(){return {...camera};},
    select,fit,zoom,
    overview(){manualOverview=true;groupFocus=null;selected=null;focusOnly=false;fit();},
    context(){manualOverview=false;groupFocus=null;focusOnly=false;fit();},
    focusSources(value){focusOnly=Boolean(value);manualOverview=false;groupFocus=null;fit();},
    get focusOnly(){return focusOnly;},
    nextPage(){if(groupFocus===null)return;const count=model.nodes.filter(n=>n.group===groupFocus).length;
      if((groupPage+1)*PAGE_SIZE<count){groupPage++;fit();}},
    previousPage(){if(groupFocus!==null && groupPage>0){groupPage--;fit();}},
    get viewDescription(){return groupFocus!==null?`Group ${groupFocus}, page ${groupPage+1} · source totals preserved`:
      lastCoverage?.scope==='collapsed'?'Layer overview (display summaries; original graph unchanged)':
        focusOnly?'Recorded directed trace':'Graph in context';},
    update(next,{preserveSelection=false}={}){
      if(destroyed)fail('Viewer destroyed');
      const normalized=validateInteractiveGraphView(next),same=normalized.view_id===model.view_id&&normalized.source_revision===model.source_revision;
      model=normalized;manualOverview=false;groupFocus=null;focusOnly=false;
      if(!same || !preserveSelection || !(selected && ids()[`${selected.kind}s`].has(selected.id)))selected=null;
      svg.setAttribute('aria-label',model.title||'Interactive scientific graph');fit();
    },
    destroy(){if(destroyed)return;destroyed=true;dragging=null;container.replaceChildren();}
  };
}

/** Read-only, aligned table model for owner-side table components. Selection calls viewer.select(). */
export function interactiveGraphRows(input) {
  const model=validateInteractiveGraphView(input);
  return {nodes:model.nodes.map(n=>({id:n.id,label:n.label,kind:n.kind,group:n.group,overlay_status:model.overlays.nodes[n.id]?.status??'unavailable',metrics:copy(model.overlays.nodes[n.id]?.metrics??[])})),
    edges:model.edges.map(e=>({id:e.id,source:e.source,target:e.target,directed:e.directed,kind:e.kind,overlay_status:model.overlays.edges[e.id]?.status??'unavailable',metrics:copy(model.overlays.edges[e.id]?.metrics??[])})),
    view_id:model.view_id,source_revision:model.source_revision};
}
