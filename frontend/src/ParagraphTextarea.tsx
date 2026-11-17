import {useLayoutEffect,useMemo,useRef,type ComponentPropsWithoutRef} from 'react';
import {paragraphKeyParts,paragraphKeyRanges} from './paragraphKeys';
import './paragraphKeys.css';

const textMetrics=[
 'fontFamily','fontSize','fontWeight','fontStyle','fontStretch','fontVariant','lineHeight',
 'letterSpacing','wordSpacing','tabSize','textIndent','textAlign','textTransform','direction',
 'paddingTop','paddingRight','paddingBottom','paddingLeft','whiteSpace','overflowWrap','wordBreak',
] as const;

export function ParagraphTextarea({value,onScroll,...props}:
 ComponentPropsWithoutRef<'textarea'>&{value:string}){
 const input=useRef<HTMLTextAreaElement>(null);
 const viewport=useRef<HTMLSpanElement>(null);
 const text=useRef<HTMLSpanElement>(null);
 const parts=useMemo(()=>paragraphKeyParts(value,paragraphKeyRanges(value)),[value]);

 function syncScroll(){
  const field=input.current,layer=viewport.current;
  if(field&&layer){layer.scrollTop=field.scrollTop;layer.scrollLeft=field.scrollLeft;}
 }
 useLayoutEffect(()=>{
  const field=input.current,layer=viewport.current,paint=text.current;
  if(!field||!layer||!paint)return;
  function syncGeometry(){
   if(!field||!layer||!paint)return;
   const style=getComputedStyle(field);
   for(const key of textMetrics)paint.style[key]=style[key];
   layer.style.left=`${field.offsetLeft+field.clientLeft}px`;
   layer.style.top=`${field.offsetTop+field.clientTop}px`;
   layer.style.width=`${field.clientWidth}px`;
   layer.style.height=`${field.clientHeight}px`;
   syncScroll();
  }
  syncGeometry();
  const observer=new ResizeObserver(syncGeometry);
  observer.observe(field);
  return ()=>observer.disconnect();
 },[]);
 useLayoutEffect(syncScroll,[value]);

 return <span className="paragraph-key-input">
  <textarea {...props} ref={input} value={value} onScroll={event=>{syncScroll();onScroll?.(event);}}/>
  <span ref={viewport} className="paragraph-key-viewport" aria-hidden="true">
   <span ref={text} className="paragraph-key-text">
    {parts.map((part,i)=>part.highlight?<mark key={i}>{part.text}</mark>:part.text)}
    {value.endsWith('\n')?'\u200b':null}
   </span>
  </span>
 </span>;
}
