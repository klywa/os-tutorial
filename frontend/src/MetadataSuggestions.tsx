import {createContext,useSyncExternalStore} from 'react';
import './metadataSuggestions.css';

export type MetadataScope='card-tags'|'template-tags'|'template-batches';
export const TemplateMetadataChoices=createContext({tags:[] as string[],batch:[] as string[]});
export const templateMetadataScope=(label:string):MetadataScope=>label==='批次'?'template-batches':'template-tags';
export const lastMetadataTerm=(input:string)=>input.split(/[,，、\r\n]/u).at(-1)?.trim()??'';
export const replaceLastMetadataTerm=(input:string,value:string)=>input.replace(/[^,，、\r\n]*$/u,value);

const prefix='wxq.metadata-recent.';
const history=new Map<MetadataScope,string[]>();
const subscribers=new Set<()=>void>();
const empty:string[]=[];

function recent(scope:MetadataScope){
 const cached=history.get(scope);
 if(cached)return cached;
 let values:unknown;
 try{values=JSON.parse(localStorage.getItem(prefix+scope)??'[]');}catch{values=[];}
 const result=Array.isArray(values)?values.filter((value):value is string=>typeof value==='string'):[];
 history.set(scope,result);
 return result;
}

function subscribe(callback:()=>void){
 subscribers.add(callback);
 return ()=>{subscribers.delete(callback);};
}

const normalize=(value:string)=>value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/gu,'');
export function matchMetadataChoices(choices:string[],query:string,recency:string[]){
 const chars=Array.from(normalize(query));
 const recentRank=new Map(recency.map((value,index)=>[value,index]));
 return [...new Set(choices)].filter(value=>{
  const candidate=normalize(value);
  let offset=0;
  return chars.every(char=>{
   const found=candidate.indexOf(char,offset);
   offset=found+char.length;
   return found!==-1;
  });
 }).sort((a,b)=>(recentRank.get(a)??recency.length)-(recentRank.get(b)??recency.length)||a.localeCompare(b,'zh-CN'));
}

export default function MetadataSuggestions({scope,choices,query,selected=[],onPick,label}:{
 scope:MetadataScope;choices:string[];query:string;selected?:string[];onPick:(value:string)=>void;label:string;
}){
 const recency=useSyncExternalStore(subscribe,()=>recent(scope),()=>empty);
 const matches=matchMetadataChoices(choices,query,recency);
 if(!matches.length)return null;
 return <span className="metadata-suggestions" role="group" aria-label={label}>
  {matches.map(value=><button type="button" key={value} aria-pressed={selected.includes(value)} onClick={()=>{
   const next=[value,...recent(scope).filter(item=>item!==value)].slice(0,100);
   history.set(scope,next);
   try{localStorage.setItem(prefix+scope,JSON.stringify(next));}catch{/* In-memory recency remains available. */}
   subscribers.forEach(callback=>callback());
   onPick(value);
  }}>{value}</button>)}
 </span>;
}
