// UCA-10: no private DB access, job starts, cancels, or artifact inference.
import {summarizeObservations,scopeIdentity} from './uca-observation-contract.mjs';
const root=document.getElementById('ucaMode');
if(root){
  const button=document.getElementById('ucaObservationRefresh');
  const status=document.getElementById('ucaObservationStatus');
  const list=document.getElementById('ucaObservationJobs');
  let ticket=0;
  function reset(message){++ticket;button.disabled=false;list.replaceChildren();status.textContent=message;}
  async function readJSON(url){
    const response=await fetch(url,{cache:'no-store',credentials:'same-origin'});
    if(!response.ok) throw new Error(`Observation unavailable (${response.status})`);
    return response.json();
  }
  async function refresh(){
    const request=++ticket;
    button.disabled=true;
    list.replaceChildren();status.textContent='Checking registered producer observations…';
    try{
      const start=scopeIdentity(await readJSON('/api/uca/navigation/scope'));
      const payload=await readJSON('/api/jobs');
      const end=scopeIdentity(await readJSON('/api/uca/navigation/scope'));
      if(request!==ticket || root.classList.contains('hidden')) return;
      if(start!==end) throw new Error('Workspace changed while observing jobs');
      const summary=summarizeObservations(payload);
      for(const item of summary.rows){
        const li=document.createElement('li');
        li.textContent=`${item.owner} · ${item.label} · ${item.state} (observed only)`;
        list.appendChild(li);
      }
      status.textContent=`${summary.rows.length} registered job observation(s)${summary.truncated?' (first 30 only)':''}. Artifact verification: unavailable without explicit handoff.`;
    }catch(error){if(request===ticket)reset(`Job observations unavailable: ${error.message}`);}
    finally{if(request===ticket)button.disabled=false;}
  }
  button?.addEventListener('click',refresh);
  document.getElementById('ucaObservationOpenMonitor')?.addEventListener('click',()=>document.getElementById('jobMonitorToggle')?.click());
  document.getElementById('researchWorkspaceSelect')?.addEventListener('change',()=>reset('Workspace changed; refresh observations.'));
  document.getElementById('workspacePath')?.addEventListener('change',()=>reset('Repository changed; refresh observations.'));
  window.addEventListener('pah:uca-mode',event=>{if(event.detail?.active!==true)reset('Unified workspace inactive; refresh when reopened.');});
}
