/* JM-2 — read-only job monitor; only displays explicitly registered module jobs. */
(() => {
  const $ = id => document.getElementById(id);
  const drawer = $('jobMonitorDrawer');
  if (!drawer) return;
  const activeStates = new Set(['queued', 'running', 'paused', 'completing', 'unknown']);
  const failedStates = new Set(['failed', 'timed_out', 'interrupted']);
  const terminalStates = new Set(['succeeded', 'failed', 'timed_out', 'interrupted']);
  const expanded = new Set();
  const monitor = {open: false, timer: null, busy: false, requestId: 0, selected: null, sources: []};
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const short = value => value === null || value === undefined || value === '' ? '—' : String(value);
  const stamp = value => {
    const parsed = value && Date.parse(value);
    return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : '—';
  };
  const duration = value => {
    if (!value) return '—';
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 1000));
    return Number.isFinite(seconds) ? `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m ${seconds % 60}s` : '—';
  };
  const readableBytes = bytes => Number.isFinite(bytes) && bytes >= 0 ? `${(bytes / 1024 / 1024).toFixed(1)} MiB` : '—';
  const identity = (owner, jobId) => JSON.stringify([owner, jobId]);
  const notice = (message, error = false) => {
    $('jobMonitorNotice').textContent = message;
    $('jobMonitorNotice').classList.toggle('error', error);
  };
  const matches = job => {
    const value = $('jobMonitorFilter').value;
    if (value === 'active') return activeStates.has(job.state);
    if (value === 'failed') return failedStates.has(job.state);
    if (value === 'succeeded') return job.state === 'succeeded';
    return true;
  };
  function renderTree() {
    const tree = $('jobMonitorTree');
    tree.replaceChildren();
    let visible = 0;
    for (const source of monitor.sources) {
      const jobs = Array.isArray(source.jobs) ? source.jobs : [];
      // IDs are scoped to one source. Build only edges backed by that source.
      const byId = new Map(jobs.map(job => [job.job_id, job]));
      const children = new Map(jobs.map(job => [job.job_id, []]));
      const roots = [];
      for (const job of jobs) {
        if (job.parent_id && job.parent_id !== job.job_id && children.has(job.parent_id)) {
          children.get(job.parent_id).push(job);
        } else roots.push(job);
      }
      const shown = new Set();
      const visiting = new Set();
      function mark(job) {
        if (visiting.has(job.job_id)) return false; // never recurse into malformed cycles
        if (shown.has(job.job_id)) return true;
        visiting.add(job.job_id);
        let keep = matches(job);
        for (const child of children.get(job.job_id) || []) keep = mark(child) || keep;
        visiting.delete(job.job_id);
        if (keep) shown.add(job.job_id);
        return keep;
      }
      roots.forEach(mark);
      // Safely expose isolated cycles/orphans as roots instead of losing them.
      for (const job of jobs) if (!shown.has(job.job_id) && matches(job)) { shown.add(job.job_id); roots.push(job); }
      if (!shown.size) continue;
      const group = element('section', 'jm-source');
      group.appendChild(element('div', 'jm-source-title', `${source.owner} · ${shown.size} shown`));
      const visited = new Set();
      function add(job, depth) {
        if (!shown.has(job.job_id) || visited.has(job.job_id)) return;
        visited.add(job.job_id);
        const key = identity(source.owner, job.job_id);
        const descendants = (children.get(job.job_id) || []).filter(child => shown.has(child.job_id));
        const row = element('div', 'jm-row');
        row.style.paddingLeft = `${Math.min(depth, 12) * 14}px`;
        row.classList.toggle('selected', key === monitor.selected);
        const toggle = element('button', 'jm-expand', descendants.length ? (expanded.has(key) ? '▾' : '▸') : '·');
        toggle.type = 'button';
        toggle.disabled = !descendants.length;
        toggle.setAttribute('aria-label', `${expanded.has(key) ? 'Collapse' : 'Expand'} ${job.label}`);
        toggle.setAttribute('aria-expanded', String(expanded.has(key)));
        toggle.onclick = () => { if (expanded.has(key)) expanded.delete(key); else expanded.add(key); renderTree(); };
        row.appendChild(toggle);
        const choose = element('button', 'jm-select');
        choose.type = 'button';
        choose.setAttribute('aria-label', `Inspect ${job.label}`);
        choose.appendChild(element('span', 'jm-select-title', job.label || job.job_id));
        const meta = [job.kind, job.pid ? `PID ${job.pid}` : null, job.progress !== null && job.progress !== undefined ? `${Math.round(job.progress * 100)}%` : null].filter(Boolean).join(' · ');
        choose.appendChild(element('span', 'jm-select-meta', meta));
        choose.onclick = () => selectJob(source.owner, job);
        row.appendChild(choose);
        const status = element('span', 'jm-state', job.state);
        if (/^[a-z_]+$/.test(job.state || '')) status.classList.add(job.state);
        row.appendChild(status);
        group.appendChild(row);
        if (expanded.has(key)) descendants.forEach(child => add(child, depth + 1));
      }
      roots.forEach(job => add(job, 0));
      tree.appendChild(group);
      visible += shown.size;
    }
    if (!visible) {
      const recorded = monitor.sources.reduce((count, source) => count + (Array.isArray(source.jobs) ? source.jobs.length : 0), 0);
      const text = !recorded
        ? 'No job events have been published for this workspace. This does not mean jobs succeeded. Restart older module processes and verify their monitoring bridge.'
        : $('jobMonitorFilter').value === 'failed'
          ? 'No failures recorded among monitored jobs. Uninstrumented requests are not included.'
          : 'No recorded jobs match this filter.';
      tree.appendChild(element('p', 'jm-notice', text));
    }
  }
  function renderDetails() {
    if (!monitor.selected) return;
    const [owner, jobId] = JSON.parse(monitor.selected);
    const source = monitor.sources.find(item => item.owner === owner);
    const job = (source?.jobs || []).find(item => item.job_id === jobId);
    if (!job) {
      $('jobMonitorSelection').textContent = 'Job no longer in recent history';
      $('jobMonitorState').textContent = '';
      $('jobMonitorDetails').replaceChildren();
      $('jobMonitorLog').textContent = 'Select another job.';
      monitor.selected = null;
      return;
    }
    $('jobMonitorSelection').textContent = job.label;
    $('jobMonitorState').textContent = job.state;
    const details = $('jobMonitorDetails');
    details.replaceChildren();
    const fields = [
      ['Module', owner], ['Type', job.kind], ['Started', stamp(job.started_at)],
      ['Elapsed', duration(job.started_at)], ['Last activity', stamp(job.updated_at)],
      ['Last output', stamp(job.last_output_at)], ['Progress', job.progress == null ? '—' : `${Math.round(job.progress * 100)}%`],
      ['PID', short(job.pid)], ['Liveness', short(job.liveness)],
      ['CPU time', job.cpu_seconds == null ? '—' : `${job.cpu_seconds.toFixed(2)} s`],
      ['Memory', readableBytes(job.rss_bytes)], ['Exit code', short(job.exit_code)],
      ['Run', short(job.run_id)], ['Checkpoint', short(job.checkpoint_id)], ['Reason', short(job.reason)],
    ];
    for (const [label, value] of fields) {
      details.appendChild(element('dt', '', label));
      details.appendChild(element('dd', '', value));
    }
  }
  async function refreshOutput() {
    if (!monitor.open || !monitor.selected) return;
    const selection = monitor.selected;
    const [owner, jobId] = JSON.parse(selection);
    const id = ++monitor.requestId;
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(owner)}/${encodeURIComponent(jobId)}/output?limit=100`, {cache: 'no-store'});
      if (!response.ok) throw new Error(`Output unavailable (${response.status})`);
      const data = await response.json();
      if (!monitor.open || id !== monitor.requestId || monitor.selected !== selection) return;
      const lines = (data.output || []).map(line => `[${stamp(line.timestamp)}] ${line.stream}: ${line.text}`);
      $('jobMonitorLog').textContent = lines.length ? lines.join('\n') : 'No captured output for this job.';
    } catch (error) {
      if (monitor.open && id === monitor.requestId) $('jobMonitorLog').textContent = `Unable to read job output: ${error.message}`;
    }
  }
  function selectJob(owner, job) {
    monitor.selected = identity(owner, job.job_id);
    renderTree();
    renderDetails();
    $('jobMonitorLog').textContent = 'Loading captured output…';
    refreshOutput();
  }
  async function refresh() {
    if (!monitor.open || monitor.busy) return;
    monitor.busy = true;
    try {
      const response = await fetch('/api/jobs', {cache: 'no-store'});
      if (!response.ok) throw new Error(`Job registry unavailable (${response.status})`);
      const data = await response.json();
      if (!monitor.open) return;
      monitor.sources = Array.isArray(data.sources) ? data.sources : [];
      $('jobMonitorCount').textContent = `${data.job_count || 0} jobs`;
      $('jobMonitorUpdated').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      notice(monitor.sources.length ? 'Only explicitly registered jobs are shown. Silent processes may still be running.' : 'No registered sources yet. JM-3 will connect pyPIQUE and EBM / DBN.');
      renderTree();
      if (monitor.selected) { renderDetails(); await refreshOutput(); }
    } catch (error) {
      if (monitor.open) notice(`Unable to update jobs: ${error.message}`, true);
    } finally { monitor.busy = false; }
  }
  function setOpen(open) {
    monitor.open = Boolean(open);
    drawer.hidden = !monitor.open;
    $('jobMonitorToggle').setAttribute('aria-expanded', String(monitor.open));
    if (monitor.timer) { clearInterval(monitor.timer); monitor.timer = null; }
    if (monitor.open) {
      refresh();
      monitor.timer = setInterval(refresh, 3000);
    } else {
      monitor.requestId++; // Discard late output responses.
    }
  }
  $('jobMonitorToggle').addEventListener('click', () => setOpen(!monitor.open));
  $('toolsJobMonitor').addEventListener('click', () => {
    $('toolsMenu').classList.add('hidden');
    $('toolsMenuToggle').setAttribute('aria-expanded', 'false');
    setOpen(!monitor.open);
  });
  $('jobMonitorClose').addEventListener('click', () => setOpen(false));
  $('jobMonitorRefresh').addEventListener('click', refresh);
  $('jobMonitorFilter').addEventListener('change', renderTree);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && monitor.open) setOpen(false);
    if (event.ctrlKey && event.altKey && event.code === 'KeyJ') { event.preventDefault(); setOpen(!monitor.open); }
  });
  const resize = $('jobMonitorResize');
  let pointer = null;
  resize.addEventListener('pointerdown', event => {
    if (window.matchMedia('(max-width: 540px)').matches) return;
    pointer = event.pointerId;
    resize.setPointerCapture(pointer);
    event.preventDefault();
  });
  resize.addEventListener('pointermove', event => {
    if (event.pointerId !== pointer) return;
    const width = Math.min(Math.max(320, window.innerWidth - event.clientX), Math.max(320, window.innerWidth - 40));
    drawer.style.setProperty('--jm-width', `${width}px`);
  });
  const endResize = () => { pointer = null; };
  resize.addEventListener('pointerup', endResize);
  resize.addEventListener('pointercancel', endResize);
  resize.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const width = drawer.getBoundingClientRect().width + (event.key === 'ArrowLeft' ? 24 : -24);
    drawer.style.setProperty('--jm-width', `${Math.min(Math.max(width, 320), Math.max(320, window.innerWidth - 40))}px`);
  });
  window.addEventListener('pagehide', () => { if (monitor.timer) clearInterval(monitor.timer); });
})();
