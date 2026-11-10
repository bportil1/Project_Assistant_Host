// UCA-10: strict, read-only summary of producer observations from PAH's JM feed.
// A completed job is never proof of a source-matching artifact.
export const OWNERS = Object.freeze(['pypique','code_analyzer','hsqa_dbn','ml_lab']);
const MAX_VISIBLE = 30;
const STATES = new Set(['queued','running','paused','completing','succeeded','failed','timed_out','interrupted','unknown','cancelled','canceled']);
export function summarizeObservations(payload) {
  if (!payload || payload.ok !== true || !Array.isArray(payload.sources)) throw new Error('Job observations unavailable');
  const rows=[];
  for (const source of payload.sources) {
    if (!source || !OWNERS.includes(source.owner) || !Array.isArray(source.jobs)) continue;
    for (const job of source.jobs) {
      if (!job || typeof job.job_id !== 'string' || !job.job_id || job.job_id.length>256) continue;
      // Labels are plain text. Never insert producer strings as markup.
      const state=STATES.has(job.state) ? job.state : 'unknown';
      rows.push({owner:source.owner, job_id:job.job_id, state,
        label:typeof job.label==='string' ? job.label.slice(0,160) : job.job_id});
      if (rows.length===MAX_VISIBLE) return {rows, truncated:true, artifactVerification:'unverified'};
    }
  }
  return {rows,truncated:false,artifactVerification:'unverified'};
}
export function scopeIdentity(scopeResponse) {
  const scope=scopeResponse?.scope;
  if (scopeResponse?.ok!==true || !scope || typeof scope.project_id!=='string' ||
      !scope.project_id || typeof scope.repository_id!=='string' || !scope.repository_id) throw new Error('No active verified workspace');
  return [scope.project_id,scope.repository_id,scope.context_token,scope.context_revision].join('\u0000');
}
