import {useState,useMemo,type ReactNode,type ElementType} from 'react';
import Markdown from './EntityMarkdown';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {copyEntry,sectionClipboard} from './jsonDocument';
import {NodeActions,InlineReviewEditor,useReview} from './NoteReview';
import {scopeNodes} from './noteReviewModel';

export function CopyButton({text,label,children,className=''}:{text:string|(()=>string);label:string;children?:ReactNode;className?:string}){
 const [state,setState]=useState('');
 async function copy(){try{await navigator.clipboard.writeText(typeof text==='function'?text():text);setState('已复制');}catch{setState('复制失败，请检查剪贴板权限');}}
 return <><button type="button" className={'copy-control '+className} aria-label={label} title={label} onClick={()=>void copy()}>{children??'复制'}</button>{state&&<span className="copy-result" role="status">{state}</span>}</>;
}

function CopyHeading({node,body,children,interactive=true}:{node:Extract<KnowledgeNode,{type:'heading'}>;body:KnowledgeDocument;children:ReactNode;interactive?:boolean}){
 const Tag=('h'+node.level) as ElementType;const text=()=>sectionClipboard(body,node.id);const [state,setState]=useState('');
 async function copy(){try{await navigator.clipboard.writeText(typeof text==='function'?text():text);setState('已复制');}catch{setState('复制失败，请检查剪贴板权限');}}
 return <Tag className={'json-h'+node.level} onClick={(event:React.MouseEvent)=>{if(!(event.target as HTMLElement).closest('button,a,input,textarea'))void copy();}}>{children} <CopyButton text={text} label={'复制分段：'+node.title}>⧉</CopyButton>{interactive&&<NodeActions node={node}/>}{state&&<span className="copy-result" role="status">{state}</span>}</Tag>;
}

export default function JsonReading({body,nodes,note,onNote,interactive=true,surface='body'}:{body:KnowledgeDocument;nodes:KnowledgeNode[];note:Note;onNote:(id:string,player?:string)=>void;interactive?:boolean;surface?:string}){
 const context=useReview();const review=interactive?context:null;
 const localDraft=review?.draft&&(review.draft.surface??'body')===surface?review.draft:null;
 const hidden=new Set(localDraft?scopeNodes(body,localDraft.id).slice(1).map(n=>n.id):[]);
 const components=useMemo(()=>({a:({href,children}:{href?:string;children?:ReactNode})=>{
  const link=note.guide_related?.find(x=>x.href===href);
  const related=note.related.find(n=>n.path&&href&&n.path.split('/').at(-1)===href.split('/').at(-1));
  if(link||related)return <button className="link-button" onClick={()=>onNote(link?.note??related!.id,link?.player)}>{children}</button>;
  return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
 }}),[note,onNote]);
 const headingComponents=useMemo(()=>({...components,p:({children}:{children?:ReactNode})=><>{children}</>}),[components]);
 const draftId=localDraft?.id;
 return useMemo(()=><>{nodes.filter(n=>!hidden.has(n.id)).map(n=>draftId===n.id?<div key={n.id} id={surface==='body'?n.id:surface+'-'+n.id} data-node={n.id}><InlineReviewEditor/></div>:n.type==='heading'?<div key={n.id} className="json-heading" data-section={n.level===2?n.title:undefined} id={n.id}>
  {n.level===1?null:<CopyHeading node={n} body={body} interactive={interactive}><Markdown components={headingComponents}>{n.title}</Markdown></CopyHeading>}
 </div>:<article key={n.id} className={'json-entry '+(n.show_key?'keyed':'unkeyed')} data-node={n.id}>
  {n.show_key?<>{/^(?:[-*+] |\d+[.)] )/.test(n.prefix??'')&&<span className="entry-bullet" aria-hidden="true">{n.prefix?.match(/^\d+[.)]/)?.[0]??'•'} </span>}<CopyButton text={()=>copyEntry(n,body,note.title)} label={'复制条目：'+n.key} className="entry-key">{n.key}：</CopyButton><div className="entry-value prose"><Markdown components={components}>{n.value}</Markdown></div><CopyButton text={()=>copyEntry(n,body,note.title)} label={'复制段落：'+n.key} className="anonymous-copy"/></>:<><div className="prose"><Markdown components={components}>{n.value}</Markdown></div><CopyButton text={()=>copyEntry(n,body,note.title)} label="复制条目：正文" className="anonymous-copy"/></>}{interactive&&<NodeActions node={n} surface={surface}/>}
 </article>)}</>,[body,nodes,note,components,headingComponents,draftId,interactive,surface]);
}
