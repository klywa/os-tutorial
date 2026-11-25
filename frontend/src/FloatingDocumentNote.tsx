import {useEffect,useId,useRef,useState,type PointerEvent} from 'react';
import {createPortal} from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './floatingDocumentNote.css';

type Point={x:number;y:number};
type Props={title:string;value:string;editable:boolean;disabled?:boolean;onDirty?:(dirty:boolean)=>void;onSave:(text:string)=>Promise<void>};
const formatActions=[
 {label:'粗体',icon:'B',shortcut:'b',before:'**',after:'**',placeholder:'文字'},
 {label:'斜体',icon:'I',shortcut:'i',before:'_',after:'_',placeholder:'文字'},
 {label:'标题',icon:'H',before:'## ',line:true,placeholder:'标题'},
 {label:'项目列表',icon:'•',before:'- ',line:true,placeholder:'列表项'},
 {label:'待办事项',icon:'☐',before:'- [ ] ',line:true,placeholder:'待办事项'},
 {label:'链接',icon:'↗',shortcut:'k',before:'[',after:'](https://)',placeholder:'链接文字'},
];

function passWheelToPage(event:WheelEvent,panel:HTMLElement){
 if(event.defaultPrevented||event.ctrlKey||!event.deltaY||Math.abs(event.deltaX)>Math.abs(event.deltaY))return;
 const canScroll=(element:Element)=>{
  const atBottom=element.scrollHeight-element.clientHeight-element.scrollTop<1;
  return element.scrollHeight>element.clientHeight&&
   (event.deltaY>0?!atBottom:element.scrollTop>0)&&
   (element===document.scrollingElement||/^(auto|scroll)$/.test(getComputedStyle(element).overflowY));
 };
 for(let node=event.target instanceof Element?event.target:null;node&&panel.contains(node);node=node.parentElement){
  if(canScroll(node))return;
 }
 const behind=document.elementsFromPoint(event.clientX,event.clientY).find(node=>
  !panel.contains(node)&&!node.closest('.floating-document-note-button'));
 for(let node=behind??null;node;node=node.parentElement){
  if(!canScroll(node))continue;
  if(!event.cancelable)return;
  event.preventDefault();
  const scale=event.deltaMode===1?16:event.deltaMode===2?node.clientHeight:1;
  node.scrollBy({top:event.deltaY*scale,behavior:'instant'});
  return;
 }
}

