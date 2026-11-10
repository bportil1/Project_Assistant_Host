// UCA-10.3: explicit, read-only verification; no job-to-artifact inference.
const root=document.getElementById('ucaMode');
if (root) {
  const input=document.getElementById('ucaHandoffInput');
  const button=document.getElementById('ucaHandoffInspect');
  const status=document.getElementById('ucaHandoffStatus');
  const result=document.getElementById('ucaHandoffResult');
  let generation=0;
  function clear(message) { generation++;result.textContent='';status.textContent=message; }
  async function scope() {
    const response=await fetch('/api/uca/navigation/scope',{cache:'no-store',credentials:'same-origin'});
    if(!response.ok) throw new Error('Active workspace unavailable');
    const payload=await response.json();
    const value=payload?.scope;
    if(payload?.ok!==true || !value?.workspace_id || !value?.project_id ||
       !value?.repository_id || !value?.context_token ||
       !Number.isInteger(value?.context_revision)) throw new Error('Invalid workspace scope');
    return [value.workspace_id,value.project_id,value.repository_id,
            value.context_token,value.context_revision].join('\u0000');
  }
  button?.addEventListener('click',async()=>{
    const ticket=++generation;
    button.disabled=true;result.textContent='';status.textContent='Verifying explicit handoff…';
    try {
      const text=input.value;
      if(text.length>8192) throw new Error('Handoff exceeds size limit');
      const handoff=JSON.parse(text);
      if(!handoff || Array.isArray(handoff) || handoff.schema!=='pah.uca-analysis-handoff@1') throw new Error('Invalid handoff schema');
      const before=await scope();
      const response=await fetch('/api/uca/analysis-handoff/inspect',{
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json'},body:JSON.stringify(handoff)});
      const payload=await response.json();
      const after=await scope();
      if(ticket!==generation || root.classList.contains('hidden')) return;
      if(before!==after) throw new Error('Workspace changed during verification');
      if(!response.ok || payload.ok!==true) throw new Error(payload.error||'Handoff unavailable');
      result.textContent=JSON.stringify(payload.result,null,2);
      status.textContent='Producer handoff inspected. Check per-job and per-artifact verification states.';
    }catch(error){if(ticket===generation){result.textContent='';status.textContent=`Handoff unavailable: ${error.message}`;}}
    finally{if(ticket===generation)button.disabled=false;}
  });
  document.getElementById('researchWorkspaceSelect')?.addEventListener('change',()=>clear('Workspace changed; handoff cleared.'));
  document.getElementById('workspacePath')?.addEventListener('change',()=>clear('Repository changed; handoff cleared.'));
  window.addEventListener('pah:uca-mode',event=>{if(event.detail?.active!==true) clear('Workspace inactive; handoff cleared.');});
}
