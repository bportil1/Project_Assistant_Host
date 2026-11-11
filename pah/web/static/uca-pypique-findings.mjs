// UCA-04: optional SAT pane; reuses P5-18 producer projection + verified preview.
// No automatic editor navigation, source writes, scan execution, or MI recompute.
import {readProjection, eligibleFinding, candidateFinding, checkedEvidence} from './uca-pypique-contract.mjs';
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
  // Preserve the historical findings as browseable records. Neither of these
  // controls changes the existing scan-time verified preview endpoint.
  const detail = document.createElement('pre');
  detail.id = 'ucaFindingDetails';
  detail.hidden = true;
  detail.style.whiteSpace = 'pre-wrap';
  select.insertAdjacentElement('afterend', detail);
  const openCurrent = document.createElement('button');
  openCurrent.type = 'button';
  openCurrent.id = 'ucaFindingOpenCurrent';
  openCurrent.textContent = 'Open current file at finding line (scan revision unverified)';
  openCurrent.hidden = true;
  select.insertAdjacentElement('afterend', openCurrent);
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
    detail.hidden = true; detail.textContent = ''; openCurrent.hidden = true;
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
      let verified = 0, candidates = 0;
      select.replaceChildren(new Option('Choose a finding', ''));
      active.forEach((item,index) => {
        const ready = eligibleFinding(item, projectId);
        const loc = ready ? item.locator : candidateFinding(item,projectId) ? item.candidate : null;
        const name = String(item?.provider || 'SAT').slice(0,60);
        const id = String(item?.finding_id || 'unknown').slice(0,90);
        const title = loc ? `${loc.relative_path}:${loc.start_line}${ready ? ' [scan source hash]' : ' [current-source candidate]'}`
          : `${String(item?.summary?.file_path || 'source unavailable').slice(0,100)} [browse only]`;
        // Every finding remains selectable; candidate status is not an eligibility gate.
        select.add(new Option(`${name}: ${id} — ${title}`, String(index)));
        if (ready) verified++;
        else if (loc) candidates++;
      });
      select.disabled = !active.length;
      previous.disabled = pageOffset === 0;
      next.disabled = pageOffset + active.length >= projection.total || !active.length;
      pageLabel.textContent = projection.total
        ? `${pageOffset+1}–${pageOffset+active.length} of ${projection.total}` : 'No findings';
      status.textContent = `${active.length} findings on this page; ${verified} scan-verifiable, ${candidates} current-source candidates, ${active.length-verified-candidates} browse only.`;
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
    const ticket = ++generation;
    openCurrent.hidden = true;
    detail.hidden = true;
    if (!select.value || !item) {clearPreview('No finding selected.');return;}
    const summary=item.summary||{};
    detail.textContent = [
      `Provider: ${item.provider || 'unknown'} | Finding: ${item.finding_id || 'unknown'}`,
      `File: ${summary.file_path || item?.candidate?.relative_path || 'unknown'}`,
      `Line: ${summary.line ?? 'unknown'} | Severity: ${summary.severity || 'unknown'}`,
      `CWE: ${(summary.cwes || []).join(', ') || 'not recorded'}`,
      `Message: ${summary.message || 'not provided'}`,
      `Source evidence: ${eligibleFinding(item,projectId) ? 'scan-time hash available' : 'scan-time revision not verified'}`,
    ].join('\n'); // plain text; never injected as HTML
    detail.hidden = false;
    openCurrent.hidden = !candidateFinding(item, projectId);
    if (!eligibleFinding(item, projectId)) {
      clearPreview(candidateFinding(item,projectId)
        ? 'File/line recorded by SAT. You may locate the current source, but its scan-time revision is unverified.'
        : 'Finding available for inspection; no canonical current-repository source coordinate.');
      return;
    }
    const locator = item.locator;
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
  openCurrent.addEventListener('click', () => {
    checkScope();
    if (!select.value) return;
    const item = active[Number(select.value)];
    if (!candidateFinding(item, projectId)) return;
    const candidate = item.candidate;
    // The shared controller checks authoritative host scope, then verifies
    // the *current file bytes* before allowing Ace navigation. This does not
    // verify that the current bytes were the ones scanned by pyPIQUE.
    window.dispatchEvent(new CustomEvent('pah:uca-source-selection-request', {detail:{
      producer:'pypique', relative_path:candidate.relative_path,
      start_line:candidate.start_line, end_line:candidate.end_line,
    }}));
    previewStatus.textContent = 'Locating current source (SAT scan revision remains unverified)…';
  });
  window.addEventListener('pah:uca-navigation-status', event => {
    if (event.detail?.producer !== 'pypique' || openCurrent.hidden) return;
    previewStatus.textContent = event.detail.ok
      ? `Current file located at ${event.detail.path}:${event.detail.line}; scan-time revision remains unverified.`
      : `Current-source navigation unavailable: ${event.detail.error}`;
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
    const candidates=active.filter(item=>candidateFinding(item,projectId) &&
      item.candidate.relative_path===selection.relative_path &&
      item.candidate.start_line<=selection.end_line && item.candidate.end_line>=selection.start_line);
    previewStatus.textContent=matching.length
      ? `${matching.length} SAT finding(s) match the scan-time source hash and line range.`
      : `${candidates.length} SAT finding(s) overlap this current file/line; scan-time revision parity is not established.`;
  });
  view.addEventListener('change', () => {pageOffset=0;clear('Finding view changed. Reload findings.');});
  workspace?.addEventListener('change', checkScope);
  repository?.addEventListener('change', checkScope);
  document.getElementById('openWorkspace')?.addEventListener('click', () => clear('Workspace selection changed. Reload findings.'));
  document.querySelector('[data-mode="uca"]')?.addEventListener('click', checkScope);
}
