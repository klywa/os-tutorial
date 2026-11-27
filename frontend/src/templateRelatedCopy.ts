import catalogSource from '../../src/condition/catalog.json?raw';
import {catalogV04,currentTemplateSyntax,keyedTemplateSyntax,migrateKeyedCondition,validateExtraKey,validateKeyedCondition,validateV04Template,v04ConditionKey} from './templateV04';
import {relatedTemplateEventFamilies,templateId,templateRangeKey,templateRangeValues,templateVersionValues,type TemplateEvent,type TemplateGroup} from './templates';
import {canonicalTemplateName} from './templateInlineTrigger';

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

type RelatedCopy={kind:'existing'|'new';group:TemplateGroup;renamePeers?:TemplateGroup[]};
const version=(group:TemplateGroup)=>templateRangeKey(templateVersionValues(group.version));
const mode=(group:TemplateGroup)=>templateRangeKey(templateRangeValues(group.mode));

export function relatedCopy(source:TemplateGroup,event:string,target:TemplateEvent,groups:TemplateGroup[],newId?:string):RelatedCopy{
 if(!keyedTemplateSyntax(source.syntax_version)||!relatedTargets(event).includes(target.name))
  throw new Error('请选择本组内支持额外信息键的关联事件');
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
 const body=source.syntax_version==='0.4'?migrateKeyedCondition(event,key,source.expression??''):source.expression??'';
 const expression=mapFields(body);
 validateKeyedCondition(target.name,extraKey,expression,currentTemplateSyntax);
 const conditionKey=v04ConditionKey(expression);
 const peers=groups.filter(group=>group.event_id===target.id&&keyedTemplateSyntax(group.syntax_version)&&
  group.extra_key===extraKey&&version(group)===version(source)&&mode(group)===mode(source)&&
  (group.publication_hold??'')===(source.publication_hold??'')&&
  group.scope.player_id===source.scope.player_id&&group.scope.lineup_note_id===source.scope.lineup_note_id&&
  v04ConditionKey(group.syntax_version==='0.4'?migrateKeyedCondition(target.name,extraKey,group.expression??''):group.expression??'')===conditionKey&&
  Boolean(group.ignored)===Boolean(source.ignored));
 const first=peers[0];
 const renamePeers=first?peers.filter(group=>group.name.trim()!==first.name.trim())
  .map(group=>({...group,name:first.name})):[];
 const reconciliation=renamePeers.length?{renamePeers}:{};
 const existing=peers.find(group=>(group.priority??0)>=(source.priority??0)&&
  group.utterances.length===source.utterances.length&&group.utterances.every((row,index)=>{
   const original=source.utterances[index];
   return row.text===original.text&&Boolean(row.fixed)===Boolean(original.fixed)&&Boolean(row.ignored)===Boolean(original.ignored);
  }));
 if(existing)return {kind:'existing',group:existing,...reconciliation};

 const utterances=source.utterances.map(row=>{
  if(row.fixed&&row.ignored)throw new Error('请先解除来源话术的固定或忽略标记');
  try{validateV04Template(target.name,row.text,currentTemplateSyntax);}
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
 const prepared:TemplateGroup={...clone,id:newId??templateId('group'),event_id:target.id,
  expression,extra_key:extraKey,syntax_version:currentTemplateSyntax,review_status:null,editor_mode:'text',conditions:[],condition_tree:null,utterances};
 return {kind:'new',group:{...prepared,name:first?.name??canonicalTemplateName(prepared,target)??target.name},...reconciliation};
}
