import {useId,useState} from 'react';

export type RelatedCopyChoice={event:string;reason?:string};
export default function TemplateRelatedCopyMenu({disabled,options,onChoose,label='举一反三',buttonLabel,choicesLabel='选择关联事件'}:{
 disabled:boolean;options:()=>RelatedCopyChoice[];onChoose:(event:string)=>void;label?:string;buttonLabel?:string;choicesLabel?:string;
}){
 const [choices,setChoices]=useState<RelatedCopyChoice[]|null>(null);
 const id=useId();
 return <span className="template-related-copy" onBlur={e=>{
  if(!e.currentTarget.contains(e.relatedTarget))setChoices(null);
 }} onKeyDown={e=>{
  if(e.key==='Escape'){setChoices(null);e.currentTarget.querySelector('button')?.focus();}
 }}>
  <button type="button" disabled={disabled} aria-expanded={choices!==null} aria-controls={id} aria-label={buttonLabel}
   onClick={()=>setChoices(choices?null:options())}>{label}</button>
  {choices&&<span id={id} className="template-related-choices" role="group" aria-label={choicesLabel}>
   {choices.map(({event,reason})=><span key={event}>
    <button type="button" disabled={disabled||!!reason} onClick={()=>{setChoices(null);onChoose(event);}}>{event}</button>
    {reason&&<small>{reason}</small>}
   </span>)}
  </span>}
 </span>;
}
