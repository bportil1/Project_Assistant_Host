(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {status: null, selectedPath: null, activeTab: 'changes'};

  async function api(url, options = {}) {
    const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `${response.status} ${response.statusText}`);
    return data;
  }

  function toast(message, error = false) {
    const node = $('gitToast');
    node.textContent = message;
    node.classList.remove('hidden');
    node.classList.toggle('error', error);
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => node.classList.add('hidden'), 3600);
  }

  function setVisible(id, visible) { $(id)?.classList.toggle('hidden', !visible); }

  function hostBridge() {
    try {
      if (window.parent && window.parent !== window && window.parent._pahGitHost) return window.parent._pahGitHost;
      if (window.top?.opener?._pahGitHost) return window.top.opener._pahGitHost;
    } catch (_) {}
    return null;
  }

  function notifyHostStatus() {
    try { hostBridge()?.statusChanged?.(); } catch (_) {}
  }

  function notifyHostWorktreeChanged() {
    try { hostBridge()?.worktreeChanged?.(); } catch (_) {}
  }

  function hasDirtyHostBuffers() {
    try { return Boolean(hostBridge()?.hasDirtyBuffers?.()); } catch (_) { return false; }
  }

  function statusLabel(item) {
    if (item.untracked) return '??';
    return item.status || `${item.index_status || ' '}${item.worktree_status || ' '}`;
  }

  function trackingLabel(status) {
    const tracking = status?.tracking;
    if (!tracking?.upstream) return 'None';
    const ahead = Number.isInteger(tracking.ahead) ? tracking.ahead : '?';
    const behind = Number.isInteger(tracking.behind) ? tracking.behind : '?';
    return `${tracking.upstream} · ↑${ahead} ↓${behind}`;
  }

  function renderConnectivity(status) {
    const remoteEnabled = Boolean(status?.remote_enabled);
    const badge = $('gitConnectivityBadge');
    if (badge) {
      badge.textContent = remoteEnabled ? 'MANUAL REMOTE' : 'LOCAL ONLY';
      badge.classList.toggle('remote', remoteEnabled);
      badge.classList.toggle('local', !remoteEnabled);
    }
    $('gitConnectivityText').textContent = remoteEnabled ? 'Manual Remote' : 'Local only';
    $('gitEnableRemote').disabled = remoteEnabled;
    $('gitDisableRemote').disabled = !remoteEnabled;
    for (const id of ['gitFetch', 'gitPull', 'gitPush', 'gitClone', 'gitSubmoduleRecorded', 'gitSubmoduleRemote']) {
      const node = $(id);
      if (node) node.disabled = !remoteEnabled;
    }
  }

  function renderStatus(status) {
    state.status = status;
    $('gitRepoLabel').textContent = status.repository_root || status.workspace || 'No workspace';
    setVisible('gitUnavailable', !status.git_available);
    setVisible('gitNoWorkspace', status.git_available && !status.workspace);
    setVisible('gitNotRepository', status.git_available && Boolean(status.workspace) && !status.is_repository);
    setVisible('gitRepository', status.git_available && status.is_repository);
    renderConnectivity(status);
    if (!status.git_available || !status.is_repository) return;

    $('gitRoot').textContent = status.repository_root || '—';
    $('gitBranch').textContent = status.branch || (status.detached ? 'detached HEAD' : '(no commits yet)');
    $('gitHead').textContent = status.head || '—';
    $('gitChangeCount').textContent = String((status.changes || []).length);
    $('gitTrackingSummary').textContent = trackingLabel(status);
    $('gitChangeSummary').textContent = `${status.staged_count || 0} staged · ${status.unstaged_count || 0} unstaged · ${status.untracked_count || 0} untracked`;
    $('gitStagedSummary').textContent = `${status.staged_count || 0} staged`;
    $('gitSyncSummary').textContent = status.tracking?.upstream ? trackingLabel(status) : 'Explicit only';
    renderChanges(status.changes || []);
    renderSubmodules(status.submodules || []);
    renderRemotes(status.remotes || [], status.tracking || null);
    $('gitCommit').disabled = !(status.staged_count > 0);
  }

  function renderChanges(changes) {
    const holder = $('gitChanges');
    holder.replaceChildren();
    if (!changes.length) {
      const empty = document.createElement('div');
      empty.className = 'git-empty-list';
      empty.textContent = 'Working tree clean.';
      holder.appendChild(empty);
      state.selectedPath = null;
      $('gitWorkingDiff').disabled = true;
      $('gitStagedDiff').disabled = true;
      $('gitDiff').textContent = 'No local changes.';
      return;
    }
    for (const item of changes) {
      const row = document.createElement('div');
      row.className = 'git-change-row';
      row.classList.toggle('selected', item.path === state.selectedPath);
      row.dataset.path = item.path;

      const status = document.createElement('span');
      status.className = 'git-change-status';
      status.textContent = statusLabel(item);
      const path = document.createElement('button');
      path.type = 'button';
      path.className = 'git-change-path';
      path.textContent = item.path;
      path.title = item.path;
      path.onclick = () => selectChange(item);
      const actions = document.createElement('span');
      actions.className = 'git-change-actions';
      if (item.staged) {
        const unstage = document.createElement('button');
        unstage.type = 'button';
        unstage.textContent = 'Unstage';
        unstage.onclick = event => { event.stopPropagation(); changeStage(false, item.path); };
        actions.appendChild(unstage);
      }
      if (item.unstaged || item.untracked) {
        const stage = document.createElement('button');
        stage.type = 'button';
        stage.textContent = 'Stage';
        stage.onclick = event => { event.stopPropagation(); changeStage(true, item.path); };
        actions.appendChild(stage);
      }
      row.append(status, path, actions);
      holder.appendChild(row);
    }
  }

  function selectChange(item) {
    state.selectedPath = item.path;
    document.querySelectorAll('.git-change-row').forEach(row => row.classList.toggle('selected', row.dataset.path === item.path));
    $('gitDiffTitle').textContent = `DIFF · ${item.path}`;
    $('gitWorkingDiff').disabled = !(item.unstaged || item.untracked);
    $('gitStagedDiff').disabled = !item.staged;
    if (item.staged && !(item.unstaged || item.untracked)) loadDiff(true);
    else loadDiff(false);
  }

  async function loadDiff(staged) {
    if (!state.selectedPath) return;
    try {
      const data = await api(`/api/git/diff?staged=${staged ? '1' : '0'}&path=${encodeURIComponent(state.selectedPath)}`);
      $('gitDiff').textContent = data.diff || (staged ? 'No staged diff for this file.' : 'No working-tree diff for this file.');
    } catch (error) { toast(error.message, true); }
  }

  async function changeStage(stage, path) {
    try {
      const endpoint = stage ? '/api/git/stage' : '/api/git/unstage';
      const data = await api(endpoint, {method: 'POST', body: JSON.stringify({paths: [path]})});
      renderStatus(data);
      notifyHostStatus();
      state.selectedPath = path;
      const updated = (data.changes || []).find(item => item.path === path);
      if (updated) selectChange(updated);
      else $('gitDiff').textContent = 'File no longer has local changes.';
    } catch (error) { toast(error.message, true); }
  }

  async function refreshStatus() {
    try {
      const data = await api('/api/git/status');
      renderStatus(data);
      if (data.is_repository && state.activeTab === 'history') await loadHistory();
      if (data.is_repository && state.activeTab === 'branches') await loadBranches();
    } catch (error) { toast(error.message, true); }
  }

  async function initRepository() {
    if (!window.confirm('Enable Local Git for this workspace? This creates a local .git repository only; no remote will be configured or contacted.')) return;
    try {
      const data = await api('/api/git/init', {method: 'POST', body: '{}'});
      renderStatus(data);
      toast('Local Git repository initialized.');
      notifyHostStatus();
    } catch (error) { toast(error.message, true); }
  }

  async function commit() {
    const message = $('gitCommitMessage').value.trim();
    if (!message) return toast('Enter a commit message.', true);
    try {
      const data = await api('/api/git/commit', {method: 'POST', body: JSON.stringify({message})});
      $('gitCommitMessage').value = '';
      renderStatus(data);
      $('gitDiff').textContent = 'Commit created locally.';
      toast('Local commit created.');
      notifyHostStatus();
      if (state.activeTab === 'history') await loadHistory();
    } catch (error) { toast(error.message, true); }
  }

  async function loadHistory() {
    try {
      const data = await api('/api/git/history?limit=40');
      const holder = $('gitHistory');
      holder.replaceChildren();
      if (!(data.history || []).length) {
        holder.innerHTML = '<div class="git-empty-list">No local commits yet.</div>';
        return;
      }
      for (const item of data.history) {
        const row = document.createElement('div');
        row.className = 'git-history-row';
        row.innerHTML = '<span class="git-history-sha"></span><span class="git-history-subject"></span><span class="git-history-meta"></span><span class="git-history-meta"></span>';
        row.children[0].textContent = item.short;
        row.children[1].textContent = item.subject;
        row.children[2].textContent = item.author;
        row.children[3].textContent = item.date;
        holder.appendChild(row);
      }
    } catch (error) { toast(error.message, true); }
  }

  async function loadBranches() {
    try {
      const data = await api('/api/git/branches');
      const holder = $('gitBranches');
      holder.replaceChildren();
      if (!(data.branches || []).length && !(data.remote_branches || []).length) {
        holder.innerHTML = '<div class="git-empty-list">No branches yet.</div>';
        return;
      }
      for (const name of data.branches || []) {
        const row = document.createElement('div');
        row.className = `git-branch-row${name === data.current ? ' current' : ''}`;
        const label = document.createElement('span');
        label.textContent = name === data.current ? `${name} · current` : name;
        row.appendChild(label);
        if (name !== data.current) {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = 'Switch';
          button.onclick = () => switchBranch(name);
          row.appendChild(button);
        }
        holder.appendChild(row);
      }
      for (const name of data.remote_branches || []) {
        const row = document.createElement('div');
        row.className = 'git-branch-row remote';
        const label = document.createElement('span');
        label.textContent = `${name} · cached remote`;
        row.appendChild(label);
        holder.appendChild(row);
      }
      $('gitRemoteBranchSummary').textContent = `${(data.remote_branches || []).length} cached remote refs`;
    } catch (error) { toast(error.message, true); }
  }

  async function switchBranch(name) {
    if (hasDirtyHostBuffers()) return toast('Save or close unsaved PAH editor buffers before switching branches.', true);
    if (!window.confirm(`Switch to local branch “${name}”? Uncommitted disk changes must already be compatible with the switch.`)) return;
    try {
      const data = await api('/api/git/branches/switch', {method: 'POST', body: JSON.stringify({name})});
      renderStatus(data);
      await loadBranches();
      notifyHostWorktreeChanged();
      toast(`Switched to ${name}.`);
    } catch (error) { toast(error.message, true); }
  }

  function renderRemotes(rows, tracking) {
    const holder = $('gitRemotes');
    const select = $('gitRemoteSelect');
    holder.replaceChildren();
    select.replaceChildren();
    if (!rows.length) {
      holder.innerHTML = '<div class="git-empty-list">No remotes configured. Adding a remote changes only local .git/config and does not contact it.</div>';
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No remote configured';
      select.appendChild(option);
    }
    for (const item of rows) {
      const row = document.createElement('div');
      row.className = 'git-remote-row';
      const name = document.createElement('strong');
      name.textContent = item.name;
      const url = document.createElement('span');
      url.className = 'git-remote-url';
      url.textContent = item.fetch_url || '—';
      url.title = item.fetch_url || '';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'Remove';
      remove.onclick = () => removeRemote(item.name);
      row.append(name, url, remove);
      holder.appendChild(row);

      const option = document.createElement('option');
      option.value = item.name;
      option.textContent = item.name;
      if (tracking?.remote === item.name) option.selected = true;
      select.appendChild(option);
    }
    const networkDisabled = !state.status?.remote_enabled || !rows.length;
    for (const id of ['gitFetch', 'gitPull', 'gitPush']) $(id).disabled = networkDisabled;
  }

  async function setConnectivity(mode) {
    if (mode === 'manual_remote') {
      const ok = window.confirm('Enable Manual Remote Git for this PAH session? PAH will still contact a remote only when you explicitly click Fetch, Pull, Push, Clone, or a submodule update. Credentials remain with Git/your credential helper.');
      if (!ok) return;
    }
    try {
      await api('/api/git/connectivity', {method: 'POST', body: JSON.stringify({mode})});
      await refreshStatus();
      notifyHostStatus();
      toast(mode === 'manual_remote' ? 'Manual Remote enabled for this workspace session.' : 'Git returned to Local Only.');
    } catch (error) { toast(error.message, true); }
  }

  async function addRemote() {
    const name = $('gitRemoteName').value.trim();
    const url = $('gitRemoteUrl').value.trim();
    if (!name || !url) return toast('Enter both a remote name and URL/path.', true);
    try {
      const data = await api('/api/git/remotes', {method: 'POST', body: JSON.stringify({name, url})});
      $('gitRemoteName').value = '';
      $('gitRemoteUrl').value = '';
      renderStatus(data);
      notifyHostStatus();
      toast(`Remote ${name} added locally. No network connection was made.`);
    } catch (error) { toast(error.message, true); }
  }

  async function removeRemote(name) {
    if (!window.confirm(`Remove remote “${name}” from this repository? This edits local Git configuration only.`)) return;
    try {
      const data = await api(`/api/git/remotes/${encodeURIComponent(name)}`, {method: 'DELETE'});
      renderStatus(data);
      notifyHostStatus();
      toast(`Remote ${name} removed.`);
    } catch (error) { toast(error.message, true); }
  }

  function selectedRemote() {
    return $('gitRemoteSelect').value || null;
  }

  async function remoteAction(action) {
    if (!state.status?.remote_enabled) return toast('Enable Manual Remote before contacting a remote.', true);
    if (action === 'pull' && hasDirtyHostBuffers()) return toast('Save or close unsaved PAH editor buffers before pulling.', true);
    const remote = selectedRemote();
    if (!remote) return toast('Choose/configure a remote first.', true);
    if (action === 'pull' && !window.confirm(`Pull from ${remote} using fast-forward only? PAH will not create a merge commit or start a rebase.`)) return;
    if (action === 'push' && !window.confirm(`Push the current branch to ${remote}?`)) return;
    try {
      const body = {remote};
      if (action === 'push') body.set_upstream = !state.status?.tracking;
      const data = await api(`/api/git/${action}`, {method: 'POST', body: JSON.stringify(body)});
      renderStatus(data);
      notifyHostStatus();
      if (action === 'pull') notifyHostWorktreeChanged();
      if (state.activeTab === 'branches') await loadBranches();
      toast(`${action[0].toUpperCase()}${action.slice(1)} completed.`);
    } catch (error) { toast(error.message, true); }
  }

  async function cloneRepository() {
    if (!state.status?.remote_enabled) return toast('Enable Manual Remote before cloning.', true);
    const url = $('gitCloneUrl').value.trim();
    const destination = $('gitCloneDestination').value.trim();
    const branch = $('gitCloneBranch').value.trim();
    if (!url || !destination) return toast('Enter a repository URL/path and destination.', true);
    if (!window.confirm(`Clone into ${destination}? This is an explicit remote-capable operation.`)) return;
    try {
      const data = await api('/api/git/clone', {method: 'POST', body: JSON.stringify({url, destination, branch})});
      toast(`Cloned to ${data.destination}.`);
      const bridge = hostBridge();
      if (bridge?.openWorkspacePath && window.confirm('Clone complete. Open the cloned project in PAH now?')) {
        await bridge.openWorkspacePath(data.destination);
      }
    } catch (error) { toast(error.message, true); }
  }

  function renderSubmodules(rows) {
    const holder = $('gitSubmodules');
    holder.replaceChildren();
    if (!rows.length) {
      holder.innerHTML = '<div class="git-empty-list">No submodules recorded in this repository.</div>';
      return;
    }
    for (const item of rows) {
      const row = document.createElement('div');
      row.className = 'git-submodule-row';
      const commit = document.createElement('span');
      commit.className = 'git-submodule-commit';
      commit.textContent = item.commit.slice(0, 12);
      const path = document.createElement('span');
      path.className = 'git-submodule-path';
      path.textContent = item.path;
      path.title = item.description || item.path;
      const status = document.createElement('span');
      status.textContent = item.state.replaceAll('_', ' ');
      row.append(commit, path, status);
      holder.appendChild(row);
    }
  }

  async function updateSubmodules(mode) {
    if (!state.status?.remote_enabled) return toast('Enable Manual Remote before updating submodules.', true);
    if (hasDirtyHostBuffers()) return toast('Save or close unsaved PAH editor buffers before updating submodules.', true);
    const label = mode === 'tracked_remote' ? 'tracked remote branches' : 'recorded commits';
    if (!window.confirm(`Recursively update submodules to ${label}? This operation may contact configured submodule remotes.`)) return;
    try {
      const data = await api('/api/git/submodules/update', {method: 'POST', body: JSON.stringify({mode})});
      renderSubmodules(data.submodules || []);
      await refreshStatus();
      notifyHostWorktreeChanged();
      toast('Recursive submodule update completed.');
    } catch (error) { toast(error.message, true); }
  }

  async function setTab(name) {
    state.activeTab = name;
    document.querySelectorAll('.git-tab').forEach(button => button.classList.toggle('active', button.dataset.gitTab === name));
    for (const tab of ['changes', 'history', 'branches', 'remotes', 'submodules']) setVisible(`gitTab${tab[0].toUpperCase()}${tab.slice(1)}`, tab === name);
    if (name === 'history') await loadHistory();
    if (name === 'branches') await loadBranches();
    if (name === 'remotes') await refreshStatus();
  }

  $('gitRefresh').onclick = refreshStatus;
  $('gitInit').onclick = initRepository;
  $('gitWorkingDiff').onclick = () => loadDiff(false);
  $('gitStagedDiff').onclick = () => loadDiff(true);
  $('gitCommit').onclick = commit;
  $('gitCommitMessage').addEventListener('keydown', event => { if (event.key === 'Enter') commit(); });
  $('gitEnableRemote').onclick = () => setConnectivity('manual_remote');
  $('gitDisableRemote').onclick = () => setConnectivity('local_only');
  $('gitAddRemote').onclick = addRemote;
  $('gitFetch').onclick = () => remoteAction('fetch');
  $('gitPull').onclick = () => remoteAction('pull');
  $('gitPush').onclick = () => remoteAction('push');
  $('gitClone').onclick = cloneRepository;
  $('gitSubmoduleRecorded').onclick = () => updateSubmodules('recorded');
  $('gitSubmoduleRemote').onclick = () => updateSubmodules('tracked_remote');
  document.querySelectorAll('[data-git-tab]').forEach(button => button.onclick = () => setTab(button.dataset.gitTab));

  refreshStatus();
})();
