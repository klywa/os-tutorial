import {memo,useEffect,useMemo,useState} from 'react';
import type {KnowledgeNode} from './types';
import {displayValue,textDiff} from './noteReviewModel';
import {createDiffDebouncer} from './diffDebounce';

const RenderedDiff=memo(function RenderedDiff({before,after,split}:{before:string;after:string;split:boolean}){
 const parts=textDiff(before,after);
 if(split)return <div className="proposal-split-diff" aria-label="实时差异">
  <section aria-label="原文"><h4>原文</h4><div>{before?parts.map((p,i)=>p.kind==='add'?null:p.kind==='remove'?<del key={i}>{p.text}</del>:<span key={i}>{p.text}</span>):<em>无原文</em>}</div></section>
  <section aria-label="拟修改"><h4>拟修改</h4><div>{after?parts.map((p,i)=>p.kind==='remove'?null:p.kind==='add'?<ins key={i}>{p.text}</ins>:<span key={i}>{p.text}</span>):<em>将删除</em>}</div></section>
 </div>;
 return <div className="review-diff" aria-label="实时差异">{parts.map((p,i)=>p.kind==='remove'?<del key={i}><span className="diff-mark" aria-label="删除">−</span>{p.text}</del>:p.kind==='add'?<ins key={i}><span className="diff-mark" aria-label="增加">+</span>{p.text}</ins>:<span key={i}>{p.text}</span>)}</div>;
});
export const DiffText=memo(function DiffText({before,after,composing=false,split=false}:{before:string;after:string;composing?:boolean;split?:boolean}){
 const [display,setDisplay]=useState(()=>({before,after}));
 const timer=useMemo(()=>createDiffDebouncer(setDisplay),[]);
 useEffect(()=>{timer.update({before,after},composing);return timer.cancel;},[before,after,composing,timer]);
 return <RenderedDiff before={display.before} after={display.after} split={split}/>;
});
export const NodeFields=memo(function NodeFields({node,original,onChange,showDiff=true,onComposing}:{node:KnowledgeNode;original:KnowledgeNode;onChange:(node:KnowledgeNode)=>void;showDiff?:boolean;onComposing?:(value:boolean)=>void}){
 const [composing,setComposing]=useState(false);
 const composition={onCompositionStart:()=>{setComposing(true);onComposing?.(true);},onCompositionEnd:()=>{setComposing(false);onComposing?.(false);}};
 const before=original as unknown as Record<string,unknown>;
 return <div className="review-node-fields">{node.type==='heading'?<label>章节标题<input data-card-completion aria-label="章节标题" {...composition} value={node.title} readOnly={node.level===1} onChange={e=>onChange({...node,title:e.target.value})}/>{showDiff&&<DiffText composing={composing} before={String(before.title??'')} after={node.title}/>}</label>:<>
 <label className="inline"><input type="checkbox" checked={node.show_key} onChange={e=>onChange({...node,show_key:e.target.checked,key:e.target.checked&&original.type==='entry'?original.key:'正文'})}/>显示名称</label>
 {node.show_key&&<label>名称<input data-card-completion aria-label="名称" {...composition} value={node.key} onChange={e=>onChange({...node,key:e.target.value})}/>{showDiff&&<DiffText composing={composing} before={String(before.key??'')} after={node.key}/>}</label>}
 <label>正文<textarea data-card-completion aria-label="正文" {...composition} rows={Math.max(3,Math.min(14,Math.ceil(node.value.length/70)))} value={node.value} onChange={e=>onChange({...node,value:e.target.value})}/></label>{showDiff&&<DiffText composing={composing} before={String(before.value??'')} after={node.value}/>}</>}</div>;
});
export function ValueEditor({value,onChange,label,onValidity,onComposing,disabled=false}:{value:unknown;onChange:(value:unknown)=>void;label:string;onValidity?:(valid:boolean)=>void;onComposing?:(composing:boolean)=>void;disabled?:boolean}){
 const [text,setText]=useState(displayValue(value)),[error,setError]=useState('');
 return <><textarea data-card-completion={typeof value==='string'?true:undefined} onCompositionStart={()=>onComposing?.(true)} onCompositionEnd={()=>onComposing?.(false)} aria-label={label} disabled={disabled} rows={Math.min(15,Math.max(3,text.split('\n').length))} value={text} onChange={e=>{setText(e.target.value);try{const v=typeof value==='string'?e.target.value:JSON.parse(e.target.value);setError('');onValidity?.(true);onChange(v);}catch{onValidity?.(false);setError('请输入有效 JSON，或使用上方按钮选择版本');}}}/>{error&&<p className="error" role="alert">{error}</p>}</>;
}
