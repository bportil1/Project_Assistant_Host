// UCA-06: browser-only dispatch eligibility; server-owned evidence verification precedes this step.
const sha = /^[0-9a-f]{64}$/;
const safePath = path => typeof path === 'string' && path.length > 0 && path.length <= 4096 &&
  !/[\\%:\0]/.test(path) && !path.startsWith('/') &&
  path.split('/').every(segment => segment && segment !== '.' && segment !== '..');
export const selectionSchema = 'pah.source-selection@1';
export function fromVerifiedEvidence(evidence, {workspace, repository}) {
  if (!evidence || evidence.schema !== 'pah.source-evidence@1' || evidence.mode !== 'read_only' ||
      evidence.producer_module !== 'pypique' || !evidence.project_id ||
      !sha.test(evidence.source_sha256 || '') || !safePath(evidence.relative_path) ||
      !Number.isSafeInteger(evidence.start_line) || evidence.start_line < 1 ||
      !Number.isSafeInteger(evidence.end_line) || evidence.end_line < evidence.start_line ||
      !workspace || !repository) throw new Error('Unverified or out-of-scope source selection');
  return Object.freeze({schema:selectionSchema, producer:'pypique', project_id:evidence.project_id,
    relative_path:evidence.relative_path, source_sha256:evidence.source_sha256,
    start_line:evidence.start_line, end_line:evidence.end_line, workspace, repository});
}
export function createNavigationBus(scope) {
  if (!Array.isArray(scope) || scope.length !== 2 || !scope.every(Boolean)) throw new Error('Navigation scope required');
  let activeScope=JSON.stringify(scope), epoch=0, sequence=0, last=null;
  const consumed=new Map();
  return {
    switchScope(next) {
      if (!Array.isArray(next) || next.length!==2 || !next.every(Boolean)) { epoch++; last=null; consumed.clear(); activeScope=''; return epoch; }
      const key=JSON.stringify(next);
      if(key!==activeScope) {activeScope=key;epoch++;sequence=0;last=null;consumed.clear();}
      return epoch;
    },
    publish(selection) {
      if (!selection || selection.schema!==selectionSchema ||
          JSON.stringify([selection.workspace,selection.repository])!==activeScope) throw new Error('Selection outside active workspace');
      last=Object.freeze({epoch,sequence:++sequence,selection}); return last;
    },
    consume(event,consumer) {
      if (!['editor','pypique','code_analyzer'].includes(consumer) || !event || event!==last ||
          event.epoch!==epoch || event.selection.producer===consumer || consumed.get(consumer)===event.sequence) return false;
      consumed.set(consumer,event.sequence);return true;
    },
    get epoch(){return epoch;}
  };
}

// UCA-06.2: bind a browser event to server-owned scope, never local path text alone.
export function validateHostScope(scope, selectedWorkspace, selectedRepository) {
  if (!scope || scope.schema !== 'pah.uca-navigation-scope@1' ||
      typeof scope.workspace_id !== 'string' || !scope.workspace_id ||
      scope.project_id !== scope.workspace_id ||
      typeof scope.repository_id !== 'string' || !/^repo-[0-9a-f]{64}$/.test(scope.repository_id) ||
      typeof scope.context_token !== 'string' || !scope.context_token ||
      !Number.isSafeInteger(scope.context_revision) || scope.context_revision < 0 ||
      scope.workspace_id !== selectedWorkspace || scope.repository_root !== selectedRepository) {
    throw new Error('Host workspace/repository identity is unavailable or stale');
  }
  return Object.freeze({ ...scope });
}
export function bindHostIdentity(selection, host) {
  if (!selection || selection.schema !== selectionSchema ||
      selection.workspace !== host.workspace_id || selection.repository !== host.repository_root ||
      selection.project_id !== host.project_id) throw new Error('Finding does not belong to active host scope');
  return Object.freeze({...selection, workspace_id:host.workspace_id,
    repository_id:host.repository_id, context_token:host.context_token,
    context_revision:host.context_revision});
}

// UCA-06.3: verified disk selection; the server computes the digest.
export function fromVerifiedSourceRevision(result, {producer, workspace, repository}, host) {
  const source=result?.selection;
  if (result?.ok!==true || source?.schema!=='pah.uca-source-revision@1' ||
      !['editor','code_analyzer'].includes(producer) ||
      source.project_id!==host.project_id || !safePath(source.relative_path) ||
      !sha.test(source.source_sha256 || '') ||
      !Number.isSafeInteger(source.start_line) || source.start_line<1 ||
      !Number.isSafeInteger(source.end_line) || source.end_line<source.start_line ||
      host.workspace_id!==workspace || host.repository_root!==repository)
    throw new Error('Selected source revision is not verified for this workspace');
  return Object.freeze({schema:selectionSchema, producer, project_id:source.project_id,
    relative_path:source.relative_path,source_sha256:source.source_sha256,
    start_line:source.start_line,end_line:source.end_line,workspace,repository,
    workspace_id:host.workspace_id,repository_id:host.repository_id,
    context_token:host.context_token,context_revision:host.context_revision});
}
