import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import {useAuth} from './auth';

type Review={id:string;card_id:string;card_name:string;author:string;status:string;historical?:boolean;before_tags:string[];after_tags:string[];reviewer:string|null;created:string;reviewed:string|null};
type Detail={revision:string;tags:string[];suggestions?:string[];items:Review[]};
const reviewStatus:Record<string,string>={pending:'待审核',approved:'已通过',rejected:'已驳回',expired:'已失效'};
const parseTags=(value:string)=>[...new Set(value.split(/[、，,\r\n]/u).map(tag=>tag.trim()).filter(Boolean))].sort();

export function CardTagQueue({select,epoch}:{select:(id:string)=>void;epoch:number}){
 const [rows,setRows]=useState<Review[]>([]);
 const [error,setError]=useState('');
 useEffect(()=>{let live=true;api<{items:Review[]}>('cards/tag-reviews').then(data=>{if(live){setRows(data.items??[]);setError('');}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[epoch]);
 return error?<p role="alert">{error}</p>:rows.length?<details><summary>待审核标签（{rows.length}）</summary>{rows.map(r=><button key={r.id} onClick={()=>select(r.card_id)}>{r.card_name} · {r.author}</button>)}</details>:null;
}

export function canShowCardTags(season:string,category:string){
 return season==='S1'&&['heroes','equipment','effect-cards','talents'].includes(category);
}

export function CardTags({id,updated,compact=false}:{id:string;updated?:()=>void;compact?:boolean}){
 const {session}=useAuth();
 const admin=session.role==='admin',editor=admin||session.role==='annotator';
 const [data,setData]=useState<Detail|null>(null),[draft,setDraft]=useState<string|null>(null);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[epoch,setEpoch]=useState(0);
 const saving=useRef(false);
 const path='cards/'+encodeURIComponent(id)+'/tags';
 useEffect(()=>{let live=true;api<Detail>(path).then(result=>{if(live&&Array.isArray(result.tags)){setData(result);setError('');}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[path,epoch]);
 async function save(url:string,body:unknown){
  if(saving.current)return;
  saving.current=true;setBusy(true);setError('');setNotice('');
  try{
   const result=await api<Review>(url,'POST',body);
   if(result.status==='approved'){
    setData(current=>current&&{...current,tags:result.after_tags,revision:result.id});
   }
   if(url===path){
    setDraft(null);
    setNotice(result.status==='approved'?(compact?'':'标签已生效。'):'标签修改已提交审核。');
   }
   setEpoch(i=>i+1);updated?.();
  }
  catch(e){setError((e as Error).message);}
  finally{saving.current=false;setBusy(false);}
 }
 function submitDraft(){
  if(!data||draft===null)return;
  const tags=parseTags(draft);
  if(JSON.stringify(tags)===JSON.stringify([...data.tags].sort())){setDraft(null);return;}
  void save(path,{tags,revision:data.revision});
 }
 const value=draft??data?.tags.join('、')??'';
 const tags=parseTags(value);
 const label=(values:string[])=>values.join('、')||'无';
 return <section><h3>当前形态标签</h3>
 {error&&<p role="alert">{error} <button onClick={()=>setEpoch(i=>i+1)}>重新读取</button></p>}
 {notice&&<p role="status">{notice}</p>}
 {data&&<><p>{editor?'已生效：':''}{label(data.tags)}</p>{editor&&<div className="card-tag-editor" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))submitDraft();}}>
 <label>标签（用顿号分隔）<input readOnly={busy} value={value} onChange={e=>setDraft(e.target.value)}/></label>
 {!compact&&<><label>添加已有标签<select value="" disabled={busy} onChange={e=>{
  const tag=e.target.value;
  if(tag)setDraft([...tags,tag].join('、'));
 }}><option value="">请选择</option>{data.suggestions?.filter(tag=>!tags.includes(tag)).map(tag=><option key={tag}>{tag}</option>)}</select></label>
 <small>{admin?'离开标签编辑区后保存并生效。':'离开标签编辑区后提交管理员审核。'}</small></>}
 </div>}
 {editor&&!compact&&data.items.map(r=><div key={r.id}><strong>{reviewStatus[r.status]}{r.historical?'（旧标签体系）':''} · {r.author}</strong> <time dateTime={r.created}>{new Date(r.created).toLocaleString()}</time>
 <p>原标签　{label(r.before_tags)}<br/>提议标签　{label(r.after_tags)}</p>
 {r.reviewer&&<small>审核人　{r.reviewer}</small>}
 {admin&&r.status==='pending'&&<><button disabled={busy} onClick={()=>void save('cards/tag-reviews/'+r.id+'/approve',{})}>通过</button><button disabled={busy} onClick={()=>void save('cards/tag-reviews/'+r.id+'/reject',{})}>驳回</button></>}</div>)}</>}
 </section>;
}
