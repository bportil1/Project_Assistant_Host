// UCA-04: optional SAT pane; reuses P5-18 producer projection + verified preview.
// No automatic editor navigation, source writes, scan execution, or MI recompute.
import {readProjection, eligibleFinding, checkedEvidence} from './uca-pypique-contract.mjs';
const pane = document.querySelector('#ucaMode [data-uca-pane="pypique"]');
if (pane) {
  const load = document.getElementById('ucaFindingLoad');
  const view = document.getElementById('ucaFindingView');
  const previous = document.getElementById('ucaFindingPrev');
  const next = document.getElementById('ucaFindingNext');
  const pageLabel = document.getElementById('ucaFindingPage');
  const PAGE_SIZE = 200;
  let pageOffset = 0;
  const select = document.getElementById('ucaFindingSelect');
  const status = document.getElementById('ucaFindingStatus');
  const previewStatus = document.getElementById('ucaFindingPreviewStatus');
  const excerpt = document.getElementById('ucaFindingExcerpt');
  const workspace = document.getElementById('researchWorkspaceSelect');
  const repository = document.getElementById('workspacePath');
  let generation = 0;
  let active = [];
  let projectId = '';
  let scope = '';
  const scopeNow = () => JSON.stringify([workspace?.value || '', repository?.value || '']);
  const clearPreview = message => {
    excerpt.hidden = true;
    excerpt.textContent = '';
    previewStatus.textContent = message;
  };
  const clear = message => {
    generation++;
    active = [];
    projectId = '';
    load.disabled = false;
    select.disabled = true;
    select.replaceChildren(new Option('No findings loaded', ''));
    status.textContent = message;
    previous.disabled = true;
    next.disabled = true;
    pageLabel.textContent = '—';
    clearPreview('No source evidence selected.');
  };
  scope = scopeNow();
  const checkScope = () => {
    const now = scopeNow();
    if (now !== scope) { scope = now; pageOffset = 0; clear('Workspace/repository changed. Reload findings.'); }
  };
  async function loadPage(offset) {
    checkScope();
    clear('Loading findings…');
    pageOffset = offset;
    const ticket = generation;
    const originScope = scope;
    load.disabled = true;
    try {
      const response = await fetch('/api/orchestration/code-analysis/source-evidence/findings?view='
        + encodeURIComponent(view.value) + '&offset=' + pageOffset,
        {credentials:'same-origin', cache:'no-store'});
      const data = await response.json();
      checkScope();
      if (ticket !== generation || originScope !== scope) return;
      if (!response.ok || !data.ok) throw new Error(data?.error || 'Findings unavailable');
      const projection = readProjection(data.projection);
      if (projection.offset !== pageOffset) throw new Error('Finding page offset changed during loading');
      active = projection.results;
      projectId = projection.project_id;
      let available = 0;
      select.replaceChildren(new Option('Choose a finding', ''));
      active.forEach((item,index) => {
        const ready = eligibleFinding(item, projectId);
        const loc = item?.locator;
        const name = String(item?.provider || 'SAT').slice(0,60);
        const id = String(item?.finding_id || 'unknown').slice(0,90);
        const title = ready ? `${loc.relative_path}:${loc.start_line}` : `unavailable (${String(item?.reason || 'unverified source').slice(0,70)})`;
        const option = new Option(`${name}: ${id} — ${title}`, String(index));
        option.disabled = !ready;
        select.add(option);
        if (ready) available++;
      });
      select.disabled = !available;
      previous.disabled = pageOffset === 0;
      next.disabled = pageOffset + active.length >= projection.total || !active.length;
      pageLabel.textContent = projection.total
        ? `${pageOffset+1}–${pageOffset+active.length} of ${projection.total}` : 'No findings';
      status.textContent = `${active.length} findings on this page; ${available} eligible for server verification.`;
    } catch (error) {
      if (ticket === generation) clear(`Unavailable: ${error.message}`);
    } finally {
      if (ticket === generation) load.disabled = false;
    }
  }
  load.addEventListener('click', () => loadPage(0));
  previous.addEventListener('click', () => loadPage(Math.max(0, pageOffset - PAGE_SIZE)));
  next.addEventListener('click', () => loadPage(pageOffset + PAGE_SIZE));
  select.addEventListener('change', async () => {
    checkScope();
    const item = active[Number(select.value)];
    if (!select.value || !eligibleFinding(item, projectId)) return;
    const locator = item.locator;
    const ticket = ++generation;
    const originScope = scope;
    clearPreview('Verifying source fingerprint…');
    select.disabled = true;
    try {
      const response = await fetch('/api/orchestration/code-analysis/source-evidence/preview', {
        method:'POST', credentials:'same-origin', cache:'no-store',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(locator),
      });
      const result = await response.json();
      checkScope();
      if (ticket !== generation || originScope !== scope) return;
      if (!response.ok) throw new Error(result?.error || 'Source verification failed');
      const evidence = checkedEvidence(result, locator);
      excerpt.textContent = evidence.excerpt; // text only, never HTML
      excerpt.hidden = false;
      previewStatus.textContent = `Verified ${evidence.relative_path}:${evidence.start_line}-${evidence.end_line}`;
      // This is verified by PAH's read-only source endpoint. UCA-06 still
      // checks scope and the editor verifies its own loaded source revision.
      window.dispatchEvent(new CustomEvent('pah:uca-verified-evidence', {detail:{evidence}}));
    } catch (error) {
      if (ticket === generation) clearPreview(`Unavailable: ${error.message}`);
    } finally {
      if (ticket === generation) select.disabled = false;
    }
  });
  window.addEventListener('pah:uca-navigate-pypique',event=>{
    checkScope();
    const selection=event.detail?.selection;
    if(!selection || selection.schema!=='pah.source-selection@1' ||
        selection.workspace!==(workspace?.value||'') || selection.repository!==(repository?.value||'') ||
        selection.project_id!==selection.workspace_id ||
        !/^repo-[0-9a-f]{64}$/.test(selection.repository_id||'')) return;
    // Do not imply that a finding's scan-time source hash matches this selection.
    const matching=active.filter(item=>eligibleFinding(item,projectId) &&
      item.locator.relative_path===selection.relative_path &&
      item.locator.source_sha256===selection.source_sha256 &&
      item.locator.start_line<=selection.end_line && item.locator.end_line>=selection.start_line);
    previewStatus.textContent=matching.length
      ? `${matching.length} SAT finding(s) with matching source revision and overlapping lines (select to inspect).`
      : 'No loaded SAT finding with matching file revision and source range.';
  });
  view.addEventListener('change', () => {pageOffset=0;clear('Finding view changed. Reload findings.');});
  workspace?.addEventListener('change', checkScope);
  repository?.addEventListener('change', checkScope);
  document.getElementById('openWorkspace')?.addEventListener('click', () => clear('Workspace selection changed. Reload findings.'));
  document.querySelector('[data-mode="uca"]')?.addEventListener('click', checkScope);
}
