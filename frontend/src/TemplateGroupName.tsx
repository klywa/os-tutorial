import {useRef,useState} from 'react';

export default function TemplateGroupName({name,disabled,onSave}:{name:string;disabled:boolean;onSave:(name:string)=>Promise<void>}){
 const [draft,setDraft]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const trigger=useRef<HTMLButtonElement>(null),saving=useRef(false);
 function close(){setDraft(null);setError('');requestAnimationFrame(()=>trigger.current?.focus({preventScroll:true}));}
 async function save(){
  if(draft===null||saving.current||disabled)return;
  const value=draft.trim();
  if(!value){setError('请填写模板组名称');return;}
  if(value===name){close();return;}
  saving.current=true;setBusy(true);setError('');
  try{await onSave(value);close();}
  catch(reason){setError((reason as Error).message);}
  finally{saving.current=false;setBusy(false);}
 }
 if(draft===null)return <button type="button" ref={trigger} className="template-name-trigger" disabled={disabled}
  title="点击编辑模板组名称" onClick={()=>setDraft(name)}>{name}</button>;
 return <span className="template-name-edit" data-template-dirty={draft!==name||busy?true:undefined}>
  <input aria-label="模板组名称" value={draft} autoFocus readOnly={busy} onFocus={event=>event.currentTarget.select()}
   onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{
    if(event.nativeEvent.isComposing||event.keyCode===229)return;
    if(event.key==='Enter'){event.preventDefault();void save();}
    if(event.key==='Escape'&&!saving.current){event.preventDefault();event.stopPropagation();close();}
   }}/>
  <button type="button" className="primary" disabled={busy||disabled} onClick={()=>void save()}>{busy?'保存中…':'保存名称'}</button>
  <button type="button" disabled={busy} onClick={close}>取消</button>
  {error&&<small role="alert" className="template-inline-error">{error}</small>}
 </span>;
}
