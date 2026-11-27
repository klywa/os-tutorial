import {compactCondition} from './conditionEditing';
import {templateAction} from './templateAction';
import {keyedTemplateSyntax,catalogV04,namedConditionValues,readV04Condition,type ConditionNodeV04} from './templateV04';
import {effectiveExpression,fixedArguments,operators,orderTemplateEvents,relatedTemplateEventFamilies,valueText,type TemplateEvent,type TemplateGroup} from './templates';

type ScopeName=(id:string)=>string;
const familyLabels=['英雄相关事件','效果牌相关事件','装备相关事件'];
const memberships=new Map(relatedTemplateEventFamilies.flatMap((family,index)=>family.map(name=>[name,index] as const)));
const familyOf=(event:TemplateEvent)=>memberships.get(event.name)??memberships.get('解释为何'+event.name);

export function templateDisplayExpression(group:TemplateGroup,scopeName:ScopeName){
 const {player_id:player,lineup_note_id:lineup}=group.scope;
 return effectiveExpression(player&&scopeName(player),lineup&&scopeName(lineup),group.expression??'',group.syntax_version);
}

function actionKey(group:TemplateGroup,event:TemplateEvent){
 const definition=catalogV04.events[event.name];
 if(!keyedTemplateSyntax(group.syntax_version)||!definition)return undefined;
 const parts=group.extra_key?.split('-')??[];
 if(parts.includes('*')){
  const found=new Map<string,Set<string>>();
  function visit(node:ConditionNodeV04){
   if(node.kind==='binary'&&node.op==='and'){visit(node.left);visit(node.right);return;}
   const binding=namedConditionValues(node);
   if(binding?.path.length!==3||binding.path[0]!=='动作'||binding.path[2]!=='名称'||binding.values.length!==1)return;
   const field=binding.path[1],values=found.get(field)??new Set<string>();
   values.add(binding.values[0]);found.set(field,values);
  }
  const condition=readV04Condition(group.expression);
  if(condition)visit(condition);
  definition.key.forEach((field,index)=>{
   const values=found.get(field);
   if(parts[index]==='*'&&values?.size===1){
    const [name]=values;
    if(name&&!/[-*]/u.test(name))parts[index]=name;
   }
  });
 }
 return new Map(definition.key.map((field,index)=>[field,parts[index]==='*'?undefined:parts[index]] as const));
}

function sectionFor(group:TemplateGroup,event:TemplateEvent|undefined,family:number|undefined){
 if(!event)return {key:JSON.stringify([group.event_id]),title:group.event_id};
 const key=actionKey(group,event);
 if(family===undefined){
  const extra_key=key&&[...key.values()].map(value=>value??'*').join('-');
  const title=templateAction(extra_key===undefined?group:{...group,extra_key},event);
  return {key:JSON.stringify([event.id,title]),title};
 }
 const legacy=key?undefined:fixedArguments(group,event);
 if(family!==2){
  const subject=key?.get('选中')??legacy?.get(event.name.includes('选择')?'arg2':'arg1');
  return {key:JSON.stringify(['family',family,subject]),title:subject??familyLabels[family]};
 }
 const forge=event.name.includes('铸造'),transfer=event.name.includes('转移');
 const target=key?.get('目标英雄')??legacy?.get(transfer?'arg3':'arg1');
 const equipment=key?.get(forge?'目标装备':'装备')??legacy?.get(forge?'arg3':'arg2');
 const title=target&&equipment?target+' · '+equipment:equipment??(target?target+' · 装备':familyLabels[family]);
 return {key:JSON.stringify(['family',family,target,equipment]),title};
}

export function templateRelatedSection(group:TemplateGroup,event:TemplateEvent|undefined){
 const family=event&&familyOf(event);
 if(family===undefined)return;
 const section=sectionFor(group,event,family);
 if(section.title!==familyLabels[family])return section;
}

export function templateConditionLength(group:TemplateGroup,event?:TemplateEvent,scopeName:ScopeName=id=>id){
 const expression=compactCondition(templateDisplayExpression(group,scopeName));
 const legacy=group.expression===undefined?group.conditions.map(condition=>
  [event?.parameters.find(parameter=>parameter.key===condition.parameter_key)?.name??condition.parameter_key,
   operators[condition.operator],valueText(condition.value)].join(' ')).join(' '):'';
 return expression.length+legacy.length;
}

export function templateDisplaySections(groups:TemplateGroup[],events:TemplateEvent[],scopeName:ScopeName=id=>id){
 const ordered=orderTemplateEvents(events);
 const eventRanks=new Map(ordered.map((event,index)=>[event.id,index]));
 const familyRanks=new Map<number,number>();
 ordered.forEach((event,index)=>{
  const family=familyOf(event);
  if(family!==undefined&&!familyRanks.has(family))familyRanks.set(family,index);
 });
 const definitions=new Map(events.map(event=>[event.id,event]));
 const sections=new Map<string,{key:string;title:string;rank:number;events:Map<string,{
  key:string;title:string;rank:number;rows:{group:TemplateGroup;length:number}[];
 }>}>();
 for(const group of groups){
  const event=definitions.get(group.event_id),family=event&&familyOf(event);
  const section=sectionFor(group,event,family);
  const rank=(family===undefined?eventRanks.get(group.event_id):familyRanks.get(family))??ordered.length;
  let bucket=sections.get(section.key);
  if(!bucket){bucket={...section,rank,events:new Map()};sections.set(section.key,bucket);}
  let eventBucket=bucket.events.get(group.event_id);
  if(!eventBucket){
   eventBucket={key:group.event_id,title:event?.name.replace(/^解释为何\s*/u,'')??group.event_id,
    rank:eventRanks.get(group.event_id)??ordered.length,rows:[]};
   bucket.events.set(group.event_id,eventBucket);
  }
  eventBucket.rows.push({group,length:templateConditionLength(group,event,scopeName)});
 }
 return [...sections.values()].sort((a,b)=>a.rank-b.rank).map(({key,title,events})=>({key,title,
  events:[...events.values()].sort((a,b)=>a.rank-b.rank).map(({key,title,rows})=>({
   key,title,rows:rows.sort((a,b)=>a.length-b.length).map(({group})=>group),
  })),
 }));
}
