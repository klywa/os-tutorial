import {useEffect,useLayoutEffect,useRef} from 'react';
import {textDiff} from './noteReviewModel';

function selectionOffset(root:HTMLElement,node:Node|null,offset:number){
 if(!node||!root.contains(node))return null;
 const range=document.createRange();
 range.selectNodeContents(root);
 range.setEnd(node,offset);
 return range.toString().length;
}

function textPoint(root:HTMLElement,offset:number):[Node,number]{
 if(root.lastElementChild?.tagName==='BR'&&root.textContent?.length===offset){
  return [root,root.childNodes.length-1];
 }
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
 for(let node=walker.nextNode();node;node=walker.nextNode()){
  const size=node.textContent?.length??0;
  if(offset<=size)return [node,offset];
  offset-=size;
 }
 return [root,root.childNodes.length];
}

export default function ProposalDiffEditor({before,value,readOnly,onChange,onComposing}:{
 before:string;value:string;readOnly:boolean;onChange:(value:string)=>void;onComposing:(value:boolean)=>void;
}){
 const root=useRef<HTMLDivElement>(null);
 const composing=useRef(false);
 const rendered=useRef<{before:string;value:string}|null>(null);

 useLayoutEffect(()=>{
  const editor=root.current;
  if(!editor||composing.current)return;
  if(rendered.current?.before===before&&rendered.current.value===value)return;
  const selection=document.getSelection();
  const anchor=selectionOffset(editor,selection?.anchorNode??null,selection?.anchorOffset??0);
  const focus=selectionOffset(editor,selection?.focusNode??null,selection?.focusOffset??0);
  const content=document.createDocumentFragment();
  for(const part of textDiff(before,value)){
   if(part.kind==='remove')continue;
   if(part.kind==='add'){
    const mark=document.createElement('ins');mark.textContent=part.text;content.append(mark);
   }else content.append(part.text);
  }
  if(value.endsWith('\n'))content.append(document.createElement('br'));
  editor.replaceChildren(content);
  rendered.current={before,value};
  if(selection&&anchor!==null&&focus!==null){
   selection.setBaseAndExtent(...textPoint(editor,anchor),...textPoint(editor,focus));
  }
 });

 useEffect(()=>{
  const editor=root.current;
  if(!editor||readOnly)return;
  function insert(text:string){
   const selection=document.getSelection();
   if(!editor||!selection?.rangeCount||!editor.contains(selection.anchorNode)||!editor.contains(selection.focusNode))return;
   const range=selection.getRangeAt(0);
   range.deleteContents();
   const node=document.createTextNode(text);
   range.insertNode(node);
   selection.collapse(node,node.length);
   rendered.current=null;
   onChange(editor.textContent??'');
  }
  function lineBreak(event:InputEvent){
   if(!composing.current&&['insertParagraph','insertLineBreak'].includes(event.inputType)){
    event.preventDefault();insert('\n');
   }
  }
  function paste(event:ClipboardEvent){
   event.preventDefault();insert((event.clipboardData?.getData('text/plain')??'').replace(/\r\n?/g,'\n'));
  }
  editor.addEventListener('beforeinput',lineBreak);
  editor.addEventListener('paste',paste);
  return()=>{editor.removeEventListener('beforeinput',lineBreak);editor.removeEventListener('paste',paste);};
 },[onChange,readOnly]);

 return <div ref={root} className="proposal-body-diff" role="textbox" aria-label="正文" aria-multiline
  aria-readonly={readOnly} tabIndex={0} contentEditable={readOnly?false:'plaintext-only'}
  onDrop={event=>event.preventDefault()}
  onInput={event=>{
   if(readOnly)return;
   rendered.current=null;
   onChange(event.currentTarget.textContent??'');
  }}
  onCompositionStart={()=>{composing.current=true;onComposing(true);}}
  onCompositionEnd={event=>{
   composing.current=false;onComposing(false);
   if(!readOnly){rendered.current=null;onChange(event.currentTarget.textContent??'');}
  }}/>;
}
