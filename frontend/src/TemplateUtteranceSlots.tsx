import {useMemo} from 'react';
import rawCatalog from '../../src/condition/catalog.json?raw';
import {listPaths,type ConditionCatalog} from './templateRules';
import {utteranceReferences,type TemplateEvent} from './templates';

const defaultCatalog:ConditionCatalog=JSON.parse(rawCatalog);
const commonPaths=['玩家.主C','对局.当前对手.主C'];

export function invalidDirectPaths(text:string,event?:TemplateEvent,catalog=defaultCatalog){
 const refs=utteranceReferences(text).filter(path=>/^[\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*$/u.test(path));
 if(!refs.length)return [];
 const paths=new Map(listPaths(event,catalog).map(({path,type})=>[path,type]));
 const parameters=new Set(event?.parameters.map(({key})=>key));
 return refs.filter(path=>{
  if(parameters.has(path))return false;
  const type=paths.get(path.replace(/\.name$/u,'.名称'));
  return !type||type.startsWith('Array<')||type==='对局'||type==='商店';
 });
}

export function TemplateUtteranceSlots({event,catalog=defaultCatalog,disabled,onInsert}:{
 event?:TemplateEvent;catalog?:ConditionCatalog;disabled?:boolean;onInsert:(path:string)=>void;
}){
 const paths=useMemo(()=>listPaths(event,catalog).filter(({path,type})=>
  path.includes('.')&&type.split('|').every(kind=>{
   const fields=catalog.types[catalog.aliases[kind]??kind];
   return fields?.名称==='string'||kind==='阵容'&&!!fields?.阵容名;
  })).map(({path})=>path),[event,catalog]);
 const common=commonPaths.filter(path=>paths.includes(path));
 const other=paths.filter(path=>!common.includes(path));
 return <>
  {common.map(path=><button key={path} type="button" disabled={disabled} onClick={()=>onInsert(path)}>{path}</button>)}
  {!!other.length&&<select aria-label="插入其他实体槽位" value="" disabled={disabled}
   onChange={event=>{if(event.target.value)onInsert(event.target.value);}}>
   <option value="">其他实体槽位…</option>
   {other.map(path=><option key={path} value={path}>{path}</option>)}
  </select>}
 </>;
}
