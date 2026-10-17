import {useRef,useState} from 'react';
import type {Source} from './types';
import type {SourceFilters as Filters} from './acquisition';
import {taskNames} from './acquisition';
export default function SourceFilters({sources,filters,onChange,onReset}:{sources:Source[];filters:Filters;onChange:(key:keyof Filters,value:string)=>void;onReset:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);const [mobile,setMobile]=useState(false);
 const count=Object.entries(filters).filter(([k,v])=>k!=='query'&&!!v).length;
 const extras=[['date_from','发布起始日期','date'],['date_to','发布结束日期','date'],['min_views','最低播放量','number'],['max_views','最高播放量','number'],['min_duration','最短时长（秒）','number'],['max_duration','最长时长（秒）','number'],['collected_from','采集起始日期','date'],['collected_to','采集结束日期','date']] as const;
 const extraCount=extras.filter(([k])=>!!filters[k]).length;
 function select(key:keyof Filters,label:string,values:{value:string;label:string}[]){return <label>{label}<select aria-label={label} value={filters[key]??''} onChange={e=>onChange(key,e.target.value)}><option value="">全部{label}</option>{values.map(v=><option value={v.value} key={v.value}>{v.label}</option>)}</select></label>;}
 function choices(field:'keywords'|'batches'|'author'){return [...new Set(sources.flatMap(s=>field==='author'?[s.author||'']:s[field]??[]).filter(Boolean))].sort().map(value=>({value,label:value}));}
 const selects=<>{select('keyword','关键词',choices('keywords'))}{select('author','UP主',choices('author'))}{select('batch','批次',choices('batches'))}{select('stage','处理状态',['registered','preview','queued','running','downloading','transcribing','ready','prepared','complete','failed'].map(value=>({value,label:taskNames[value]||value})))}{select('deposit','沉淀状态',[{value:'unprocessed',label:'未沉淀'},{value:'submitted',label:'已提交待核对'},{value:'deposited',label:'已沉淀'}])}</>;
 function open(narrow:boolean){setMobile(narrow);dialog.current?.showModal();}
 return <section className="source-filter-bar" aria-label="筛选外部内容"><input className="source-query" aria-label="搜索标题、链接或备注" placeholder="搜索标题、链接或备注" value={filters.query??''} onChange={e=>onChange('query',e.target.value)}/><div className="source-inline-filters">{selects}<button onClick={()=>open(false)}>更多筛选{extraCount?` (${extraCount})`:''}</button><button onClick={onReset}>重置</button></div><button className="source-mobile-filter" onClick={()=>open(true)}>筛选{count?` (${count})`:''}</button>
 <dialog className="filter-dialog creator-dialog" ref={dialog} aria-label="更多筛选"><div className="section-heading"><h2>{mobile?'筛选外部内容':'更多筛选'}</h2><button aria-label="关闭筛选" onClick={()=>dialog.current?.close()}>×</button></div>{mobile&&<div className="filter-dialog-selects">{selects}</div>}<div className="extended-filters">{extras.map(([key,label,type])=><label key={key}>{label}<input type={type} aria-label={label} min={type==='number'?0:undefined} value={filters[key]??''} onChange={e=>onChange(key,e.target.value)}/></label>)}</div><div className="action-line"><button onClick={onReset}>重置全部条件</button><button className="primary" onClick={()=>dialog.current?.close()}>完成</button></div></dialog></section>;
}