export default function FloatingDocumentNote({title,value,editable,disabled,onDirty,onSave}:Props){
 const id=useId(),button=useRef<HTMLButtonElement>(null),input=useRef<HTMLTextAreaElement>(null),panel=useRef<HTMLElement>(null);
 const previousFocus=useRef<HTMLElement|null>(null);
 const pendingSave=useRef<Promise<boolean>|null>(null);
 const [open,setOpen]=useState(false),[draft,setDraft]=useState<{base:string;text:string}>(),[position,setPosition]=useState<Point>();
 const [saving,setSaving]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
 const [preview,setPreview]=useState(false);
 const pointer=useRef<{id:number;origin:Point;start:Point;moved:boolean}|null>(null),ignoreClick=useRef(false);
 const reportDirty=useRef(onDirty);reportDirty.current=onDirty;
 const text=draft?.text??value,dirty=text!==value;
 useEffect(()=>()=>reportDirty.current?.(false),[]);
 useEffect(()=>{reportDirty.current?.(dirty);if(!dirty&&draft)setDraft(undefined);},[dirty,draft]);
 useEffect(()=>{if(open&&!preview)input.current?.focus();},[open,preview]);
 useEffect(()=>{
  const node=panel.current;
  if(!open||!node)return;
  const wheel=(event:WheelEvent)=>passWheelToPage(event,node);
  node.addEventListener('wheel',wheel,{passive:false});
  return ()=>node.removeEventListener('wheel',wheel);
 },[open]);
 useEffect(()=>{
  if(!open)return;
  const leave=()=>void close(false);
  const clickOutside=(event:globalThis.PointerEvent)=>{
   const target=event.target;
   if(target instanceof Node&&!panel.current?.contains(target)&&!button.current?.contains(target))leave();
  };
  document.addEventListener('pointerdown',clickOutside,true);
  window.addEventListener('blur',leave);
  return ()=>{
   document.removeEventListener('pointerdown',clickOutside,true);
   window.removeEventListener('blur',leave);
  };
 });

 function start(event:PointerEvent<HTMLButtonElement>){
  if(!event.isPrimary||event.button!==0)return;
  const rect=event.currentTarget.getBoundingClientRect();
  ignoreClick.current=false;
  pointer.current={id:event.pointerId,origin:{x:rect.left,y:rect.top},start:{x:event.clientX,y:event.clientY},moved:false};
  event.currentTarget.setPointerCapture(event.pointerId);
 }
 function move(event:PointerEvent<HTMLButtonElement>){
  const drag=pointer.current;
  if(!drag||drag.id!==event.pointerId)return;
  const dx=event.clientX-drag.start.x,dy=event.clientY-drag.start.y;
  if(!drag.moved&&Math.hypot(dx,dy)<5)return;
  drag.moved=true;
  setPosition({x:drag.origin.x+dx,y:drag.origin.y+dy});
 }
 function end(event:PointerEvent<HTMLButtonElement>){
  if(pointer.current?.id!==event.pointerId)return;
  ignoreClick.current=pointer.current.moved;
  pointer.current=null;
 }
 async function close(restoreFocus:boolean){
  if((dirty||pendingSave.current)&&!await save(false))return;
  setDraft(undefined);onDirty?.(false);setError('');setSaved(false);setOpen(false);setPreview(false);
  if(!restoreFocus)return;
  const previous=previousFocus.current;
  (previous?.isConnected?previous:button.current)?.focus({preventScroll:true});
 }
 function updateText(next:string){
  setDraft(next===value?undefined:{base:draft?.base??value,text:next});
  onDirty?.(next!==value);setError('');setSaved(false);
 }
 function format(action:typeof formatActions[number]){
  const editor=input.current;
  if(!editor||!editable||saving)return;
  editor.focus();
  let {selectionStart:start,selectionEnd:end}=editor;
  if(action.line){
   start=start===0?0:text.lastIndexOf('\n',start-1)+1;
   if(start===end){
    const lineEnd=text.indexOf('\n',end);
    end=lineEnd<0?text.length:lineEnd;
   }
  }
  const selected=text.slice(start,end)||action.placeholder;
  const before=action.before;
  const replacement=action.line
   ?selected.split('\n').map(line=>before+line).join('\n')
   :before+selected+(action.after??'');
  editor.setSelectionRange(start,end);
  // Insert through the browser's edit history so native undo can revert formatting.
  if(!document.execCommand('insertText',false,replacement)){
   editor.setRangeText(replacement,start,end,'end');
   updateText(editor.value);
  }
  if(action.shortcut==='k'){
   const urlStart=start+before.length+selected.length+2;
   editor.setSelectionRange(urlStart,urlStart+'https://'.length);
  }else if(!action.line||start===end){
   editor.setSelectionRange(start+before.length,start+before.length+selected.length);
  }
 }
 async function save(interactive=true):Promise<boolean>{
  if(pendingSave.current)return pendingSave.current;
  if(!dirty)return true;
  if(!editable||disabled){setError('当前无法保存笔记，草稿已保留。');return false;}
  if(draft?.base!==value){
   if(!interactive){setError('文件中的笔记已由其他操作修改，请核对后手动保存。');return false;}
   if(!confirm('文件中的笔记已由其他操作修改。是否用当前草稿替换？'))return false;
  }
  setSaving(true);setError('');setSaved(false);
  const request=Promise.resolve().then(()=>onSave(text)).then(()=>{
   setDraft(undefined);onDirty?.(false);setSaved(true);return true;
  },(error:unknown)=>{
   setError(error instanceof Error?error.message:String(error));return false;
  }).finally(()=>{pendingSave.current=null;setSaving(false);});
  pendingSave.current=request;
  return request;
 }
 const left=position?`clamp(8px, ${position.x}px, calc(100vw - 46px))`:undefined;
 const top=position?`clamp(8px, ${position.y}px, calc(100dvh - 46px))`:undefined;
 return createPortal(<>
  <button ref={button} className="floating-document-note-button" type="button" title="笔记（可拖动）" aria-label="笔记"
   aria-expanded={open} aria-controls={open?id:undefined} style={position?{left,top,right:'auto'}:undefined}
   onMouseDown={event=>{if(!open){previousFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;event.preventDefault();}}}
   onBlur={event=>{if(open&&event.relatedTarget instanceof Node&&!panel.current?.contains(event.relatedTarget))void close(false);}}
   onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
   onClick={event=>{if(ignoreClick.current&&event.detail!==0){ignoreClick.current=false;return;}if(open)void close(true);else setOpen(true);}}>
   <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
    <path d="M5 3h14v13l-5 5H5zM14 21v-5h5M8 8h8M8 12h8"/>
   </svg>
  </button>
  {open&&<section ref={panel} id={id} role="dialog" aria-label="文档笔记" className="floating-document-note"
   onBlur={event=>{
    const next=event.relatedTarget;
    if(next instanceof Node&&!event.currentTarget.contains(next)&&next!==button.current)void close(false);
   }}
   onKeyDown={event=>{
    if(event.defaultPrevented||event.nativeEvent.isComposing)return;
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();void close(true);return;}
    if(!event.ctrlKey&&!event.metaKey||event.altKey)return;
    const key=event.key.toLowerCase();
    if(key==='s'){event.preventDefault();event.stopPropagation();void save();return;}
    if(event.target!==input.current||event.shiftKey)return;
    const action=formatActions.find(item=>item.shortcut===key);
    if(action&&editable&&!saving){event.preventDefault();event.stopPropagation();format(action);}
   }}>
   <header><div><strong>笔记</strong><p className="muted">{title}</p></div><button type="button" aria-label="关闭笔记" onClick={()=>void close(true)} disabled={saving}>×</button></header>
   <form onSubmit={event=>{event.preventDefault();void save();}}>
    <div className="floating-note-tools" role="group" aria-label="笔记编辑工具">
     {editable&&formatActions.map(action=><button key={action.label} type="button" aria-label={action.label}
      title={action.shortcut?`${action.label}（Ctrl/⌘+${action.shortcut.toUpperCase()}）`:action.label}
      disabled={preview||saving} onMouseDown={event=>event.preventDefault()} onClick={()=>format(action)}>{action.icon}</button>)}
     <button type="button" className="floating-note-preview-toggle" aria-pressed={preview} onClick={()=>setPreview(next=>!next)}>{preview?'返回编辑':'预览'}</button>
    </div>
    <textarea hidden={preview} ref={input} aria-label="笔记内容" value={text} readOnly={!editable||saving}
     onChange={event=>updateText(event.target.value)}/>
    {preview&&<div className="floating-note-preview" tabIndex={0} aria-label="笔记预览">
     {text.trim()?<ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>:<p className="muted">暂无笔记内容</p>}
    </div>}
    <footer>
     {error&&<p role="alert">{error}</p>}
     {saved&&<p role="status">已保存到当前文件</p>}
     {!error&&!saved&&dirty&&<p className="muted">有未保存的修改</p>}
     {editable&&<button className="primary" type="submit" title="Ctrl/⌘+S" disabled={!dirty||disabled||saving}>{saving?'正在保存…':'保存'}</button>}
    </footer>
   </form>
  </section>}
 </>,document.body);
}
