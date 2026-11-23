import {useRef,useState} from 'react';

type ExpressionEdit={value:string;scope:string;save:(value:string)=>Promise<void>};
export function TemplateConditionPreview({expression,edit,expressionEdit,allowCopy=true,removed=false}:{expression:string;edit?:{label:string;disabled:boolean;onClick:()=>void};expressionEdit?:ExpressionEdit;allowCopy?:boolean;removed?:boolean}){
 const output=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null),[message,setMessage]=useState('');
 const [draft,setDraft]=useState<(ExpressionEdit&{text:string})|null>(null);
 const [saving,setSaving]=useState(false),[error,setError]=useState('');
 function close(){setDraft(null);setError('');requestAnimationFrame(()=>trigger.current?.focus({preventScroll:true}));}
 async function save(){
  if(!draft||saving||edit?.disabled)return;
  if(draft.text.trim()===draft.value.trim()){close();return;}
  setSaving(true);setError('');
  try{await draft.save(draft.text.trim());close();}
  catch(error){setError((error as Error).message);}
  finally{setSaving(false);}
 }
 async function copy(){
  try{await navigator.clipboard.writeText(expression);setMessage('已复制完整条件');}
  catch{
   const selection=window.getSelection();
   if(selection&&output.current){
    const range=document.createRange();range.selectNodeContents(output.current);
    selection.removeAllRanges();selection.addRange(range);
    setMessage('已选中完整条件，请按 Ctrl+C 或 ⌘C 复制');
   }
  }
 }
 return <div className="template-condition-preview"><h3>完整触发条件</h3>
  {draft?<form className="template-expression-editor" onSubmit={e=>{e.preventDefault();void save();}}>
   {draft.scope&&<div className="rule-expression" aria-label="模板组适用范围">{draft.scope}</div>}
   <textarea aria-label="正式条件表达式" rows={3} spellCheck={false} autoFocus value={draft.text} readOnly={saving}
    onChange={e=>setDraft({...draft,text:e.target.value})} onKeyDown={e=>{
     if(e.key==='Escape'&&!saving){e.stopPropagation();close();}
     if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();void save();}
    }}/>
   <div className="template-condition-actions">
    <button type="button" disabled={saving} onClick={close}>取消</button>
    <button type="submit" className="primary" disabled={saving||edit?.disabled}>{saving?'保存中…':'保存条件'}</button>
   </div>
   {error&&<p role="alert" className="template-inline-error">{error}</p>}
  </form>:<div ref={output}>
   {expressionEdit&&!removed?<button ref={trigger} type="button" className="rule-expression template-expression-edit-trigger"
    aria-label="就地编辑完整触发条件" disabled={edit?.disabled}
    onClick={()=>{setMessage('');setDraft({...expressionEdit,text:expressionEdit.value});}}>
    {expression||'无条件限制'}
   </button>:<output className="rule-expression">{removed?<><s>{expression}</s> <small>拟删除</small></>:expression||'无条件限制'}</output>}
  </div>}
  {(edit||allowCopy&&expression)&&<div className="template-condition-actions">
   {edit&&<button type="button" aria-label={edit.label} disabled={edit.disabled} onClick={edit.onClick}>编辑模板组</button>}
   {!draft&&allowCopy&&expression&&<button type="button" onClick={()=>void copy()}>复制完整条件</button>}
   {message&&<small role="status">{message}</small>}
  </div>}
 </div>;
}
