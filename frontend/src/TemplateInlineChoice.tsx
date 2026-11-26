import {useId,useRef,useState} from 'react';
import {matchMetadataChoices} from './MetadataSuggestions';
import {EntityChip} from './EntityCards';

export default function TemplateInlineChoice({label,value,choices,onSave,disabled=false,className='',allowText=false,autoStart=false,onCancel,previewIds,firstChoice}:{
 label:string;value:string;choices:string[];onSave:(value:string)=>Promise<void>;disabled?:boolean;className?:string;allowText?:boolean;
 autoStart?:boolean;onCancel?:()=>void;previewIds?:string[];firstChoice?:string;
}){
 const [query,setQuery]=useState<string|null>(autoStart?'':null),[active,setActive]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const saving=useRef(false),trigger=useRef<HTMLButtonElement>(null),listId=useId();
 const options=matchMetadataChoices(choices,query??'',[]).filter(choice=>choice!==firstChoice);
 const typed=query?.trim();
 const manual=allowText&&typed&&typed!==firstChoice&&!choices.includes(typed)?typed:undefined;
 const matches=[...(firstChoice?[firstChoice]:[]),...(manual?[manual]:[]),...options].slice(0,30);
 function close(focus=false){
  setQuery(null);setError('');
  if(focus)requestAnimationFrame(()=>trigger.current?.focus());
 }
 function cancel(focus=false){close(focus);onCancel?.();}
 async function save(candidate:string){
  if(saving.current||!candidate.trim())return;
  saving.current=true;setBusy(true);setError('');
  try{await onSave(candidate);close(true);}
  catch(issue){setError((issue as Error).message);}
  finally{saving.current=false;setBusy(false);}
 }
 if(query===null){
  const triggerClass='template-inline-trigger '+className,ariaLabel=label+'：'+value;
  const open=()=>{setActive(0);setQuery('');};
  return previewIds?.length?<EntityChip ids={previewIds} label={value}
   previewButton={{ref:trigger,className:triggerClass,ariaLabel,disabled,onClick:open}}/>:
   <button ref={trigger} type="button" className={triggerClass} disabled={disabled} aria-label={ariaLabel} onClick={open}>{value}</button>;
 }
 return <span className="template-inline-choice" onBlur={event=>{
  if(!saving.current&&!event.currentTarget.contains(event.relatedTarget))cancel();
 }}>
  <input autoFocus role="combobox" aria-label={label} aria-expanded={!!matches.length} aria-controls={matches.length?listId:undefined}
   aria-activedescendant={matches[active]?listId+'-'+active:undefined} aria-autocomplete="list" placeholder={value}
   value={query} readOnly={busy} onChange={event=>{setQuery(event.target.value);setActive(firstChoice&&event.target.value.trim()?1:0);}} onKeyDown={event=>{
    if(event.nativeEvent.isComposing)return;
    if(event.key==='Escape'&&!busy){event.preventDefault();event.stopPropagation();cancel(true);}
    if(event.key==='ArrowDown'&&matches.length){event.preventDefault();setActive((active+1)%matches.length);}
    if(event.key==='ArrowUp'&&matches.length){event.preventDefault();setActive((active+matches.length-1)%matches.length);}
    if(event.key==='Enter'){
     event.preventDefault();
     const choice=matches[active]??(firstChoice&&matchMetadataChoices([firstChoice],query,[]).length?firstChoice:allowText?query.trim():'');
     if(choice)void save(choice);
    }
   }}/>
  {!!matches.length&&<span id={listId} className="template-inline-options" role="listbox" aria-label={label+'候选'}>
   {matches.map((choice,index)=><button key={choice} type="button" role="option" id={listId+'-'+index} tabIndex={-1} aria-selected={active===index}
    disabled={busy} onMouseDown={event=>event.preventDefault()} onClick={()=>void save(choice)}>{choice===manual?`使用「${choice}」`:choice}</button>)}
  </span>}
  {busy&&<span role="status" className="muted">保存中…</span>}
  {error&&<span role="alert" className="error">{error}</span>}
 </span>;
}
