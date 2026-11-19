import {useRef,useState} from 'react';

export function TemplateConditionPreview({expression}:{expression:string}){
 const output=useRef<HTMLOutputElement>(null),[message,setMessage]=useState('');
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
  <output ref={output} className="rule-expression">{expression||'无条件限制'}</output>
  {expression&&<button type="button" onClick={()=>void copy()}>复制完整条件</button>}
  {message&&<small role="status">{message}</small>}
 </div>;
}
