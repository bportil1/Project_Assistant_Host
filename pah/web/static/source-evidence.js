/* P5-18 read-only evidence preview. No editor or source-write operations. */
(() => {
  'use strict';
  const input = document.getElementById('sourceEvidenceLocator');
  const output = document.getElementById('sourceEvidenceOutput');
  const status = document.getElementById('sourceEvidenceStatus');
  const verify = document.getElementById('sourceEvidenceVerify');
  const clear = document.getElementById('sourceEvidenceClear');
  if (!input || !output || !status || !verify || !clear) return;
  const findView = document.getElementById('sourceEvidenceFindingView');
  const loadFindings = document.getElementById('sourceEvidenceLoadFindings');
  const findSelect = document.getElementById('sourceEvidenceFindingSelect');
  const findingsStatus = document.getElementById('sourceEvidenceFindingsStatus');
  let findingsRequest = 0;
  let projected = [];
  const clearFindings = (message) => {
    ++findingsRequest;
    projected = [];
    if (findSelect) {
      findSelect.replaceChildren(new Option('No findings loaded', ''));
      findSelect.disabled = true;
    }
    if (findingsStatus) findingsStatus.textContent = message;
  };
  if (loadFindings && findSelect && findView && findingsStatus) {
    loadFindings.addEventListener('click', async () => {
      clearFindings('Loading producer-owned finding projections…');
      const ticket = findingsRequest;
      loadFindings.disabled = true;
      try {
        const response = await fetch('/api/orchestration/code-analysis/source-evidence/findings?view=' + encodeURIComponent(findView.value), {credentials: 'same-origin', cache: 'no-store'});
        const data = await response.json();
        if (ticket !== findingsRequest) return;
        if (!response.ok || !data.ok) throw new Error(data.error || 'Findings unavailable');
        const payload = data.projection;
        if (payload?.schema !== 'pypique.source-evidence-projections@1' || !Array.isArray(payload.results) || payload.results.length > 100) {
          throw new Error('Incompatible pyPIQUE finding list');
        }
        projected = payload.results;
        findSelect.replaceChildren(new Option('Choose a finding', ''));
        let actionable = 0;
        projected.forEach((item, index) => {
          const valid = item?.status === 'ready_for_pah_verification' && item.locator?.producer_module === 'pypique' && item.locator?.project_id === payload.project_id;
          const label = `${item?.provider || 'SAT'}: ${item?.finding_id || 'unknown'} — ${valid ? (item.locator.relative_path + ':' + item.locator.start_line) : ('unavailable (' + (item?.reason || 'missing evidence') + ')')}`;
          const option = new Option(label, String(index));
          option.disabled = !valid;
          if (valid) actionable++;
          findSelect.add(option);
        });
        findSelect.disabled = actionable === 0;
        findingsStatus.textContent = `${projected.length} findings loaded; ${actionable} have explicit source fingerprints. Select one to verify.`;
      } catch (error) {
        if (ticket === findingsRequest) { clearFindings('Unavailable: ' + error.message); loadFindings.disabled = false; }
      } finally {
        if (ticket === findingsRequest) loadFindings.disabled = false;
      }
    });
    findSelect.addEventListener('change', () => {
      if (!findSelect.value) return;
      const selected = projected[Number(findSelect.value)];
      if (!selected || selected.status !== 'ready_for_pah_verification' || !selected.locator) return;
      input.value = JSON.stringify(selected.locator, null, 2);
      verify.click();  // Existing server-side source verification, not an editor action.
    });
    findView.addEventListener('change', () => clearFindings('Finding view changed. Reload to select.'));
  }
  let requestNumber = 0;
  const reset = (message) => {
    output.hidden = true;
    output.textContent = '';
    status.textContent = message;
  };
  clear.addEventListener('click', () => {
    requestNumber += 1;
    input.value = '';
    clearFindings('Finding selection cleared.');
    reset('No source evidence selected.');
  });
  verify.addEventListener('click', async () => {
    const current = ++requestNumber;
    reset('Verifying source identity…');
    verify.disabled = true;
    try {
      const locator = JSON.parse(input.value);
      if (!locator || Array.isArray(locator) || typeof locator !== 'object') throw new Error('Expected a JSON object');
      const response = await fetch('/api/orchestration/code-analysis/source-evidence/preview', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(locator),
      });
      const result = await response.json();
      if (current !== requestNumber) return;
      if (!response.ok || !result.ok) throw new Error(result.error || 'Evidence verification failed');
      const evidence = result.evidence;
      if (!evidence || evidence.mode !== 'read_only' || evidence.schema !== 'pah.source-evidence@1') throw new Error('Unsupported evidence response');
      // textContent explicitly prevents HTML execution from source text.
      output.textContent = evidence.excerpt;
      output.hidden = false;
      status.textContent = `Verified ${evidence.relative_path}:${evidence.start_line}-${evidence.end_line} (SHA-256 ${evidence.source_sha256.slice(0, 12)}…)`;
    } catch (error) {
      if (current === requestNumber) reset(`Unavailable: ${error.message}`);
    } finally {
      if (current === requestNumber) verify.disabled = false;
    }
  });
  // A workspace switch invalidates any prior preview, even when a fetch is in flight.
  document.getElementById('researchWorkspaceSelect')?.addEventListener('change', () => {
    requestNumber += 1;
    clearFindings('Workspace changed. Reload findings.');
    reset('Workspace changed. Reverify the source evidence.');
    verify.disabled = false;
  });
  document.getElementById('openWorkspace')?.addEventListener('click', () => {
    requestNumber += 1;
    clearFindings('Workspace selection changed. Reload findings.');
    reset('Workspace selection changed. Reverify the source evidence.');
    verify.disabled = false;
  });
})();
