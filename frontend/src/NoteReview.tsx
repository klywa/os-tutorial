import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {api} from './model';
import {equalValue,scopeNodes} from './noteReviewModel';
import {NodeFields} from './ReviewFields';
import ReviewComments from './ReviewComments';
import ReviewHistory from './ReviewHistory';
import './noteReview.css';

export type Annotation={id:string;note_id:string;node_id:string;text:string;status:'open'|'resolved';revision:string;created_at:string;result?:string;result_revision?:string;anchor_state:'current'|'changed'|'missing';target:KnowledgeNode[]};
type Draft={id:string;base:Note;body:KnowledgeDocument};
type Review={readOnly?:boolean;note:Note;draft:Draft|null;dirty:boolean;busy:boolean;error:string;comments:Annotation[];commentNode:string|null;
 startEdit:(id:string)=>void;startComment:(id:string)=>void;openHistory:()=>void;updateNodes:(nodes:KnowledgeNode[],changed:boolean)=>void;
 cancel:()=>void;save:()=>Promise<void>;warn:()=>void;reloadComments:()=>Promise<void>;setExtraDirty:(dirty:boolean)=>void;closeComments:()=>void};
const Context=createContext<Review|null>(null);
export const useReview=()=>useContext(Context);
export function ReviewProvider({note,children,onSaved,onDirty,externalDirty=false,readOnly=false}:{note?:Note;children:ReactNode;onSaved:(note:Note)=>void;onDirty:(dirty:boolean)=>void;externalDirty?:boolean;readOnly?:boolean}){
 const [draft,setDraft]=useState<Draft|null>(null),[extraDirty,setExtra]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [comments,setComments]=useState<Annotation[]>([]),[commentNode,setCommentNode]=useState<string|null>(null),[history,setHistory]=useState(false);
 const pendingNodes=useRef<KnowledgeNode[]>([]),dirtyRef=useRef(false),savingRef=useRef(false);
 const [inlineDirty,setInlineDirty]=useState(false);
 const dirty=inlineDirty||extraDirty;
 async function reloadComments(){if(note)setComments(await api<Annotation[]>('annotations?note_id='+encodeURIComponent(note.id)));}
 useEffect(()=>{let live=true;if(note)void api<Annotation[]>('annotations?note_id='+encodeURIComponent(note.id)).then(rows=>{if(live)setComments(rows);}).catch(e=>{if(live)setError('批注载入失败：'+e.message);});return()=>{live=false;};},[note?.id,note?.revision]);
 if(!note?.document)return <>{children}</>;
 function warn(){if(!savingRef.current)setError('修改未保存，请保存或取消');}
 function guard(){if(readOnly){setError('请先确认最新版本后编辑');return false;}if(dirty||externalDirty){warn();return false;}setError('');return true;}
 function changeDirty(value:boolean){setExtra(value);if(!value&&!inlineDirty)setError(error=>error==='修改未保存，请保存或取消'?'':error);onDirty(value||inlineDirty);}
 const review:Review={readOnly,note,draft,dirty,busy,error,comments,commentNode,
  startEdit:id=>{if(!guard())return;setCommentNode(null);pendingNodes.current=scopeNodes(note.document!,id);dirtyRef.current=false;setInlineDirty(false);setDraft({id,base:note,body:note.document!});},
  startComment:id=>{if(!guard())return;setDraft(null);setCommentNode(id);},
  openHistory:()=>{if(!guard())return;setDraft(null);setCommentNode(null);setHistory(true);},
  updateNodes:(nodes,changed)=>{if(!draft)return;pendingNodes.current=nodes;if(changed!==dirtyRef.current){dirtyRef.current=changed;setInlineDirty(changed);onDirty(changed||extraDirty);}},
  cancel:()=>{setDraft(null);setInlineDirty(false);dirtyRef.current=false;setError('');onDirty(extraDirty);},
  save:async()=>{if(!draft||savingRef.current)return;if(readOnly){setError('请恢复连接并确认最新版本后保存，草稿已保留');return;}savingRef.current=true;const changes=new Map(pendingNodes.current.map(n=>[n.id,n]));const body={...draft.body,nodes:draft.body.nodes.map(n=>changes.get(n.id)??n)};setBusy(true);setError('');try{const saved=await api<Note>('notes/'+encodeURIComponent(note.id),'PUT',{revision:draft.base.revision,document:body});setDraft(null);setInlineDirty(false);dirtyRef.current=false;setError('');onDirty(false);onSaved(saved);}catch(e){setError((e as Error).message+'；草稿已保留。');}finally{savingRef.current=false;setBusy(false);}},
  warn,reloadComments,setExtraDirty:changeDirty,closeComments:()=>{setCommentNode(null);setExtra(false);onDirty(false);}};
 return <Context.Provider value={review}>{children}{error&&!draft&&<div className="review-notice" role="alert">{error}<button onClick={()=>setError('')}>关闭提示</button></div>}
 {commentNode&&<ReviewComments review={review}/>}
 {history&&<ReviewHistory readOnly={readOnly} note={note} onDirty={changeDirty} onSaved={saved=>{setHistory(false);setExtra(false);setError('');onDirty(false);onSaved(saved);}} onClose={()=>{setHistory(false);setExtra(false);onDirty(false);}}/>}
 </Context.Provider>;
}
export function NodeActions({node}:{node:KnowledgeNode}){
 const review=useReview();if(!review)return null;
 const title=node.type==='heading'?node.title:node.show_key?node.key:'正文';
 const count=review.comments.filter(c=>c.node_id===node.id&&c.status==='open').length;
 return <span className="node-review-actions"><button type="button" disabled={review.busy} aria-label={(node.type==='heading'?'编辑章节：':'编辑段落：')+title} onClick={()=>review.startEdit(node.id)}>编辑</button><button type="button" aria-label={'批注：'+title} onClick={()=>review.startComment(node.id)}>批注{count>0&&<span className="annotation-count">{count}</span>}</button></span>;
}
export function HistoryButton(){const review=useReview();return review?<><button onClick={review.openHistory}>历史版本</button><button onClick={()=>review.startComment('*')}>全部批注{review.comments.some(c=>c.status==='open')&&`（${review.comments.filter(c=>c.status==='open').length}）`}</button></>:null;}
export function InlineReviewEditor(){
 const review=useReview();if(!review?.draft)return null;
 return <LocalInlineEditor review={review} draft={review.draft}/>;
}
function LocalInlineEditor({review,draft}:{review:Review;draft:Draft}){
 const original=useMemo(()=>scopeNodes(draft.base.document!,draft.id),[draft.base,draft.id]);
 const [nodes,setNodes]=useState(()=>scopeNodes(draft.body,draft.id));
 const local=useRef(nodes);
 const originals=useMemo(()=>new Map(original.map(n=>[n.id,n])),[original]),changedIds=useRef(new Set<string>());
 const change=useCallback((node:KnowledgeNode)=>{const next=local.current.map(n=>n.id===node.id?node:n);local.current=next;setNodes(next);if(equalValue(node,originals.get(node.id)))changedIds.current.delete(node.id);else changedIds.current.add(node.id);review.updateNodes(next,changedIds.current.size>0);},[review.updateNodes,originals]);
 return <section className="inline-review-editor" aria-label="局部编辑" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null)&&review.dirty&&!review.busy)review.warn();}}>
 <div className="review-toolbar"><strong>{nodes[0]?.type==='heading'?'编辑章节':'编辑段落'}</strong><button disabled={review.busy} onClick={review.cancel}>取消</button><button disabled={review.busy||!review.dirty} className="primary" onClick={()=>void review.save()}>{review.busy?'保存中…':'保存'}</button></div>
 {review.error&&<p className="error" role="alert">{review.error}</p>}
 <fieldset disabled={review.busy}>{nodes.map((n,i)=><NodeFields key={n.id} node={n} original={original[i]} onChange={change}/>)}</fieldset>
 </section>;
}
export type {Review};
