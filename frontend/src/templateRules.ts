import {resolveTemplateEntities,type TemplateEntity,type TemplateEvent,type TemplateParameter} from './templates';

export type ConditionNode = {kind:'leaf';left:string;operator:string;right:string}
 | {kind:'all'|'any'|'not';children:ConditionNode[]};
export type ConditionCatalog = {
 events:Record<string,{parameters:Record<string,string>}>;
 roots:Record<string,string>;
 types:Record<string,Record<string,string>>;
 aliases:Record<string,string>;
 unit_types?:string[];
 operations:Record<string,string[]>;
 enums?:Record<string,string[]>;
 card_tags?:Record<string,{type:string;tags:string[]}>;
};
type CountFilter={source:string;field:'标签'|'阵营'|'英雄';choices?:string[]};
export type PathOption={path:string;type:string;operations?:string[];choices?:string[];filter?:CountFilter};
export const emptyTree=():ConditionNode=>({kind:'all',children:[]});
export function renderRule(node:ConditionNode):string{
 if(node.kind==='leaf')return [node.left,node.operator,node.right].filter(Boolean).join(' ');
 const children=node.children.map(renderRule);
 if(node.kind==='not')return 'not ('+children.join('')+')';
 if(children.length<2)return children[0]??'';
 return '('+children.join(node.kind==='all'?' and ':' or ')+')';
}
export function completeTree(node:ConditionNode,root=true):boolean{
 if(node.kind==='leaf')return completeOperand(node.left)&&(!node.operator||completeOperand(node.right));
 if(node.kind==='not'&&node.children.length!==1)return false;
 return (node.children.length>0||(root&&node.kind==='all'))&&node.children.every(child=>completeTree(child,false));
}
function completeOperand(path:string):boolean{
 if(!path)return false;
 const filter=readCountFilter(path);
 if(!filter)return true;
 if(filter.field!=='英雄')return !!filter.value;
 try{
  const heroes=JSON.parse(filter.value);
  return Array.isArray(heroes)&&heroes.length>0&&heroes.every(hero=>
   typeof hero==='string'?!!hero.trim():
    hero?.类型==='英雄'&&typeof (hero.名称??hero.name)==='string'&&!!(hero.名称??hero.name).trim()
    &&Object.keys(hero).every(key=>['类型','名称','name','已觉醒'].includes(key))
    &&(!('已觉醒' in hero)||typeof hero.已觉醒==='boolean'));
 }catch{return false;}
}
export function switchToText(tree:ConditionNode,lastComplete:ConditionNode|null,expression:string){
 return {editor_mode:'text' as const,expression,condition_tree:completeTree(tree)?tree:lastComplete};
}
const primitiveTypes={text:'string',number:'number',boolean:'bool',entity:'实体'};
const entityType:Record<string,string>={heroes:'英雄',equipment:'装备',players:'棋手',talents:'天赋','effect-cards':'效果牌','player-skills':'棋手技能',derivatives:'衍生物'};
export function countPath({source,field}:CountFilter,value:string){
 return `${source}.计数(${field}, ${field==='英雄'?value||'[]':JSON.stringify(value)})`;
}
export function readCountFilter(path:string):{source:string;field:CountFilter['field'];value:string}|undefined{
 const heroes=path.match(/^(.+)\.计数\s*\(\s*英雄\s*,\s*(.*)\)$/s);
 if(heroes)return {source:heroes[1],field:'英雄',value:heroes[2]};
 const match=path.match(/^(.+)\.计数\s*\(\s*(标签|阵营)\s*,\s*("(?:[^"\\]|\\.)*")\s*\)$/);
 if(!match)return;
 const [,source,field,literal]=match;
 try{return {source,field:field as CountFilter['field'],value:JSON.parse(literal)};}catch{return;}
}
export function findPathOption(paths:PathOption[],path:string){
 const filter=readCountFilter(path);
 const key=filter?countPath(filter,''):path;
 return paths.find(p=>p.path===key);
}
export function parameterType(p:TemplateParameter){
 return p.dsl_type||(p.type==='entity'&&p.entity_categories?.map(c=>entityType[c]).filter(Boolean).join('|'))||primitiveTypes[p.type];
}
export function listPaths(event:TemplateEvent|undefined,catalog?:ConditionCatalog):PathOption[]{
 const params=Object.fromEntries((event?.parameters??[]).map(p=>[p.key,parameterType(p)]));
 const roots={...params,...catalog?.events[event?.name??'']?.parameters,...catalog?.roots};
 const paths:PathOption[]=[];
 const tagsByType=new Map<string,Set<string>>();
 for(const {type,tags} of Object.values(catalog?.card_tags??{})){
  const values=tagsByType.get(type)??new Set<string>();
  for(const tag of tags)values.add(tag);
  tagsByType.set(type,values);
 }
 function tagChoices(owners:string[]){
  return [...new Set(owners.flatMap(t=>[...(tagsByType.get(t==='单位'?'英雄':t)??[])]))].sort();
 }
 function walk(path:string,declared:string,ancestors:string[],operations?:string[],choices?:string[]){
  const type=catalog?.aliases[declared]??declared;
  paths.push({path,type,operations,choices});
  const memberTypes=members(type).map(t=>catalog?.aliases[t]??t);
  if(memberTypes.length){
   paths.push({path:path+'.计数()',type:'int'});
   if(memberTypes.length===1&&['英雄','单位'].includes(memberTypes[0])){
    const filters:CountFilter[]=[{source:path,field:'标签',choices:tagChoices(['英雄'])},{source:path,field:'阵营'},{source:path,field:'英雄'}];
    for(const filter of filters)paths.push({path:countPath(filter,''),type:'int',filter});
   }
   for(const key of Object.keys(catalog?.types[memberTypes[0]]??{})){
    const types=memberTypes.map(t=>catalog?.types[t]?.[key]);
    if(types.every(t=>t==='int'||t==='number'))paths.push({path:path+'.求和('+key+')',type:types.every(t=>t==='int')?'int':'number'});
   }
   if(memberTypes.every(t=>catalog?.types[t]?.['标签']==='Array<string>'))paths.push({path:path+'.标签',type:'Array<string>',operations:['has'],choices:tagChoices(memberTypes)});
   return;
  }
  if(ancestors.includes(type))return;
  const variants=type.split('|').map(t=>catalog?.aliases[t]??t);
  for(const [key,child] of Object.entries(catalog?.types[variants[0]]??{})){
   if(variants.every(t=>catalog?.types[t]?.[key]===child))walk(path+'.'+key,child,[...ancestors,type],variants.map(t=>catalog?.operations[t+'.'+key]).find(Boolean),key==='标签'?tagChoices(variants):catalog?.enums?.[variants[0]+'.'+key]);
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
export function compatibleRight(left:string,right:string,operator:string,aliases:Record<string,string>={},unitTypes:string[]=[]){
 const leftTypes=operator==='has'?members(left):left.split('|');
 const rightTypes=operator==='in'?members(right):right.split('|');
 const unitCompatible=(x:string,y:string)=>x==='单位'&&(unitTypes.includes(y)||
  (y==='string'&&leftTypes.length===1&&rightTypes.length===1));
 return leftTypes.some(first=>rightTypes.some(second=>{
  const x=aliases[first]??first,y=aliases[second]??second;
  return x===y||(numeric(x)&&numeric(y))||unitCompatible(x,y)||unitCompatible(y,x);
 }));
}
export function newLeaf(paths:PathOption[]):ConditionNode{
 const first=paths.find(p=>p.path==='arg1.阵容名')??paths.find(p=>p.path.endsWith('.名称'))??paths[0];
 return {kind:'leaf',left:first?.path??'',operator:first?operatorsFor(first)[0]:'is',right:''};
}

export function treeEntities(tree:ConditionNode,paths:PathOption[],cards:(TemplateEntity&{category:string;aliases?:string[]})[],unitTypes:string[]=[]):TemplateEntity[]{
 const found=new Map<string,TemplateEntity>();
 const types=new Map(paths.map(p=>[p.path,p.type]));
 function visit(node:ConditionNode){
  if(node.kind!=='leaf'){node.children.forEach(visit);return;}
  if(!['is','has','in'].includes(node.operator))return;
  let literal:unknown;
  try{literal=JSON.parse(node.right);}catch{return;}
  const leftType=node.left.endsWith('.名称')?types.get(node.left.slice(0,-3)):types.get(node.left);
  const typesForName=leftType?(node.operator==='has'?members(leftType):leftType.split('|')):[];
  for(const value of Array.isArray(literal)?literal:[literal]){
   const typed=typeof value==='object'&&value!==null;
   const name=typed?value.名称:value;
   if(typeof name!=='string')continue;
   const targetTypes=typed?[value.类型]:typesForName.flatMap(t=>t==='单位'?unitTypes:[t]);
   const categories=Object.keys(entityType).filter(c=>targetTypes.includes(entityType[c]));
   if(!categories.length&&!targetTypes.includes('实体'))continue;
   for(const ref of resolveTemplateEntities(name,cards,categories))found.set(ref.id,ref);
  }
 }
 visit(tree);
 return [...found.values()];
}
