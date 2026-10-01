(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  let launcherState = null;

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function setMessage(message, isError = false) {
    const node = $('launcherMessage');
    if (!message) {
      node.textContent = '';
      node.classList.add('hidden');
      return;
    }
    node.textContent = message;
    node.dataset.kind = isError ? 'error' : 'info';
    node.classList.remove('hidden');
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }

  function instanceRow(instance) {
    const status = instance.running ? `Running · PID ${instance.pid}` : `${instance.health || 'stopped'} · PID ${instance.pid || '—'}`;
    const target = instance.url
      ? `<a href="${escapeHtml(instance.url)}">${escapeHtml(instance.url)}</a>`
      : '<span>URL unavailable</span>';
    const current = instance.current ? ' · current launcher process' : '';
    const stopDisabled = !instance.running || instance.current ? 'disabled' : '';
    return `
      <div class="launcher-instance" data-instance-id="${escapeHtml(instance.instance_id)}">
        <div>
          <div class="launcher-instance-id">${escapeHtml(instance.instance_id)}${current}</div>
          <div class="launcher-instance-status">${escapeHtml(status)}</div>
        </div>
        <div>${target}</div>
        <div class="launcher-instance-actions">
          <button type="button" data-stop-instance="${escapeHtml(instance.instance_id)}" ${stopDisabled}>Stop</button>
        </div>
      </div>`;
  }

  function workspaceCard(workspace) {
    const running = Number(workspace.running_count || 0);
    const capabilities = (workspace.capability_labels || []).length
      ? workspace.capability_labels.map(label => `<span class="launcher-tag">${escapeHtml(label)}</span>`).join('')
      : '<span class="launcher-module-list">No capabilities enabled</span>';
    const modules = (workspace.modules || []).length
      ? workspace.modules.map(item => `${escapeHtml(item.display_name)}${item.installed ? '' : ' (not installed)'}`).join(' · ')
      : 'No modules enabled';
    const warnings = (workspace.warnings || []).length
      ? `<ul class="launcher-warning-list">${workspace.warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
      : '';
    const instances = (workspace.instances || []).length
      ? `<div class="launcher-instances"><span class="launcher-meta-label">Instances</span>${workspace.instances.map(instanceRow).join('')}</div>`
      : '';
    return `
      <article class="launcher-card" data-workspace-id="${escapeHtml(workspace.id)}">
        <div class="launcher-card-top">
          <div>
            <h2>${escapeHtml(workspace.name || workspace.id)}</h2>
            <div class="launcher-workspace-id">${escapeHtml(workspace.id)}</div>
          </div>
          <div class="launcher-state ${running ? 'running' : ''}">${running ? `${running} running instance${running === 1 ? '' : 's'}` : 'Not running'}</div>
        </div>
        <div class="launcher-actions">
          <button class="primary" type="button" data-open-workspace="${escapeHtml(workspace.id)}">${running ? 'Open' : 'Start & Open'}</button>
          <button type="button" data-new-instance="${escapeHtml(workspace.id)}">Open New Instance</button>
        </div>
        <div class="launcher-meta">
          <div class="launcher-meta-block">
            <span class="launcher-meta-label">Capabilities</span>
            <div class="launcher-tags">${capabilities}</div>
          </div>
          <div class="launcher-meta-block">
            <span class="launcher-meta-label">Enabled Modules</span>
            <div class="launcher-module-list">${modules}</div>
          </div>
        </div>
        ${warnings}
        ${instances}
      </article>`;
  }

  function render(data) {
    launcherState = data;
    const workspaces = data.workspaces || [];
    $('launcherSummary').textContent = `${workspaces.length} workspace${workspaces.length === 1 ? '' : 's'} · ${data.running_count || 0} running instance${data.running_count === 1 ? '' : 's'}`;
    $('launcherCurrentInstance').textContent = data.current_instance_id ? `Launcher instance: ${data.current_instance_id}` : '';
    $('launcherWorkspaces').innerHTML = workspaces.map(workspaceCard).join('');
    $('launcherEmpty').classList.toggle('hidden', workspaces.length > 0);
  }

  async function loadLauncher() {
    try {
      const data = await requestJson('/api/launcher');
      render(data);
      setMessage('');
    } catch (error) {
      setMessage(error.message, true);
    }
  }

  async function resolveStartedUrl(workspaceId, instanceId) {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise(resolve => window.setTimeout(resolve, 100));
      const data = await requestJson('/api/launcher');
      const workspace = (data.workspaces || []).find(item => item.id === workspaceId);
      const instance = (workspace?.instances || []).find(item => item.instance_id === instanceId);
      if (instance?.url) return instance.url;
    }
    return null;
  }

  async function openWorkspace(workspaceId, newInstance) {
    setMessage(newInstance ? 'Starting a new isolated PAH instance…' : 'Opening workspace…');
    try {
      const result = await requestJson(`/api/launcher/workspaces/${encodeURIComponent(workspaceId)}/open`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({new_instance: Boolean(newInstance)}),
      });
      let url = result.url;
      if (!url && result.instance?.instance_id) {
        url = await resolveStartedUrl(workspaceId, result.instance.instance_id);
      }
      if (!url) throw new Error('PAH instance started, but its URL is not available yet. Refresh the launcher to inspect it.');
      window.location.href = url;
    } catch (error) {
      setMessage(error.message, true);
      await loadLauncher();
    }
  }

  async function stopInstance(instanceId) {
    setMessage('Stopping PAH instance…');
    try {
      await requestJson(`/api/launcher/instances/${encodeURIComponent(instanceId)}/stop`, {method: 'POST'});
      await new Promise(resolve => window.setTimeout(resolve, 120));
      await loadLauncher();
    } catch (error) {
      setMessage(error.message, true);
    }
  }

  document.addEventListener('click', event => {
    const openButton = event.target.closest('[data-open-workspace]');
    if (openButton) {
      openWorkspace(openButton.dataset.openWorkspace, false);
      return;
    }
    const newButton = event.target.closest('[data-new-instance]');
    if (newButton) {
      openWorkspace(newButton.dataset.newInstance, true);
      return;
    }
    const stopButton = event.target.closest('[data-stop-instance]');
    if (stopButton) stopInstance(stopButton.dataset.stopInstance);
  });

  $('launcherRefresh')?.addEventListener('click', loadLauncher);
  loadLauncher();
})();
