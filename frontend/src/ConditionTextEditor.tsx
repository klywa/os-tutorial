import {useId,useLayoutEffect,useRef,useState,type KeyboardEvent} from 'react';
import {EntityChip,useCards} from './EntityCards';
import {splitEntities} from './entityText';
import {conditionCompletion,conditionPair,normalizeConditionInput,utteranceSlotCompletion,utteranceSlotInput,type ConditionEditingConfig} from './conditionEditing';
import './conditionEditor.css';

export default function ConditionTextEditor({value,onChange,config,label,rows=4,autoFocus,readOnly,disabled,slots=false,textareaRef,onFocus,dataId,onEditorKeyDown}:{
 value:string;onChange:(value:string)=>void;config:ConditionEditingConfig;label:string;rows?:number;autoFocus?:boolean;readOnly?:boolean;disabled?:boolean;
 slots?:boolean;textareaRef?:(node:HTMLTextAreaElement|null)=>void;onFocus?:(node:HTMLTextAreaElement)=>void;dataId?:string;
 onEditorKeyDown?:(event:KeyboardEvent<HTMLTextAreaElement>)=>void;
}){
 const input=useRef<HTMLTextAreaElement>(null),mirror=useRef<HTMLDivElement>(null),options=useRef<HTMLDivElement>(null);
 const composing=useRef(false),pendingSelection=useRef<{start:number;end:number}|null>(null),id=useId(),cards=useCards();
 const [caret,setCaret]=useState<number|null>(null),[dot,setDot]=useState<number|null>(null),[active,setActive]=useState(0);
 const [hovered,setHovered]=useState<number|null>(null),[position,setPosition]=useState({left:0,top:0,above:false});
 const findChoices=slots?utteranceSlotCompletion:conditionCompletion;
 const candidate=caret===null||dot===null||readOnly||disabled?null:findChoices(value,caret,config);
 const completion=candidate?.dot===dot?candidate:null;
 const variable=!!completion&&'variable' in completion;
 const snippet=!!completion&&'snippet' in completion;
 const pair=caret===null||slots?[]:conditionPair(value,caret);
 const selected=Math.min(active,Math.max(0,(completion?.choices.length??0)-1));

 function syncMirror(){
  const field=input.current,view=mirror.current;
  if(!field||!view)return;
  view.style.width=field.clientWidth+2+'px';
  view.scrollTop=field.scrollTop;
  view.scrollLeft=field.scrollLeft;
 }
 function positionMenu(){
  const field=input.current,view=mirror.current,list=options.current;
  if(!field||!view||!list||caret===null)return;
  const walker=document.createTreeWalker(view,NodeFilter.SHOW_TEXT);
  let remaining=caret,node=walker.nextNode();
  while(node&&remaining>(node.textContent?.length??0)){
   remaining-=node.textContent?.length??0;
   node=walker.nextNode();
  }
  const bounds=field.getBoundingClientRect(),range=document.createRange();
  if(node){range.setStart(node,remaining);range.collapse(true);}
  const point=node?range.getBoundingClientRect():bounds;
  const lineBottom=Math.min(bounds.bottom,Math.max(bounds.top+20,point.bottom));
  const above=lineBottom+list.offsetHeight+8>window.innerHeight&&point.top>list.offsetHeight;
  const next={left:Math.max(0,Math.min(point.left-bounds.left,bounds.width-list.offsetWidth)),
   top:above?point.top-bounds.top-list.offsetHeight-4:lineBottom-bounds.top+4,above};
  setPosition(current=>current.left===next.left&&current.top===next.top&&current.above===next.above?current:next);
 }
 useLayoutEffect(()=>{
  const field=input.current;
  if(!field)return;
  const observer=new ResizeObserver(()=>{syncMirror();setHovered(null);});
  observer.observe(field);
  return ()=>observer.disconnect();
 },[]);
 useLayoutEffect(()=>{
  if(input.current&&pendingSelection.current){
   const {start,end}=pendingSelection.current;
   input.current.setSelectionRange(start,end);
   pendingSelection.current=null;
  }
  syncMirror();
  positionMenu();
  const list=options.current,option=list?.querySelector<HTMLElement>('[aria-selected=true]');
  if(list&&option){
   if(option.offsetTop<list.scrollTop)list.scrollTop=option.offsetTop;
   else if(option.offsetTop+option.offsetHeight>list.scrollTop+list.clientHeight)list.scrollTop=option.offsetTop+option.offsetHeight-list.clientHeight;
  }
 });

 function apply(next:string,index:number,offer=false,end=index){
  if(next!==input.current?.value||end!==index)pendingSelection.current={start:index,end};
  setCaret(index===end?index:null);
  setDot(offer?findChoices(next,index,config)?.dot??null:null);
  setActive(0);
  onChange(next);
 }
 function update(field:HTMLTextAreaElement){
  if(composing.current){onChange(field.value);return;}
  const position=field.selectionStart,collapsed=position===field.selectionEnd;
  const value=slots?field.value:normalizeConditionInput(field.value);
  const next=collapsed?utteranceSlotInput(value,position,slots):{value,caret:position};
  apply(next.value,next.caret,collapsed);
 }
 function pick(index:number){
  const option=completion?.choices[index];
  if(!option||!completion)return;
  const insert=option.insert??option.label;
  const start=completion.start;
  apply(value.slice(0,start)+insert+value.slice(completion.end),
   start+(option.selection?.start??insert.length),false,start+(option.selection?.end??insert.length));
 }
 function keyDown(event:KeyboardEvent<HTMLTextAreaElement>){
  if(composing.current||event.nativeEvent.isComposing||event.keyCode===229)return;
  if(completion&&event.key==='Escape'){event.preventDefault();event.stopPropagation();setDot(null);return;}
  if(completion?.choices.length&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.shiftKey){
   if(event.key==='ArrowUp'||event.key==='ArrowDown'){
    event.preventDefault();
    setActive((selected+(event.key==='ArrowDown'?1:-1)+completion.choices.length)%completion.choices.length);
    return;
   }
   if(event.key==='Enter'||event.key==='Tab'){event.preventDefault();pick(selected);return;}
  }
  onEditorKeyDown?.(event);
 }
 const [open,close]=pair;
 function inside(start:number){return close!==undefined&&start>open&&start<close;}
 let offset=0;
 const marked=slots?value:splitEntities(value,cards).map(token=>{
  const start=offset;
  offset+=token.text.length;
  if(token.ids)return <span key={start} className={inside(start)?'condition-active-range':undefined} data-condition-entity={start}><EntityChip ids={token.ids} label={token.text} mirrorHover={hovered===start}/></span>;
  const splits=[start,...[open,open+1,close,close+1].filter(index=>index>start&&index<offset),offset];
  return [...new Set(splits)].map((index,i,points)=>{
   if(i===points.length-1)return null;
   const text=value.slice(index,points[i+1]);
   if(pair.includes(index))return <span key={index} className={pair.length===2?'condition-matching-bracket':'condition-unmatched-bracket'}>{text}</span>;
   return inside(index)?<span key={index} className="condition-active-range">{text}</span>:text;
  });
 });
 return <div className="condition-code-editor">
  <div className="condition-code-mirror" ref={mirror} aria-hidden="true">{marked}{'\n'}</div>
  <textarea ref={node=>{input.current=node;textareaRef?.(node);}} aria-label={label} rows={rows} autoFocus={autoFocus} readOnly={readOnly} disabled={disabled} data-id={dataId} spellCheck={false}
   aria-autocomplete="list" aria-controls={completion?id:undefined} aria-activedescendant={completion?.choices.length?id+'-'+selected:undefined}
   value={value} onChange={event=>update(event.currentTarget)} onKeyDown={keyDown}
   onFocus={event=>{setCaret(event.currentTarget.selectionStart);onFocus?.(event.currentTarget);}}
   onCompositionStart={()=>{composing.current=true;setDot(null);}}
   onCompositionEnd={event=>{composing.current=false;update(event.currentTarget);}}
   onSelect={event=>{
    const field=event.currentTarget,index=field.selectionStart;
    setCaret(index===field.selectionEnd?index:null);
    if(dot!==null&&(index!==field.selectionEnd||findChoices(field.value,index,config)?.dot!==dot))setDot(null);
   }}
   onBlur={()=>{setDot(null);setCaret(null);}}
   onScroll={()=>{syncMirror();positionMenu();setHovered(null);}}
   onPointerLeave={()=>setHovered(null)} onPointerMove={event=>{
    const {clientX:x,clientY:y}=event;
    const hit=Array.from(mirror.current?.querySelectorAll<HTMLElement>('[data-condition-entity]')??[]).find(element=>
     Array.from(element.getClientRects()).some(rect=>x>=rect.left&&x<=rect.right&&y>=rect.top&&y<=rect.bottom));
    setHovered(hit?Number(hit.dataset.conditionEntity):null);
   }}/>
  {completion&&<div className="condition-field-options" ref={options} style={{left:position.left,top:position.top}} id={id} role="listbox" aria-label={snippet?'条件片段候选':slots?'话术变量候选':variable?'条件变量候选':'条件字段候选'}>
   {completion.choices.map((field,index)=><button type="button" key={field.label} role="option" id={id+'-'+index} aria-selected={selected===index}
    onMouseDown={event=>event.preventDefault()} onClick={()=>pick(index)}>{field.label}
    {(field.type||field.guard)&&<small>{field.type}{field.guard?' · 可能需要守卫':''}</small>}</button>)}
   {!completion.choices.length&&<p role="status">{snippet?'没有匹配的条件片段':variable?'没有匹配的变量':'没有匹配的字段'}</p>}
  </div>}
 </div>;
}
