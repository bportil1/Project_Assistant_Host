// UCA-05: read-only client-side shape checks. Server remains source of authorization.
const text = v => typeof v === 'string' ? v : '';
export function readAnalyzerStatus(data) {
  if (data?.ok !== true || typeof data.available !== 'boolean'
      || typeof data.analyzed !== 'boolean' || typeof data.stale !== 'boolean') {
    throw new Error('Incompatible Code Analyzer status');
  }
  return { available: data.available, analyzed: data.analyzed, stale: data.stale,
    generation: Number.isSafeInteger(data.generation) ? data.generation : 0 };
}
export function readAnalyzerFunctions(data) {
  if (data?.ok !== true || !Array.isArray(data.functions)
      || typeof data.stale !== 'boolean') throw new Error('Incompatible Code Analyzer function list');
  return data.functions.filter(item => item && typeof item.id === 'string' && item.id.length <= 4096
    && item.id.length > 0 && typeof item.path === 'string').slice(0, 200);
}
export function readAnalyzerEntity(data, expectedId) {
  const entity = data?.entity;
  if (data?.ok !== true || !entity || entity.id !== expectedId
      || typeof entity.path !== 'string' || typeof entity.node_type !== 'string'
      || typeof data.stale !== 'boolean') throw new Error('Incompatible Code Analyzer entity');
  return { id: entity.id, name: text(entity.qualified_name || entity.name),
    path: entity.path, type: entity.node_type,
    start: Number.isSafeInteger(entity.metadata?.line_start) ? entity.metadata.line_start : null,
    end: Number.isSafeInteger(entity.metadata?.line_end) ? entity.metadata.line_end : null,
    stale: data.stale };
}
export function readAnalyzerDependencies(data) {
  if (data?.ok !== true || !Array.isArray(data.outgoing) || !Array.isArray(data.incoming)) {
    throw new Error('Incompatible Code Analyzer dependencies');
  }
  return { outgoing: data.outgoing.length, incoming: data.incoming.length };
}
