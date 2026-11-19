import {useEffect,useState} from 'react';
import {useAuth} from './auth';
import {api} from './model';
import {TemplateDialog} from './TemplateEditor';
import type {TemplateGroup} from './templates';

export type FeedbackTarget={group?:TemplateGroup;utteranceId?:string};
type Message={action:string;by:string;at:string;body?:string;revisions?:{body:string;at:string}[];edited_at?:string};
type Thread={id:string;group_id:string;group_name:string;utterance_id?:string;original_text:string;original_group?:TemplateGroup;status:string;messages:Message[]};
export type Activity={id:string;original_submission?:TemplateGroup|null;group_id:string;action:string;at:string;by:string;source?:string;batch_id?:string;reason?:string;original_text?:string;body?:string;before?:TemplateGroup|null;submitted?:TemplateGroup|null;reviewed?:TemplateGroup|null;after?:TemplateGroup|null};
const labels:Record<string,string>={fix_utterance:'固定话术',unfix_utterance:'取消固定话术',resolve_conflict:'处理同步冲突',submit:'提交导入提案',proposal_comment:'回复提案讨论',create:'新建模板组',edit_group:'编辑模板组',add_utterance:'增加话术',edit_utterance:'修改话术',delete_utterance:'删除话术',delete:'删除模板组',ignore:'忽略模板组',unignore:'取消忽略模板组',ignore_utterance:'忽略话术',unignore_utterance:'取消忽略话术',approve:'采纳提案',approve_partial:'部分采纳',edit:'修改提案',reject:'拒绝提案',confirm_warning:'确认关联资料',comment_edit:'编辑批注',comment_create:'添加批注',comment_reply:'回复批注',comment_close:'关闭批注',comment_reopen:'重开批注'};
export function activityLabel(row:Activity){return `${labels[row.action]??row.action} · ${row.by} · ${new Date(row.at).toLocaleString()}`;}

function ChangeSummary({record}:{record:Activity}){
 const before=record.before,after=record.after??record.reviewed??record.submitted;
 if(!before||!after)return null;
 const rows=new Map(before.utterances.map(row=>[row.id,row]));
 const newRows=new Map(after.utterances.map(row=>[row.id,row]));
 const fields={name:'组名',scope:'适用范围',conditions:'条件',expression:'表达式',explanation:'说明',priority:'优先级',ignored:'忽略状态',event_id:'事件'} as const;
 return <ul>{(Object.keys(fields) as (keyof typeof fields)[]).filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k])).map(k=><li key={k}>{fields[k]}：{JSON.stringify(before[k])??'无'} → {JSON.stringify(after[k])??'无'}</li>)}{Array.from(new Set([...rows.keys(),...newRows.keys()])).filter(id=>JSON.stringify(rows.get(id))!==JSON.stringify(newRows.get(id))).map(id=><li key={id}>话术：{rows.get(id)?.text??'无'} → {newRows.get(id)?.text??'无'}{newRows.get(id)?.ignored?'（忽略）':''}</li>)}</ul>;
}

