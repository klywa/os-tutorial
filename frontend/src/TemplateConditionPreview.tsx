import {useRef,useState,type ReactNode} from 'react';
import ConditionTextEditor from './ConditionTextEditor';
import {EntityText} from './EntityCards';
import {compactCondition,conditionBracketRanges,type ConditionEditingConfig} from './conditionEditing';

type ExpressionEdit={value:string;save:(value:string)=>Promise<void>};
function ConditionRanges({value}:{value:string}){
 const source=compactCondition(value)||'无条件限制';
 const {ranges}=conditionBracketRanges(source);
 const stack:{start:number;end:number;children:ReactNode[]}[]=[{start:0,end:Infinity,children:[]}];
 let cursor=0;
 function append(end:number){
  if(end>cursor)stack.at(-1)?.children.push(<EntityText inline key={cursor}>{source.slice(cursor,end)}</EntityText>);
  cursor=end;
 }
 function pop(){
  const frame=stack.at(-1)!;append(frame.end+1);stack.pop();
  stack.at(-1)?.children.push(<span key={frame.start} className="condition-bracket-range">{frame.children}</span>);
 }
 for(const {start,end} of ranges){
  while(stack.length>1&&stack.at(-1)!.end<start)pop();
  append(start);
  stack.push({start,end,children:[]});
 }
 while(stack.length>1)pop();
 append(source.length);
 return <>{stack[0].children}</>;
}
export function TemplateConditionPreview({expression,edit,expressionEdit,allowCopy=true,removed=false,config={},autoStart=false,onExit}:{expression:string;edit?:{label:string;disabled:boolean;onClick:()=>void};expressionEdit?:ExpressionEdit;allowCopy?:boolean;removed?:boolean;config?:ConditionEditingConfig;autoStart?:boolean;onExit?:()=>void}){
 const output=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null),[message,setMessage]=useState('');
 const [draft,setDraft]=useState<(ExpressionEdit&{text:string})|null>(()=>autoStart&&expressionEdit?{...expressionEdit,text:expressionEdit.value}:null);
 const [saving,setSaving]=useState(false),[error,setError]=useState('');
 const formatted=<ConditionRanges value={expression}/>;
 function begin(){if(expressionEdit&&!edit?.disabled){setMessage('');setDraft({...expressionEdit,text:expressionEdit.value});}}
 function close(){setDraft(null);setError('');onExit?.();requestAnimationFrame(()=>trigger.current?.focus({preventScroll:true}));}
 async function save(){
  if(!draft||saving||edit?.disabled)return;
  const {text,value}=draft;
  if(text.trim()===value.trim()){close();return;}
  setSaving(true);setError('');
  try{await draft.save(text.trim());close();}
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
  {draft?<form className="template-expression-editor" data-template-dirty={draft.text!==draft.value||saving?true:undefined} onSubmit={e=>{e.preventDefault();void save();}}
   onBlur={onExit?e=>{if(!saving&&draft.text.trim()===draft.value.trim()&&!e.currentTarget.contains(e.relatedTarget))close();}:undefined}>
   <ConditionTextEditor label="正式条件表达式" rows={3} autoFocus value={draft.text} readOnly={saving} config={config}
    onChange={text=>setDraft({...draft,text})} onEditorKeyDown={e=>{
     if(e.key==='Escape'&&!saving){e.preventDefault();e.stopPropagation();close();}
     if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();void save();}
    }}/>
   <div className="template-condition-actions">
    <button type="button" disabled={saving} onClick={close}>取消</button>
    <button type="submit" className="primary" disabled={saving||edit?.disabled}>{saving?'保存中…':'保存条件'}</button>
    {edit&&<button type="button" aria-label={edit.label} disabled={saving||edit.disabled} onClick={edit.onClick}>编辑模板组</button>}
   </div>
   {error&&<p role="alert" className="template-inline-error">{error}</p>}
  </form>:<div ref={output}>
   {expressionEdit&&!removed?<div className="rule-expression template-expression-reading">
    <button ref={trigger} type="button" className="template-expression-edit-trigger"
     aria-label="就地编辑完整触发条件" disabled={edit?.disabled} onClick={begin}/>
    <div className="template-expression-content" onClick={event=>{
     if(event.target instanceof Element&&!event.target.closest('[role=button],button')&&window.getSelection()?.isCollapsed!==false)begin();
    }}>{formatted}</div>
   </div>:<output className="rule-expression">{removed?<><s>{formatted}</s> <small>拟删除</small></>:formatted}</output>}
  </div>}
  {!draft&&(edit||allowCopy&&expression)&&<div className="template-condition-actions">
   {edit&&<button type="button" aria-label={edit.label} disabled={edit.disabled} onClick={edit.onClick}>编辑模板组</button>}
   {!draft&&allowCopy&&expression&&<button type="button" onClick={()=>void copy()}>复制完整条件</button>}
   {message&&<small role="status">{message}</small>}
  </div>}
 </div>;
}
