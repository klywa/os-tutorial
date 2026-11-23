import {useRef,useState} from 'react';

export default function TemplateInlineMetadata({label,values,onSave,disabled=false,proposalPrevious}:{
 label:string;values:string[];onSave?:(values:string[])=>Promise<void>;disabled?:boolean;proposalPrevious?:string[];
}){
 const [draft,setDraft]=useState<string[]|null>(null),[input,setInput]=useState('');
 const [pending,setPending]=useState<string[]|null>(null),[error,setError]=useState('');
 const trigger=useRef<HTMLButtonElement>(null),field=useRef<HTMLInputElement>(null);
 const composing=useRef(false);
 const savingDraft=useRef<{values:string[];save:typeof onSave}>(undefined);
 const retry=useRef<string[]|undefined>(undefined);
 const shown=draft??pending??values;
 const chips=shown.map(value=><span className="template-metadata-chip" key={value}
  data-proposal-change={proposalPrevious&&!proposalPrevious.includes(value)||undefined}>{value}</span>);
 const removed=proposalPrevious?.filter(value=>!shown.includes(value)).map(value=>
  <span className="template-metadata-chip" key={value} data-proposal-change><s>{value}</s> <small>拟删除</small></span>);

 function append(list:string[]){
  const value=input.trim();
  return value&&!list.includes(value)?[...list,value]:list;
 }
 function close(){
  setDraft(null);
  setInput('');
  composing.current=false;
 }
 function begin(){
  setError('');
  savingDraft.current={values,save:onSave};
  setDraft(retry.current??[...values]);
  retry.current=undefined;
 }
 async function commit(){
  const started=savingDraft.current;
  if(!draft||!started?.save)return;
  const next=append(draft);
  close();
  if(next.length===started.values.length&&next.every((value,index)=>value===started.values[index]))return;
  setPending(next);
  try{await started.save(next);}
  catch(error){retry.current=next;setError((error as Error).message);}
  finally{setPending(null);}
 }
 const className='template-inline-metadata '+(label==='批次'?'template-inline-batch':'template-inline-tags');
 if(!onSave)return values.length>0||removed?.length
  ? <span className={className} role="group" aria-label={label}>{chips}{removed}</span>
  : null;
 return <span className={className} aria-busy={pending!==null}>
  {draft!==null?<span className="template-metadata-editor" role="group" aria-label={'编辑'+label}
   onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))void commit();}}
   onKeyDown={event=>{
    if(composing.current||event.nativeEvent.isComposing)return;
    if(event.key==='Escape'){
     event.preventDefault();event.stopPropagation();close();
     requestAnimationFrame(()=>trigger.current?.focus());
    }else if(event.key==='Enter'&&event.target===field.current){
     event.preventDefault();setDraft(append(draft));setInput('');
    }
   }}>
   {draft.map(value=><button type="button" className="template-metadata-chip" aria-label={'移除'+label+' '+value}
    key={value} onClick={()=>{field.current?.focus();setDraft(draft.filter(item=>item!==value));}}>{value}<span aria-hidden="true">×</span></button>)}
   <input ref={field} autoFocus aria-label={'新增'+label} placeholder={'添加'+label} value={input} maxLength={40}
    onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;}} onChange={event=>setInput(event.target.value)}/>
  </span>:<button ref={trigger} type="button" className="template-metadata-trigger"
   aria-label={'编辑'+label+(shown.length?'：'+shown.join('、'):'')} title={'编辑'+label}
   disabled={disabled||pending!==null} onClick={begin}
   onPointerDown={event=>{
    if(event.button!==0||!document.activeElement?.closest('.template-metadata-editor'))return;
    // The other editor can resize when it blurs, moving this button before the click lands.
    event.preventDefault();
    begin();
   }}>
   {shown.length?chips:<span className="template-metadata-empty">＋ {label}</span>}{removed}
   {shown.length>0&&<span className="template-metadata-pencil" aria-hidden="true">✎</span>}
  </button>}
  {error&&<span className="template-metadata-error" role="alert">{label}保存失败：{error}</span>}
 </span>;
}
