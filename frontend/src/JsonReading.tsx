import {useState,type ReactNode} from 'react';
import Markdown from './EntityMarkdown';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {copyEntry,renderNode,sectionMarkdown} from './jsonDocument';

export function CopyButton({text,label,children,className=''}:{text:string;label:string;children?:ReactNode;className?:string}){
 const [state,setState]=useState('');
 async function copy(){try{await navigator.clipboard.writeText(text);setState('已复制');}catch{setState('复制失败，请检查剪贴板权限');}}
 return <><button type="button" className={'copy-control '+className} aria-label={label} title={label} onClick={()=>void copy()}>{children??'复制'}</button>{state&&<span className="copy-result" role="status">{state}</span>}</>;
}

function CopyHeading({node,body,children}:{node:Extract<KnowledgeNode,{type:'heading'}>;body:KnowledgeDocument;children:ReactNode}){
 const Tag=node.level===2?'h2':'h3';const text=sectionMarkdown(body,node.id);const [state,setState]=useState('');
 async function copy(){try{await navigator.clipboard.writeText(text);setState('已复制');}catch{setState('复制失败，请检查剪贴板权限');}}
 return <Tag className={'json-h'+node.level} onClick={event=>{if(!(event.target as HTMLElement).closest('button,a'))void copy();}}>{children} <CopyButton text={text} label={'复制分段：'+node.title}>⧉</CopyButton>{state&&<span className="copy-result" role="status">{state}</span>}</Tag>;
}

export default function JsonReading({body,nodes,note,onNote}:{body:KnowledgeDocument;nodes:KnowledgeNode[];note:Note;onNote:(id:string,player?:string)=>void}){
 const components={a:({href,children}:{href?:string;children?:ReactNode})=>{
  const link=note.guide_related?.find(x=>x.href===href);
  const related=note.related.find(n=>n.path&&href&&n.path.split('/').at(-1)===href.split('/').at(-1));
  if(link||related)return <button className="link-button" onClick={()=>onNote(link?.note??related!.id,link?.player)}>{children}</button>;
  return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
 }};
 return <>{nodes.map(n=>n.type==='heading'?<div key={n.id} className="json-heading" data-section={n.level===2?n.title:undefined} id={n.id}>
  {n.level===1?null:n.level<=3?<CopyHeading node={n} body={body}><Markdown components={{...components,p:({children})=><>{children}</>}}>{n.title}</Markdown></CopyHeading>:<Markdown components={components}>{renderNode(n)}</Markdown>}
 </div>:<article key={n.id} className={'json-entry '+(n.show_key?'keyed':'unkeyed')} data-node={n.id}>
  {n.show_key?<>{/^(?:[-*+] |\d+[.)] )/.test(n.prefix??'')&&<span className="entry-bullet" aria-hidden="true">{n.prefix?.match(/^\d+[.)]/)?.[0]??'•'} </span>}<CopyButton text={copyEntry(n)} label={'复制条目：'+n.key} className="entry-key">{n.key}：</CopyButton><div className="entry-value prose"><Markdown components={components}>{n.value}</Markdown></div></>:<><div className="prose"><Markdown components={components}>{n.value}</Markdown></div><CopyButton text={copyEntry(n)} label="复制条目：正文" className="anonymous-copy"/></>}
 </article>)}</>;
}