export default function TemplateFeedback({target,groups,revision,onLocate,admin,onClose,onChanged}:{target:FeedbackTarget;groups:TemplateGroup[];revision?:string;onLocate:(gid:string,uid?:string)=>void;admin:boolean;onClose:()=>void;onChanged:()=>void}){
 const {session}=useAuth();
 const [edit,setEdit]=useState<{thread:string;index:number;revision:number;body:string}|null>(null);
 const group=target.group,uid=target.utteranceId;
 const [tab,setTab]=useState<'comments'|'history'>('comments'),[status,setStatus]=useState('open');
 const [threads,setThreads]=useState<Thread[]>([]),[history,setHistory]=useState<Activity[]>([]),[serial,refresh]=useState(0);
 const [body,setBody]=useState(''),[replies,setReplies]=useState<Record<string,string>>({}),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{
  let active=true;const params=new URLSearchParams();if(group)params.set('group_id',group.id);if(tab==='comments')params.set('status',status);
  setLoading(true);
  const request=tab==='comments'?api<{items:Thread[]}>('templates/comments?'+params).then(r=>{if(active)setThreads(r.items);}):api<{items:Activity[]}>('templates/history?'+params).then(r=>{if(active)setHistory(r.items);});
  request.catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
 },[group?.id,status,tab,serial]);
 async function post(path:string,data:unknown,clear?:()=>void){setBusy(true);setError('');try{await api('templates/comments'+path,'POST',data);clear?.();refresh(n=>n+1);onChanged();}catch(e){setError((e as Error).message);if((e as {status?:number}).status===409)refresh(n=>n+1);}finally{setBusy(false);}}
 const original=uid?group?.utterances.find(u=>u.id===uid)?.text:group?.name;
 const visible=group?threads.filter(t=>(t.utterance_id??undefined)===uid):threads;
 function close(){if(!busy&&(!(edit||body.trim()||Object.values(replies).some(v=>v.trim()))||confirm('放弃未发送的批注？')))onClose();}
 return <TemplateDialog title={group?group.name+' · 批注与记录':'模板批注与记录'} wide onClose={close}><div className="template-form">
 <nav aria-label="反馈视图"><button aria-pressed={tab==='comments'} onClick={()=>setTab('comments')}>批注讨论</button><button aria-pressed={tab==='history'} onClick={()=>setTab('history')}>管理员操作记录</button></nav>
 {error&&<p role="alert" className="error">{error}</p>}
 {tab==='comments'?<><label>批注状态<select value={status} onChange={e=>setStatus(e.target.value)}><option value="open">待处理</option><option value="closed">已关闭</option><option value="all">全部批注</option></select></label>
 {group&&<form onSubmit={e=>{e.preventDefault();void post('',{group_id:group.id,utterance_id:uid,original_text:original,revision,body},()=>setBody(''));}}><label>{uid?'话术批注':'模板组批注'}<textarea maxLength={4000} value={body} onChange={e=>setBody(e.target.value)}/></label>{uid&&<blockquote>{original}</blockquote>}<button disabled={busy||!body.trim()}>发布批注</button></form>}
 {loading?<p role="status">正在读取…</p>:!visible.length?<p>没有符合条件的批注。</p>:visible.map(t=><section key={t.id} className="template-feedback-thread"><h3>{t.group_name} · {t.utterance_id?'话术':'模板组'} · {t.status==='open'?'待处理':'已关闭'}</h3>{groups.some(g=>g.id===t.group_id&&(!t.utterance_id||g.utterances.some(u=>u.id===t.utterance_id)))?<button onClick={()=>onLocate(t.group_id,t.utterance_id)}>定位到{t.utterance_id?'话术':'模板组'}</button>:<p>批注对象已删除，以下为当时原文。</p>}<blockquote>{t.original_text}</blockquote>{t.original_group&&<details><summary>批注时的模板组</summary><pre>{JSON.stringify(t.original_group,null,2)}</pre></details>}{t.messages.map((m,i)=>{
  if(m.action==='edit')return null;
  const editing=edit?.thread===t.id&&edit.index===i;
  const revision=m.revisions?.length??0;
  return <div key={i}><p><strong>{m.by}</strong> <small>{new Date(m.at).toLocaleString()}</small> {m.body??labels['comment_'+m.action]} {m.edited_at&&<small>已编辑</small>}</p>
   {!!m.revisions?.length&&<details><summary>修改历史（{revision}）</summary>{m.revisions.map((r,n)=><p key={n}><small>{new Date(r.at).toLocaleString()}</small> {r.body}</p>)}</details>}
   {m.body&&m.by===(session.username??'local')&&t.status==='open'&&(editing&&edit?<div><label>修改批注内容<textarea maxLength={4000} value={edit.body} onChange={e=>setEdit({...edit,body:e.target.value})}/></label>
    {revision!==edit.revision&&<button disabled={busy} onClick={()=>setEdit({...edit,revision})}>已核对最新内容，保留我的草稿</button>}
    <button disabled={busy||!edit.body.trim()||revision!==edit.revision} onClick={()=>void post('/'+t.id+'/edit',{message_index:i,message_revision:edit.revision,body:edit.body},()=>setEdit(null))}>保存批注修改</button>
    <button disabled={busy} onClick={()=>setEdit(null)}>取消修改</button></div>:<button disabled={busy||!!edit} onClick={()=>setEdit({thread:t.id,index:i,revision,body:m.body!})}>编辑我的批注</button>)}
  </div>;
 })}
 {t.status==='open'&&<label>回复批注<textarea value={replies[t.id]??''} maxLength={4000} onChange={e=>setReplies({...replies,[t.id]:e.target.value})}/><button disabled={busy||!replies[t.id]?.trim()} onClick={()=>void post('/'+t.id+'/reply',{body:replies[t.id]},()=>setReplies(r=>({...r,[t.id]:''})))}>发送回复</button></label>}
 {admin&&<button disabled={busy} onClick={()=>void post('/'+t.id+(t.status==='open'?'/close':'/reopen'),{})}>{t.status==='open'?'关闭批注':'重开批注'}</button>}</section>)}</>:loading?<p role="status">正在读取…</p>:history.length?history.map(h=><details key={h.id}><summary>{activityLabel(h)}{!group&&' · '+(h.after?.name??h.before?.name??h.group_id)}</summary><ChangeSummary record={h}/><p>记录 {h.id}</p><p>{h.source} {h.batch_id} {h.reason}</p>{h.original_text&&<blockquote>{h.original_text}</blockquote>}{h.body&&<p>{h.body}</p>}{([['操作前',h.before],['原始提交稿',h.original_submission],['本次建议',h.submitted],['审批稿',h.reviewed],['操作后',h.after]] as const).map(([name,value])=>value&&<details key={name}><summary>{name} · {value.name}</summary><pre>{JSON.stringify(value,null,2)}</pre></details>)}</details>):<p>暂无管理员操作记录。</p>}
 </div></TemplateDialog>;
}
