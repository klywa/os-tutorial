import {cardCategories} from './cardCatalog';
import {parameterRole} from './templateAction';
import {members,parameterType,type ConditionCatalog} from './templateRules';
import {catalogV04,namedConditionValues,readV04Condition,type ConditionNodeV04} from './templateV04';
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

function visitComparisons(source:string,visit:(left:string,operator:string,right:string)=>void,positiveOnly=false){
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
  else if(tokens[start]==='not'){if(!positiveOnly)walk(start+1,end,nesting+1);}
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

function actionCardType(event:string,field:string){
 if(field.endsWith('英雄'))return '英雄';
 if(field.endsWith('装备'))return '装备';
 if(field==='目标')return '单位';
 if(field!=='选中'&&field!=='卡牌')return;
 return ['效果牌','天赋','棋手技能','英雄'].find(type=>event.includes(type));
}

export function buildTemplateEntityIndex(groups:TemplateGroup[],events:TemplateEvent[],entities:CatalogEntity[],catalog?:ConditionCatalog,onMissing?:(name:string,categories:string[])=>void,actionOnly=false,lineupHeroes?:ReadonlySet<string>):TemplateEntityEntry[]{
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
  function remember(parameter:TemplateParameter,value:unknown,array:boolean,legacy=false,nameField=false,actionType?:string){
   const declared=actionType??catalog?.events[event.name]?.parameters[parameter.key]??parameterType(parameter);
   const inner=members(declared);
   if(actionOnly&&inner.length)return;
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
     if(actionType&&allowed.size===1){
      const category=[...allowed][0],key=JSON.stringify([category,name.trim()]);
      const entry=entries.get(key)??{key,id:key,name:name.trim(),category,aliases:[],groupIds:new Set<string>(),roles:new Map<string,string[]>()};
      entries.set(key,entry);
      matches=[entry];
     }
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
  if(group.syntax_version==='0.4'){
   const action=catalogV04.events[event.name];
   if(!action)continue;
   const fields=catalogV04.actions[action.action],keyed=new Set<string>();
   function record(field:string,value:string){
    const type=actionCardType(event.name,field);
    if(type&&fields[field]?.replace(/\?$/u,'')==='卡牌'){
     remember({id:field,key:field,name:field,type:'entity'},value,false,false,false,type);
    }
   }
   const parts=group.extra_key?.split('-')??[];
   action.key.forEach((field,index)=>{
    const value=parts[index];
    if(value&&value!=='*'){keyed.add(field);record(field,value);}
   });
   function visit(node:ConditionNodeV04){
    if(node.kind==='binary'&&(node.op==='and'||node.op==='or')){
     visit(node.left);visit(node.right);return;
    }
    const fact=namedConditionValues(node);
    if(fact?.path.length===3&&fact.path[0]==='动作'&&fact.path[2]==='名称'&&!keyed.has(fact.path[1])){
     for(const value of fact.values)record(fact.path[1],value);
    }
   }
   const expression=readV04Condition(group.expression);
   if(expression){
    visit(expression);
    if(lineupHeroes?.size){
     function conjuncts(node:ConditionNodeV04):ConditionNodeV04[]{
      return node.kind==='binary'&&node.op==='and'?[...conjuncts(node.left),...conjuncts(node.right)]:[node];
     }
     function referencesName(node:ConditionNodeV04,path:string):boolean{
      if(node.kind==='path')return node.parts.join('.')===path;
      if(node.kind==='binary')return referencesName(node.left,path)||referencesName(node.right,path);
      if(node.kind==='negation')return referencesName(node.child,path);
      return node.kind==='call'&&node.args.some(arg=>referencesName(arg,path));
     }
     const terms=conjuncts(expression);
     for(const term of terms){
      if(term.kind!=='binary'||term.op!=='in'||term.left.kind!=='path'||term.right.kind!=='path'||
        term.right.parts.join('.')!=='我方.阵容英雄名列表')continue;
      const [root,field,property,...rest]=term.left.parts;
      if(root!=='动作'||property!=='名称'||rest.length||keyed.has(field)||actionCardType(event.name,field)!=='英雄')continue;
      const path=term.left.parts.join('.');
      if(terms.some(other=>other!==term&&referencesName(other,path)))continue;
      for(const name of lineupHeroes)record(field,name);
     }
    }
   }
   continue;
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
   },actionOnly);
  }else for(const condition of group.conditions){
   const parameter=parameters.get(condition.parameter_key);
   if(parameter?.type==='entity'&&(condition.operator==='eq'||!actionOnly&&condition.operator==='ne'))remember(parameter,condition.value,false,true);
  }
 }
 return [...entries.values()].sort((a,b)=>b.groupIds.size-a.groupIds.size||a.name.localeCompare(b.name,'zh-CN')||a.category.localeCompare(b.category));
}
