// Cross-window routing is UI assistance, not a new authority for source evidence.
const sha=/^[0-9a-f]{64}$/;
export function eligibleRelay(selection,workspace,repository){
  return !!selection && selection.schema==='pah.source-selection@1' &&
    ['pypique','editor','code_analyzer'].includes(selection.producer) &&
    typeof workspace==='string'&&!!workspace&&selection.workspace===workspace&&
    typeof repository==='string'&&!!repository&&selection.repository===repository&&
    selection.workspace_id===workspace&&selection.project_id===workspace&&
    /^repo-[0-9a-f]{64}$/.test(selection.repository_id||'')&&
    typeof selection.context_token==='string'&&!!selection.context_token&&
    Number.isSafeInteger(selection.context_revision)&&selection.context_revision>=0&&
    typeof selection.relative_path==='string'&&selection.relative_path.length>0&&
    !/[\\%:\0]/.test(selection.relative_path)&&!selection.relative_path.startsWith('/')&&
    selection.relative_path.split('/').every(part=>part&&part!=='.'&&part!=='..')&&
    sha.test(selection.source_sha256||'')&&
    Number.isSafeInteger(selection.start_line)&&selection.start_line>=1&&
    Number.isSafeInteger(selection.end_line)&&selection.end_line>=selection.start_line;
}
