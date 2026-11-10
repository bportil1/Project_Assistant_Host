// Local-only cross-window navigation relay. A remote message is never trusted:
// every receiving window binds host scope and re-verifies the current disk SHA.
import {validateHostScope} from './uca-navigation-contract.mjs';
import {eligibleRelay} from './uca-window-navigation-contract.mjs';

const root=document.getElementById('ucaMode');
if (root && 'BroadcastChannel' in window) {
  const workspace=document.getElementById('researchWorkspaceSelect');
  const repository=document.getElementById('workspacePath');
  const scope=()=>[workspace?.value||'',repository?.value||''];
  const channel=new BroadcastChannel('pah.uca.verified-navigation.v1');
  const targets=['editor','pypique','code_analyzer'];
  let transmitting=false, epoch=0;
  for (const target of targets) {
    window.addEventListener(`pah:uca-navigate-${target}`,event=>{
      if (transmitting || root.classList.contains('hidden')) return;
      const selection=event.detail?.selection;
      if (!eligibleRelay(selection,...scope())) return;
      // Only verified navigation events emitted by the local UCA controller.
      channel.postMessage({kind:'source-selection',target,selection});
    });
  }
  const invalidate=()=>{epoch++;};
  workspace?.addEventListener('change',invalidate);
  repository?.addEventListener('change',invalidate);
  window.addEventListener('pah:uca-mode',event=>{if(!event.detail?.active)invalidate();});
  channel.onmessage=async event=>{
    const {kind,target,selection}=event.data||{};
    if(kind!=='source-selection'||!targets.includes(target)||
        root.classList.contains('hidden')||!eligibleRelay(selection,...scope()))return;
    const ticket=epoch, before=JSON.stringify(scope());
    try {
      const hostReply=await fetch('/api/uca/navigation/scope', {credentials:'same-origin',cache:'no-store'});
      const hostData=await hostReply.json();
      if(!hostReply.ok || hostData.ok!==true) return;
      const host=validateHostScope(hostData.scope,selection.workspace,selection.repository);
      if(host.project_id!==selection.project_id||host.repository_id!==selection.repository_id||
          host.context_token!==selection.context_token||host.context_revision!==selection.context_revision)return;
      if(ticket!==epoch||before!==JSON.stringify(scope())||root.classList.contains('hidden'))return;
      const sourceReply=await fetch('/api/uca/navigation/verify-source',{
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({project_id:host.project_id,relative_path:selection.relative_path,
          start_line:selection.start_line,end_line:selection.end_line}),
      });
      const data=await sourceReply.json();
      if(!sourceReply.ok||data.ok!==true||data.selection?.source_sha256!==selection.source_sha256||
          data.selection?.relative_path!==selection.relative_path||
          ticket!==epoch||before!==JSON.stringify(scope())||root.classList.contains('hidden'))return;
      transmitting=true;
      try {window.dispatchEvent(new CustomEvent(`pah:uca-navigate-${target}`,{detail:{selection}}));}
      finally {transmitting=false;}
    }catch(_){ /* unverifiable cross-window navigation is dropped */ }
  };
  window.addEventListener('beforeunload',()=>channel.close());
}
