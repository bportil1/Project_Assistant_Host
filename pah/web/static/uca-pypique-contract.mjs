// UCA-04: strict projection/evidence shape checks; not an authorization boundary.
const sha = /^[0-9a-f]{64}$/;
const safePath = value => typeof value === 'string' && value.length > 0 && value.length <= 4096
  && !value.includes('\\') && !value.includes('%') && !value.includes('\0')
  && !value.startsWith('/') && !value.includes(':')
  && value.split('/').every(part => part && part !== '.' && part !== '..');
export function readProjection(data) {
  if (!data || data.schema !== 'pypique.source-evidence-projections@1'
      || typeof data.project_id !== 'string' || !data.project_id
      || !Array.isArray(data.results) || data.results.length > 100) {
    throw new Error('Incompatible pyPIQUE finding projection');
  }
  return data;
}
export function eligibleFinding(item, projectId) {
  const loc = item?.locator;
  return item?.status === 'ready_for_pah_verification'
    && (loc?.schema === undefined || loc?.schema === 'pah.source-evidence@1') && loc?.producer_module === 'pypique'
    && loc?.project_id === projectId && safePath(loc?.relative_path)
    && sha.test(loc?.source_sha256 || '')
    && Number.isSafeInteger(loc?.start_line) && loc.start_line > 0
    && Number.isSafeInteger(loc?.end_line) && loc.end_line >= loc.start_line;
}
export function checkedEvidence(data, locator) {
  const evidence = data?.evidence;
  if (!data?.ok || evidence?.schema !== 'pah.source-evidence@1'
      || evidence.mode !== 'read_only' || evidence.project_id !== locator.project_id
      || evidence.relative_path !== locator.relative_path
      || evidence.source_sha256 !== locator.source_sha256
      || evidence.start_line !== locator.start_line || evidence.end_line !== locator.end_line
      || typeof evidence.excerpt !== 'string') {
    throw new Error('Source-evidence response does not match selected finding');
  }
  return evidence;
}
