import {useProposals,type Proposal} from './Proposals';
import {useCapabilities,useCanEditNote} from './auth';
import {useEditLocks,leaseRef,type Resource,type Lease} from './editLocks';
import {createContext,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {api} from './model';
import {equalValue,scopeNodes} from './noteReviewModel';
import {NodeFields} from './ReviewFields';
import ReviewComments from './ReviewComments';
import ReviewHistory from './ReviewHistory';
import './noteReview.css';

export type Annotation={id:string;note_id:string;node_id:string;text:string;status:'open'|'resolved';revision:string;created_at:string;result?:string;result_revision?:string;anchor_state:'current'|'changed'|'missing';target:KnowledgeNode[]};
type Draft={surface?:string;id:string;base:Note;body:KnowledgeDocument};
type Review={canSave:boolean;proposals:Proposal[];proposing:boolean;legacyReviews:boolean;readOnly?:boolean;note:Note;locks:ReturnType<typeof useEditLocks>;loss:{lease:Lease;reason:string;at:number}[];draft:Draft|null;dirty:boolean;busy:boolean;uncertain:boolean;error:string;comments:Annotation[];commentNode:string|null;
 startEdit:(id:string,surface?:string)=>void;startComment:(id:string)=>void;openHistory:()=>void;updateNodes:(nodes:KnowledgeNode[],changed:boolean)=>void;
 cancel:()=>void;save:(changes?:unknown[])=>Promise<void>;warn:()=>void;reloadComments:()=>Promise<void>;setExtraDirty:(dirty:boolean)=>void;closeComments:()=>void};
const Context=createContext<Review|null>(null);
export const useReview=()=>useContext(Context);
export function ReviewProvider({note,children,onSaved,onDirty,externalDirty=false,readOnly=false}:{note?:Note;children:ReactNode;onSaved:(note:Note)=>void;onDirty:(dirty:boolean)=>void;externalDirty?:boolean;readOnly?:boolean}){
 const {reviews,inlineEdit,proposeNotes}=useCapabilities();
 const editNotes=useCanEditNote(note?.id);
 readOnly=readOnly||(!proposeNotes&&!editNotes);
 const {items:proposals}=useProposals(note?.id);
 const [loss,setLoss]=useState<{lease:Lease;reason:string;at:number}[]>([]);
 const locks=useEditLocks(note?.id,(lease,reason)=>setLoss(rows=>[...rows,{lease,reason,at:Date.now()}]));
 const requestRef=useRef<{note_id:string;client_id:string;request_id:string;changes:unknown[]}|null>(null);
 const [uncertain,setUncertain]=useState(false);
 const [draft,setDraft]=useState<Draft|null>(null),[extraDirty,setExtra]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [comments,setComments]=useState<Annotation[]>([]),[commentNode,setCommentNode]=useState<string|null>(null),[history,setHistory]=useState(false);
 const pendingNodes=useRef<KnowledgeNode[]>([]),dirtyRef=useRef(false),savingRef=useRef(false);
 const [inlineDirty,setInlineDirty]=useState(false);
 const dirty=inlineDirty||extraDirty;
 async function reloadComments(){if(reviews&&note)setComments(await api<Annotation[]>('annotations?note_id='+encodeURIComponent(note.id)));}
 useEffect(()=>{let live=true;if(reviews&&note)void api<Annotation[]>('annotations?note_id='+encodeURIComponent(note.id)).then(rows=>{if(live)setComments(rows);}).catch(e=>{if(live)setError('批注载入失败：'+e.message);});return()=>{live=false;};},[note?.id,note?.revision,reviews]);
 if(!inlineEdit||!note?.document)return <>{children}</>;
 function warn(){if(!savingRef.current)setError('修改未保存，请保存或取消');}
 function guard(){if(readOnly){setError('请先确认最新版本后编辑');return false;}if(dirty||externalDirty){warn();return false;}setError('');return true;}
 function changeDirty(value:boolean){setExtra(value);if(!value&&!inlineDirty)setError(error=>error==='修改未保存，请保存或取消'?'':error);onDirty(value||inlineDirty);}
 const review:Review={canSave:!readOnly&&(proposeNotes||editNotes),proposals,proposing:proposeNotes,legacyReviews:reviews,readOnly,note,locks,loss,draft,dirty,busy,uncertain,error,comments,commentNode,
  startEdit:(id,surface)=>{if(!guard())return;setCommentNode(null);pendingNodes.current=scopeNodes(note.document!,id);dirtyRef.current=false;setInlineDirty(false);setDraft({id,surface,base:note,body:note.document!});},
  startComment:id=>{if(!guard())return;setDraft(null);setCommentNode(id);},
  openHistory:()=>{if(!guard())return;setDraft(null);setCommentNode(null);setHistory(true);},
  updateNodes:(nodes,changed)=>{if(!draft)return;pendingNodes.current=nodes;if(changed!==dirtyRef.current){dirtyRef.current=changed;setInlineDirty(changed);onDirty(changed||extraDirty);}},
  cancel:()=>{setUncertain(false);requestRef.current=null;void locks.release();setDraft(null);setInlineDirty(false);dirtyRef.current=false;setError('');onDirty(extraDirty);},
  save:async(changes)=>{
   if(!draft||savingRef.current)return;
   if(readOnly||(!proposeNotes&&!editNotes)){setError('当前笔记暂停编辑，草稿已保留');return;}
   const replay=!changes&&requestRef.current;
   if(!replay&&(readOnly||(!proposeNotes&&!editNotes)||!locks.online)){setError('请恢复连接并确认最新版本后保存，草稿已保留');return;}
   if(!replay&&!changes?.length)return;
   if(!replay)requestRef.current={note_id:note.id,client_id:locks.clientId,request_id:crypto.randomUUID(),changes:changes!};
   const payload=requestRef.current!;savingRef.current=true;setBusy(true);setError('');
   try{const saved=proposeNotes?null:await api<Note>('notes/'+encodeURIComponent(note.id)+'/entries','PUT',payload);
    if(proposeNotes){await api('proposals','POST',payload);window.dispatchEvent(new Event('wxq:proposals-changed'));}
    requestRef.current=null;setUncertain(false);void locks.release();setDraft(null);setInlineDirty(false);dirtyRef.current=false;setError('');onDirty(false);if(saved)onSaved(saved);
   }catch(e){const status=(e as Error&{status?:number}).status;const unknown=!status||status>=500;setUncertain(unknown);if(!unknown)requestRef.current=null;setError((e as Error).message+(unknown?'；保存结果尚未确认，请重试核对。':'；草稿已保留。'));}
   finally{savingRef.current=false;setBusy(false);}
  },
  warn,reloadComments,setExtraDirty:changeDirty,closeComments:()=>{setCommentNode(null);setExtra(false);onDirty(false);}};
 return <Context.Provider value={review}>{children}{error&&!draft&&<div className="review-notice" role="alert">{error}<button onClick={()=>setError('')}>关闭提示</button></div>}
 {commentNode&&<ReviewComments review={review}/>}
 {history&&<ReviewHistory readOnly={readOnly} note={note} onDirty={changeDirty} onSaved={saved=>{setHistory(false);setExtra(false);setError('');onDirty(false);if(saved)onSaved(saved);}} onClose={()=>{setHistory(false);setExtra(false);onDirty(false);}}/>}
 </Context.Provider>;
}
export function NodeActions({node,surface}:{node:KnowledgeNode;surface?:string}){
 const review=useReview();if(!review)return null;
 const title=node.type==='heading'?node.title:node.show_key?node.key:'正文';
 const owner=node.type==='entry'?review.locks.owner({kind:'entry',id:node.id}):undefined;
 const count=review.comments.filter(c=>c.node_id===node.id&&c.status==='open').length;
 return <span className="node-review-actions"><button type="button" disabled={review.readOnly||review.busy||!!owner&&review.proposing} aria-label={(node.type==='heading'?'编辑章节：':'编辑段落：')+title} onClick={()=>review.startEdit(node.id,surface)}>{owner&&!review.proposing?'接管编辑':'编辑'}</button>{owner&&<small className="lock-hint">{owner.owner} 正在编辑 · 已锁定</small>}{review.legacyReviews&&<button type="button" aria-label={'批注：'+title} onClick={()=>review.startComment(node.id)}>批注{count>0&&<span className="annotation-count">{count}</span>}</button>}</span>;
}
export function HistoryButton(){const review=useReview();return review?.legacyReviews?<><button onClick={review.openHistory}>历史版本</button><button onClick={()=>review.startComment('*')}>全部批注{review.comments.some(c=>c.status==='open')&&`（${review.comments.filter(c=>c.status==='open').length}）`}</button></>:null;}
export function InlineReviewEditor(){
 const review=useReview();if(!review?.draft)return null;
 return <LocalInlineEditor key={review.draft.id+'|'+review.draft.surface} review={review} draft={review.draft}/>;
}
function LocalInlineEditor({review,draft}:{review:Review;draft:Draft}){
 const initial=useMemo(()=>scopeNodes(draft.base.document!,draft.id),[draft.base,draft.id]);
 const originals=useRef(new Map(initial.map(n=>[n.id,n]))),targets=useRef(new Map<string,Resource>());
 const [nodes,setNodes]=useState(initial),[message,setMessage]=useState(''),[acquiring,setAcquiring]=useState('');
 const local=useRef(nodes),chapter=initial[0]?.type==='heading';
 const locks=review.locks,processed=useRef(review.loss.length);
 function update(next:KnowledgeNode[]){local.current=next;setNodes(next);review.updateNodes(next,!equalValue(next,[...originals.current.values()]));}
 function targetFor(n:KnowledgeNode):Resource{return targets.current.get(n.id)??{kind:'entry',id:n.id};}
 async function enter(n:KnowledgeNode){const target=targetFor(n);setAcquiring(n.id);setMessage('');try{
  const lease=await locks.acquire(target,!review.proposing);targets.current.set(n.id,target);
  const fresh=lease.baseline.node;
  if(fresh&&!equalValue(fresh,originals.current.get(n.id))){const prior=originals.current.get(n.id),current=local.current.find(v=>v.id===n.id),changed=!equalValue(current,prior);originals.current.set(n.id,fresh);update(local.current.map(v=>v.id!==n.id?v:changed&&v.type==='entry'&&fresh.type==='entry'?{...fresh,key:v.key,value:v.value}:fresh));setMessage(changed?'最新正文已变化，草稿保留并显示与最新正文的差异；请核对后保存。':'条目已有更新，已载入最新内容，请核对后编辑。');}
 }catch(e){setMessage((e as Error).message);}finally{setAcquiring('');}}
 useEffect(()=>{if(!chapter&&initial[0])void enter(initial[0]);return()=>{void locks.release();};},[]);
 useEffect(()=>{const losses=review.loss.slice(processed.current);processed.current=review.loss.length;for(const loss of losses){const affected=[...targets.current].filter(([,t])=>JSON.stringify(t)===JSON.stringify(loss.lease.resource)).map(([id])=>id);
  if(loss.reason==='admin_takeover'){
   let next=local.current.filter(n=>!affected.includes(n.id)||originals.current.has(n.id));
   for(const id of affected){const original=originals.current.get(id);if(original){const index=next.findIndex(n=>n.id===id);if(index>=0)next=next.map(n=>n.id===id?original:n);else {const position=initial.findIndex(n=>n.id===id);next.splice(Math.min(position,next.length),0,original);}}targets.current.delete(id);}
   update(next);setMessage('管理员已接管或确认此条，该条未提交草稿已清空。其他修改保留。');
  }else setMessage('编辑权限已暂停，草稿已保留。请重新取得编辑权限并核对正文。');}
 },[review.loss]);
 async function insert(at:number){
  const before=local.current.slice(0,at),anchor=[...before].reverse().find(n=>originals.current.has(n.id));if(!anchor){setMessage('请从章节内插入条目');return;}
  const all=draft.base.document!.nodes;let section:string|undefined;
  for(const n of all){if(n.type==='heading')section=n.id;if(n.id===anchor.id)break;}
  if(!section)return;const target:Resource={kind:'slot',section_id:section,left_id:anchor.id};setAcquiring('insert');
  try{await locks.acquire(target,!review.proposing);const node:KnowledgeNode={id:crypto.randomUUID(),type:'entry',key:'新条目',show_key:true,value:''};targets.current.set(node.id,target);update([...local.current.slice(0,at),node,...local.current.slice(at)]);}catch(e){setMessage((e as Error).message);}finally{setAcquiring('');}
 }
 function blur(n:KnowledgeNode,e:React.FocusEvent){if(e.currentTarget.contains(e.relatedTarget as Node|null))return;if(equalValue(n,originals.current.get(n.id)))void locks.release(targetFor(n));}
 function save(){const changes:unknown[]=[];
  for(const n of nodes){if(n.type!=='entry'||equalValue(n,originals.current.get(n.id)))continue;const lease=locks.get(targetFor(n));if(!lease){setMessage('请重新取得所有已修改条目的编辑权限后再保存。');return;}changes.push({kind:originals.current.has(n.id)?'update':'insert',node:n,lease:leaseRef(lease)});}
  for(const n of originals.current.values()){if(n.type!=='entry'||nodes.some(v=>v.id===n.id))continue;const lease=locks.get(targetFor(n));if(!lease){setMessage('删除条目的权限已暂停，请先恢复条目并重新取得权限。');return;}changes.push({kind:'delete',lease:leaseRef(lease)});}
  void review.save(changes);
 }
 return <section className="inline-review-editor" aria-label="局部编辑">
 <div className="review-toolbar"><strong>{chapter?'编辑章节':'编辑段落'}</strong><button disabled={review.busy} onClick={review.cancel}>取消</button>{review.uncertain&&<button disabled={review.busy} onClick={()=>void review.save()}>重试核对保存结果</button>}<button disabled={review.uncertain||review.busy||!review.dirty||!review.canSave||!locks.online} className="primary" onClick={save}>{review.busy?'保存中…':review.proposing?'暂存待确认':'保存'}</button></div>
 {!review.canSave&&<p role="status">正在等待同步或确认最新版本，草稿已保留。</p>}{!locks.online&&<p role="status">连接中断，编辑已暂停；草稿保留。</p>}
 {(review.error||message)&&<p className="error" role="alert">{review.error||message}</p>}
 <fieldset disabled={review.readOnly||review.busy||review.uncertain}>{nodes.map((n,i)=>{const target=targetFor(n),lease=locks.get(target),owner=locks.owner(target);return <div key={n.id} className="entry-edit-row" data-entry={n.id} onBlur={e=>blur(n,e)}>
 {n.type==='heading'?<strong>{n.title}</strong>:<><div className="entry-lock-status">{owner&&<span className="lock-hint">{owner.owner} 正在编辑 · 已锁定</span>}{!lease&&<button disabled={!!acquiring||!!owner&&review.proposing} onClick={()=>void enter(n)}>{acquiring===n.id?'正在取得权限…':owner&&!review.proposing?'接管编辑':'编辑此项'}</button>}{lease&&<small>正在编辑</small>}</div><fieldset disabled={!lease}><NodeFields node={n} original={originals.current.get(n.id)??n} onChange={node=>update(local.current.map(v=>v.id===node.id?node:v))}/></fieldset></>}
 <div className="scope-insert-actions">{n.type==='entry'&&<>{chapter&&<><button onClick={()=>void insert(i)}>在前面插入</button><button onClick={()=>void insert(i+1)}>在后面插入</button></>}<button disabled={!lease} onClick={()=>{update(local.current.filter(o=>o.id!==n.id));if(!originals.current.has(n.id)&&!local.current.some(v=>JSON.stringify(targetFor(v))===JSON.stringify(target)))void locks.release(target);}}>删除条目</button></>}{n.type==='heading'&&<button onClick={()=>void insert(i+1)}>章节开头插入条目</button>}</div></div>;})}{[...originals.current.values()].filter(n=>n.type==='entry'&&!nodes.some(v=>v.id===n.id)).map(n=><div className="entry-edit-row" key={'deleted-'+n.id}><del>{n.type==='entry'?n.key:''} · 待删除</del>{n.type==='entry'&&<p>{n.value}</p>}{!locks.get(targetFor(n))&&<button onClick={()=>void enter(n)}>重新取得删除权限</button>}<button onClick={()=>{const next=[...local.current];const index=initial.findIndex(v=>v.id===n.id);next.splice(Math.min(index,next.length),0,n);update(next);void locks.release(targetFor(n));}}>恢复条目</button></div>)}{chapter&&<button onClick={()=>void insert(local.current.length)}>章节末尾插入条目</button>}</fieldset>
 </section>;
}
export type {Review};
