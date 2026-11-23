import {cardCategories} from './cardCatalog';
import {parameterRole} from './templateAction';
import {members,parameterType,type ConditionCatalog} from './templateRules';
import type {TemplateEntity,TemplateEvent,TemplateGroup,TemplateParameter} from './templates';

type CatalogEntity=TemplateEntity&{category?:string;aliases?:string[]};
export type TemplateEntityEntry={
 key:string;
 id:string;
 name:string;
 category:string;
 aliases:string[];
 groupIds:Set<string>;
 roles:Map<string,string[]>;
};

const comparisons=new Set(['is','has','in']);

function visitComparisons(source:string,visit:(left:string,operator:string,right:string)=>void){
 const tokens=source.match(/"(?:\\.|[^"\\])*"|[\p{L}_][\p{L}\p{N}_]*|[^\s]/gu)??[];
 function walk(start:number,end:number,nesting=0){
  if(nesting>64)return;
  let depth=0,clause=start,firstClose=-1,operator=-1;
  for(let i=start;i<end;i++){
   const token=tokens[i];
   if(['(','[','{'].includes(token))depth++;
   else if([')',']','}'].includes(token)){
    if(--depth===0&&firstClose===-1)firstClose=i;
   }else if(!depth){
    if(token==='and'||token==='or'){
     walk(clause,i,nesting+1);
     clause=i+1;
    }else if(comparisons.has(token))operator=i;
   }
  }
  if(clause!==start)walk(clause,end,nesting+1);
  else if(tokens[start]==='not')walk(start+1,end,nesting+1);
  else if(tokens[start]==='('&&firstClose===end-1)walk(start+1,end-1,nesting+1);
  else if(operator!==-1)visit(tokens.slice(start,operator).join(''),tokens[operator],tokens.slice(operator+1,end).join(''));
 }
 walk(0,tokens.length);
}

function pathArgument(path:string,parameters:Map<string,TemplateParameter>){
 const [key,field,...rest]=path.split('.');
 if(rest.length||(field!==undefined&&field!=='名称'&&field!=='name'))return;
 const parameter=parameters.get(key);
 if(parameter)return {parameter,nameField:field!==undefined};
}

const defaultUnitTypes=['英雄','衍生物'];
const entityTypes=new Map(Object.entries(cardCategories).map(([category,type])=>[type,category]));
const canonicalCategory=(category:string)=>category==='player'?'players':category;

