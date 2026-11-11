/** Universal, offline scientific table exports: one implementation for every host. */
import {selectView, TableContractError} from './table_view.mjs';
const str = v => v === null || v === undefined ? '' : String(v);
const shown = (row, id) => row.display_values?.[id] ?? str(row.values[id]);
const escapeXml = s => str(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');
function escapeTex(s) {
  return str(s).replace(/[\\{}$&#%_^~]/g, c => ({'\\':'\\textbackslash{}','{':'\\{','}':'\\}','$':'\\$','&':'\\&','#':'\\#','%':'\\%','_':'\\_','^':'\\textasciicircum{}','~':'\\textasciitilde{}'}[c]));
}
function matrix(snapshot, scope, {rawNumeric=false}={}) {
  const data = selectView(snapshot, {scope}); // reject incomplete windows
  const namedColumns = new Map(snapshot.columns.map(c=>[c.id,c]));
  return {data, headers: data.columns.map(c => rawNumeric ? (namedColumns.get(c.id)?.export_title ?? c.title) : c.title),
    rows: data.rows.map(r => data.columns.map(c => rawNumeric && ['integer','number'].includes(c.kind) ? str(r.values[c.id]) : shown(r, c.id)))};
}
export function exportCsv(snapshot, {scope='all_matching',rawNumeric=false}={}) {
  const {headers, rows} = matrix(snapshot, scope, {rawNumeric});
  const quote = v => /[",\r\n]/.test(v) ? `"${v.replace(/"/g,'""')}"` : v;
  return '\ufeff' + [headers, ...rows].map(r => r.map(quote).join(',')).join('\r\n') + '\r\n';
}
export function exportTex(snapshot, {scope='all_matching', caption='Scientific results', label='tab:results'}={}) {
  const {data, headers, rows} = matrix(snapshot, scope);
  if (!/^[a-zA-Z0-9:_-]{1,100}$/.test(label)) throw new TableContractError('LaTeX label contains invalid characters');
  const aligns = data.columns.map(c => ['number','integer'].includes(c.kind) ? 'r' : 'l').join('');
  const emit = r => r.map(escapeTex).join(' & ') + ' \\\\';
  return ['% PAH_Shared: current filtered/sorted table across all pages',
    '\\begin{table}[htbp]', '\\centering', `\\caption{${escapeTex(caption)}}`, `\\label{${label}}`,
    `\\begin{tabular}{${aligns}}`, '\\hline', emit(headers), '\\hline',
    ...rows.map(emit), '\\hline', '\\end{tabular}', '\\end{table}', ''].join('\n');
}
/** Independent SVG vector image of exactly the selected table (no viewport clipping). */
export function exportSvg(snapshot, {scope='all_matching', title='Scientific results'}={}) {
  const {data, headers, rows} = matrix(snapshot, scope);
  const all = [headers,...rows];
  const widths = headers.map((_,i) => Math.max(90, Math.min(360, 18 + Math.max(...all.map(r => Math.min(56,str(r[i]).length))) * 7.1)));
  const width = widths.reduce((a,b) => a+b,0), height = 51 + all.length*24;
  if (width > 16000 || height > 20000 || all.length > 6000) {
    throw new TableContractError('Image exceeds safe dimensions; use CSV/TeX or a current-page image');
  }
  const output = [`<svg xmlns="http://www.w3.org/2000/svg" width="${Math.ceil(width)}" height="${height}" viewBox="0 0 ${Math.ceil(width)} ${height}">`,
    '<rect width="100%" height="100%" fill="#fff"/>',
    `<text x="10" y="20" font-family="sans-serif" font-size="14" font-weight="600" fill="#24282d">${escapeXml(title)}</text>`];
  for (let row=0;row<all.length;row++) {
    const y=32+row*24;
    if (row===0) output.push(`<rect x="0" y="${y}" width="${Math.ceil(width)}" height="24" fill="#f3f4f6"/>`);
    let x=0;
    for (let i=0;i<widths.length;i++) {
      output.push(`<rect x="${x}" y="${y}" width="${widths[i]}" height="24" fill="none" stroke="#d5d9de" stroke-width="0.5"/>`);
      const text=str(all[row][i]);
      const limit=Math.max(1,Math.floor((widths[i]-15)/7.1));
      const trimmed=text.length>limit?text.slice(0,limit-1)+'…':text;
      output.push(`<text x="${x+7}" y="${y+16}" font-family="sans-serif" font-size="12" fill="#24282d">${escapeXml(trimmed)}</text>`);
      x+=widths[i];
    }
  }
  output.push('</svg>');
  return output.join('');
}
export async function svgToPng(svg) {
  if (typeof document==='undefined') throw new TableContractError('PNG requires a browser canvas');
  const blob = new Blob([svg], {type:'image/svg+xml;charset=utf-8'}), url=URL.createObjectURL(blob);
  try {
    const img=new Image();
    await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('SVG image failed to load'));img.src=url;});
    const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
    const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Canvas is unavailable');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0);
    return await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('PNG conversion failed')),'image/png'));
  } finally {URL.revokeObjectURL(url);}
}
export async function downloadTable(snapshot, format, {scope='all_matching', title='Scientific results', filename='table',rawNumeric=false}={}) {
  if (!['csv','tex','svg','png'].includes(format)) throw new TableContractError('Unsupported export format');
  const content=format==='csv'?exportCsv(snapshot,{scope,rawNumeric}):format==='tex'?exportTex(snapshot,{scope,caption:title}):exportSvg(snapshot,{scope,title});
  const data=format==='png'?await svgToPng(content):new Blob([content],{type:format==='csv'?'text/csv;charset=utf-8':format==='tex'?'text/plain;charset=utf-8':'image/svg+xml;charset=utf-8'});
  const url=URL.createObjectURL(data);
  try {
    const a=document.createElement('a');a.href=url;a.download=`${filename.replace(/[^\w.-]+/g,'_')}.${format}`;
    document.body.appendChild(a);a.click();a.remove();
  } finally {setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
