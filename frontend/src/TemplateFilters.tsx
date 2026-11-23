import {useEffect,useRef,useState} from 'react';
import {emptyTemplateFilters,lineupPlayer,type TemplateEvent,type TemplateFilters,type TemplateGroup} from './templates';
import type {Note} from './types';

const historyKey='wxq.templates.recent-searches';
const reviewStatuses=[
 ['ai_generated','AI 生成'],['initial_reviewed','初审完成'],['final_reviewed','终审完成'],
] as const;

export function TemplateEventList({events,groups,selected,onSelect,disabled}:{
 events:TemplateEvent[];
 groups:TemplateGroup[];
 selected:string;
 onSelect:(event:string)=>void;
 disabled:boolean;
}){
 const [open,setOpen]=useState(false);
 const trigger=useRef<HTMLButtonElement>(null),closeButton=useRef<HTMLButtonElement>(null);
 const categories=new Map<string,TemplateEvent[]>(),counts=new Map<string,number>();
 for(const event of events){
  const category=event.category||'未分类';
  const items=categories.get(category)??[];
  items.push(event);
  categories.set(category,items);
 }
 for(const group of groups)counts.set(group.event_id,(counts.get(group.event_id)??0)+1);
 useEffect(()=>{if(open)closeButton.current?.focus();},[open]);
 function close(){
  if(!open)return;
  setOpen(false);
  trigger.current?.focus();
 }
 function pick(event:string){onSelect(event);close();}
 return <>
  <button type="button" ref={trigger} className="template-mobile-events" disabled={disabled} aria-expanded={open}
   aria-controls="template-events" onClick={()=>setOpen(true)}>事件分类</button>
  {open&&<button type="button" className="template-drawer-backdrop" aria-label="关闭事件分类" onClick={close}/>}
  <aside id="template-events" className={'template-events'+(open?' template-events-open':'')} aria-label="事件分类"
   onKeyDown={e=>{if(e.key==='Escape')close();}}>
   <button type="button" ref={closeButton} className="template-mobile-close" onClick={close}>收起事件分类</button>
   <button type="button" disabled={disabled} aria-pressed={!selected} className={!selected?'selected':''} onClick={()=>pick('')}>
    <span>全部事件</span><span>{groups.length}</span>
   </button>
   {[...categories].map(([category,items])=><section key={category}><h2>{category}</h2>
    {items.map(event=><button type="button" key={event.id} disabled={disabled} aria-pressed={event.id===selected}
     className={event.id===selected?'selected':''} onClick={()=>pick(event.id)}>
     <span>{event.name}</span><span>{counts.get(event.id)??0}</span>
    </button>)}
   </section>)}
  </aside>
 </>;
}

function loadHistory():string[]{
 try{
  const value:unknown=JSON.parse(localStorage.getItem(historyKey)??'[]');
  return Array.isArray(value)?value.filter((item):item is string=>typeof item==='string').slice(0,5):[];
 }catch{return [];}
}

