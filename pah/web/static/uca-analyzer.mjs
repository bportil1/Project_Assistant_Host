// UCA-05: inspect producer-owned Code Analyzer results without replacing its controller.
import {readAnalyzerStatus, readAnalyzerFunctions, readAnalyzerEntity, readAnalyzerDependencies} from './uca-analyzer-contract.mjs';
const pane = document.querySelector('#ucaMode [data-uca-pane="analyzer"]');
if (pane) {
  const $ = id => document.getElementById(id);
  const load = $('ucaAnalyzerLoad'), run = $('ucaAnalyzerRun');
  const status = $('ucaAnalyzerStatus'), select = $('ucaAnalyzerEntity');
  const detailStatus = $('ucaAnalyzerEntityStatus'), details = $('ucaAnalyzerDetails');
  const dependencies = $('ucaAnalyzerDependencies');
  const workspace = $('researchWorkspaceSelect'), repository = $('workspacePath');
  let epoch = 0, scope = '', rows = [], statusSnapshot = null, selectedEntity = null;
  const currentScope = () => JSON.stringify([workspace?.value || '', repository?.value || '']);
  const resetDetails = (message='No structure selected.') => {
    details.hidden = true; details.replaceChildren();
    dependencies.hidden = true; dependencies.replaceChildren();
    detailStatus.textContent = message;
  };
  const reset = message => {
    epoch++; rows = []; statusSnapshot = null; selectedEntity = null;
    const share=document.getElementById('ucaAnalyzerShareSelection'); if(share)share.disabled=true;
    select.disabled = true; select.replaceChildren(new Option('No analysis loaded', ''));
    load.disabled = false; run.disabled = false;
    resetDetails(); status.textContent = message;
  };
  scope = currentScope();
  const checkScope = () => {
    const next = currentScope();
    if (next !== scope) { scope = next; reset('Workspace or repository changed. Reload analysis.'); }
  };
  async function request(url, options) {
    const response = await fetch(url, {credentials:'same-origin', cache:'no-store', ...options});
    const data = await response.json();
    if (!response.ok || data?.ok !== true) throw new Error(data?.error || 'Code Analyzer request failed');
    return data;
  }
  async function refresh() {
    checkScope(); reset('Loading existing Code Analyzer results…');
    const token = epoch, originalScope = scope;
    load.disabled = true;
    try {
      const snapshot = readAnalyzerStatus(await request('/api/analyzer/status'));
      checkScope(); if (token !== epoch || originalScope !== scope) return;
      statusSnapshot = snapshot;
      if (!snapshot.available) { status.textContent = 'Code Analyzer is unavailable in this workspace.'; return; }
      if (!snapshot.analyzed) { status.textContent = 'No analysis has been run. Run Python analysis explicitly if desired.'; return; }
      const data = await request('/api/analyzer/functions');
      checkScope(); if (token !== epoch || originalScope !== scope) return;
      rows = readAnalyzerFunctions(data);
      if (data.stale !== snapshot.stale) { status.textContent = 'Analysis changed during loading. Reload to inspect.'; rows=[]; return; }
      select.replaceChildren(new Option('Choose an analyzed structure', ''));
      for (let i=0; i<rows.length; i++) {
        const item = rows[i];
        select.add(new Option(`${String(item.qualified_name || item.name || item.id).slice(0,120)} — ${item.path}`, String(i)));
      }
      select.disabled = rows.length === 0;
      status.textContent = `${rows.length} structures shown (up to 200). ${snapshot.stale ? 'STALE: source changed since analysis; inspection only.' : 'Read-only analysis catalog.'}`;
    } catch (error) {
      if (token === epoch) reset(`Code Analyzer unavailable: ${error.message}`);
    } finally { if (token === epoch) load.disabled = false; }
  }
  load.addEventListener('click', refresh);
  run.addEventListener('click', async () => {
    checkScope(); reset('Running Code Analyzer by explicit request…');
    const token = epoch, originalScope = scope;
    run.disabled = true;
    try {
      await request('/api/analyzer/analyze', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      checkScope(); if (token !== epoch || originalScope !== scope) return;
      await refresh();
    } catch (error) { if (token === epoch) reset(`Analysis unavailable: ${error.message}`); }
    finally { if (token === epoch) run.disabled = false; }
  });
  select.addEventListener('change', async () => {
    checkScope();
    const row = rows[Number(select.value)];
    if (!select.value || !row || !statusSnapshot) { resetDetails(); return; }
    const token=++epoch, originalScope=scope;
    resetDetails('Loading structural evidence…'); select.disabled=true;
    try {
      const [entityData, dependencyData] = await Promise.all([
        request('/api/analyzer/entity?id='+encodeURIComponent(row.id)),
        request('/api/analyzer/dependencies?id='+encodeURIComponent(row.id)),
      ]);
      checkScope(); if (token !== epoch || originalScope !== scope) return;
      const entity=readAnalyzerEntity(entityData,row.id);
      const counts=readAnalyzerDependencies(dependencyData);
      if (entity.stale !== statusSnapshot.stale) throw new Error('Analysis state changed. Reload results.');
      for (const [key,value] of [['Name',entity.name],['Type',entity.type],['File',entity.path],
        ['Lines', entity.start == null ? 'Unknown' : `${entity.start}${entity.end == null ? '' : '–'+entity.end}`]]) {
        const term=document.createElement('dt'), description=document.createElement('dd');
        term.textContent=key; description.textContent=String(value); details.append(term,description);
      }
      details.hidden=false;
      dependencies.textContent=`Dependencies: ${counts.incoming} incoming, ${counts.outgoing} outgoing.`;
      dependencies.hidden=false;
      detailStatus.textContent=entity.stale ? 'Stale structural evidence; do not treat line locations as current.' : 'Structural evidence from existing Code Analyzer results.';
      selectedEntity=entity;
      const share=document.getElementById('ucaAnalyzerShareSelection');
      if(share)share.disabled=entity.stale || entity.start==null || !entity.path;
      // UCA-06 will publish verified source-selection events. No editor navigation here.
    } catch(error) { if (token === epoch) resetDetails(`Structure unavailable: ${error.message}`); }
    finally { if (token === epoch) select.disabled=false; }
  });
  document.getElementById('ucaAnalyzerShareSelection')?.addEventListener('click',()=>{
    checkScope();
    if(!selectedEntity || !statusSnapshot?.analyzed || statusSnapshot.stale || selectedEntity.stale ||
       !Number.isSafeInteger(selectedEntity.start) || selectedEntity.start<1) return;
    window.dispatchEvent(new CustomEvent('pah:uca-source-selection-request',{detail:{
      producer:'code_analyzer',relative_path:selectedEntity.path,
      start_line:selectedEntity.start,end_line:selectedEntity.start,
    }}));
    detailStatus.textContent='Verifying source location; structural match remains a candidate until AST revision parity is established.';
  });
  window.addEventListener('pah:uca-navigation-status',event=>{
    if(event.detail?.producer==='code_analyzer')detailStatus.textContent=event.detail.ok
      ? 'Source location verified on disk; AST revision equivalence is not established.'
      : `Navigation unavailable: ${event.detail.error}`;
  });
  // UCA-06: file/line overlap is contextual, not verified AST revision parity.
  window.addEventListener('pah:uca-navigate-code_analyzer', event => {
    checkScope();
    const source = event.detail?.selection;
    if (!source || source.schema!=='pah.source-selection@1' ||
        source.workspace !== (workspace?.value||'') ||
        source.workspace_id !== source.workspace || source.project_id !== source.workspace_id ||
        !/^repo-[0-9a-f]{64}$/.test(source.repository_id || '') ||
        source.repository !== (repository?.value||'') ||
        !statusSnapshot?.analyzed || statusSnapshot.stale) {
      resetDetails('No current, comparable structural analysis available.'); return;
    }
    const matches=rows.filter(item=>item.path===source.relative_path &&
       Number.isSafeInteger(item.line_start ?? item.metadata?.line_start) &&
       (item.line_start ?? item.metadata?.line_start)<=source.end_line &&
       (item.line_end ?? item.metadata?.line_end ?? item.line_start ?? item.metadata?.line_start)>=source.start_line);
    detailStatus.textContent=matches.length
       ? `${matches.length} structural candidate(s) overlap ${source.relative_path}:${source.start_line}. AST revision equivalence is not established.`
       : `No indexed structure at ${source.relative_path}:${source.start_line}; no analysis rerun.`;
  });
  workspace?.addEventListener('change',checkScope);
  repository?.addEventListener('change',checkScope);
  $('openWorkspace')?.addEventListener('click',()=>reset('Workspace selection changed. Reload analysis.'));
  document.querySelector('[data-mode="uca"]')?.addEventListener('click',checkScope);
}
