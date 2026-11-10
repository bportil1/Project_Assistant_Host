// UCA-09: explicit read-only provider analysis; existing Python catalog remains independent.
import {readProviderNavigation, providerOverlap} from './uca-provider-navigation-contract.mjs';
const pane=document.querySelector('#ucaMode [data-uca-pane="analyzer"]');
if(pane) {
  const $=id=>document.getElementById(id);
  const file=$('ucaProviderFile'), inspect=$('ucaProviderInspect'), status=$('ucaProviderStatus');
  const capabilities=$('ucaProviderCapabilities'), select=$('ucaProviderNode');
  const nodeStatus=$('ucaProviderNodeStatus'), diagnostics=$('ucaProviderDiagnostics'), locate=$('ucaProviderLocate');
  const workspace=$('researchWorkspaceSelect'), repository=$('workspacePath');
  let epoch=0, scope=JSON.stringify([workspace?.value||'',repository?.value||'']);
  let snapshot=null;
  function reset(message) {
    epoch++; snapshot=null; select.replaceChildren(new Option('No provider results',''));
    select.disabled=true; locate.disabled=true; capabilities.textContent='';
    diagnostics.replaceChildren(); nodeStatus.textContent=''; status.textContent=message;
  }
  function checkScope() {
    const next=JSON.stringify([workspace?.value||'',repository?.value||'']);
    if(next!==scope) {scope=next; reset('Repository changed. Inspect source again.');}
  }
  function selectedNode() {return select.value==='' ? null : (snapshot?.items[Number(select.value)] ?? null);}
  inspect.addEventListener('click',async()=>{
    checkScope();reset('Inspecting selected source…');
    const token=epoch, currentScope=scope;
    const relative=file.value.trim(), projectId=workspace?.value||'';
    if(!projectId || relative.includes('\\') || relative.startsWith('/') ||
       relative.split('/').some(part=>!part || part==='.' || part==='..') ||
       !/\.(py|as|atl|atlas)$/i.test(relative)) {
      status.textContent='Select a supported, repository-relative Python or ATLAS file.';return;
    }
    inspect.disabled=true;
    try {
      const response=await fetch('/api/uca/analyzer/provider-navigation',{
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({project_id:projectId,relative_path:relative})
      });
      const payload=await response.json();checkScope();
      if(epoch!==token||scope!==currentScope) return;
      if(!response.ok)throw Error(payload?.error||'Provider unavailable');
      snapshot=readProviderNavigation(payload,projectId,relative);
      for(const [i,n] of snapshot.items.slice(0,200).entries())
        select.add(new Option(`${n.kind}: ${n.name} (line ${n.start_line})`,String(i)));
      select.disabled=snapshot.items.length===0;
      capabilities.textContent=`${snapshot.language} · ${snapshot.provider_id} · `+
        Object.entries(snapshot.capabilities).filter(([,v])=>v===true).map(([k])=>k).join(', ');
      diagnostics.replaceChildren();
      for(const diagnostic of snapshot.diagnostics.slice(0,50)) {
        const li=document.createElement('li'); li.textContent=String(diagnostic).slice(0,1000);
        diagnostics.append(li);
      }
      status.textContent=`${snapshot.items.length} structural nodes (${Math.min(200,snapshot.items.length)} displayed). `+
        'Source fingerprint verified at inspection time; provider semantics remain as declared.';
    } catch(e) { if(epoch===token)reset(`Provider inspection unavailable: ${e.message}`); }
    finally {if(epoch===token) inspect.disabled=false;}
  });
  select.addEventListener('change',()=>{
    const n=selectedNode();locate.disabled=!n;
    nodeStatus.textContent=n?`${n.relative_path}:${n.start_line}–${n.end_line} · ${n.confidence||'structural'} (provider-reported)`:'No node selected';
  });
  locate.addEventListener('click',()=>{
    checkScope();const n=selectedNode();if(!n||!snapshot)return;
    window.dispatchEvent(new CustomEvent('pah:uca-source-selection-request',{detail:{
      producer:'code_analyzer',relative_path:n.relative_path,
      start_line:n.start_line,end_line:n.end_line,
    }}));
    nodeStatus.textContent='Verifying current source location; parser semantics are not independently verified.';
  });
  window.addEventListener('pah:uca-navigate-code_analyzer',event=>{
    checkScope();const selection=event.detail?.selection;
    const matches=providerOverlap(snapshot,selection);
    if(matches.length)nodeStatus.textContent=`${matches.length} source-revision-matched provider node(s) overlap this location.`;
  });
  workspace?.addEventListener('change',checkScope);
  repository?.addEventListener('change',checkScope);
  $('openWorkspace')?.addEventListener('click',()=>reset('Workspace changed. Inspect source again.'));
}
