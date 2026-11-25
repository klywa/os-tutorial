import catalogSource from '../../src/condition/catalog.json?raw';
import {catalogV04,validateExtraKey,validateV04,validateV04Template,v04ConditionKey} from './templateV04';
import {relatedTemplateEventFamilies,templateId,type TemplateEvent,type TemplateGroup} from './templates';

const signatures:Record<string,{category:string;parameters:Record<string,string>}>=JSON.parse(catalogSource).events;
const semanticField=(field:string)=>field==='目标装备'?'装备':field;

export function relatedTargets(event:string){
 return (relatedTemplateEventFamilies.find(family=>family.includes(event))??[]).filter(name=>name!==event);
}

export function relatedEventDefinition(name:string):TemplateEvent{
 const definition=signatures[name];
 const parameters=Object.entries(definition?.parameters??{}).map(([key,dsl_type])=>{
  const entity=({'英雄':'heroes','效果牌':'effect-cards','装备':'equipment'} as Record<string,string>)[dsl_type];
  return {id:'p_'+key,key,name:key,dsl_type,type:entity?'entity' as const:'text' as const,
   ...(entity?{entity_categories:[entity]}:{})};
 });
 return {id:templateId('event'),name,category:definition?.category??'解释类',parameters};
}

export function relatedDisplayRows(
 visible:TemplateGroup[], available:ReadonlyMap<string,TemplateGroup>, parents:ReadonlyMap<string,string>,
){
 const children=new Map<string,TemplateGroup[]>();
 for(const [child,parent] of parents){
  const group=available.get(child);
  if(!group||!available.has(parent))continue;
  const branch=children.get(parent)??[];
  branch.push(group);
  children.set(parent,branch);
 }
 const attached=new Set<string>();
 function mark(group:TemplateGroup){
  for(const child of children.get(group.id)??[]){
   if(attached.has(child.id))continue;
   attached.add(child.id);
   mark(child);
  }
 }
 visible.forEach(mark);
 const roots=new Map<string,TemplateGroup>(),rows:TemplateGroup[]=[];
 function add(group:TemplateGroup,root:TemplateGroup){
  if(roots.has(group.id))return;
  roots.set(group.id,root);
  rows.push(group);
  for(const child of children.get(group.id)??[])add(child,root);
 }
 visible.filter(group=>!attached.has(group.id)).forEach(group=>add(group,group));
 return {rows,roots};
}

type RelatedCopy={kind:'existing'|'new';group:TemplateGroup};
const version=(group:TemplateGroup)=>(group.version?.trim()||'S1').toUpperCase();
const mode=(group:TemplateGroup)=>group.mode||'万象大赛';

export function relatedCopy(source:TemplateGroup,event:string,target:TemplateEvent,groups:TemplateGroup[],newId?:string):RelatedCopy{
 if(source.syntax_version!=='0.4'||!relatedTargets(event).includes(target.name))
  throw new Error('请选择本组内的 v0.4 关联事件');
 const oldEvent=catalogV04.events[event],newEvent=catalogV04.events[target.name];
 const fields=catalogV04.actions[newEvent.action];
 const targetFields=new Map(Object.keys(fields).map(field=>[semanticField(field),field]));
 const key=source.extra_key??'';
 validateExtraKey(event,key);
 const segments=new Map(oldEvent.key.map((field,index)=>[semanticField(field),key.split('-')[index]]));
 const targetKeyFields=newEvent.key.map(semanticField);
 for(const [field,value] of segments){
  if(value!=='*'&&!targetKeyFields.includes(field))throw new Error('目标事件无法保留额外信息键中的'+field);
 }
 const extraKey=targetKeyFields.map(field=>segments.get(field)??'*').join('-');
 validateExtraKey(target.name,extraKey);
 const mapFields=(text:string)=>text.replace(/"(?:[^"\\]|\\.)*"|(?<![\p{L}\p{N}_.])动作\s*\.\s*([\p{L}][\p{L}\p{N}_]*)/gu,(token,field:string|undefined)=>{
  if(!field)return token;
  const mapped=targetFields.get(semanticField(field));
  if(!mapped)throw new Error('目标事件不提供动作.'+field);
  return mapped===field?token:'动作.'+mapped;
 });
 const expression=mapFields(source.expression??'');
 validateV04(target.name,expression);
 const conditionKey=v04ConditionKey(expression);
 const existing=groups.find(group=>group.event_id===target.id&&group.syntax_version==='0.4'&&group.name.trim()===source.name.trim()&&
  group.extra_key===extraKey&&version(group)===version(source)&&mode(group)===mode(source)&&
  (group.priority??0)===(source.priority??0)&&(group.publication_hold??'')===(source.publication_hold??'')&&
  group.scope.player_id===source.scope.player_id&&group.scope.lineup_note_id===source.scope.lineup_note_id&&
  v04ConditionKey(group.expression??'')===conditionKey&&Boolean(group.ignored)===Boolean(source.ignored)&&
  group.utterances.length===source.utterances.length&&group.utterances.every((row,index)=>{
   const original=source.utterances[index];
   return row.text===original.text&&Boolean(row.fixed)===Boolean(original.fixed)&&Boolean(row.ignored)===Boolean(original.ignored);
  }));
 if(existing)return {kind:'existing',group:existing};

 const utterances=source.utterances.map(row=>{
  if(row.fixed&&row.ignored)throw new Error('请先解除来源话术的固定或忽略标记');
  try{validateV04Template(target.name,row.text);}
  catch(error){throw new Error('目标事件无法保留原话术槽位：'+(error as Error).message);}
  return {...row,id:templateId('utterance')};
 });
 const clone=structuredClone(source);
 delete clone.wording_brief;
 delete clone.explanation;
 delete clone.explanation_before;
 delete clone.explanation_after;
 delete clone.reviewed_at;
 delete clone.reviewed_by;
 delete clone.last_modified_by;
 delete clone.entity_snapshot;
 return {kind:'new',group:{...clone,id:newId??templateId('group'),event_id:target.id,
  expression,extra_key:extraKey,review_status:null,editor_mode:'text',conditions:[],condition_tree:null,utterances}};
}
