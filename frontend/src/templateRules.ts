import {resolveTemplateEntities,type TemplateEntity,type TemplateEvent,type TemplateParameter} from './templates';

export type ConditionNode = {kind:'leaf';left:string;operator:string;right:string}
 | {kind:'all'|'any'|'not';children:ConditionNode[]};
export type ConditionCatalog = {
 events:Record<string,{parameters:Record<string,string>}>;
 roots:Record<string,string>;
 types:Record<string,Record<string,string>>;
 aliases:Record<string,string>;
 operations:Record<string,string[]>;
 enums?:Record<string,string[]>;
};
export type PathOption={path:string;type:string;operations?:string[];choices?:string[]};
export const emptyTree=():ConditionNode=>({kind:'all',children:[]});
export function renderRule(node:ConditionNode):string{
 if(node.kind==='leaf')return [node.left,node.operator,node.right].filter(Boolean).join(' ');
 const children=node.children.map(renderRule);
 if(node.kind==='not')return 'not ('+children.join('')+')';
 if(children.length<2)return children[0]??'';
 return '('+children.join(node.kind==='all'?' and ':' or ')+')';
}
export function completeTree(node:ConditionNode,root=true):boolean{
 if(node.kind==='leaf')return !!node.left&&(!node.operator||!!node.right);
 if(node.kind==='not'&&node.children.length!==1)return false;
 return (node.children.length>0||(root&&node.kind==='all'))&&node.children.every(child=>completeTree(child,false));
}
export function switchToText(tree:ConditionNode,lastComplete:ConditionNode|null,expression:string){
 return {editor_mode:'text' as const,expression,condition_tree:completeTree(tree)?tree:lastComplete};
}
const primitiveTypes={text:'string',number:'number',boolean:'bool',entity:'实体'};
const entityType:Record<string,string>={heroes:'英雄',equipment:'装备',players:'棋手',talents:'天赋','effect-cards':'效果牌','player-skills':'棋手技能',derivatives:'衍生物'};
export function parameterType(p:TemplateParameter){
 return p.dsl_type||(p.type==='entity'&&p.entity_categories?.map(c=>entityType[c]).filter(Boolean).join('|'))||primitiveTypes[p.type];
}
export function listPaths(event:TemplateEvent|undefined,catalog?:ConditionCatalog):PathOption[]{
 const params=Object.fromEntries((event?.parameters??[]).map(p=>[p.key,parameterType(p)]));
 const roots={...params,...catalog?.events[event?.name??'']?.parameters,...catalog?.roots};
 const paths:PathOption[]=[];
 function walk(path:string,declared:string,ancestors:string[],operations?:string[],choices?:string[]){
  const type=catalog?.aliases[declared]??declared;
  paths.push({path,type,operations,choices});
  if(ancestors.includes(type)||members(type).length)return;
  const variants=type.split('|').map(t=>catalog?.aliases[t]??t);
  for(const [key,child] of Object.entries(catalog?.types[variants[0]]??{})){
   if(variants.every(t=>catalog?.types[t]?.[key]===child))walk(path+'.'+key,child,[...ancestors,type],variants.map(t=>catalog?.operations[t+'.'+key]).find(Boolean),catalog?.enums?.[variants[0]+'.'+key]);
  }
 }
 for(const [path,type] of Object.entries(roots))walk(path,type,[]);
 return paths;
}
export function numeric(type:string){return ['number','int','float'].includes(type);}
export function members(type:string){return type.startsWith('Array<')?type.slice(6,-1).split('|'):[];}
export function operatorsFor(path:PathOption){
 if(path.operations)return path.operations;
 if(members(path.type).length)return ['has'];
 if(numeric(path.type))return ['==','<','<=','>','>=','in'];
 if(path.type==='bool')return ['','==','in'];
 return ['is','in'];
}
export function compatibleRight(left:string,right:string,operator:string,aliases:Record<string,string>={}){
 const same=(a:string,b:string)=>a.split('|').some(x=>b.split('|').some(y=>(aliases[x]??x)===(aliases[y]??y)||(numeric(x)&&numeric(y))));
 if(operator==='has')return members(left).some(t=>same(t,right));
 if(operator==='in')return members(right).some(t=>same(t,left));
 return same(left,right);
}
export function newLeaf(paths:PathOption[]):ConditionNode{
 const first=paths.find(p=>p.path.endsWith('.名称'))??paths[0];
 return {kind:'leaf',left:first?.path??'',operator:first?operatorsFor(first)[0]:'is',right:''};
}

export function treeEntities(tree:ConditionNode,paths:PathOption[],cards:(TemplateEntity&{category:string;aliases?:string[]})[]):TemplateEntity[]{
 const found=new Map<string,TemplateEntity>();
 const types=new Map(paths.map(p=>[p.path,p.type]));
 function visit(node:ConditionNode){
  if(node.kind!=='leaf'){node.children.forEach(visit);return;}
  if(!['is','has','in'].includes(node.operator))return;
  let literal:unknown;
  try{literal=JSON.parse(node.right);}catch{return;}
  const type=node.left.endsWith('.名称')?types.get(node.left.slice(0,-3)):types.get(node.left);
  for(const value of Array.isArray(literal)?literal:[literal]){
   const typed=typeof value==='object'&&value!==null;
   const targetType=typed?value.类型:type;
   const name=typed?value.名称:value;
   if(typeof name!=='string')continue;
   const categories=Object.keys(entityType).filter(c=>typeof targetType==='string'&&targetType.split('|').includes(entityType[c]));
   if(!categories.length&&targetType!=='实体')continue;
   for(const ref of resolveTemplateEntities(name,cards,categories))found.set(ref.id,ref);
  }
 }
 visit(tree);
 return [...found.values()];
}