export function buildTemplateEntityIndex(groups:TemplateGroup[],events:TemplateEvent[],entities:CatalogEntity[],catalog?:ConditionCatalog,onMissing?:(name:string,categories:string[])=>void):TemplateEntityEntry[]{
 const entries=new Map<string,TemplateEntityEntry>();
 const byId=new Map<string,TemplateEntityEntry>();
 const names=new Map<string,Set<TemplateEntityEntry>>();
 const aliases=new Map<string,Set<TemplateEntityEntry>>();
 function addIndex(index:Map<string,Set<TemplateEntityEntry>>,name:string,entry:TemplateEntityEntry){
  const key=name.trim(),values=index.get(key)??new Set<TemplateEntityEntry>();
  values.add(entry);
  index.set(key,values);
 }
 for(const entity of entities){
  if(!entity.category)continue;
  const category=canonicalCategory(entity.category),name=entity.name.trim();
  if(!Object.hasOwn(cardCategories,category)||!name)continue;
  const key=JSON.stringify([category,name]);
  const entry=entries.get(key)??{key,id:entity.id,name,category,aliases:[],groupIds:new Set<string>(),roles:new Map<string,string[]>()};
  entries.set(key,entry);
  byId.set(entity.id,entry);
  addIndex(names,name,entry);
  for(const alias of entity.aliases??[]){
   if(!entry.aliases.includes(alias))entry.aliases.push(alias);
   addIndex(aliases,alias,entry);
  }
 }
 const definitions=new Map(events.map(event=>[event.id,{event,parameters:new Map(event.parameters.map(parameter=>[parameter.key,parameter]))}]));
 const canonicalType=(name:string)=>catalog?.aliases[name]??name;
 const categories=(types:string[])=>new Set(types.flatMap(type=>{
  const canonical=canonicalType(type);
  return (canonical==='单位'?(catalog?.unit_types??defaultUnitTypes):[canonical]).flatMap(value=>{
   const category=entityTypes.get(canonicalType(value));
   return category?[category]:[];
  });
 }));
 for(const group of groups){
  const definition=definitions.get(group.event_id);
  if(!definition)continue;
  const {event,parameters}=definition;
  function remember(parameter:TemplateParameter,value:unknown,array:boolean,legacy=false,nameField=false){
   const declared=catalog?.events[event.name]?.parameters[parameter.key]??parameterType(parameter);
   const inner=members(declared);
   if(!legacy&&((inner.length>0)!==array||array&&nameField))return;
   const types=inner.length?inner:declared.split('|');
   const allowed=categories(types);
   const generic=types.includes('实体')&&parameter.type==='entity';
   if(generic)for(const category of parameter.entity_categories??[])allowed.add(canonicalCategory(category));
   if(!allowed.size&&!generic)return;
   function matchesCategory(entry:TemplateEntityEntry){return allowed.has(entry.category)||generic&&!allowed.size;}
   const literal=typeof value==='object'&&value!==null&&!Array.isArray(value)?value as Record<string,unknown>:undefined;
   let matches:TemplateEntityEntry[];
   if(legacy&&typeof literal?.id==='string'){
    const exact=byId.get(literal.id);
    matches=exact&&matchesCategory(exact)?[exact]:[];
   }else{
    const name=typeof value==='string'?value:literal?.名称??literal?.name;
    if(typeof name!=='string'||!name.trim())return;
    const type=literal?.类型;
    const explicit=typeof type==='string'?entityTypes.get(canonicalType(type)):undefined;
    if(literal&&!explicit)return;
    const candidates=(index:Map<string,Set<TemplateEntityEntry>>)=>[...(index.get(name.trim())??[])]
     .filter(entry=>matchesCategory(entry)&&(!explicit||entry.category===explicit));
    matches=candidates(names);
    if(!matches.length)matches=candidates(aliases);
    if(!matches.length&&(!explicit||allowed.has(explicit)||generic)){
     onMissing?.(name.trim(),explicit?[explicit]:[...allowed]);
    }
    // A bare name in a unit or union must identify exactly one class of card.
    if(matches.length!==1)return;
   }
   for(const entry of matches){
    entry.groupIds.add(group.id);
    const role=parameterRole(event,parameter)||parameter.key;
    const roles=entry.roles.get(group.id)??[];
    if(!roles.includes(role))roles.push(role);
    entry.roles.set(group.id,roles);
   }
  }
  if(group.expression?.trim()){
   visitComparisons(group.expression,(left,operator,right)=>{
    const operands=operator==='has'?[[left,right,true,false],[right,left,false,true]] as const:
     operator==='in'?[[left,right,false,true],[right,left,true,false]] as const:
      [[left,right,false,false],[right,left,false,false]] as const;
    for(const [path,raw,array,list] of operands){
     const argument=pathArgument(path,parameters);
     if(!argument)continue;
     let value:unknown;
     try{value=JSON.parse(raw);}catch{continue;}
     if(list){
      if(Array.isArray(value))for(const item of value)remember(argument.parameter,item,array,false,argument.nameField);
     }else remember(argument.parameter,value,array,false,argument.nameField);
    }
   });
  }else for(const condition of group.conditions){
   const parameter=parameters.get(condition.parameter_key);
   if(parameter?.type==='entity'&&['eq','ne'].includes(condition.operator))remember(parameter,condition.value,false,true);
  }
 }
 return [...entries.values()].sort((a,b)=>b.groupIds.size-a.groupIds.size||a.name.localeCompare(b.name,'zh-CN')||a.category.localeCompare(b.category));
}
