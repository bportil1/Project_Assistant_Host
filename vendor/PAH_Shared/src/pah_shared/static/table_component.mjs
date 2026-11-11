/** The one table UI/interaction engine for PAH_Shared consumers. */
import {selectView,validateSnapshot,TableContractError} from './table_view.mjs';
import {downloadTable} from './table_exports.mjs';
const text = v => v == null ? '' : String(v);
const controllers = new WeakMap();
function el(tag, attrs={}, children=[]) {
  const n=document.createElement(tag);
  Object.entries(attrs).forEach(([k,v])=>{if(k==='class')n.className=v;else if(k==='text')n.textContent=v;else n.setAttribute(k,v);});
  children.forEach(c=>n.appendChild(c));return n;
}
export function mountTable(container, input, {title='Scientific results',filename='table',onCellActivate=null}={}) {
  if (!container || typeof container.replaceChildren!=='function') throw new TypeError('Table container must be a DOM element');
  let snapshot=validateSnapshot(input);
  let filters={};
  const toolbar=el('div',{class:'ps-controls'});
  const search=el('input',{type:'search','aria-label':'Search table',placeholder:'Search rows…'});
  const clear=el('button',{type:'button',text:'Clear'});
  const exportButtons={};
  for(const fmt of ['csv','tex','svg','png']) {
    const b=el('button',{type:'button',text:fmt.toUpperCase(),title:`Export ${fmt.toUpperCase()} (all matching rows)`});
    exportButtons[fmt]=b;toolbar.appendChild(b);
  }
  const status=el('span',{class:'ps-status','aria-live':'polite'});
  toolbar.prepend(search,clear);toolbar.appendChild(status);
  const viewport=el('div',{class:'ps-table-frame'});
  const footer=el('div',{class:'ps-pages'});
  const prev=el('button',{type:'button',text:'Previous'}),next=el('button',{type:'button',text:'Next'});
  const counter=el('span');footer.append(prev,counter,next);
  container.classList.add('ps-table-workspace');
  container.replaceChildren(toolbar,viewport,footer);
  function repaint(){
    const data=selectView(snapshot,{scope:'current_page'});
    const table=el('table',{class:'ps-table','aria-label':title});
    const header=el('tr');
    for(const col of data.columns) {
      const th=el('th',{'scope':'col'});const desc=snapshot.columns.find(c=>c.id===col.id)?.description;if(desc)th.title=desc;
      const b=el('button',{type:'button',class:'ps-sort',text:col.title});
      const sort=snapshot.view.sort.find(s=>s.column_id===col.id);
      th.setAttribute('aria-sort',sort?(sort.direction==='asc'?'ascending':'descending'):'none');
      b.addEventListener('click',()=>{
        snapshot.view.sort=sort?(sort.direction==='asc'?[{column_id:col.id,direction:'desc'}]:[]):[{column_id:col.id,direction:'asc'}];
        snapshot.view.page.index=0;repaint();
      });th.appendChild(b);header.appendChild(th);
    }
    const thead=el('thead',{},[header]);
    const filterRow=el('tr',{class:'ps-filters'});
    for(const col of data.columns){
      const th=el('th');const input=el('input',{type:'search',placeholder:'Filter…','aria-label':`Filter ${col.title}`});
      input.value=filters[col.id]??'';
      input.addEventListener('input',()=>{
        filters[col.id]=input.value;
        snapshot.view.filters=Object.entries(filters).filter(([,v])=>v).map(([column_id,value])=>({column_id,op:'contains',value}));
        snapshot.view.page.index=0;
        const cursorStart=input.selectionStart, cursorEnd=input.selectionEnd;
        repaint();
        const focus=viewport.querySelectorAll('.ps-filters input')[data.columns.findIndex(c=>c.id===col.id)];
        if(focus){focus.focus();focus.setSelectionRange(cursorStart??focus.value.length,cursorEnd??focus.value.length);}
      });
      th.appendChild(input);filterRow.appendChild(th);
    }
    thead.appendChild(filterRow);table.appendChild(thead);
    const body=el('tbody');
    for(const r of data.rows){const tr=el('tr');
      for(const col of data.columns){
        const td=el('td',{text:r.display_values?.[col.id]??text(r.values[col.id])});
        if(col.kind==='integer'||col.kind==='number')td.classList.add('ps-table__numeric');
        if (typeof onCellActivate === 'function') {
          td.tabIndex = 0;
          td.classList.add('ps-table__activatable');
          const activate = () => onCellActivate({rowId:r.id,columnId:col.id,value:r.values[col.id],row:r,column:col});
          td.addEventListener('click',activate);
          td.addEventListener('keydown',event=>{
            if(event.key==='Enter'||event.key===' '){event.preventDefault();activate();}
          });
        }
        tr.appendChild(td);
      }body.appendChild(tr);
    }
    table.appendChild(body);viewport.replaceChildren(table);
    const maxPage=Math.max(0,Math.ceil(data.total_filtered_rows/snapshot.view.page.size)-1);
    if(snapshot.view.page.index>maxPage){snapshot.view.page.index=maxPage;repaint();return;}
    prev.disabled=snapshot.view.page.index===0;next.disabled=snapshot.view.page.index>=maxPage;
    counter.textContent=`Page ${snapshot.view.page.index+1} / ${maxPage+1}`;
    status.textContent=`${data.total_filtered_rows} matching row(s)`;
  }
  search.value=snapshot.view.search;
  search.addEventListener('input',()=>{snapshot.view.search=search.value;snapshot.view.page.index=0;repaint();});
  clear.addEventListener('click',()=>{filters={};snapshot.view.filters=[];snapshot.view.search='';snapshot.view.sort=[];snapshot.view.page.index=0;search.value='';repaint();});
  prev.addEventListener('click',()=>{snapshot.view.page.index--;repaint();});
  next.addEventListener('click',()=>{snapshot.view.page.index++;repaint();});
  for(const [fmt,b] of Object.entries(exportButtons))b.addEventListener('click',async()=>{
    try{await downloadTable(snapshot,fmt,{title,filename});status.textContent=`Exported ${fmt.toUpperCase()}`;}
    catch(e){status.textContent=`Export unavailable: ${e.message}`;}
  });
  repaint();
  return {
    update(next, {preserveView=true}={}) {
      const incoming=validateSnapshot(next);
      if (preserveView && incoming.columns.map(c=>c.id).join('|')===snapshot.columns.map(c=>c.id).join('|')) {
        incoming.view=structuredClone(snapshot.view);
      } else {filters={};search.value=incoming.view.search;}
      snapshot=incoming;repaint();
    },
    getSnapshot:()=>structuredClone(snapshot), destroy:()=>{container.replaceChildren();controllers.delete(container);}
  };
}
/** Dash or any other framework need only supply JSON through an HTML data attribute. */
export function autoMountTables({selector='[data-pah-shared-table]'}={}) {
  const scan=()=>document.querySelectorAll(selector).forEach(node=>{
    const raw=node.getAttribute('data-pah-shared-table');
    if(!raw)return;
    const old=controllers.get(node);
    if(old?.raw===raw)return;
    try{
      const obj=JSON.parse(raw);
      if(old){old.controller.update(obj,{preserveView:false});old.raw=raw;}
      else controllers.set(node,{raw,controller:mountTable(node,obj,{title:node.dataset.pahTitle??'Scientific results',filename:node.dataset.pahFilename??'table'})});
    }catch(e){node.textContent=`Shared table unavailable: ${e.message}`;}
  });
  scan();
  const observer=new MutationObserver(mutations=>{
    // Dash/Plotly update many unrelated nodes: only scan for table host changes.
    const relevant=mutations.some(m=>m.type==='attributes' ||
      [...m.addedNodes].some(n=>n.nodeType===1 && (n.matches?.(selector) || n.querySelector?.(selector))));
    if(relevant)scan();
  });
  observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-pah-shared-table']});
  return ()=>observer.disconnect();
}
