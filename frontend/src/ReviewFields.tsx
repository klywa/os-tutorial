import {useState} from 'react';
import type {KnowledgeNode} from './types';
import {displayValue,textDiff} from './noteReviewModel';

export function DiffText({before,after}:{before:string;after:string}){
 return <div className="review-diff" aria-label="实时差异">{textDiff(before,after).map((p,i)=>p.kind==='remove'?<del key={i}><span className="diff-mark" aria-label="删除">−</span>{p.text}</del>:p.kind==='add'?<ins key={i}><span className="diff-mark" aria-label="增加">+</span>{p.text}</ins>:<span key={i}>{p.text}</span>)}</div>;
}
export function NodeFields({node,original,onChange}:{node:KnowledgeNode;original:KnowledgeNode;onChange:(node:KnowledgeNode)=>void}){
 const before=original as unknown as Record<string,unknown>;
 return <div className="review-node-fields">{node.type==='heading'?<label>章节标题<input value={node.title} readOnly={node.level===1} onChange={e=>onChange({...node,title:e.target.value})}/><DiffText before={String(before.title??'')} after={node.title}/></label>:<>
 {node.show_key&&<label>名称<input value={node.key} onChange={e=>onChange({...node,key:e.target.value})}/><DiffText before={String(before.key??'')} after={node.key}/></label>}
 <label>正文<textarea rows={Math.max(3,Math.min(14,Math.ceil(node.value.length/70)))} value={node.value} onChange={e=>onChange({...node,value:e.target.value})}/></label><DiffText before={String(before.value??'')} after={node.value}/></>}</div>;
}
export function ValueEditor({value,onChange,label,onValidity,disabled=false}:{value:unknown;onChange:(value:unknown)=>void;label:string;onValidity?:(valid:boolean)=>void;disabled?:boolean}){
 const [text,setText]=useState(displayValue(value)),[error,setError]=useState('');
 return <><textarea aria-label={label} disabled={disabled} rows={Math.min(15,Math.max(3,text.split('\n').length))} value={text} onChange={e=>{setText(e.target.value);try{const v=typeof value==='string'?e.target.value:JSON.parse(e.target.value);setError('');onValidity?.(true);onChange(v);}catch{onValidity?.(false);setError('请输入有效 JSON，或使用上方按钮选择版本');}}}/>{error&&<p className="error" role="alert">{error}</p>}</>;
}