function choices(groups:TemplateGroup[],get:(group:TemplateGroup)=>string[]){
 return [...new Set(groups.flatMap(get).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
}

export default function TemplateFilterBar({filters,patch,groups,players,lineups,disabled,showMode=true}:{
 filters:TemplateFilters;
 patch:(value:Partial<TemplateFilters>)=>void;
 groups:TemplateGroup[];
 players:{id:string;name:string}[];
 lineups:Note[];
 disabled:boolean;
 showMode?:boolean;
}){
 const [history,setHistory]=useState(loadHistory);
 const [showHistory,setShowHistory]=useState(false);
 const [open,setOpen]=useState(false);
 const menu=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const active=[filters.player,filters.lineup,filters.version,showMode&&filters.mode,filters.review_status,filters.actor].filter(Boolean).length+
  (filters.tags?.length??0)+(filters.batch?.length??0);
 const users=choices(groups,group=>group.last_modified_by?.kind==='user'?[group.last_modified_by.username??'']:[]);
 useEffect(()=>{
  if(!open)return;
  function outside(e:PointerEvent){if(!menu.current?.contains(e.target as Node))setOpen(false);}
  function escape(e:KeyboardEvent){if(e.key==='Escape'){setOpen(false);trigger.current?.focus();}}
  document.addEventListener('pointerdown',outside);
  document.addEventListener('keydown',escape);
  return ()=>{
   document.removeEventListener('pointerdown',outside);
   document.removeEventListener('keydown',escape);
  };
 },[open]);
 function remember(value:string){
  const query=value.trim();
  if(query){
   const next=[query,...history.filter(item=>item.toLocaleLowerCase()!==query.toLocaleLowerCase())].slice(0,5);
   setHistory(next);
   try{localStorage.setItem(historyKey,JSON.stringify(next));}catch{/* Session history remains available. */}
  }
  setShowHistory(false);
 }
 return <fieldset className="template-filters" disabled={disabled}>
  <div className="template-filter-menu" ref={menu} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setOpen(false);}}>
   <button type="button" ref={trigger} aria-expanded={open} aria-controls="template-filter-options" onClick={()=>setOpen(!open)}>筛选 {active>0&&<span>（{active}）</span>} ▾</button>
   <div className="template-filter-options" id="template-filter-options" hidden={!open}>
    <label>棋手<select value={filters.player} onChange={e=>patch({player:e.target.value})}>
     <option value="">全部棋手</option><option value="common">仅通用棋手</option>{players.map(player=><option key={player.id} value={player.id}>{player.name}（含通用）</option>)}
    </select></label>
    <label>阵容棋手组合<select value={filters.lineup} onChange={e=>patch({lineup:e.target.value})}>
     <option value="">全部组合</option><option value="common">仅通用组合</option>
     {lineups.filter(note=>lineupPlayer(note)&&(!filters.player||lineupPlayer(note)===filters.player)).map(note=><option key={note.id} value={note.id}>{note.title}（含通用）</option>)}
    </select></label>
    {(['version','mode'] as const).filter(field=>showMode||field==='version').map((field,index)=><label key={field}>{index===0?'版本':'模式'}
     <select value={filters[field]??''} onChange={e=>patch({[field]:e.target.value})}>
      <option value="">全部</option>{choices(groups,group=>[group[field]??'']).map(value=><option key={value}>{value}</option>)}
     </select></label>)}
    <fieldset className="template-filter-tags"><legend>标签</legend>
     {choices(groups,group=>group.tags??[]).map(tag=><label key={tag}><input type="checkbox" checked={filters.tags?.includes(tag)??false} onChange={e=>patch({tags:e.target.checked?[...(filters.tags??[]),tag]:(filters.tags??[]).filter(item=>item!==tag)})}/>{tag}</label>)}
    </fieldset>
    <label>审核状态<select value={filters.review_status??''} onChange={e=>patch({review_status:e.target.value as TemplateFilters['review_status']})}>
     <option value="">全部状态</option>
     <option value="unmarked">未标记</option>
     {reviewStatuses.map(([value,label])=><option key={value} value={value}>{label}</option>)}
    </select></label>
    <label>最后修改人<select value={filters.actor??''} onChange={e=>patch({actor:e.target.value})}>
     <option value="">所有修改人</option><option value="ai">AI</option>
     <option value="user">全部用户</option>{users.map(username=><option key={username} value={'user:'+username}>{username}</option>)}
    </select></label>
    <fieldset className="template-filter-tags"><legend>批次</legend>
     {choices(groups,group=>group.batch??[]).map(batch=><label key={batch}><input type="checkbox" checked={filters.batch?.includes(batch)??false}
      onChange={e=>patch({batch:e.target.checked?[...(filters.batch??[]),batch]:(filters.batch??[]).filter(item=>item!==batch)})}/>{batch}</label>)}
    </fieldset>
    <button type="button" disabled={!active} onClick={()=>patch({...emptyTemplateFilters,event:filters.event,query:filters.query})}>清空筛选</button>
   </div>
  </div>
  <div className="template-search" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setShowHistory(false);}}>
   <input type="search" aria-label="搜索模板" placeholder="话术、条件或模板名称（逗号分隔关键词）" value={filters.query}
    onChange={e=>patch({query:e.target.value})} onFocus={()=>setShowHistory(true)} onClick={()=>setShowHistory(true)}
    onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();remember(filters.query);}if(e.key==='Escape')setShowHistory(false);}}/>
   {showHistory&&history.length>0&&<div className="template-search-history" aria-label="最近搜索">
    {history.map(query=><button type="button" key={query} onClick={()=>{patch({query});remember(query);}}>{query}</button>)}
   </div>}
  </div>
 </fieldset>;
}
