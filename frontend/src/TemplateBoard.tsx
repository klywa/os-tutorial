import {useEffect,useId,useRef,useState,type PointerEvent} from 'react';
import {cardCategories} from './cardCatalog';
import type {TemplateEntityEntry} from './templateEntityIndex';
import type {TemplateEvent,TemplateGroup} from './templates';

export {buildTemplateEntityIndex,type TemplateEntityEntry} from './templateEntityIndex';

export function TemplateEntityList({entries,selected,onSelect,disabled=false}:{
 entries:TemplateEntityEntry[];
 selected:string;
 onSelect:(key:string)=>void;
 disabled?:boolean;
}){
 const [open,setOpen]=useState(false),[query,setQuery]=useState('');
 const trigger=useRef<HTMLButtonElement>(null),search=useRef<HTMLInputElement>(null),id=useId();
 const terms=query.trim().toLocaleLowerCase().split(/\s+/u).filter(Boolean);
 const filtered=entries.filter(entry=>{
  const label=[entry.name,cardCategories[entry.category],...entry.aliases].join(' ').toLocaleLowerCase();
  return terms.every(term=>label.includes(term));
 });
 useEffect(()=>{if(open)search.current?.focus();},[open]);
 function close(){
  if(!open)return;
  setOpen(false);
  trigger.current?.focus();
 }
 function pick(key:string){onSelect(key);close();}
 return <>
  <button type="button" ref={trigger} className="template-mobile-events" disabled={disabled} aria-expanded={open}
   aria-controls={id} onClick={()=>setOpen(true)}>实体列表</button>
  {open&&<button type="button" className="template-drawer-backdrop" aria-label="关闭实体列表" onClick={close}/>}
  <aside id={id} className={'template-events template-entities'+(open?' template-events-open':'')} aria-label="实体列表"
   onKeyDown={e=>{if(e.key==='Escape')close();}}>
   <button type="button" className="template-mobile-close" onClick={close}>收起实体列表</button>
   <label className="template-entity-search">查找实体
    <input ref={search} type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="名称、别名或类别"/>
   </label>
   <button type="button" disabled={disabled} aria-pressed={!selected} className={!selected?'selected':''} onClick={()=>pick('')}>全部实体</button>
   {filtered.map(entry=><button type="button" key={entry.key} disabled={disabled} aria-pressed={entry.key===selected}
    className={entry.key===selected?'selected':''} onClick={()=>pick(entry.key)}>
    <span>{entry.name}<small>{cardCategories[entry.category]}</small></span><span>{entry.groupIds.size}</span>
   </button>)}
   {!filtered.length&&<p className="muted">{query?'没有符合搜索的实体。':'暂无实体资料。'}</p>}
  </aside>
 </>;
}

type Drag={pointerId:number;last:string;visited:Set<string>;select:boolean;moved:boolean;point?:{x:number;y:number}};

function scrollingParent(board:HTMLElement){
 for(let node=board.parentElement;node;node=node.parentElement){
  if(node.scrollHeight>node.clientHeight&&/^(auto|scroll)$/.test(getComputedStyle(node).overflowY))return node;
 }
}

