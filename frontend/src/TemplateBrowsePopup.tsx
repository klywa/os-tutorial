import {useEffect,useRef,type ReactNode} from 'react';
import {ReadingCards} from './EntityCards';

export default function TemplateBrowsePopup({title,children,error,onClose,busy}:{
 title:string;children:ReactNode;error?:string;onClose:()=>void;busy:boolean;
}){
 const panel=useRef<HTMLElement>(null);
 const active=useRef({onClose,busy});active.current={onClose,busy};
 function dismiss(){
  if(active.current.busy||panel.current?.querySelector('[data-template-dirty]'))return false;
  active.current.onClose();
  return true;
 }
 useEffect(()=>{
  const previous=document.activeElement;
  const node=panel.current;
  node?.focus({preventScroll:true});
  let lastFocused:HTMLElement|null=node;
  function focus(event:FocusEvent){
   const target=event.target;
   if(!(target instanceof HTMLElement)||!node)return;
   if(node.contains(target)){lastFocused=target;return;}
   if(target.closest('.template-overlay,.entity-popover,.card-completion'))return;
   if(!dismiss())(lastFocused?.isConnected?lastFocused:node).focus({preventScroll:true});
  }
  document.addEventListener('focusin',focus);
  return ()=>{
   document.removeEventListener('focusin',focus);
   if(previous instanceof HTMLElement&&document.activeElement===document.body)previous.focus({preventScroll:true});
  };
 },[]);
 return <div className="template-browse-popup-layer">
  <div className="template-browse-popup-backdrop" onPointerDown={event=>event.preventDefault()} onClick={()=>dismiss()}/>
  <section ref={panel} tabIndex={-1} className="template-detail-panel template-browse-popup" role="dialog" aria-label={title}
   onKeyDown={event=>{
    if(event.key==='Escape'&&!event.defaultPrevented&&event.target instanceof Node&&event.currentTarget.contains(event.target)){
     event.preventDefault();event.stopPropagation();dismiss();
    }
   }}>
   <header><strong>{title}</strong><button type="button" aria-label="关闭模板详情" onClick={()=>dismiss()}>关闭</button></header>
   {error&&<p className="error" role="alert">{error}</p>}
   <ReadingCards cardSearch alwaysShowDock><div className="template-card-stack template-browse-popup-cards">{children}</div></ReadingCards>
  </section>
 </div>;
}
