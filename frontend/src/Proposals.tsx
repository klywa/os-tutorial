import {useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {useAuth,useCanEditNote,type Role} from './auth';
import {api} from './model';
import {equalValue} from './noteReviewModel';
import {DiffText} from './ReviewFields';
import ProposalDiffEditor from './ProposalDiffEditor';
import type {KnowledgeNode} from './types';
import {syncLabel} from './syncStatus';
import {useEditLocks,leaseRef,type Resource} from './editLocks';
type EvidenceLocation={source:string}&(
 {type:'document';paragraph_start:number;paragraph_end:number}|
 {type?:'video';start:number;end:number;frame?:string}
);
type EvidenceChange={claim_id:string;evidence:EvidenceLocation[];inference:boolean};
export type Proposal={id:string;note_id:string;note_title:string;author:string;kind:'insert'|'update'|'delete';node_id:string;section_id:string;after_id:string|null;base_node:KnowledgeNode|null;proposed_node:KnowledgeNode|null;revision:number;status:string;created_at:string;updated_at:string;reviewed_by?:string|null;result_revision?:string|null;conflict?:unknown;current_node?:KnowledgeNode|null;evidence_changes?:EvidenceChange[]};
function ProposalEvidence({changes}:{changes:EvidenceChange[]}){
 return <details><summary>证据 · {changes.reduce((total,change)=>total+change.evidence.length,0)} 处</summary>
  {changes.map(change=><section key={change.claim_id}>
   <p>{change.inference?'有据推导':'直接证据'} · 结论 {change.claim_id}</p>
   <ul>{change.evidence.map((location,index)=>{
    if(location.type==='document')return <li key={index}>{location.source} · 第 {location.paragraph_start}–{location.paragraph_end} 段</li>;
    const [video,part]=location.source.split(':p');
    return <li key={index}><a href={`https://www.bilibili.com/video/${encodeURIComponent(video)}/?p=${encodeURIComponent(part)}&t=${Math.floor(location.start)}`} target="_blank" rel="noreferrer">{location.source}</a> · {location.start}–{location.end} 秒{location.frame&&` · ${location.frame}`}</li>;
   })}</ul>
  </section>)}
 </details>;
}
function nodeText(node:KnowledgeNode|null){return !node?'':node.type==='heading'?node.title:(node.show_key?node.key+'：':'')+node.value;}
export function proposalEditPayload(item:Proposal,draft:KnowledgeNode|null,draftRevision:number,editing:boolean,rebase=false){
 return {revision:editing?draftRevision:item.revision,proposed_node:editing?draft:item.proposed_node,...(rebase?{rebase:true}:{})};
}
export function ProposalCard({item:incoming,onChanged,onLocate,locating=false,onDraft}:{item:Proposal;onChanged:()=>void;onLocate?:(item:Proposal)=>void;locating?:boolean;onDraft?:(id:string,active:boolean)=>void}){
 const {session}=useAuth();
 const [saved,setSaved]=useState<Proposal|null>(null);
 const item=saved&&saved.revision>incoming.revision?saved:incoming;
 const [edit,setEdit]=useState<{base:KnowledgeNode;node:KnowledgeNode;revision:number;confirmed:boolean}|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[acquiring,setAcquiring]=useState(false),[composing,setComposing]=useState(false);
 const pendingRequest=useRef(false), acquiringLock=useRef(false),releasingLock=useRef(false);
 const admin=session.role==='admin',own=session.role==='annotator'&&session.username===item.author,pending=item.status==='pending';
 const canEdit=pending&&(admin||own)&&item.kind!=='delete'&&!!item.proposed_node;
 const dirty=!!edit&&!equalValue(edit.node,edit.base);
 const stale=!!edit&&edit.revision!==item.revision;
 const noteEditable=useCanEditNote(item.note_id);
 const target:Resource=item.kind==='insert'?{kind:'slot',section_id:item.section_id,left_id:item.after_id??item.section_id}:{kind:'entry',id:item.node_id};
 const locks=useEditLocks(item.note_id,()=>{setComposing(false);setError('编辑权限已暂停，当前输入已保留。');});
 const lease=locks.get(target),owner=locks.owner(target);
 const blocked=busy||acquiring||locating;
 const confirmed=!item.evidence_changes||!!edit?.confirmed;
 const canSave=dirty&&!stale&&!!lease&&locks.online&&!composing&&confirmed&&(!item.evidence_changes||!item.conflict);

 useEffect(()=>{
  if(!dirty&&!composing)return;
  onDraft?.(item.id,true);
  return()=>onDraft?.(item.id,false);
 },[item.id,dirty,composing,onDraft]);
 useEffect(()=>{
  const guard=(event:Event)=>{
   if(busy||dirty||composing){
    event.preventDefault();
    setError(busy?'正在保存，请稍候。':'请先保存或撤销改动。');
   }
  };
  const events=['wxq:before-role-change','wxq:before-proposal-locate','wxq:before-proposal-view-change'];
  for(const event of events)window.addEventListener(event,guard);
  return()=>{for(const event of events)window.removeEventListener(event,guard);};
 },[busy,dirty,composing]);

 async function reset(){
  releasingLock.current=true;
  setEdit(null);setError('');setComposing(false);
  try{await locks.release();}finally{releasingLock.current=false;}
 }
 async function begin(rebase=false,takeover=false){
  const node=item.proposed_node;
  if(!canEdit||!node||acquiringLock.current||pendingRequest.current||releasingLock.current||stale||(!rebase&&lease))return;
  if(item.evidence_changes&&item.conflict)return;
  acquiringLock.current=true;setAcquiring(true);setError('');
  try{
   const acquired=await locks.acquire(target,admin&&(rebase||takeover));
   if(rebase){await mutate('edit',true,acquired);return;}
   setEdit(current=>current??{base:node,node,revision:item.revision,confirmed:false});
  }catch(e){setError((e as Error).message);}
  finally{acquiringLock.current=false;setAcquiring(false);}
 }
 async function mutate(action:string,rebase=false,acquired=lease){
  if(pendingRequest.current)return;
  pendingRequest.current=true;setBusy(true);setError('');
  try{
   const withEdit=action==='edit'||(action==='approve'&&dirty);
   const data=withEdit?{
    ...proposalEditPayload(item,edit?.node??null,edit?.revision??item.revision,!!edit,rebase),
    client_id:locks.clientId,lease:acquired?leaseRef(acquired):undefined,
    ...(item.evidence_changes&&edit?.confirmed?{evidence_changes:item.evidence_changes}:{})
   }:{revision:item.revision};
   const result=await api<Proposal>('proposals/'+encodeURIComponent(item.id)+(action==='edit'?'':'/'+action),action==='edit'?'PUT':'POST',data);
   setSaved(result);
   await reset();
   window.dispatchEvent(new Event('wxq:proposals-changed'));
   if(action==='approve')window.dispatchEvent(new Event('wxq:knowledge-saved'));
   onChanged();
  }catch(e){setError((e as Error).message);}
  finally{pendingRequest.current=false;setBusy(false);}
 }

 const node=edit?.node??item.proposed_node;
 const readOnly=!edit||!lease||blocked||stale;
 function changeNode(next:KnowledgeNode){
  if(!readOnly)setEdit(current=>current&&({...current,node:next,confirmed:false}));
 }
 const editor=canEdit&&node&&<div className="proposal-inline-editor" onFocusCapture={()=>{if(!edit)void begin();}}>
  {node.type==='heading'?<input aria-label="章节标题" value={node.title} readOnly={readOnly}
    onCompositionStart={()=>setComposing(true)} onCompositionEnd={()=>setComposing(false)}
    onChange={e=>changeNode({...node,title:e.target.value})}/>:<>
   <div className="proposal-name-row">
    <label><input type="checkbox" checked={node.show_key} disabled={readOnly}
     onChange={e=>{const show_key=e.target.checked;const base=edit?.base;changeNode({...node,show_key,key:show_key?(base?.type==='entry'&&base.show_key?base.key:'正文'):'正文'});}}/>显示名称</label>
    {node.show_key&&<input aria-label="名称" value={node.key} readOnly={readOnly}
     onCompositionStart={()=>setComposing(true)} onCompositionEnd={()=>setComposing(false)}
     onChange={e=>changeNode({...node,key:e.target.value})}/>}
   </div>
   <ProposalDiffEditor before={item.base_node?.type==='entry'?item.base_node.value:''}
    value={node.value} readOnly={readOnly} onComposing={setComposing}
    onChange={value=>changeNode({...node,value})}/>
  </>}
  {acquiring&&<p role="status">正在获取编辑权限…</p>}
  {owner&&!lease&&<p className="lock-hint">{owner.owner} 正在编辑 · 已锁定</p>}
  {!lease&&!acquiring&&!stale&&(!!edit||!!error||!!owner&&admin)&&!(item.evidence_changes&&item.conflict)&&
   <button type="button" onClick={()=>void begin(false,!!owner)}>{owner&&admin?'接管编辑':'重新取得编辑权限'}</button>}
 </div>;

 return <article className="proposal-card" data-proposal-id={item.id} aria-label={'提案 '+item.author} aria-busy={blocked}>
  <header><strong>{item.author}</strong> · {item.note_title} · {pending?'暂存待确认':({approved:'已确认',rejected:'已拒绝',withdrawn:'已撤回'}[item.status]??item.status)}</header>
  <DiffText before={nodeText(item.base_node)} after={nodeText(node)} composing={composing} split={pending||dirty} editor={editor}/>
  {item.evidence_changes&&<ProposalEvidence changes={item.evidence_changes}/>}
  {item.evidence_changes&&dirty&&<label className="inline">
   <input type="checkbox" checked={!!edit?.confirmed} disabled={blocked||stale||composing}
    onChange={e=>{const checked=e.target.checked;setEdit(current=>current&&({...current,confirmed:checked}));}}/> 我已核对证据，仍支持本次改稿
  </label>}
  {busy&&<p role="status" aria-live="polite">正在保存…</p>}
  {stale&&<p role="alert">这条提案已在别处更新。当前输入仍保留，请核对后撤销本次改动，再按最新提案编辑。</p>}
  {!!item.conflict&&<div role="alert">{item.evidence_changes?'正式正文或证据已变化，请重新提交提案。':'正式正文已变化，请核对当前正文后重新对齐。'}<pre>{nodeText(item.current_node??null)}</pre></div>}
  {onLocate&&<div className="proposal-location-action"><button type="button" disabled={blocked} onClick={()=>onLocate(item)}>{locating?'正在定位…':'定位到原文'}</button></div>}
  {error&&<p role="alert">{error}</p>}
  {!pending&&dirty&&<button type="button" onClick={()=>void reset()}>撤销改动</button>}
  {pending&&(admin||own)&&<div className="proposal-actions"><fieldset disabled={blocked}>
   {canEdit&&dirty&&<button disabled={!canSave} onClick={()=>void mutate('edit')}>保存改稿</button>}
   {(dirty||stale)&&<button disabled={composing} onClick={()=>void reset()}>撤销改动</button>}
   {admin&&!item.evidence_changes&&!!item.conflict&&<button disabled={stale||composing} onClick={()=>void begin(true)}>按当前正文重新对齐</button>}
   {admin?<><button disabled={!noteEditable||!!item.conflict||stale||composing||(dirty&&!canSave)} onClick={()=>void mutate('approve')}>{busy?'正在保存…':'确认此条'}</button>
    <button disabled={dirty||composing} onClick={()=>void mutate('reject')}>拒绝此条</button></>:
    <button disabled={dirty||composing} onClick={()=>void mutate('withdraw')}>撤回此条</button>}
  </fieldset></div>}
 </article>;
}
export function useProposals(noteId?:string){
 const {session}=useAuth();const key=[session.role,session.username,noteId].join('|');const [snapshot,setSnapshot]=useState<{key:string;items:Proposal[]}>({key:'',items:[]}),[error,setError]=useState('');
 const epoch=useRef(0),currentKey=useRef(key);currentKey.current=key;
 async function reload(){const requestEpoch=++epoch.current;if(!['admin','annotator'].includes(session.role)){setSnapshot({key,items:[]});return;}try{const result=await api<{items:Proposal[]}>('proposals'+(noteId?'?note_id='+encodeURIComponent(noteId):''));if(requestEpoch!==epoch.current||currentKey.current!==key)return;setSnapshot({key,items:result.items});setError('');}catch(e){if(requestEpoch===epoch.current&&currentKey.current===key)setError((e as Error).message);}}
 useEffect(()=>{
  setSnapshot({key,items:[]});if(!['admin','annotator'].includes(session.role))return;void reload();
  const changed=()=>void reload(),visible=()=>{if(document.visibilityState==='visible')void reload();};
  const timer=setInterval(changed,15000);
  window.addEventListener('wxq:proposals-changed',changed);window.addEventListener('wxq:knowledge-saved',changed);window.addEventListener('focus',changed);document.addEventListener('visibilitychange',visible);
  return()=>{epoch.current++;clearInterval(timer);window.removeEventListener('wxq:proposals-changed',changed);window.removeEventListener('wxq:knowledge-saved',changed);window.removeEventListener('focus',changed);document.removeEventListener('visibilitychange',visible);};
 },[noteId,session.role,session.username]);
 return {items:!['admin','annotator'].includes(session.role)||snapshot.key!==key?[]:snapshot.items,error,reload};
}

function useProposalDrafts(){
 const [draftIds,setDraftIds]=useState<Set<string>>(()=>new Set());
 const onDraft=useCallback((id:string,active:boolean)=>setDraftIds(previous=>{
  if(previous.has(id)===active)return previous;
  const next=new Set(previous);
  if(active)next.add(id);else next.delete(id);
  return next;
 }),[]);
 return {draftIds,onDraft};
}

export function ProposalOverlay({nodeId,items}:{nodeId:string;items:Proposal[]}){
 const {draftIds,onDraft}=useProposalDrafts();
 function insertionAnchor(item:Proposal){let anchor=item.after_id;const seen=new Set([item.id]);while(anchor){const previous=items.find(p=>p.kind==='insert'&&p.status==='pending'&&p.node_id===anchor);if(!previous)break;if(seen.has(previous.id))return item.section_id;seen.add(previous.id);anchor=previous.after_id;}return anchor??item.section_id;}
 return <>{items.filter(p=>draftIds.has(p.id)||(p.status==='pending'&&(p.kind==='insert'?insertionAnchor(p)===nodeId:p.node_id===nodeId))).map(item=><ProposalCard key={item.id} item={item} onDraft={onDraft} onChanged={()=>{}}/>)}</>;
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
 async function locate(item:Proposal){if(!onLocate||locating||locateBusy.current)return;setError('');if(!window.dispatchEvent(new Event('wxq:before-proposal-locate',{cancelable:true}))){setError('提案改稿尚未保存，请先保存或撤销改动后定位。');return;}locateBusy.current=true;setLocating(item.id);try{if(await onLocate(item)){setOpen(false);setAccountOpen(false);}else setError('定位已取消，请先保存或取消当前修改。');}catch(e){setError('无法定位：'+(e as Error).message);}finally{locateBusy.current=false;setLocating('');}}
 const {items,reload,error:loadError}=useProposals();
 const {draftIds,onDraft}=useProposalDrafts();
 useLayoutEffect(()=>{if(open&&items.length&&drawer.current)drawer.current.scrollTop=panel.scrollTop.current;},[open,items.length]);
 const [accountOpen,setAccountOpen]=useState(false);const account=useRef<HTMLDivElement>(null);
 useEffect(()=>{const close=(e:Event)=>{if(e instanceof KeyboardEvent?e.key==='Escape':!account.current?.contains(e.target as Node))setAccountOpen(false);};document.addEventListener('pointerdown',close);document.addEventListener('keydown',close);return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',close);};},[]);
 const names:Record<Role,string>={admin:'管理员',annotator:'编写员',guest:'访客',viewer:'浏览者'};
 const allowed=session.allowed_roles??((session.account_role??session.role)==='admin'?['admin','annotator','viewer']:[session.role]);
 function canChange(){return beforeChange()&&window.dispatchEvent(new Event('wxq:before-role-change',{cancelable:true}));}
 function canChangeView(){return window.dispatchEvent(new Event('wxq:before-proposal-view-change',{cancelable:true}));}
 async function change(role:Role){if(!canChange())return;setBusy(true);try{await switchRole?.(role);setOpen(false);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function retrySync(){setRetrying(true);setError('');try{await api('admin/sync/retry','POST',{});}catch(e){setError((e as Error).message);}finally{setRetrying(false);}}
 if(session.role==='guest')return <div className="account-controls"><button className="login-trigger" onClick={openLogin}>登录</button></div>;
 return <div ref={account} className="account-controls"><button className="mobile-account-trigger" aria-expanded={accountOpen} aria-label="账号菜单" onClick={()=>setAccountOpen(v=>!v)}>{session.username??'本地'} · {names[session.role]} ▾</button><div className={'account-items '+(accountOpen?'is-open':'')}><span className="account-name" title={session.username??undefined}>{session.username??(session.mode==='local'?'本地':'访客')} · {names[session.role]}</span>{session.sync&&<small role="status" aria-live="polite" title={syncLabel(session.sync)}>{syncLabel(session.sync)}</small>}{session.role==="admin"&&session.sync&&(session.sync.state==="conflict"||session.sync.state==="pending"&&session.sync.phase==="waiting-retry")&&<button disabled={retrying||busy} onClick={()=>void retrySync()}>{retrying?"正在排队…":"重试同步"}</button>}{allowed.length>1&&<select aria-label="切换身份" disabled={busy} value={session.role} onChange={e=>void change(e.target.value as Role)}>{allowed.map(role=><option key={role} value={role}>{names[role]}</option>)}</select>}{<>{session.role!=='viewer'&&<button onClick={()=>{if(!open||canChangeView())setOpen(!open);}}>提案</button>}{session.mode==='public'&&<button disabled={busy} onClick={()=>{if(canChange())void logout().catch(e=>setError(e.message));}}>退出登录</button>}</>}{error&&!open&&<span className="account-error" role="alert">{error}</span>}</div>{open&&<aside ref={drawer} onScroll={e=>{panel.scrollTop.current=e.currentTarget.scrollTop;}} className="proposal-drawer" role="dialog" aria-label="提案审核"><header><strong>提案</strong><button onClick={()=>{if(canChangeView())setOpen(false);}}>关闭</button></header><label>状态<select aria-label="状态" value={status} onChange={e=>{if(!canChangeView())return;panel.scrollTop.current=0;setStatus(e.target.value);}}><option value="pending">待确认</option><option value="closed">已结束</option></select></label>{session.role==='admin'&&<label>作者<input aria-label="作者" value={author} onChange={e=>{if(!canChangeView())return;panel.scrollTop.current=0;setAuthor(e.target.value);}}/></label>}<label>笔记<input aria-label="笔记" value={note} onChange={e=>{if(!canChangeView())return;panel.scrollTop.current=0;setNote(e.target.value);}}/></label>{error&&<p role="alert">{error}</p>}{loadError&&<p role="alert">{loadError}</p>}{items.filter(p=>draftIds.has(p.id)||(status==='pending'?p.status==='pending':p.status!=='pending')&&(!author||p.author.includes(author))&&(!note||p.note_title.includes(note))).map(item=><ProposalCard key={item.id} item={item} onDraft={onDraft} onChanged={()=>void reload()} onLocate={onLocate?item=>void locate(item):undefined} locating={!!locating}/>)}{!items.length&&<p>暂无提案</p>}</aside>}</div>;
}