export default function TemplateBoard({groups,events,selected,onSelectionChange,onDetail,byEvent=false,selectionDisabled=false,entity}:{
 groups:TemplateGroup[];
 events:TemplateEvent[];
 selected:ReadonlySet<string>;
 onSelectionChange:(ids:string[],selected:boolean)=>void;
 onDetail:(id:string)=>void;
 byEvent?:boolean;
 selectionDisabled?:boolean;
 entity?:TemplateEntityEntry;
}){
 const board=useRef<HTMLDivElement>(null),drag=useRef<Drag|null>(null),skipClick=useRef(false),scrollFrame=useRef(0);
 const eventNames=new Map(events.map(event=>[event.id,event.name]));
 const eventRows=new Map<string,TemplateGroup[]>();
 for(const group of groups){
  const key=byEvent?group.event_id:'';
  const rows=eventRows.get(key)??[];
  rows.push(group);
  eventRows.set(key,rows);
 }
 const sections=[...eventRows];
 const order=sections.flatMap(([,rows])=>rows.map(row=>row.id));
 const positions=new Map(order.map((id,index)=>[id,index]));
 useEffect(()=>()=>window.cancelAnimationFrame(scrollFrame.current),[]);
 function startDrag(event:PointerEvent<HTMLButtonElement>,id:string){
  skipClick.current=false;
  if(event.button!==0||event.pointerType==='touch'||selectionDisabled)return;
  drag.current={pointerId:event.pointerId,last:id,visited:new Set(),select:!selected.has(id),moved:false};
  event.currentTarget.setPointerCapture?.(event.pointerId);
 }
 function rowIds(from:string,to:string){
  const start=positions.get(from),end=positions.get(to);
  if(start===undefined||end===undefined)return [];
  return order.slice(Math.min(start,end),Math.max(start,end)+1);
 }
 function selectAtPoint(state:Drag,x:number,y:number){
  const row=document.elementFromPoint(x,y)?.closest<HTMLElement>('[data-template-board-row]');
  const id=row?.dataset.templateBoardRow;
  if(!id||!board.current?.contains(row)||id===state.last)return;
  // The scroll handler can append more rows while the pointer is captured.
  const rendered=Array.from(board.current.querySelectorAll<HTMLElement>('[data-template-board-row]'),item=>item.dataset.templateBoardRow!);
  const start=rendered.indexOf(state.last),end=rendered.indexOf(id);
  if(start<0||end<0)return;
  const next=rendered.slice(Math.min(start,end),Math.max(start,end)+1).filter(key=>!state.visited.has(key));
  for(const key of next)state.visited.add(key);
  state.last=id;
  state.moved=true;
  if(next.length)onSelectionChange(next,state.select);
 }
 function scrollDrag(){
  scrollFrame.current=0;
  const state=drag.current,node=board.current;
  if(!state?.point||!node)return;
  const parent=scrollingParent(node);
  if(!parent)return;
  const {x,y}=state.point,{left,right,top,bottom}=parent.getBoundingClientRect();
  if(x<left||x>right)return;
  const edge=28;
  const steps=y<top+edge?-Math.min(16,top+edge-y):y>bottom-edge?Math.min(16,y-(bottom-edge)):0;
  if(!steps)return;
  const before=parent.scrollTop;
  parent.scrollTop+=steps;
  selectAtPoint(state,x,Math.min(bottom-2,Math.max(top+2,y)));
  if(before!==parent.scrollTop)scrollFrame.current=window.requestAnimationFrame(scrollDrag);
 }
 function moveDrag(event:PointerEvent<HTMLDivElement>){
  const state=drag.current;
  if(!state||state.pointerId!==event.pointerId||selectionDisabled)return;
  state.point={x:event.clientX,y:event.clientY};
  selectAtPoint(state,event.clientX,event.clientY);
  if(!scrollFrame.current)scrollFrame.current=window.requestAnimationFrame(scrollDrag);
 }
 function finishDrag(event:PointerEvent<HTMLDivElement>){
  const state=drag.current;
  if(state?.pointerId!==event.pointerId)return;
  window.cancelAnimationFrame(scrollFrame.current);
  scrollFrame.current=0;
  skipClick.current=state.moved;
  drag.current=null;
 }
 return <div className="template-board" ref={board} onPointerMove={moveDrag} onPointerUp={finishDrag}
  onPointerCancel={finishDrag} onLostPointerCapture={finishDrag}>
  {sections.map(([event,rows])=><section key={event} className="template-board-section" aria-label={event?eventNames.get(event)??event:undefined}>
   {event&&<h3>{eventNames.get(event)??event} <small>{rows.length}</small></h3>}
   <ul>{rows.map(group=>{
    const checked=selected.has(group.id),roles=entity?.roles.get(group.id);
    return <li key={group.id} data-template-board-row={group.id} className={checked?'selected':undefined}>
     <button type="button" className="template-board-pick" data-template-board-pick={group.id} aria-label={'选择'+group.name}
      aria-pressed={checked} aria-description={roles?.join('、')} disabled={selectionDisabled} onPointerDown={e=>startDrag(e,group.id)}
      onClick={e=>{
       if(e.detail&&skipClick.current){skipClick.current=false;return;}
       onSelectionChange([group.id],!checked);
      }} onKeyDown={e=>{
       if(!['ArrowDown','ArrowUp'].includes(e.key))return;
       const index=positions.get(group.id);
       if(index===undefined)return;
       const next=order[index+(e.key==='ArrowDown'?1:-1)];
       if(!next)return;
       e.preventDefault();
       if(e.shiftKey)onSelectionChange(rowIds(group.id,next),true);
       board.current?.querySelector<HTMLElement>('[data-template-board-pick="'+CSS.escape(next)+'"]')?.focus();
      }}>
      <span aria-hidden="true" className="template-board-check">{checked?'✓':''}</span>
      <span className="template-board-name" title={group.name}>{group.name}</span>
      {!byEvent&&<small className="template-board-event">{eventNames.get(group.event_id)??group.event_id}</small>}
      {roles?.map(role=><small className="template-board-role" key={role} title={role}>{role}</small>)}
      {group.ignored&&<small className="template-ignored">已忽略</small>}
      <small className="template-board-count">{group.utterances.length} 条话术</small>
     </button>
     <button type="button" className="template-board-detail" aria-label={'查看'+group.name+'详情'} onClick={()=>onDetail(group.id)}>详情</button>
    </li>;
   })}</ul>
  </section>)}
 </div>;
}
