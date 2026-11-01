import {useEffect,useRef,useState} from 'react';
import {useAuth,useCapabilities,type Role} from './auth';
import {api} from './model';
import {equalValue} from './noteReviewModel';
import {DiffText,NodeFields} from './ReviewFields';
import type {KnowledgeNode} from './types';
export type Proposal={id:string;note_id:string;note_title:string;author:string;kind:'insert'|'update'|'delete';node_id:string;section_id:string;after_id:string|null;base_node:KnowledgeNode|null;proposed_node:KnowledgeNode|null;revision:number;status:string;created_at:string;updated_at:string;reviewed_by?:string|null;result_revision?:string|null;conflict?:unknown;current_node?:KnowledgeNode|null};
function nodeText(node:KnowledgeNode|null){return !node?'':node.type==='heading'?node.title:(node.show_key?node.key+'：':'')+node.value;}
export function proposalEditPayload(item:Proposal,draft:KnowledgeNode|null,draftRevision:number,editing:boolean,rebase=false){
 return {revision:editing?draftRevision:item.revision,proposed_node:editing?draft:item.proposed_node,...(rebase?{rebase:true}:{})};
}
export function ProposalCard({item,onChanged}:{item:Proposal;onChanged:()=>void}){
 const {session}=useAuth(),cap=useCapabilities();const [editing,setEditing]=useState(false),[draft,setDraft]=useState(item.proposed_node),[draftRevision,setDraftRevision]=useState(item.revision),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{const guard=(event:Event)=>{if(editing&&!equalValue(draft,item.proposed_node)&&!confirm('提案改稿尚未保存，确定放弃并切换身份吗？'))event.preventDefault();};window.addEventListener('wxq:before-role-change',guard);return()=>window.removeEventListener('wxq:before-role-change',guard);},[editing,draft,item.proposed_node]);
 const admin=session.role==='admin',own=session.username===item.author,pending=item.status==='pending';
 async function mutate(action:string,rebase=false){setBusy(true);setError('');try{await api('proposals/'+encodeURIComponent(item.id)+(action==='edit'?'':'/'+action),action==='edit'?'PUT':'POST',action==='edit'?proposalEditPayload(item,draft,draftRevision,editing,rebase):{revision:item.revision});setEditing(false);window.dispatchEvent(new Event('wxq:proposals-changed'));if(action==='approve')window.dispatchEvent(new Event('wxq:knowledge-saved'));onChanged();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <article className="proposal-card" aria-label={'提案 '+item.author}><header><strong>{item.author}</strong> · {item.note_title} · {pending?'暂存待确认':({approved:'已确认',rejected:'已拒绝',withdrawn:'已撤回'}[item.status]??item.status)}</header><DiffText before={nodeText(item.base_node)} after={nodeText(item.proposed_node)}/>{!!item.conflict&&<div role="alert">正式正文已变化，请核对当前正文后重新对齐。<pre>{nodeText(item.current_node??null)}</pre></div>}
 {editing&&draft&&<NodeFields node={draft} original={item.base_node??draft} onChange={setDraft}/>}
 {error&&<p role="alert">{error}</p>}{pending&&(admin||own)&&<div className="proposal-actions"><fieldset disabled={busy}>{item.kind!=='delete'&&(editing?<><button onClick={()=>void mutate('edit')}>保存改稿</button><button onClick={()=>setEditing(false)}>取消改稿</button></>:<button onClick={()=>{setDraft(item.proposed_node);setDraftRevision(item.revision);setEditing(true);}}>修改提案</button>)}{admin&&!!item.conflict&&<button onClick={()=>void mutate('edit',true)}>按当前正文重新对齐</button>}{admin?<><button disabled={!cap.editNotes||editing||!!item.conflict} onClick={()=>void mutate('approve')}>确认此条</button><button onClick={()=>void mutate('reject')}>拒绝此条</button></>:<button onClick={()=>void mutate('withdraw')}>撤回此条</button>}</fieldset></div>}</article>;
}
export function useProposals(noteId?:string){
 const {session}=useAuth();const key=[session.role,session.username,noteId].join('|');const [snapshot,setSnapshot]=useState<{key:string;items:Proposal[]}>({key:'',items:[]}),[error,setError]=useState('');
 const epoch=useRef(0),currentKey=useRef(key);currentKey.current=key;
 async function reload(){const requestEpoch=++epoch.current;if(session.role==='guest'){setSnapshot({key,items:[]});return;}try{const result=await api<{items:Proposal[]}>('proposals'+(noteId?'?note_id='+encodeURIComponent(noteId):''));if(requestEpoch!==epoch.current||currentKey.current!==key)return;setSnapshot({key,items:result.items});setError('');}catch(e){if(requestEpoch===epoch.current&&currentKey.current===key)setError((e as Error).message);}}
 useEffect(()=>{
  setSnapshot({key,items:[]});if(session.role==='guest')return;void reload();
  const changed=()=>void reload(),visible=()=>{if(document.visibilityState==='visible')void reload();};
  const timer=setInterval(changed,15000);
  window.addEventListener('wxq:proposals-changed',changed);window.addEventListener('wxq:knowledge-saved',changed);window.addEventListener('focus',changed);document.addEventListener('visibilitychange',visible);
  return()=>{epoch.current++;clearInterval(timer);window.removeEventListener('wxq:proposals-changed',changed);window.removeEventListener('wxq:knowledge-saved',changed);window.removeEventListener('focus',changed);document.removeEventListener('visibilitychange',visible);};
 },[noteId,session.role,session.username]);
 return {items:session.role==='guest'||snapshot.key!==key?[]:snapshot.items,error,reload};
}

export function ProposalOverlay({nodeId,items}:{nodeId:string;items:Proposal[]}){
 function insertionAnchor(item:Proposal){let anchor=item.after_id;const seen=new Set([item.id]);while(anchor){const previous=items.find(p=>p.kind==='insert'&&p.status==='pending'&&p.node_id===anchor);if(!previous)break;if(seen.has(previous.id))return item.section_id;seen.add(previous.id);anchor=previous.after_id;}return anchor??item.section_id;}
 return <>{items.filter(p=>p.status==='pending'&&(p.kind==='insert'?insertionAnchor(p)===nodeId:p.node_id===nodeId)).map(item=><ProposalCard key={item.id} item={item} onChanged={()=>{}}/>)}</>;
}

export function AccountControls({beforeChange}:{beforeChange:()=>boolean}){
 const {session,switchRole,logout}=useAuth();const [open,setOpen]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[author,setAuthor]=useState(''),[note,setNote]=useState(''),[status,setStatus]=useState('pending');
 const {items,reload,error:loadError}=useProposals();
 const names:Record<Role,string>={admin:'管理员',annotator:'编写员',guest:'访客'};
 const allowed=session.allowed_roles??((session.account_role??session.role)==='admin'?['admin','annotator']:[session.role]);
 function canChange(){return beforeChange()&&window.dispatchEvent(new Event('wxq:before-role-change',{cancelable:true}));}
 async function change(role:Role){if(!canChange())return;setBusy(true);try{await switchRole?.(role);setOpen(false);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <div className="account-controls"><span>{session.username??(session.mode==='local'?'本地':'访客')} · {names[session.role]}</span>{session.sync&&<small role="status">{session.sync.message??session.sync.state}</small>}{allowed.length>1&&<select aria-label="切换身份" disabled={busy} value={session.role} onChange={e=>void change(e.target.value as Role)}>{allowed.map(role=><option key={role} value={role}>{names[role]}</option>)}</select>}{session.role!=='guest'&&<><button onClick={()=>setOpen(!open)}>提案</button>{session.mode==='public'&&<button disabled={busy} onClick={()=>{if(canChange())void logout().catch(e=>setError(e.message));}}>退出登录</button>}</>}{error&&<span role="alert">{error}</span>}{open&&session.role!=='guest'&&<aside className="proposal-drawer" role="dialog" aria-label="提案审核"><header><strong>提案</strong><button onClick={()=>setOpen(false)}>关闭</button></header><label>状态<select value={status} onChange={e=>setStatus(e.target.value)}><option value="pending">待确认</option><option value="closed">已结束</option></select></label>{session.role==='admin'&&<label>作者<input value={author} onChange={e=>setAuthor(e.target.value)}/></label>}<label>笔记<input value={note} onChange={e=>setNote(e.target.value)}/></label>{loadError&&<p role="alert">{loadError}</p>}{items.filter(p=>(status==='pending'?p.status==='pending':p.status!=='pending')&&(!author||p.author.includes(author))&&(!note||p.note_title.includes(note))).map(item=><ProposalCard key={item.id} item={item} onChanged={()=>void reload()}/>)}{!items.length&&<p>暂无提案</p>}</aside>}</div>;
}
