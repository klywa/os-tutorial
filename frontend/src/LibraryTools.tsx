import {useEffect,useRef,useState} from 'react';
import type {CSSProperties,ReactNode} from 'react';
import {entityLabel} from './model';
import type {DirectoryFilters} from './directoryModel';
import type {Entity,Options} from './types';

function Popover({label,button,active,children,focusSearch=false}:{label:string;button:ReactNode;active?:boolean;children:ReactNode;focusSearch?:boolean}){
 const [open,setOpen]=useState(false),[position,setPosition]=useState<CSSProperties>({});
 const root=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null);
 function place(){const r=trigger.current?.getBoundingClientRect();if(!r)return;const width=Math.min(340,window.innerWidth-16);setPosition({top:r.bottom+8,left:Math.min(Math.max(8,r.left),window.innerWidth-width-8),width,maxHeight:Math.max(160,window.innerHeight-r.bottom-16)});}
 useEffect(()=>{if(!open)return;place();if(focusSearch)panel.current?.querySelector<HTMLInputElement>('input')?.focus();
  const outside=(e:PointerEvent)=>{if(e.target instanceof Node&&!root.current?.contains(e.target))setOpen(false);};
  document.addEventListener('pointerdown',outside);window.addEventListener('resize',place);
  return()=>{document.removeEventListener('pointerdown',outside);window.removeEventListener('resize',place);};
 },[open]);
 return <div className="library-popover-root" ref={root} onBlur={e=>{if(e.relatedTarget instanceof Node&&root.current?.contains(e.relatedTarget))return;setTimeout(()=>{if(!root.current?.contains(document.activeElement))setOpen(false);},0);}} onKeyDown={e=>{if(e.nativeEvent.isComposing)return;if(open&&e.key==='Escape'){e.stopPropagation();e.preventDefault();setOpen(false);trigger.current?.focus();}}}>
  <button ref={trigger} type="button" className={'library-tool '+(active?'has-filters':'')+(open?' selected':'')} aria-label={label} title={label} aria-expanded={open} aria-haspopup="dialog" onClick={()=>{place();setOpen(!open);}}>{button}</button>
  {open&&<div ref={panel} className="library-popover" role="dialog" aria-label={label} style={position}>{children}</div>}
 </div>;
}

export default function LibraryTools({mode,filters,options,counts,total,resultCount,onChange,onNew}:{mode:'play'|'notes';filters:DirectoryFilters&{banned:string[];unknown:boolean};options:Options;counts:Record<string,number>;total:number;resultCount:number;onChange:(p:Partial<DirectoryFilters&{banned:string[];unknown:boolean}>)=>void;onNew:()=>void}){
 const applied=!!(filters.query.trim()||filters.player||filters.hero);
 function entitySelect(label:string,category:string,value:string,key:'player'|'hero',empty:string){return <label>{label}<select aria-label={label} value={value} onChange={e=>onChange({[key]:e.target.value})}><option value="">{empty}</option>{options.entities.filter((e:Entity)=>e.category===category).map(e=><option key={e.id} value={e.id}>{entityLabel(e)}</option>)}</select></label>;}
 return <div className="library-tools">
  <div className="library-heading"><h2>{mode==='notes'?'知识目录':'选择打法'}</h2><span>{total}篇</span>
   <Popover label="搜索笔记" active={applied} focusSearch button={<><svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>{applied&&<small>{resultCount}</small>}</>}>
    <div className="popover-heading"><strong>搜索与筛选</strong><span role="status">{resultCount}篇结果</span></div>
    <label>关键词<input aria-label="搜索笔记关键词" placeholder="打法、英雄或关键词" value={filters.query} onChange={e=>onChange({query:e.target.value})}/></label>
    {entitySelect('按棋手筛选','players',filters.player,'player','全部棋手')}
    {entitySelect('按核心英雄筛选','heroes',filters.hero,'hero','全部核心英雄')}
    <button type="button" className="quiet" onClick={()=>onChange({query:'',player:'',hero:''})}>清除搜索筛选</button>
   </Popover>
   <button className="library-tool" type="button" aria-label="新建笔记" title="新建笔记" onClick={onNew}>＋</button>
  </div>
  {mode==='notes'?<div className="note-type-switch" role="group" aria-label="笔记类型">{[['','全部'],['lineup','阵容'],['player','棋手'],['other','其他']].map(([type,label])=><button key={type} type="button" aria-pressed={filters.type===type} className={filters.type===type?'selected':''} onClick={()=>onChange({type})}>{label}<small>{counts[type]??0}</small></button>)}</div>:<div className="game-conditions">
   <Popover label="本局条件" active={!!filters.banned.length||filters.unknown} button={<>本局条件<span>{filters.banned.length?'禁用 '+filters.banned.length:'未选禁用'}</span></>}>
    <strong>本局禁用阵营</strong><div className="faction-grid">{options.factions.map(f=><button key={f.id} type="button" aria-pressed={filters.banned.includes(f.id)} className={'faction '+(filters.banned.includes(f.id)?'banned':'')} onClick={()=>onChange({banned:filters.banned.includes(f.id)?filters.banned.filter(x=>x!==f.id):[...filters.banned,f.id]})}>{f.name}</button>)}</div>
    <label className="check"><input type="checkbox" checked={filters.unknown} onChange={e=>onChange({unknown:e.target.checked})}/>显示适用情况待确认的打法</label>
    <button type="button" className="quiet" onClick={()=>onChange({banned:[],unknown:false})}>清除本局条件</button>
   </Popover>
  </div>}
  {applied&&<div className="filter-summary"><span title={[filters.query,options.entities.find(e=>e.id===filters.player)?.name,options.entities.find(e=>e.id===filters.hero)?.name].filter(Boolean).join(' · ')}>筛选中 · {resultCount}篇</span><button type="button" className="quiet" aria-label="清除搜索筛选" onClick={()=>onChange({query:'',player:'',hero:''})}>清除 ×</button></div>}
 </div>;
}
