import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {api} from './model';
import {useAuth} from './auth';
import MetadataSuggestions,{lastMetadataTerm,replaceLastMetadataTerm} from './MetadataSuggestions';

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
 const field=useRef<HTMLSpanElement>(null),trigger=useRef<HTMLButtonElement>(null),initialDraft=useRef('');
 const editing=draft!==null;
 const path='cards/'+encodeURIComponent(id)+'/tags';
 useEffect(()=>{let live=true;api<Detail>(path).then(result=>{if(live&&Array.isArray(result.tags)){setData(result);setError('');}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[path,epoch]);
 function showDraft(value:string){
  const node=field.current;
  if(!node)return;
  node.textContent=value;
  node.focus();
  const selection=node.ownerDocument.getSelection(),range=node.ownerDocument.createRange();
  range.selectNodeContents(node);range.collapse(false);
  selection?.removeAllRanges();selection?.addRange(range);
 }
 useLayoutEffect(()=>{if(editing)showDraft(initialDraft.current);},[editing]);
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
 function submitDraft(restoreFocus=false){
  if(!data||draft===null)return;
  const tags=parseTags(field.current?.innerText??draft);
  if(JSON.stringify(tags)===JSON.stringify([...data.tags].sort())){
   setDraft(null);
   if(restoreFocus)requestAnimationFrame(()=>trigger.current?.focus());
   return;
  }
  void save(path,{tags,revision:data.revision}).then(()=>{
   if(restoreFocus)requestAnimationFrame(()=>trigger.current?.focus());
  });
 }
 const completedTags=draft===null?data?.tags??[]:parseTags(replaceLastMetadataTerm(draft,''));
 const label=(values:string[])=>values.join('、')||'无';
 return <section><h3>当前形态标签</h3>
 {error&&<p role="alert">{error} <button onClick={()=>setEpoch(i=>i+1)}>重新读取</button></p>}
 {notice&&<p role="status">{notice}</p>}
 {data&&<>{editor?<div className="card-tag-editor" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))submitDraft();}}>
 <p>{editing?<span ref={field} className="card-tag-inline card-tag-editing" role="textbox" aria-label="编辑当前形态标签"
  aria-multiline="false" aria-busy={busy} aria-readonly={busy} tabIndex={0} contentEditable={busy?false:'plaintext-only'}
  data-placeholder="输入标签，用顿号分隔" onInput={e=>setDraft(e.currentTarget.innerText)} onKeyDown={e=>{
   if(busy||e.nativeEvent.isComposing||e.keyCode===229)return;
   if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setDraft(null);setError('');requestAnimationFrame(()=>trigger.current?.focus());}
   if(e.key==='Enter'){e.preventDefault();submitDraft(true);}
  }}/>:<button type="button" ref={trigger} className="card-tag-inline" aria-label="编辑当前形态标签" onClick={()=>{
   initialDraft.current=data.tags.join('、');setDraft(initialDraft.current);setNotice('');
  }}>{data.tags.length?label(data.tags):'＋ 添加标签'}</button>}</p>
 {editing&&!busy&&<MetadataSuggestions scope="card-tags" choices={(data.suggestions??[]).filter(tag=>!completedTags.includes(tag))}
  query={lastMetadataTerm(draft)} label="匹配标签"
  onPick={tag=>{const value=replaceLastMetadataTerm(draft,tag)+'、';showDraft(value);setDraft(value);}}/>}
 </div>:<p>{label(data.tags)}</p>}
 {editor&&!compact&&data.items.map(r=><div key={r.id}><strong>{reviewStatus[r.status]}{r.historical?'（旧标签体系）':''} · {r.author}</strong> <time dateTime={r.created}>{new Date(r.created).toLocaleString()}</time>
 <p>原标签　{label(r.before_tags)}<br/>提议标签　{label(r.after_tags)}</p>
 {r.reviewer&&<small>审核人　{r.reviewer}</small>}
 {admin&&r.status==='pending'&&<><button disabled={busy} onClick={()=>void save('cards/tag-reviews/'+r.id+'/approve',{})}>通过</button><button disabled={busy} onClick={()=>void save('cards/tag-reviews/'+r.id+'/reject',{})}>驳回</button></>}</div>)}</>}
 </section>;
}
