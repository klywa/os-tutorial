import {useProposals,type Proposal} from './Proposals';
import {useCapabilities} from './auth';
import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {api} from './model';
import {equalValue,scopeNodes,replaceScope} from './noteReviewModel';
import {NodeFields} from './ReviewFields';
import ReviewComments from './ReviewComments';
import ReviewHistory from './ReviewHistory';
import './noteReview.css';

export type Annotation={id:string;note_id:string;node_id:string;text:string;status:'open'|'resolved';revision:string;created_at:string;result?:string;result_revision?:string;anchor_state:'current'|'changed'|'missing';target:KnowledgeNode[]};
type Draft={surface?:string;id:string;base:Note;body:KnowledgeDocument};
type Review={canSave:boolean;proposals:Proposal[];proposing:boolean;legacyReviews:boolean;readOnly?:boolean;note:Note;draft:Draft|null;dirty:boolean;busy:boolean;error:string;comments:Annotation[];commentNode:string|null;
 startEdit:(id:string,surface?:string)=>void;startComment:(id:string)=>void;openHistory:()=>void;updateNodes:(nodes:KnowledgeNode[],changed:boolean)=>void;
 cancel:()=>void;save:()=>Promise<void>;warn:()=>void;reloadComments:()=>Promise<void>;setExtraDirty:(dirty:boolean)=>void;closeComments:()=>void};
