import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {useAuth} from './auth';
import {cardCategories,checkCardVersion,loadCardCatalog} from './cardCatalog';
import {cardQuery,completeCardName,rankCards} from './cardCompletionSearch';
import {activeWorkspace} from './readerCache';
import {onSessionReset} from './sessionRequest';
import type {CardSummary} from './types';
import './cardCompletion.css';

type Field = HTMLInputElement|HTMLTextAreaElement;
type Active = {field:Field;query:NonNullable<ReturnType<typeof cardQuery>>};
type Catalog = {cards:CardSummary[]}|{error:true};
const popupId='card-completion-options';
const eligible=(field:EventTarget|null):field is Field=>
 (field instanceof HTMLTextAreaElement||field instanceof HTMLInputElement&&field.type==='text')
 &&field.hasAttribute('data-card-completion')&&!field.readOnly&&!field.matches(':disabled');
const queryAt=(field:Field)=>cardQuery(field.value,field.selectionStart??0,field.selectionEnd??0);

export default function CardCompletion(){
 const {session:{mode}}=useAuth();
 const [active,setActive]=useState<Active|null>(null);
 const [catalog,setCatalog]=useState<Catalog|null>(null);
 const [index,setIndex]=useState(0);
 const current=useRef<Active|null>(null);
 const composing=useRef(false);
 const pending=useRef<Promise<CardSummary[]>|null>(null);
 const menu=useRef<HTMLDivElement>(null);
 const field=active?.field;
 const cards=useMemo(()=>active&&catalog&&'cards' in catalog?rankCards(catalog.cards,active.query.text):[],[active,catalog]);

 function close(){
  current.current=null;
  pending.current=null;
  setActive(null);
 }
 function confirm(card:CardSummary){
  const selection=current.current;
  const target=selection?.field;
  const query=target&&eligible(target)&&document.activeElement===target?queryAt(target):null;
  close();
  if(!target||!query||query.start!==selection.query.start||query.text!==selection.query.text)return;
  const {value,caret}=completeCardName(target.value,query,card.name);
  // Use the native setter so React sees an input change and runs the field's existing handler.
  const prototype=target instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype,'value')!.set!.call(target,value);
  target.setSelectionRange(caret,caret);
  target.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertReplacementText',data:card.name}));
 }

 useEffect(()=>{
  function load(){
   const workspace=activeWorkspace();
   if(mode!=='public')return loadCardCatalog(workspace);
   return checkCardVersion().then(()=>workspace===activeWorkspace()?loadCardCatalog(workspace):[]);
  }
  function update(target:EventTarget|null,allowOpen:boolean){
   if(!eligible(target)||document.activeElement!==target)return;
   const previous=current.current;
   const query=queryAt(target);
   if(!query){if(previous?.field===target)close();return;}
   if(!allowOpen&&(previous?.field!==target||previous.query.start!==query.start)){
    if(previous)close();
    return;
   }
   if(previous?.field===target&&previous.query.start===query.start&&previous.query.end===query.end&&previous.query.text===query.text)return;
   const start=previous?.field!==target||previous.query.start!==query.start;
   const next={field:target,query};
   current.current=next;
   setActive(next);
   setIndex(0);
   if(start){
    setCatalog(null);
    const request=pending.current=load();
    void request.then(
     cards=>{if(pending.current===request)setCatalog({cards});},
     ()=>{if(pending.current===request)setCatalog({error:true});},
    );
   }
  }
  const input=(event:Event)=>{
   const change=event as InputEvent;
   if(!composing.current&&!change.isComposing&&change.inputType!=='insertReplacementText')update(event.target,true);
  };
  const compositionStart=()=>{composing.current=true;close();};
  const compositionEnd=(event:Event)=>{composing.current=false;update(event.target,true);};
  const selection=()=>{if(current.current&&!composing.current)update(document.activeElement,false);};
  const blur=(event:FocusEvent)=>{if(current.current?.field===event.target)close();composing.current=false;};
  const invalidate=()=>close();
  const unsubscribe=onSessionReset(invalidate);
  document.addEventListener('input',input);
  document.addEventListener('compositionstart',compositionStart);
  document.addEventListener('compositionend',compositionEnd);
  document.addEventListener('selectionchange',selection);
  document.addEventListener('focusout',blur);
  window.addEventListener('reader-workspace',invalidate);
  window.addEventListener('cards-version-changed',invalidate);
  return ()=>{
   unsubscribe();
   document.removeEventListener('input',input);
   document.removeEventListener('compositionstart',compositionStart);
   document.removeEventListener('compositionend',compositionEnd);
   document.removeEventListener('selectionchange',selection);
   document.removeEventListener('focusout',blur);
   window.removeEventListener('reader-workspace',invalidate);
   window.removeEventListener('cards-version-changed',invalidate);
  };
 },[mode]);

 useLayoutEffect(()=>{
  if(!field||!menu.current)return;
  const target=field;
  const popup=menu.current;
  function position(){
   if(!target.isConnected||!eligible(target)||document.activeElement!==target){close();return;}
   const rect=target.getBoundingClientRect();
   const viewport=window.visualViewport;
   const x=viewport?.offsetLeft??0,y=viewport?.offsetTop??0;
   const width=viewport?.width??window.innerWidth,height=viewport?.height??window.innerHeight;
   const above=rect.top-y-12,below=y+height-rect.bottom-12;
   const overlay=Math.max(above,below)<48;
   const up=below<Math.min(280,popup.scrollHeight)&&above>below;
   const popupWidth=Math.min(Math.max(rect.width,240),440,width-16);
   popup.style.width=popupWidth+'px';
   popup.style.maxHeight=Math.max(0,Math.min(280,overlay?height/2:up?above:below))+'px';
   popup.style.left=Math.max(x+8,Math.min(rect.left,x+width-popupWidth-8))+'px';
   popup.style.top=(overlay?y+height-popup.offsetHeight-8:up?Math.max(y+8,rect.top-popup.offsetHeight-4):rect.bottom+4)+'px';
  }
  popup.showPopover?.();
  position();
  const observer=new ResizeObserver(position);
  observer.observe(target);
  observer.observe(popup);
  const visibility=new IntersectionObserver(([entry])=>{if(!entry.isIntersecting)close();});
  visibility.observe(target);
  document.addEventListener('scroll',position,true);
  window.addEventListener('resize',position);
  window.visualViewport?.addEventListener('resize',position);
  window.visualViewport?.addEventListener('scroll',position);
  return ()=>{
   observer.disconnect();
   visibility.disconnect();
   document.removeEventListener('scroll',position,true);
   window.removeEventListener('resize',position);
   window.visualViewport?.removeEventListener('resize',position);
   window.visualViewport?.removeEventListener('scroll',position);
  };
 },[field]);

 useLayoutEffect(()=>{
  if(!field)return;
  field.setAttribute('aria-controls',popupId);
  field.setAttribute('aria-autocomplete','list');
  return ()=>{field.removeAttribute('aria-controls');field.removeAttribute('aria-autocomplete');};
 },[field]);
 useLayoutEffect(()=>{
  if(!field||!cards.length)return;
  const id=popupId+'-'+index;
  field.setAttribute('aria-activedescendant',id);
  const option=document.getElementById(id),popup=menu.current;
  if(option&&popup){
   const row=option.getBoundingClientRect(),bounds=popup.getBoundingClientRect();
   if(row.top<bounds.top)popup.scrollTop+=row.top-bounds.top;
   else if(row.bottom>bounds.bottom)popup.scrollTop+=row.bottom-bounds.bottom;
  }
  return ()=>field.removeAttribute('aria-activedescendant');
 },[field,cards,index]);

 useEffect(()=>{
  if(!field)return;
  function keydown(event:KeyboardEvent){
   if(event.target!==current.current?.field||event.isComposing||composing.current||event.keyCode===229)return;
   if(event.key==='Escape'){
    event.preventDefault();
    event.stopPropagation();
    close();
   }else if(cards.length&&(event.key==='ArrowDown'||event.key==='ArrowUp'||event.key==='Enter')
    &&!event.altKey&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey){
    event.preventDefault();
    event.stopPropagation();
    if(event.key==='Enter')confirm(cards[index]);
    else setIndex(value=>Math.max(0,Math.min(cards.length-1,value+(event.key==='ArrowDown'?1:-1))));
   }
  }
  document.addEventListener('keydown',keydown,true);
  return ()=>document.removeEventListener('keydown',keydown,true);
 },[field,cards,index]);

 if(!field)return null;
 return createPortal(<div ref={menu} className="card-completion" popover="manual">
  <div id={popupId} role="listbox" aria-label="卡牌候选">
   {cards.map((card,i)=><div key={card.id} id={popupId+'-'+i} role="option" aria-selected={i===index}
    className="card-completion-option" onMouseDown={e=>e.preventDefault()} onClick={()=>confirm(card)}>
    <div className="card-completion-heading"><strong>{card.name}</strong><small>{cardCategories[card.category]}{card.awakened?' · 觉醒':''}{card.faction.name&&' · '+card.faction.name}</small></div>
    {card.effect&&<div className="card-completion-effect">{card.effect}</div>}
   </div>)}
  </div>
  {!cards.length&&<div className="card-completion-status" role="status">{!catalog?'正在载入卡牌…':'error' in catalog?'卡牌加载失败，重新输入 # 重试。':'没有匹配的卡牌。'}</div>}
 </div>,field.closest('dialog')??document.body);
}
