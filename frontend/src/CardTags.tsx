import {useEffect,useState} from 'react';
import {api} from './model';
import {useAuth} from './auth';

type Review={id:string;card_id:string;card_name:string;author:string;status:string;before_tags:string[];after_tags:string[];reviewer:string|null;created:string;reviewed:string|null};
type Detail={revision:string;tags:string[];items:Review[]};

export function CardTagQueue({select,epoch}:{select:(id:string)=>void;epoch:number}){
 const [rows,setRows]=useState<Review[]>([]);
 const [error,setError]=useState('');
 useEffect(()=>{let live=true;api<{items:Review[]}>('cards/tag-reviews').then(data=>{if(live){setRows(data.items??[]);setError('');}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[epoch]);
 return error?<p role="alert">{error}</p>:rows.length?<details><summary>待审核标签（{rows.length}）</summary>{rows.map(r=><button key={r.id} onClick={()=>select(r.card_id)}>{r.card_name} · {r.author}</button>)}</details>:null;
}

export function CardTags({id,updated}:{id:string;updated:()=>void}){
 const {session}=useAuth();
 const editor=session.role==='admin'||session.role==='annotator';
 const [data,setData]=useState<Detail|null>(null),[draft,setDraft]=useState<string|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[epoch,setEpoch]=useState(0);
 const path='cards/'+encodeURIComponent(id)+'/tags';
 useEffect(()=>{let live=true;api<Detail>(path).then(result=>{if(live&&Array.isArray(result.tags)){setData(result);setError('');}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[path,epoch]);
 async function save(url:string,body:unknown){
  setBusy(true);setError('');
  try{await api(url,'POST',body);setDraft(null);setEpoch(i=>i+1);updated();}
  catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }
 const label=(values:string[])=>values.join('、')||'无';
 return <section><h3>当前形态标签</h3>
 {error&&<p role="alert">{error} <button onClick={()=>setEpoch(i=>i+1)}>重新读取</button></p>}
 {data&&<><p>{label(data.tags)}</p>{editor&&(draft===null?<button onClick={()=>setDraft(data.tags.join('、'))}>编辑标签</button>:<form onSubmit={e=>{e.preventDefault();void save(path,{tags:draft.split(/[、，,\n]/u).map(v=>v.trim()).filter(Boolean),revision:data.revision});}}>
 <label>标签（用顿号分隔）<input value={draft} onChange={e=>setDraft(e.target.value)}/></label>
 <button disabled={busy}>提交标签提案</button><button type="button" disabled={busy} onClick={()=>setDraft(null)}>取消</button></form>)}
 {editor&&data.items.map(r=><div key={r.id}><strong>{{pending:'待审核',approved:'已通过',rejected:'已驳回'}[r.status]} · {r.author}</strong> <time dateTime={r.created}>{new Date(r.created).toLocaleString()}</time>
 <p>原标签　{label(r.before_tags)}<br/>提议标签　{label(r.after_tags)}</p>
 {r.reviewer&&<small>审核人　{r.reviewer}</small>}
 {session.role==='admin'&&r.status==='pending'&&<><button disabled={busy} onClick={()=>void save('cards/tag-reviews/'+r.id+'/approve',{})}>通过</button><button disabled={busy} onClick={()=>void save('cards/tag-reviews/'+r.id+'/reject',{})}>驳回</button></>}</div>)}</>}
 </section>;
}
