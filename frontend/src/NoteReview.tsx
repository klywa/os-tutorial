import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {api} from './model';
import {equalValue,scopeNodes} from './noteReviewModel';
import {NodeFields} from './ReviewFields';
import ReviewComments from './ReviewComments';
import ReviewHistory from './ReviewHistory';
import './noteReview.css';

export type Annotation={id:string;note_id:string;node_id:string;text:string;status:'open'|'resolved';revision:string;created_at:string;result?:string;result_revision?:string;anchor_state:'current'|'changed'|'missing';target:KnowledgeNode[]};
type Draft={id:string;base:Note;body:KnowledgeDocument};
type Review={note:Note;draft:Draft|null;dirty:boolean;busy:boolean;error:string;comments:Annotation[];commentNode:string|null;
 startEdit:(id:string)=>void;startComment:(id:string)=>void;openHistory:()=>void;update:(body:KnowledgeDocument)=>void;
 cancel:()=>void;save:()=>Promise<void>;warn:()=>void;reloadComments:()=>Promise<void>;setExtraDirty:(dirty:boolean)=>void;closeComments:()=>void};
const Context=createContext<Review|null>(null);
export const useReview=()=>useContext(Context);
export function ReviewProvider({note,children,onSaved,onDirty,externalDirty=false}:{note?:Note;children:ReactNode;onSaved:(note:Note)=>void;onDirty:(dirty:boolean)=>void;externalDirty?:boolean}){
 const [draft,setDraft]=useState<Draft|null>(null),[extraDirty,setExtra]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [comments,setComments]=useState<Annotation[]>([]),[commentNode,setCommentNode]=useState<string|null>(null),[history,setHistory]=useState(false);
 const dirty=!!draft&&!equalValue(draft.body,draft.base.document)||extraDirty;
 async function reloadComments(){if(note)setComments(await api<Annotation[]>('annotations?note_id='+encodeURIComponent(note.id)));}
 useEffect(()=>{let live=true;if(note)void api<Annotation[]>('annotations?note_id='+encodeURIComponent(note.id)).then(rows=>{if(live)setComments(rows);}).catch(e=>{if(live)setError('批注载入失败：'+e.message);});return()=>{live=false;};},[note?.id,note?.revision]);
 if(!note?.document)return <>{children}</>;
 function warn(){setError('修改未保存，请保存或取消');}
 function guard(){if(dirty||externalDirty){warn();return false;}setError('');return true;}
 function changeDirty(value:boolean){setExtra(value);onDirty(value||!!draft&&!equalValue(draft.body,draft.base.document));}
 const review:Review={note,draft,dirty,busy,error,comments,commentNode,
  startEdit:id=>{if(!guard())return;setCommentNode(null);setDraft({id,base:structuredClone(note),body:structuredClone(note.document!)});},
  startComment:id=>{if(!guard())return;setDraft(null);setCommentNode(id);},
  openHistory:()=>{if(!guard())return;setDraft(null);setCommentNode(null);setHistory(true);},
  update:body=>{if(!draft)return;setDraft({...draft,body});onDirty(!equalValue(body,draft.base.document));},
  cancel:()=>{setDraft(null);setError('');onDirty(extraDirty);},
  save:async()=>{if(!draft||busy)return;setBusy(true);setError('');try{const saved=await api<Note>('notes/'+encodeURIComponent(note.id),'PUT',{revision:draft.base.revision,document:draft.body});setDraft(null);onDirty(false);onSaved(saved);}catch(e){setError((e as Error).message+'；草稿已保留。');}finally{setBusy(false);}},
  warn,reloadComments,setExtraDirty:changeDirty,closeComments:()=>{setCommentNode(null);setExtra(false);onDirty(false);}};
 return <Context.Provider value={review}>{children}{error&&!draft&&<div className="review-notice" role="alert">{error}<button onClick={()=>setError('')}>关闭提示</button></div>}
 {commentNode&&<ReviewComments review={review}/>}
 {history&&<ReviewHistory note={note} onDirty={changeDirty} onSaved={saved=>{setHistory(false);setExtra(false);onDirty(false);onSaved(saved);}} onClose={()=>{setHistory(false);setExtra(false);onDirty(false);}}/>}
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
 const {draft}=review;const nodes=scopeNodes(draft.body,draft.id);const original=scopeNodes(draft.base.document!,draft.id);
 return <section className="inline-review-editor" aria-label="局部编辑" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null)&&review.dirty)review.warn();}}>
 <div className="review-toolbar"><strong>{nodes[0]?.type==='heading'?'编辑章节':'编辑段落'}</strong><button disabled={review.busy} onClick={review.cancel}>取消</button><button disabled={review.busy||!review.dirty} className="primary" onClick={()=>void review.save()}>{review.busy?'保存中…':'保存'}</button></div>
 {review.error&&<p className="error" role="alert">{review.error}</p>}
 <fieldset disabled={review.busy}>{nodes.map((n,i)=><NodeFields key={n.id} node={n} original={original[i]} onChange={node=>review.update({...draft.body,nodes:draft.body.nodes.map(n=>n.id===node.id?node:n)})}/>)}</fieldset>
 </section>;
}
export type {Review};
