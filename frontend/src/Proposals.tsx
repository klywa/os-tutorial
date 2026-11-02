import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {useAuth,useCapabilities,type Role} from './auth';
import {api} from './model';
import {equalValue} from './noteReviewModel';
import {DiffText,NodeFields} from './ReviewFields';
import type {KnowledgeNode} from './types';
import {syncLabel} from './syncStatus';
import {useEditLocks,leaseRef,type Resource} from './editLocks';
export type Proposal={id:string;note_id:string;note_title:string;author:string;kind:'insert'|'update'|'delete';node_id:string;section_id:string;after_id:string|null;base_node:KnowledgeNode|null;proposed_node:KnowledgeNode|null;revision:number;status:string;created_at:string;updated_at:string;reviewed_by?:string|null;result_revision?:string|null;conflict?:unknown;current_node?:KnowledgeNode|null};
function nodeText(node:KnowledgeNode|null){return !node?'':node.type==='heading'?node.title:(node.show_key?node.key+'：':'')+node.value;}
export function proposalEditPayload(item:Proposal,draft:KnowledgeNode|null,draftRevision:number,editing:boolean,rebase=false){
 return {revision:editing?draftRevision:item.revision,proposed_node:editing?draft:item.proposed_node,...(rebase?{rebase:true}:{})};
}
export function ProposalCard({item,onChanged,onLocate,locating=false}:{item:Proposal;onChanged:()=>void;onLocate?:(item:Proposal)=>void;locating?:boolean}){
 const {session}=useAuth(),cap=useCapabilities();const [editing,setEditing]=useState(false),[draft,setDraft]=useState(item.proposed_node),[draftRevision,setDraftRevision]=useState(item.revision),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{const guard=(event:Event)=>{if(editing&&!equalValue(draft,item.proposed_node)&&!confirm('提案改稿尚未保存，确定放弃并切换身份吗？'))event.preventDefault();};window.addEventListener('wxq:before-role-change',guard);return()=>window.removeEventListener('wxq:before-role-change',guard);},[editing,draft,item.proposed_node]);
 useEffect(()=>{const guard=(event:Event)=>{if(editing&&!equalValue(draft,item.proposed_node)){event.preventDefault();setError('提案改稿尚未保存，请先保存或取消后定位。');}};window.addEventListener('wxq:before-proposal-locate',guard);return()=>window.removeEventListener('wxq:before-proposal-locate',guard);},[editing,draft,item.proposed_node]);
 const target:Resource=item.kind==='insert'?{kind:'slot',section_id:item.section_id,left_id:item.after_id??item.section_id}:{kind:'entry',id:item.node_id};
 const locks=useEditLocks(item.note_id,(_lease,reason)=>{if(reason==='admin_takeover'){setDraft(item.proposed_node);setEditing(false);setError('管理员已接管或确认此条，未提交改稿已清空。');}else setError('编辑权限已暂停，草稿保留。请重新取得权限。');});
 const lease=locks.get(target),owner=locks.owner(target);
 async function begin(rebase=false){setError('');try{const next=await locks.acquire(target,session.role==='admin');if(rebase){await mutate('edit',true,next);return;}if(!editing){setDraft(item.proposed_node);setDraftRevision(item.revision);}setEditing(true);}catch(e){setError((e as Error).message);}}
 const admin=session.role==='admin',own=session.username===item.author,pending=item.status==='pending';
 async function mutate(action:string,rebase=false,acquired=lease){setBusy(true);setError('');try{await api('proposals/'+encodeURIComponent(item.id)+(action==='edit'?'':'/'+action),action==='edit'?'PUT':'POST',action==='edit'?{...proposalEditPayload(item,draft,draftRevision,editing,rebase),client_id:locks.clientId,lease:acquired?leaseRef(acquired):undefined}:{revision:item.revision});void locks.release();setEditing(false);window.dispatchEvent(new Event('wxq:proposals-changed'));if(action==='approve')window.dispatchEvent(new Event('wxq:knowledge-saved'));onChanged();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <article className="proposal-card" data-proposal-id={item.id} aria-label={'提案 '+item.author} aria-busy={busy}><header><strong>{item.author}</strong> · {item.note_title} · {pending?'暂存待确认':({approved:'已确认',rejected:'已拒绝',withdrawn:'已撤回'}[item.status]??item.status)}</header><DiffText before={nodeText(item.base_node)} after={nodeText(item.proposed_node)}/>{busy&&<p role="status" aria-live="polite">正在保存…</p>}{!!item.conflict&&<div role="alert">正式正文已变化，请核对当前正文后重新对齐。<pre>{nodeText(item.current_node??null)}</pre></div>}
 {editing&&draft&&<fieldset disabled={!lease||!locks.online||busy}><NodeFields node={draft} original={item.base_node??draft} onChange={setDraft}/></fieldset>}{owner&&<p className="lock-hint">{owner.owner} 正在编辑 · 已锁定</p>}{editing&&!lease&&<button onClick={()=>void begin()}>重新取得编辑权限</button>}
 {onLocate&&<div className="proposal-location-action"><button type="button" disabled={busy||locating} onClick={()=>onLocate(item)}>{locating?'正在定位…':'定位到原文'}</button></div>}{error&&<p role="alert">{error}</p>}{pending&&(admin||own)&&<div className="proposal-actions"><fieldset disabled={busy||locating}>{item.kind!=='delete'&&(editing?<><button disabled={!lease||!locks.online} onClick={()=>void mutate('edit')}>保存改稿</button><button onClick={()=>{void locks.release();setEditing(false);}}>取消改稿</button></>:<button disabled={!!owner&&!admin} onClick={()=>void begin()}>{owner&&admin?'接管改稿':'修改提案'}</button>)}{admin&&!!item.conflict&&<button onClick={()=>void begin(true)}>按当前正文重新对齐</button>}{admin?<><button disabled={!cap.editNotes||editing||!!item.conflict} onClick={()=>void mutate('approve')}>{busy?'正在保存…':'确认此条'}</button><button onClick={()=>void mutate('reject')}>拒绝此条</button></>:<button onClick={()=>void mutate('withdraw')}>撤回此条</button>}</fieldset></div>}</article>;
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

export function useProposalPanelState(){
 const [open,setOpen]=useState(false),[author,setAuthor]=useState(''),[note,setNote]=useState(''),[status,setStatus]=useState('pending'),[locating,setLocating]=useState('');
 const scrollTop=useRef(0);
 return {open,setOpen,author,setAuthor,note,setNote,status,setStatus,locating,setLocating,scrollTop};
}
export function AccountControls({beforeChange,onLocate,panel:externalPanel}:{beforeChange:()=>boolean;onLocate?:(item:Proposal)=>Promise<boolean>;panel?:ReturnType<typeof useProposalPanelState>}){
 const {session,switchRole,logout,openLogin}=useAuth();const [error,setError]=useState(''),[busy,setBusy]=useState(false),[retrying,setRetrying]=useState(false);
 const localPanel=useProposalPanelState(),panel=externalPanel??localPanel;const {open,setOpen,author,setAuthor,note,setNote,status,setStatus,locating,setLocating}=panel;
 const drawer=useRef<HTMLElement>(null),locateBusy=useRef(false);
 async function locate(item:Proposal){if(!onLocate||locating||locateBusy.current)return;setError('');if(!window.dispatchEvent(new Event('wxq:before-proposal-locate',{cancelable:true}))){setError('提案改稿尚未保存，请先保存或取消后定位。');return;}locateBusy.current=true;setLocating(item.id);try{if(await onLocate(item)){setOpen(false);setAccountOpen(false);}else setError('定位已取消，请先保存或取消当前修改。');}catch(e){setError('无法定位：'+(e as Error).message);}finally{locateBusy.current=false;setLocating('');}}
 const {items,reload,error:loadError}=useProposals();
 useLayoutEffect(()=>{if(open&&items.length&&drawer.current)drawer.current.scrollTop=panel.scrollTop.current;},[open,items.length]);
 const [accountOpen,setAccountOpen]=useState(false);const account=useRef<HTMLDivElement>(null);
 useEffect(()=>{const close=(e:Event)=>{if(e instanceof KeyboardEvent?e.key==='Escape':!account.current?.contains(e.target as Node))setAccountOpen(false);};document.addEventListener('pointerdown',close);document.addEventListener('keydown',close);return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',close);};},[]);
 const names:Record<Role,string>={admin:'管理员',annotator:'编写员',guest:'访客'};
 const allowed=session.allowed_roles??((session.account_role??session.role)==='admin'?['admin','annotator']:[session.role]);
 function canChange(){return beforeChange()&&window.dispatchEvent(new Event('wxq:before-role-change',{cancelable:true}));}
 async function change(role:Role){if(!canChange())return;setBusy(true);try{await switchRole?.(role);setOpen(false);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function retrySync(){setRetrying(true);setError('');try{await api('admin/sync/retry','POST',{});}catch(e){setError((e as Error).message);}finally{setRetrying(false);}}
 if(session.role==='guest')return <div className="account-controls"><button className="login-trigger" onClick={openLogin}>登录</button></div>;
 return <div ref={account} className="account-controls"><button className="mobile-account-trigger" aria-expanded={accountOpen} aria-label="账号菜单" onClick={()=>setAccountOpen(v=>!v)}>{session.username??'本地'} · {names[session.role]} ▾</button><div className={'account-items '+(accountOpen?'is-open':'')}><span className="account-name" title={session.username??undefined}>{session.username??(session.mode==='local'?'本地':'访客')} · {names[session.role]}</span>{session.sync&&<small role="status" aria-live="polite" title={syncLabel(session.sync)}>{syncLabel(session.sync)}</small>}{session.role==="admin"&&session.sync&&(session.sync.state==="conflict"||session.sync.state==="pending"&&session.sync.phase==="waiting-retry")&&<button disabled={retrying||busy} onClick={()=>void retrySync()}>{retrying?"正在排队…":"重试同步"}</button>}{allowed.length>1&&<select aria-label="切换身份" disabled={busy} value={session.role} onChange={e=>void change(e.target.value as Role)}>{allowed.map(role=><option key={role} value={role}>{names[role]}</option>)}</select>}{<><button onClick={()=>setOpen(!open)}>提案</button>{session.mode==='public'&&<button disabled={busy} onClick={()=>{if(canChange())void logout().catch(e=>setError(e.message));}}>退出登录</button>}</>}{error&&!open&&<span className="account-error" role="alert">{error}</span>}</div>{open&&<aside ref={drawer} onScroll={e=>{panel.scrollTop.current=e.currentTarget.scrollTop;}} className="proposal-drawer" role="dialog" aria-label="提案审核"><header><strong>提案</strong><button onClick={()=>setOpen(false)}>关闭</button></header><label>状态<select aria-label="状态" value={status} onChange={e=>{panel.scrollTop.current=0;setStatus(e.target.value);}}><option value="pending">待确认</option><option value="closed">已结束</option></select></label>{session.role==='admin'&&<label>作者<input aria-label="作者" value={author} onChange={e=>{panel.scrollTop.current=0;setAuthor(e.target.value);}}/></label>}<label>笔记<input aria-label="笔记" value={note} onChange={e=>{panel.scrollTop.current=0;setNote(e.target.value);}}/></label>{error&&<p role="alert">{error}</p>}{loadError&&<p role="alert">{loadError}</p>}{items.filter(p=>(status==='pending'?p.status==='pending':p.status!=='pending')&&(!author||p.author.includes(author))&&(!note||p.note_title.includes(note))).map(item=><ProposalCard key={item.id} item={item} onChanged={()=>void reload()} onLocate={onLocate?item=>void locate(item):undefined} locating={!!locating}/>)}{!items.length&&<p>暂无提案</p>}</aside>}</div>;
}
