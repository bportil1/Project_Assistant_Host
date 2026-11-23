/* MI-06 — generic, local module process management. No scientific state. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const dialog = $('moduleInstancesDialog');
  if (!dialog) return;
  const moduleSelect = $('moduleInstancesSelect');
  const launchButton = $('moduleInstancesLaunch');
  const capability = $('moduleInstancesCapability');
  const list = $('moduleInstancesList');
  let modules = [];
  let polling = null;
  let loading = false;
  let profileToken = null;

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {'Content-Type': 'application/json', ...options.headers},
    });
    let body = {};
    try { body = await response.json(); } catch (_) { /* preserve HTTP error */ }
    if (!response.ok || body.ok === false) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  }

  function localUiUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(value, window.location.href);
      const host = url.hostname.toLowerCase();
      if (!['http:', 'https:'].includes(url.protocol)) return null;
      if (url.origin !== window.location.origin && !['127.0.0.1', 'localhost', '[::1]'].includes(host)) return null;
      return url.href;
    } catch (_) { return null; }
  }

  function info(message, error = false) {
    capability.textContent = message;
    capability.dataset.error = error ? 'true' : 'false';
  }

  function addButton(parent, label, handler, enabled = true) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.disabled = !enabled;
    if (enabled) button.addEventListener('click', handler);
    parent.appendChild(button);
    return button;
  }

  function updateCapability() {
    const selected = modules.find(item => item.module_id === moduleSelect.value);
    const supported = Boolean(selected?.multi_instance_launchable);
    launchButton.disabled = !supported || loading;
    if (!selected) info('Select a module.');
    else if (!selected.enabled) info('This module is disabled for the selected workspace. Running siblings remain unaffected.');
    else if (!supported) info('No independent process launch contract. Legacy module launch remains available outside this manager.');
    else info('New instance will use the selected workspace at launch; existing instances keep their original workspace.');
  }

  async function refresh() {
    const [profile, registry] = await Promise.all([
      request('/api/orchestration/modules'), request('/api/orchestration/instances'),
    ]);
    modules = profile.modules || [];
    profileToken = profile.context_token || null;
    const current = moduleSelect.value;
    moduleSelect.replaceChildren();
    for (const item of modules) {
      const option = document.createElement('option');
      option.value = item.module_id;
      option.textContent = item.display_name || item.module_id;
      moduleSelect.appendChild(option);
    }
    if (modules.some(item => item.module_id === current)) moduleSelect.value = current;
    updateCapability();
    list.replaceChildren();
    const instances = (registry.instances || []).slice().sort((a, b) =>
      `${a.module_id}/${a.module_instance_id}`.localeCompare(`${b.module_id}/${b.module_instance_id}`));
    if (!instances.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No registered module instances on this PAH host.';
      list.appendChild(empty);
    }
    for (const instance of instances) {
      const row = document.createElement('article');
      row.className = 'module-instances-entry';
      const content = document.createElement('div');
      const heading = document.createElement('strong');
      const matching = modules.find(item => item.module_id === instance.module_id);
      heading.textContent = matching?.display_name || instance.module_id;
      const id = document.createElement('small');
      id.textContent = `Instance: ${instance.module_instance_id}`;
      const details = document.createElement('small');
      const scope = instance.workspace_id || 'unbound';
      details.textContent = `Workspace: ${scope} · PID: ${instance.pid ?? '—'} · Port: ${instance.port ?? '—'} · ${instance.managed_process ? 'PAH-owned process' : 'Legacy/unmanaged'}`;
      content.append(heading, id, details);
      const actions = document.createElement('div');
      actions.className = 'actions';
      const localUrl = localUiUrl(instance.url);
      addButton(actions, 'Open window', () => window.open(localUrl, '_blank', 'noopener'), Boolean(localUrl));
      addButton(actions, 'Stop', async () => {
        if (!window.confirm(`Stop instance ${instance.module_instance_id}? Other instances will stay running.`)) return;
        try {
          await request(`/api/orchestration/instances/${encodeURIComponent(instance.module_instance_id)}/shutdown`, {method: 'POST'});
          await refresh();
        } catch (error) { info(error.message, true); }
      }, Boolean(instance.managed_process));
      row.append(content, actions);
      list.appendChild(row);
    }
  }

  async function safeRefresh() {
    if (loading) return;
    loading = true;
    try { await refresh(); }
    catch (error) { updateCapability(); info(error.message, true); }
    finally { loading = false; launchButton.disabled = !modules.find(item => item.module_id === moduleSelect.value)?.multi_instance_launchable; }
  }

  $('moduleInstancesToggle')?.addEventListener('click', () => {
    dialog.showModal();
    safeRefresh();
    if (polling) clearInterval(polling);
    polling = setInterval(() => { if (!document.hidden) safeRefresh(); }, 15000);
  });
  $('moduleInstancesClose')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { if (polling) clearInterval(polling); polling = null; });
  moduleSelect.addEventListener('change', updateCapability);
  $('moduleInstancesRefresh')?.addEventListener('click', safeRefresh);
  launchButton.addEventListener('click', async () => {
    if (launchButton.disabled || loading) return;
    const moduleId = moduleSelect.value;
    loading = true;
    launchButton.disabled = true;
    try {
      const result = await request(`/api/orchestration/modules/${encodeURIComponent(moduleId)}/instances`, {
        method: 'POST', body: '{}', headers: profileToken ? {'X-PAH-Context-Token': profileToken} : {},
      });
      await refresh();
      info(`Started instance ${result.instance.module_instance_id}. Use Open window if the module exposes a browser UI.`);
    } catch (error) { info(error.message, true); }
    finally { loading = false; launchButton.disabled = !modules.find(item => item.module_id === moduleSelect.value)?.multi_instance_launchable; }
  });
})();
