import {useEffect,useId,useRef,useState} from 'react';

type Choice={value:string;label:string};
export default function SearchSelect({label,value,choices,onChange}:{label:string;value:string;choices:Choice[];onChange:(value:string)=>void}){
 const id=useId(),root=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null),list=useRef<HTMLDivElement>(null),composing=useRef(false);
 const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[active,setActive]=useState(0);
 const options=[{value:'',label:'全部'+label},...choices];
 const matched=options.filter(option=>option.label.toLowerCase().includes(query.trim().toLowerCase()));
 const selected=options.find(option=>option.value===value)?.label||value;
 const current=Math.min(active,matched.length-1);
 function close(){setOpen(false);setQuery('');}
 function expand(){setQuery('');setActive(Math.max(0,options.findIndex(option=>option.value===value)));setOpen(true);}
 function choose(option:Choice){onChange(option.value);close();input.current?.focus();}
 useEffect(()=>{
  if(!open)return;
  function outside(event:PointerEvent){if(!root.current?.contains(event.target as Node))close();}
  document.addEventListener('pointerdown',outside);
  return ()=>document.removeEventListener('pointerdown',outside);
 },[open]);
 useEffect(()=>{if(open)list.current?.querySelector('[data-active="true"]')?.scrollIntoView({block:'nearest'});},[open,current,query]);
 return <div className="search-select" ref={root} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))close();}}>
  <div className="search-select-control"><input ref={input} role="combobox" aria-label={label} aria-expanded={open} aria-autocomplete="list" aria-controls={open?id:undefined} aria-activedescendant={open&&current>=0?`${id}-${current}`:undefined} autoComplete="off" placeholder={open?'输入搜索'+label:'全部'+label} value={open?query:selected} onFocus={()=>{if(!open)expand();}} onClick={()=>{if(!open)expand();}} onChange={event=>{setQuery(event.target.value);setActive(0);setOpen(true);}} onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;}} onKeyDown={event=>{
   if(composing.current||event.nativeEvent.isComposing||event.keyCode===229)return;
   if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();close();}
   if(event.key==='ArrowDown'||event.key==='ArrowUp'){
    event.preventDefault();if(!open){expand();return;}
    setActive(Math.max(0,Math.min(matched.length-1,current+(event.key==='ArrowDown'?1:-1))));
   }
   if(event.key==='Enter'){event.preventDefault();if(!open)expand();else if(current>=0)choose(matched[current]);}
  }}/><button type="button" className="search-select-toggle" aria-label={'展开'+label+'选项'} aria-expanded={open} onMouseDown={event=>event.preventDefault()} onClick={()=>{if(open)close();else expand();input.current?.focus();}}>▾</button></div>
  {open&&<div className="search-select-options" role="listbox" aria-label={label+'选项'} id={id} ref={list}>{matched.map((option,index)=><button type="button" role="option" aria-selected={option.value===value} data-active={index===current} id={`${id}-${index}`} key={option.value} tabIndex={-1} title={option.label} onMouseDown={event=>event.preventDefault()} onClick={()=>choose(option)}>{option.label}</button>)}{!matched.length&&<div className="search-select-empty" role="status">无匹配选项</div>}</div>}
 </div>;
}
