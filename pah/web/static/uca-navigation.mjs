// UCA-06. Event delivery only: authorization and fingerprint verification live in PAH.
import {createNavigationBus, fromVerifiedEvidence, validateHostScope, bindHostIdentity, fromVerifiedSourceRevision} from './uca-navigation-contract.mjs';
const root=document.getElementById('ucaMode');
if(root){
  const workspace=document.getElementById('researchWorkspaceSelect');
  const repository=document.getElementById('workspacePath');
  const scope=()=>[workspace?.value||'',repository?.value||''];
  let bus=null;
  const reset=()=>{if(bus) bus.switchScope(scope());};
  let requestEpoch=0;
  const invalidate=()=>{requestEpoch++;reset();};
  window.addEventListener('pah:uca-verified-evidence', async event=>{
    // P5-18 source verification must already have succeeded. This second
    // binding prevents cross-project browser dispatch but is not authorization.
    if(root.classList.contains('hidden'))return;
    const current=scope();
    if(!current.every(Boolean))return;
    const ticket=++requestEpoch;
    try {
      const response=await fetch('/api/uca/navigation/scope', {credentials:'same-origin',cache:'no-store'});
      const data=await response.json();
      if(!response.ok || data.ok !== true) throw new Error('Host scope unavailable');
      if(ticket!==requestEpoch || JSON.stringify(scope())!==JSON.stringify(current) || root.classList.contains('hidden'))return;
      const host=validateHostScope(data.scope,current[0],current[1]);
      const selection=bindHostIdentity(
        fromVerifiedEvidence(event.detail?.evidence,{workspace:current[0],repository:current[1]}),host);
      if(!bus) bus=createNavigationBus(current);
      bus.switchScope(current);
      const navigation=bus.publish(selection);
      for(const consumer of ['editor','code_analyzer']){
        if(bus.consume(navigation,consumer))
          window.dispatchEvent(new CustomEvent('pah:uca-navigate-'+consumer,{detail:navigation}));
      }
    }catch(_){ /* incomplete or stale scope must not dispatch navigation */ }
  });
  window.addEventListener('pah:uca-source-selection-request', async event => {
    if(root.classList.contains('hidden')) return;
    const detail=event.detail || {};
    if(!['editor','code_analyzer','pypique'].includes(detail.producer)) return;
    const current=scope();
    if(!current.every(Boolean)) return;
    const ticket=++requestEpoch;
    try {
      const hostResponse=await fetch('/api/uca/navigation/scope', {credentials:'same-origin',cache:'no-store'});
      const hostData=await hostResponse.json();
      if(!hostResponse.ok || hostData.ok!==true) throw new Error('Host scope unavailable');
      const host=validateHostScope(hostData.scope,current[0],current[1]);
      // Scope may change while the host identity request is in flight.
      // Do not even request a source revision for an abandoned selection.
      if(ticket!==requestEpoch || JSON.stringify(scope())!==JSON.stringify(current) ||
          root.classList.contains('hidden')) return;
      const sourceResponse=await fetch('/api/uca/navigation/verify-source', {
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({project_id:host.project_id,relative_path:detail.relative_path,
          start_line:detail.start_line,end_line:detail.end_line}),
      });
      const sourceData=await sourceResponse.json();
      if(!sourceResponse.ok || sourceData.ok!==true) throw new Error(sourceData?.error || 'Source verification failed');
      if(ticket!==requestEpoch || JSON.stringify(scope())!==JSON.stringify(current) || root.classList.contains('hidden'))return;
      const selection=fromVerifiedSourceRevision(sourceData,{producer:detail.producer,
        workspace:current[0],repository:current[1]},host);
      // Current disk verification never establishes scan-time pyPIQUE provenance
      // or Code Analyzer AST revision equivalence. These remain distinct claims.
      if(!bus)bus=createNavigationBus(current);
      bus.switchScope(current);
      const navigation=bus.publish(selection);
      for(const consumer of ['editor','pypique','code_analyzer']) {
        if(bus.consume(navigation,consumer))
          window.dispatchEvent(new CustomEvent('pah:uca-navigate-'+consumer,{detail:navigation}));
      }
      window.dispatchEvent(new CustomEvent('pah:uca-navigation-status',
        {detail:{producer:detail.producer,ok:true,path:selection.relative_path,line:selection.start_line}}));
    }catch(error){
      if(ticket===requestEpoch)window.dispatchEvent(new CustomEvent('pah:uca-navigation-status',
        {detail:{producer:detail.producer,ok:false,error:String(error.message)}}));
    }
  });
  workspace?.addEventListener('change',invalidate);
  repository?.addEventListener('change',invalidate);
  document.getElementById('openWorkspace')?.addEventListener('click',invalidate);
  window.addEventListener('pah:uca-mode',event=>{if(event.detail?.active!==true)invalidate();});
}