const Context=createContext<Review|null>(null);
export const useReview=()=>useContext(Context);
export function ReviewProvider({note,children,onSaved,onDirty,externalDirty=false,readOnly=false}:{note?:Note;children:ReactNode;onSaved:(note:Note)=>void;onDirty:(dirty:boolean)=>void;externalDirty?:boolean;readOnly?:boolean}){
 const {reviews,inlineEdit,proposeNotes,editNotes}=useCapabilities();
 const {items:proposals}=useProposals(note?.id);
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
 const review:Review={canSave:!readOnly&&(proposeNotes||editNotes),proposals,proposing:proposeNotes,legacyReviews:reviews,readOnly,note,draft,dirty,busy,error,comments,commentNode,
  startEdit:(id,surface)=>{if(!guard())return;setCommentNode(null);pendingNodes.current=scopeNodes(note.document!,id);dirtyRef.current=false;setInlineDirty(false);setDraft({id,surface,base:note,body:note.document!});},
  startComment:id=>{if(!guard())return;setDraft(null);setCommentNode(id);},
  openHistory:()=>{if(!guard())return;setDraft(null);setCommentNode(null);setHistory(true);},
  updateNodes:(nodes,changed)=>{if(!draft)return;pendingNodes.current=nodes;if(changed!==dirtyRef.current){dirtyRef.current=changed;setInlineDirty(changed);onDirty(changed||extraDirty);}},
  cancel:()=>{setDraft(null);setInlineDirty(false);dirtyRef.current=false;setError('');onDirty(extraDirty);},
  save:async()=>{if(!draft||savingRef.current)return;if(readOnly||(!proposeNotes&&!editNotes)){setError('请恢复连接并确认最新版本后保存，草稿已保留');return;}savingRef.current=true;const body=replaceScope(draft.body,draft.id,pendingNodes.current);setBusy(true);setError('');try{const saved=proposeNotes?null:await api<Note>('notes/'+encodeURIComponent(note.id),'PUT',{revision:draft.base.revision,document:body});if(proposeNotes){await api('proposals','POST',{note_id:note.id,revision:draft.base.revision,scope_id:draft.id,nodes:pendingNodes.current});window.dispatchEvent(new Event('wxq:proposals-changed'));}setDraft(null);setInlineDirty(false);dirtyRef.current=false;setError('');onDirty(false);if(saved)onSaved(saved);}catch(e){setError((e as Error).message+'；草稿已保留。');}finally{savingRef.current=false;setBusy(false);}},
  warn,reloadComments,setExtraDirty:changeDirty,closeComments:()=>{setCommentNode(null);setExtra(false);onDirty(false);}};
 return <Context.Provider value={review}>{children}{error&&!draft&&<div className="review-notice" role="alert">{error}<button onClick={()=>setError('')}>关闭提示</button></div>}
 {commentNode&&<ReviewComments review={review}/>}
 {history&&<ReviewHistory readOnly={readOnly} note={note} onDirty={changeDirty} onSaved={saved=>{setHistory(false);setExtra(false);setError('');onDirty(false);if(saved)onSaved(saved);}} onClose={()=>{setHistory(false);setExtra(false);onDirty(false);}}/>}
 </Context.Provider>;
}
export function NodeActions({node,surface}:{node:KnowledgeNode;surface?:string}){
 const review=useReview();if(!review)return null;
 const title=node.type==='heading'?node.title:node.show_key?node.key:'正文';
 const count=review.comments.filter(c=>c.node_id===node.id&&c.status==='open').length;
 return <span className="node-review-actions"><button type="button" disabled={review.busy} aria-label={(node.type==='heading'?'编辑章节：':'编辑段落：')+title} onClick={()=>review.startEdit(node.id,surface)}>编辑</button>{review.legacyReviews&&<button type="button" aria-label={'批注：'+title} onClick={()=>review.startComment(node.id)}>批注{count>0&&<span className="annotation-count">{count}</span>}</button>}</span>;
}
export function HistoryButton(){const review=useReview();return review?.legacyReviews?<><button onClick={review.openHistory}>历史版本</button><button onClick={()=>review.startComment('*')}>全部批注{review.comments.some(c=>c.status==='open')&&`（${review.comments.filter(c=>c.status==='open').length}）`}</button></>:null;}
export function InlineReviewEditor(){
 const review=useReview();if(!review?.draft)return null;
 return <LocalInlineEditor review={review} draft={review.draft}/>;
}
function LocalInlineEditor({review,draft}:{review:Review;draft:Draft}){
 const original=useMemo(()=>scopeNodes(draft.base.document!,draft.id),[draft.base,draft.id]);
 const [nodes,setNodes]=useState(()=>scopeNodes(draft.body,draft.id));
 const local=useRef(nodes);const chapter=original[0]?.type==='heading';
 function update(next:KnowledgeNode[]){local.current=next;setNodes(next);review.updateNodes(next,!equalValue(next,original));}
 const change=useCallback((node:KnowledgeNode)=>update(local.current.map(n=>n.id===node.id?node:n)),[original,review.updateNodes]);
 function insert(at:number){update([...local.current.slice(0,at),{id:crypto.randomUUID(),type:'entry',key:'新条目',show_key:true,value:''},...local.current.slice(at)]);}
 return <section className="inline-review-editor" aria-label="局部编辑" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null)&&review.dirty&&!review.busy)review.warn();}}>
 <div className="review-toolbar"><strong>{nodes[0]?.type==='heading'?'编辑章节':'编辑段落'}</strong><button disabled={review.busy} onClick={review.cancel}>取消</button><button disabled={review.busy||!review.dirty||!review.canSave} className="primary" onClick={()=>void review.save()}>{review.busy?'保存中…':review.proposing?'暂存待确认':'保存'}</button></div>
 {!review.canSave&&<p role="status">正在等待同步或确认最新版本，草稿已保留。</p>}
 {review.error&&<p className="error" role="alert">{review.error}</p>}
 <fieldset disabled={review.busy}>{nodes.map((n,i)=><div key={n.id}>{n.type==='heading'&&review.proposing?<strong>{n.title}</strong>:<NodeFields node={n} original={original.find(o=>o.id===n.id)??n} onChange={change}/>}<div className="scope-insert-actions">{n.type==='entry'&&<>{chapter&&<><button onClick={()=>insert(i)}>在前面插入</button><button onClick={()=>insert(i+1)}>在后面插入</button></>}<button onClick={()=>update(local.current.filter(o=>o.id!==n.id))}>删除条目</button></>}{n.type==='heading'&&<button onClick={()=>insert(i+1)}>章节开头插入条目</button>}</div></div>)}{chapter&&<button onClick={()=>insert(local.current.length)}>章节末尾插入条目</button>}</fieldset>
 </section>;
}
export type {Review};
