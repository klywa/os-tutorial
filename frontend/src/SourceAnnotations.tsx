import {useEffect,useRef,useState} from 'react';
import {normalizeTags} from './annotationSaving';
import type {SaveSource} from './annotationSaving';
import type {Source} from './types';

type Field='tags'|'notes';
type Value=string|string[];
// Keep unfinished and failed drafts when filtering, paging, or leaving this view.
const drafts=new Map<string,{value:Value;base:Source;error?:string}>();
let pointerDown=false;
const afterPointer=new Set<()=>void>();
if(typeof document!=='undefined'){
 document.addEventListener('pointerdown',()=>{pointerDown=true;},true);
 const finish=()=>{pointerDown=false;setTimeout(()=>{const waiting=[...afterPointer];afterPointer.clear();waiting.forEach(run=>run());},0);};
 document.addEventListener('pointerup',finish,true);
 document.addEventListener('pointercancel',finish,true);
}
function finishBlur(container:HTMLElement,commit:()=>Promise<void>){
 const check=()=>{if(!container.contains(document.activeElement))void commit();};
 queueMicrotask(()=>{if(pointerDown)afterPointer.add(check);else check();});
}
function valueOf(source:Source,field:Field):Value{return field==='tags'?source.tags??[]:source.notes??'';}
function useField(source:Source,field:Field,save:SaveSource){
 const key=(typeof location==='undefined'?'':location.origin)+':'+source.id+':'+field;
 const cached=drafts.get(key);
 const [value,setValue]=useState<Value>(cached?.value??valueOf(source,field));
 const [editing,setEditing]=useState(false),[pending,setPending]=useState(0),[error,setError]=useState(cached?.error??'');
 const current=useRef(value),base=useRef(cached?.base??source),active=useRef(false),version=useRef(0);
 useEffect(()=>{if(!active.current&&!drafts.has(key)&&!pending){current.current=valueOf(source,field);setValue(current.current);}},[source,field,key,pending]);
 function begin(){base.current=drafts.get(key)?.base??source;active.current=true;version.current++;setEditing(true);}
 function change(next:Value){current.current=next;version.current++;setValue(next);drafts.set(key,{value:next,base:base.current});}
 function cancel(){active.current=false;version.current++;drafts.delete(key);current.current=valueOf(source,field);setValue(current.current);setEditing(false);setError('');}
 async function commit(retry=false){
  if(!active.current&&!retry)return;
  active.current=false;setEditing(false);
  const next=field==='tags'?normalizeTags(current.current as string[]):current.current;
  const original=retry?source:base.current;const token=version.current;
  if(!retry&&JSON.stringify(next)===JSON.stringify(valueOf(original,field))){drafts.delete(key);return;}
  const submitted={value:next,base:original};drafts.set(key,submitted);setPending(n=>n+1);setError('');
  try{
   const saved=await save(original,{[field]:next});
   if(token===version.current&&!active.current&&drafts.get(key)===submitted){drafts.delete(key);current.current=valueOf(saved,field);setValue(current.current);base.current=saved;}
  }catch(e){if(token===version.current&&drafts.get(key)===submitted){const message=(e as Error).message;drafts.set(key,{...submitted,error:message});setError(message);}}
  finally{setPending(n=>n-1);}
 }
 return {value,editing,pending,error,begin,change,cancel,commit};
}
export function TagInput({value,choices,onChange}:{value:string[];choices:string[];onChange:(value:string[])=>void}){
 const [query,setQuery]=useState('');const input=useRef<HTMLInputElement>(null);const text=query.trim();
 const options=normalizeTags([...value,...choices]).filter(tag=>tag.toLocaleLowerCase().includes(text.toLocaleLowerCase()));
 function create(){if(text){onChange(normalizeTags([...value,text]));setQuery('');input.current?.focus();}}
 return <div className="annotation-tags-editor" role="group" aria-label="标签编辑">
  <div className="annotation-tag-chips">{value.map(tag=><button type="button" key={tag} aria-label={'移除标签 '+tag} onMouseDown={e=>e.preventDefault()} onClick={()=>{onChange(value.filter(v=>v!==tag));input.current?.focus();}}>{tag} ×</button>)}</div>
  <input ref={input} autoFocus aria-label="搜索或创建标签" placeholder="搜索标签，输入新标签后回车创建" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();create();}}}/>
  <div className="annotation-tag-options">{options.slice(0,60).map(tag=><label key={tag}><input type="checkbox" checked={value.includes(tag)} onChange={e=>onChange(e.target.checked?[...value,tag]:value.filter(v=>v!==tag))}/>{tag}</label>)}</div>
  {text&&!value.includes(text)&&<button type="button" onMouseDown={e=>e.preventDefault()} onClick={create}>添加“{text}”</button>}
  <small className="muted">可多选；点击区域外自动保存，Esc 取消。</small>
 </div>;
}
export default function SourceAnnotations({source,choices,onSave}:{source:Source;choices:string[];onSave:SaveSource}){
 const tags=useField(source,'tags',onSave),notes=useField(source,'notes',onSave);
 return <div className="source-annotations">{([['tags','标签',tags],['notes','备注',notes]] as const).map(([field,label,state])=>
  <div className={'source-annotation '+field} key={field} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null))finishBlur(e.currentTarget,()=>state.commit());}} onKeyDown={e=>{if(e.key==='Escape'&&state.editing){e.preventDefault();e.stopPropagation();state.cancel();}}}>
   <span className="annotation-label">{label}</span>
   {state.editing?(field==='tags'?<TagInput value={state.value as string[]} choices={choices} onChange={state.change}/>:<textarea autoFocus aria-label="编辑备注" rows={3} value={state.value as string} onChange={e=>state.change(e.target.value)}/>):
    <button type="button" className="annotation-display" aria-label={'编辑'+label} onClick={state.begin}>{field==='tags'?(state.value as string[]).length?(state.value as string[]).map(tag=><span className="badge" key={tag}>{tag}</span>):'添加标签':(state.value as string)||'添加备注'}</button>}
   {!!state.pending&&<small role="status">保存中…</small>}
   {state.error&&<div className="annotation-error" role="alert">{state.error}；草稿已保留，请核对后重试。<button type="button" onClick={()=>void state.commit(true)}>重试</button><button type="button" onClick={state.cancel}>放弃修改</button></div>}
  </div>)}</div>;
}
