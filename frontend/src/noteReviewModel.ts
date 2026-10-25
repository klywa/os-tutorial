import type {KnowledgeDocument,KnowledgeNode} from './types';
import {blockEnd} from './jsonDocument';

export function scopeNodes(body:KnowledgeDocument,id:string){const i=body.nodes.findIndex(n=>n.id===id);return i<0?[]:body.nodes.slice(i,blockEnd(body.nodes,i));}
export type DiffPart={kind:'same'|'add'|'remove';text:string};
export function textDiff(before:string,after:string):DiffPart[]{
 const a=Array.from(before),b=Array.from(after);let prefix=0,suffix=0;
 while(prefix<a.length&&prefix<b.length&&a[prefix]===b[prefix])prefix++;
 while(suffix<a.length-prefix&&suffix<b.length-prefix&&a[a.length-1-suffix]===b[b.length-1-suffix])suffix++;
 const x=a.slice(prefix,a.length-suffix),y=b.slice(prefix,b.length-suffix),out:DiffPart[]=[];
 function push(kind:DiffPart['kind'],text:string){if(!text)return;const last=out.at(-1);if(last?.kind===kind)last.text+=text;else out.push({kind,text});}
 push('same',a.slice(0,prefix).join(''));
 if(x.length*y.length>1_000_000){push('remove',x.join(''));push('add',y.join(''));}
 else{
  const dp=Array.from({length:x.length+1},()=>new Uint32Array(y.length+1));
  for(let i=x.length-1;i>=0;i--)for(let j=y.length-1;j>=0;j--)dp[i][j]=x[i]===y[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
  let i=0,j=0;while(i<x.length||j<y.length){if(i<x.length&&j<y.length&&x[i]===y[j]){push('same',x[i++]);j++;}else if(i<x.length&&(j===y.length||dp[i+1][j]>=dp[i][j+1]))push('remove',x[i++]);else push('add',y[j++]);}
 }
 push('same',suffix?a.slice(a.length-suffix).join(''):'');return out;
}
export type ReviewField={id:string;label:string;collection?:'nodes'|'supporting_nodes';nodeId?:string;key:string;path:string[];oldValue:unknown;newValue:unknown};
const labels:Record<string,string>={title:'标题',key:'名称',value:'正文',level:'标题层级',show_key:'显示名称',separator:'段落间隔',prefix:'前缀',key_suffix:'名称后缀',leading:'篇首格式',semantics:'结构化知识',space:'标题间隔',type:'节点类型'};
export function displayValue(v:unknown){return v===undefined?'（不存在）':typeof v==='string'?v:JSON.stringify(v,null,2);}
export function equalValue(a:unknown,b:unknown){return JSON.stringify(a)===JSON.stringify(b);}
export function hasReviewChanges(draft:KnowledgeDocument,base:KnowledgeDocument,invalid:Record<string,boolean>){return !equalValue(draft,base)||Object.values(invalid).some(Boolean);}
export function reviewFields(old:KnowledgeDocument,current:KnowledgeDocument):ReviewField[]{
 const out:ReviewField[]=[];
 function field(f:ReviewField){if(!equalValue(f.oldValue,f.newValue))out.push(f);}
 for(const collection of ['nodes','supporting_nodes'] as const){
  const a=old[collection]??[],b=current[collection]??[];
  const ids=[...new Set([...a.map(n=>n.id),...b.map(n=>n.id)])];
  for(const id of ids){
   const x=a.find(n=>n.id===id),y=b.find(n=>n.id===id),n=y??x!;
   const label=(n.type==='heading'?n.title:n.show_key?n.key:'正文')+(collection==='supporting_nodes'?'（支撑知识）':'');
   if(!x||!y)field({id:collection+id,label:label+(!x?' · 新增':' · 删除'),collection,nodeId:id,key:'$node',path:[],oldValue:x,newValue:y});
   else for(const key of new Set([...Object.keys(x),...Object.keys(y)]))if(key!=='id')field({id:collection+id+key,label:label+' / '+(labels[key]??key),collection,nodeId:id,key,path:[],oldValue:(x as unknown as Record<string,unknown>)[key],newValue:(y as unknown as Record<string,unknown>)[key]});
  }
  const common=new Set(a.filter(n=>b.some(m=>m.id===n.id)).map(n=>n.id));
  if(!equalValue(a.filter(n=>common.has(n.id)).map(n=>n.id),b.filter(n=>common.has(n.id)).map(n=>n.id)))field({id:collection+'order',label:collection==='nodes'?'正文顺序':'支撑知识顺序',collection,key:'$order',path:[],oldValue:a.map(n=>n.id),newValue:b.map(n=>n.id)});
 }
 function walk(a:unknown,b:unknown,path:string[]){
  if(equalValue(a,b))return;
  if(a&&b&&typeof a==='object'&&typeof b==='object'&&!Array.isArray(a)&&!Array.isArray(b)){
   for(const k of new Set([...Object.keys(a),...Object.keys(b)]))walk((a as Record<string,unknown>)[k],(b as Record<string,unknown>)[k],[...path,k]);
  }else field({id:'body'+JSON.stringify(path),label:path.map(p=>labels[p]??p).join(' / '),key:path.at(-1)!,path,oldValue:a,newValue:b});
 }
 for(const key of new Set([...Object.keys(old),...Object.keys(current)]))if(!['nodes','supporting_nodes','schema_version'].includes(key))walk((old as unknown as Record<string,unknown>)[key],(current as unknown as Record<string,unknown>)[key],[key]);
 return out;
}
export function applyReviewField(body:KnowledgeDocument,f:ReviewField,value:unknown,reference:KnowledgeDocument){
 const next=structuredClone(body);
 if(f.collection){
  let nodes=next[f.collection]??[];
  if(f.key==='$order'){
   const order=value as string[];nodes=[...nodes].sort((a,b)=>{const i=order.indexOf(a.id),j=order.indexOf(b.id);return (i<0?order.length:i)-(j<0?order.length:j);});
  }else if(f.key==='$node'){
   nodes=nodes.filter(n=>n.id!==f.nodeId);
   if(value){const node=structuredClone(value) as KnowledgeNode;const source=reference[f.collection]??[];const idx=source.findIndex(n=>n.id===f.nodeId);const following=source.slice(idx+1).find(n=>nodes.some(m=>m.id===n.id));const at=following?nodes.findIndex(n=>n.id===following.id):nodes.length;nodes.splice(at,0,node);}
  }else nodes=nodes.map(n=>{if(n.id!==f.nodeId)return n;const copy={...n} as unknown as Record<string,unknown>;if(value===undefined)delete copy[f.key];else copy[f.key]=structuredClone(value);return copy as KnowledgeNode;});
  next[f.collection]=nodes;
 }else{
  let target=next as unknown as Record<string,unknown>;
  for(const k of f.path.slice(0,-1)){if(!target[k]||typeof target[k]!=='object')target[k]={};target=target[k] as Record<string,unknown>;}
  if(value===undefined)delete target[f.key];else target[f.key]=structuredClone(value);
 }
 return next;
}
