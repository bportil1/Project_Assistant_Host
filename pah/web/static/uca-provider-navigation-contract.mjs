// UCA-09: narrow browser validation; the producer owns source verification.
export const NAV_SCHEMA = 'code-analyzer.provider-navigation@1';
export function readProviderNavigation(data, expectedProject, expectedPath) {
  const s=data?.snapshot;
  if(data?.ok!==true || data.project_id!==expectedProject || !s ||
     s.schema!==NAV_SCHEMA || s.relative_path!==expectedPath ||
     !/^[a-f0-9]{64}$/.test(s.source_sha256||'') ||
     s.source_revision_verified!==true ||
     !['Python','ATLAS','python','atlas'].includes(s.language) ||
     !s.capabilities || typeof s.capabilities!=='object' ||
     !Array.isArray(s.items) || s.items.length>5000 || !Array.isArray(s.diagnostics)) {
    throw new Error('Incompatible language-provider navigation response');
  }
  const ids=new Set();
  for(const n of s.items) {
    if(!n || typeof n.id!=='string' || !n.id || ids.has(n.id) ||
       typeof n.name!=='string' || typeof n.kind!=='string' ||
       n.relative_path!==expectedPath ||
       !Number.isSafeInteger(n.start_line) || n.start_line<1 ||
       !Number.isSafeInteger(n.end_line) || n.end_line<n.start_line ||
       (n.parent_id!==null && typeof n.parent_id!=='string')) {
      throw new Error('Invalid structural navigation node');
    }
    ids.add(n.id);
  }
  for(const n of s.items) if(n.parent_id!==null && !ids.has(n.parent_id))
    throw new Error('Missing structural parent');
  return s;
}
export function providerOverlap(s, selection) {
  if(!s || !selection || s.relative_path!==selection.relative_path ||
     s.source_sha256!==selection.source_sha256) return [];
  return s.items.filter(n=>n.start_line<=selection.end_line && n.end_line>=selection.start_line);
}
