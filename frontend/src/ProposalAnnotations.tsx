import {useState} from 'react';
import type {Proposal} from './Proposals';
import type {KnowledgeNode} from './types';

export type ProposalAnnotation = {
 id:string; field:string|null; snapshot:unknown; proposal_revision:number;
 author:string; created_at:string; text:string; revision:number;
 status:'open'|'responded'|'closed'; anchor_state:'current'|'changed'|'missing';
 responses:{author:string;created_at:string;text:string;proposal_revision:number}[];
 closed_by?:string; closed_at?:string;
};
export type ResponseDraft = {id:string;revision:number;text:string};
export const fieldNames:Record<string,string> = {title:'章节标题', name:'名称', body:'正文', evidence:'证据'};
export function proposalFields(node:KnowledgeNode|null) {
 if(!node)return [];
 if(node.type==='heading')return ['title'];
 return node.show_key?['name','body']:['body'];
}

const statuses = {open:'待处理',responded:'已回应',closed:'已关闭'};
export function AnnotationSummary({item,admin,canRespond,busy,responses,onResponse,onClose}:{
 item:Proposal;admin:boolean;canRespond:boolean;busy:boolean;responses:Record<string,ResponseDraft>;
 onResponse:(annotation:ProposalAnnotation,text:string)=>void;onClose:(annotation:ProposalAnnotation)=>void;
}){
 const annotations=item.annotations??[];
 if(!annotations.length)return null;
 const unresolved=annotations.filter(a=>a.status!=='closed').length;
 return <section className="proposal-annotations" aria-label="提案批注">
  <h3>批注{unresolved>0&&`（${unresolved} 条未关闭）`}</h3>
  {annotations.map(a=>{
   const [nodeId,field]=a.field?[a.field.slice(0,a.field.lastIndexOf(':')),a.field.slice(a.field.lastIndexOf(':')+1)]:['',''];
   const child=item.section_entries?.find(entry=>entry.node.id===nodeId)?.node;
   const draft=responses[a.id];
   const stale=!!draft&&draft.revision!==a.revision;
   return <article key={a.id} className="proposal-annotation">
    <header><strong>{child&&(child.type==='entry'?child.key:child.title)+' · '}{fieldNames[field]??'整条提案'}</strong>{' · '}{a.author} · {statuses[a.status]} <time dateTime={a.created_at}>{new Date(a.created_at).toLocaleString()}</time></header>
    {a.anchor_state!=='current'&&<small>{a.anchor_state==='missing'?'原字段已移除':'内容已变化'}</small>}
    {a.field&&<details><summary>批注时的内容</summary><pre>{typeof a.snapshot==='string'?a.snapshot:JSON.stringify(a.snapshot,null,2)}</pre></details>}
    <p>{a.text}</p>
    {a.responses.map((response,i)=><div className="proposal-annotation-response" key={i}>
     <small>{response.author} · 改稿版本 {response.proposal_revision}</small><p>{response.text}</p>
    </div>)}
    {a.closed_by&&<small>{a.closed_by} 已关闭</small>}
    {canRespond&&a.status!=='closed'&&<label>随改稿回应<textarea maxLength={4000} value={draft?.text??''} disabled={busy}
     onChange={e=>onResponse(a,e.target.value)}/></label>}
    {stale&&<p role="alert">批注已更新，请核对后重新编辑回应。</p>}
    {draft&&a.status==='closed'&&<button type="button" onClick={()=>onResponse(a,'')}>清除未保存回应</button>}
    {admin&&item.status==='pending'&&a.status!=='closed'&&<button disabled={busy} type="button" onClick={()=>onClose(a)}>关闭批注</button>}
   </article>;
  })}
 </section>;
}

export function AnnotationForm({field,annotations,canComment,busy,onAdd}:{
 field:string|null;annotations:ProposalAnnotation[];canComment:boolean;busy:boolean;
 onAdd:(field:string|null,text:string)=>Promise<boolean>;
}){
 const [open,setOpen]=useState(false),[text,setText]=useState('');
 const count=annotations.filter(a=>a.field===field&&a.status==='open').length;
 if(!canComment&&!count)return null;
 const label=fieldNames[field===null?'':field.slice(field.lastIndexOf(':')+1)]??'整条提案';
 return <div className="proposal-annotation-tools">
  {canComment&&<button type="button" aria-label={label+'：添加批注'} aria-expanded={open} disabled={busy}
   onClick={()=>setOpen(!open)}>{label} · 添加批注</button>}
  {count>0&&<small>{count} 条待处理</small>}
  {canComment&&open&&<form onSubmit={async e=>{
   e.preventDefault();
   if(await onAdd(field,text)){setOpen(false);setText('');}
  }}>
   <label>批注<textarea autoFocus maxLength={4000} value={text} disabled={busy} onChange={e=>setText(e.target.value)}/></label>
   <button disabled={busy||!text.trim()}>保存批注</button>
   <button type="button" disabled={busy} onClick={()=>{setOpen(false);setText('');}}>取消</button>
  </form>}
 </div>;
}
