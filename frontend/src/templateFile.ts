import {effectiveExpression,resolveTemplateEntities,templateId,type TemplateChange,type TemplateEntity,type TemplateEvent,type TemplateGroup,type TemplateParameter,type TemplateSnapshot} from './templates';
import {listPaths,parameterType,treeEntities,type ConditionCatalog,type ConditionNode} from './templateRules';
import {buildTemplateEntityIndex} from './templateEntityIndex';

type JsonObject=Record<string,unknown>;
type FileDocument={kind:'speech-template-library';schema_version:3;events:JsonObject[];groups:JsonObject[]}&JsonObject;
export type LocalFileHandle={
 name:string;
 isSameEntry?:(other:LocalFileHandle)=>Promise<boolean>;
 getFile:()=>Promise<{text:()=>Promise<string>}>;
 createWritable:(options?:{mode:'exclusive'})=>Promise<{write:(text:string)=>Promise<void>;close:()=>Promise<void>;abort:()=>Promise<void>}>;
};
export type OfficialTemplateCatalog={season:string;version?:string;items:(TemplateEntity&{category:string;aliases?:string[]})[]};
type Entity=TemplateEntity&{category?:string;aliases?:string[]};
type FileLookups={entities?:Entity[];lineups?:{id:string;title:string;player_id?:string|null}[]};
export type TemplateFile={document:FileDocument;snapshot:TemplateSnapshot};
const entityTypes:Record<string,string>={'英雄':'heroes','装备':'equipment','效果牌':'effect-cards','棋手':'players','天赋':'talents','棋手技能':'player-skills','衍生物':'derivatives'};
const canonicalTypes=Object.fromEntries(Object.entries(entityTypes).map(([type,category])=>[category,type]));
const metadata=['version','mode','tags','batch','explanation','explanation_before','explanation_source','explanation_after','review_status','last_modified_by','reviewed_by','reviewed_at','entity_snapshot'] as const;
const record=(value:unknown):value is JsonObject=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const validName=(value:unknown):value is string=>typeof value==='string'&&!!value.trim();
const localId=(kind:string,identity:string)=>'file-'+kind+'-'+encodeURIComponent(identity);
export const templateGroupVersion=(group:{version?:unknown})=>(typeof group.version==='string'&&group.version.trim()||'S1').toUpperCase();
export const templateGroupSeason=(group:{version?:unknown})=>templateGroupVersion(group)==='S2'?'S2':'S1';
const validTree=(node:unknown):node is ConditionNode=>record(node)&&(node.kind==='leaf'
 ? typeof node.left==='string'&&typeof node.operator==='string'&&typeof node.right==='string'
 : ['all','any','not'].includes(String(node.kind))&&Array.isArray(node.children)&&node.children.every(validTree));

function readEvent(row:JsonObject):TemplateEvent{
 const signature=typeof row.signature==='string'?/^(.*?)\((.*)\)\s*$/u.exec(row.signature):null;
 const name=row.name??signature?.[1]?.trim();
 if(!validName(name))throw new Error('事件缺少有效名称。');
 const id=typeof row.id==='string'?row.id:localId('event',name);
 const parameters=row.parameters??signature?.[2].trim().split(',').filter(Boolean).map(entry=>{
  const [key,rawType]=entry.split(':').map(value=>value.trim());
  if(!key||!rawType)throw new Error('事件签名中的参数无效。');
  const dsl_type=rawType.replace(/\s*([|<>])\s*/g,'$1'),category=entityTypes[dsl_type];
  const type=category||dsl_type==='单位'?'entity':dsl_type==='int'||dsl_type==='number'?'number':dsl_type==='bool'?'boolean':'text';
  return {key,name:key,type,dsl_type,...(category?{entity_categories:[category]}:{})};
 });
 if(!Array.isArray(parameters)||parameters.some(value=>!record(value)||!validName(value.key)||!validName(value.name)||!['text','number','boolean','entity'].includes(String(value.type))))
  throw new Error('事件参数无效：'+name);
 return {id,name,category:typeof row.category==='string'?row.category:undefined,parameters:parameters.map((value:TemplateParameter)=>{
  const parameter={...value,id:value.id??localId('parameter',value.key)};
  return parameter;
 })};
}

export function parseTemplateFile(raw:string,lookups:FileLookups={}):TemplateFile{
 const candidate:unknown=JSON.parse(raw.replace(/^\uFEFF/,''));
 if(!record(candidate)||candidate.kind!=='speech-template-library'||candidate.schema_version!==3||
  !Array.isArray(candidate.events)||!candidate.events.every(record)||!Array.isArray(candidate.groups)||!candidate.groups.every(record))
  throw new Error('请选择 v3 话术模板库 JSON 文件。');
 const document=candidate as FileDocument;
 const events=document.events.map(readEvent);
 const namedEvents=new Map(events.map(event=>[event.name,event]));
 if(namedEvents.size!==events.length||new Set(events.map(event=>event.id)).size!==events.length)
  throw new Error('文件中有重名或重复编号的事件。');
 const scopeNames:Record<string,string>=Object.create(null);
 const readScope=(name:unknown,kind:'player'|'lineup',player:string|null=null)=>{
  if(name==null)return null;
  if(!validName(name))throw new Error('模板的适用范围无效。');
  const id=(kind==='player'
   ? lookups.entities?.find(row=>['player','players'].includes(row.category??'')&&row.name===name)?.id
   : lookups.lineups?.find(row=>row.title===name&&row.player_id===player)?.id)??localId(kind,name);
  scopeNames[id]=name;
  return id;
 };
 const ids=new Set<string>();
 const groups=document.groups.map((row):TemplateGroup=>{
  const event=typeof row.event_name==='string'?namedEvents.get(row.event_name):undefined;
  if(!event||!validName(row.name)||typeof row.expression!=='string'||!Array.isArray(row.utterances)||!row.utterances.length||
   !row.utterances.every(validName)||row.condition_tree!=null&&!validTree(row.condition_tree))
   throw new Error('模板组无效：'+String(row.name??''));
  const id=typeof row.id==='string'?row.id:localId('group',JSON.stringify([event.name,row.name,templateGroupVersion(row)]));
  if(ids.has(id))throw new Error('文件中有重名或重复编号的模板组：'+row.name);
  ids.add(id);
  const scope=record(row.scope)?row.scope:{};
  const player_id=readScope(scope.player,'player');
  const lineup_note_id=readScope(scope.lineup,'lineup',player_id);
  const findEntity=(name:string,categories?:string[])=>resolveTemplateEntities(name,lookups.entities??[],categories);
  const conditions=Array.isArray(row.conditions)?row.conditions.map((value,index)=>{
   if(!record(value)||!validName(value.parameter_key)||!['eq','ne','gt','gte','lt','lte','between'].includes(String(value.operator)))
    throw new Error('模板条件无效：'+row.name);
   const parameter=event.parameters.find(parameter=>parameter.key===value.parameter_key);
   if(!parameter)throw new Error('模板条件引用了文件中未定义的参数：'+value.parameter_key);
   const entity=parameter.type==='entity'&&typeof value.value==='string'
    ? findEntity(value.value,parameter.entity_categories)[0]??{id:localId('entity',value.value),name:value.value}:value.value;
   return {id:localId('condition',String(index)),parameter_key:value.parameter_key,operator:value.operator as TemplateGroup['conditions'][number]['operator'],value:entity};
  }):[];
  const related_entities=(Array.isArray(row.related_entities)?row.related_entities:[]).flatMap(value=>{
   if(!record(value)||!validName(value.名称)||!validName(value.类型))return [];
   const category=entityTypes[value.类型];
   const found=findEntity(value.名称,category?[category]:undefined);
   return found.length?found:[{id:localId('entity',value.类型+'|'+value.名称),name:value.名称}];
  });
  const invalidMetadata=(['version','mode','explanation','explanation_before','explanation_source','explanation_after','reviewed_by','reviewed_at'] as const)
   .some(key=>Object.hasOwn(row,key)&&typeof row[key]!=='string')||
   (['batch','tags'] as const).some(key=>Object.hasOwn(row,key)&&(!Array.isArray(row[key])||!(row[key] as unknown[]).every(validName)))||
   (Object.hasOwn(row,'review_status')&&row.review_status!==null&&!['ai_generated','initial_reviewed','final_reviewed'].includes(String(row.review_status)))||
   (Object.hasOwn(row,'last_modified_by')&&(!record(row.last_modified_by)||
    !(row.last_modified_by.kind==='ai'||row.last_modified_by.kind==='user'&&validName(row.last_modified_by.username))))||
   (Object.hasOwn(row,'entity_snapshot')&&(!record(row.entity_snapshot)||!validName(row.entity_snapshot.season)||
    !record(row.entity_snapshot.entities)||!Object.values(row.entity_snapshot.entities).every(record)));
  if(invalidMetadata)throw new Error('模板组的标记或审核资料无效：'+row.name);
  return {id,name:row.name,event_id:event.id,scope:{player_id,lineup_note_id},conditions,related_entities,expression:row.expression,
   editor_mode:row.editor_mode==='tree'?'tree':'text',condition_tree:row.condition_tree as ConditionNode|null|undefined,
   priority:typeof row.priority==='number'?row.priority:0,
   utterances:row.utterances.map((text,index)=>({id:localId('utterance',String(index)),text})),
   ...Object.fromEntries(metadata.filter(key=>Object.hasOwn(row,key)).map(key=>[key,row[key]])),
  };
 });
 const portableCatalog=document.condition_catalog;
 const condition_catalog=record(portableCatalog)&&record(portableCatalog.events)&&Object.values(portableCatalog.events).every(event=>record(event)&&record(event.parameters))&&record(portableCatalog.aliases)&&record(portableCatalog.types)&&
  record(portableCatalog.operations)&&record(portableCatalog.roots)?portableCatalog as ConditionCatalog:undefined;
 return {document,snapshot:{schema_version:3,revision:'local-file',groups,events,scope_names:scopeNames,condition_catalog}};
}

export function fileImportDocument(file:TemplateFile,ids:Iterable<string>):FileDocument{
 const selected=new Set(ids);
 const groups=file.document.groups.filter((_,index)=>selected.has(file.snapshot.groups[index].id));
 const eventNames=new Set(groups.map(group=>group.event_name));
 return {kind:'speech-template-library',schema_version:3,groups,events:file.document.events.filter((_,index)=>eventNames.has(file.snapshot.events[index].name))};
}

export function fileExportDocument(file:TemplateFile,ids?:Iterable<string>):FileDocument{
 if(ids===undefined)return file.document;
 const selection=fileImportDocument(file,ids);
 const catalog=file.snapshot.condition_catalog;
 const names=new Set(selection.groups.map(group=>group.event_name));
 return {...file.document,...selection,...(catalog?{condition_catalog:{...catalog,
  events:Object.fromEntries(Object.entries(catalog.events).filter(([name])=>names.has(name)))}}:{})};
}

function eventDefinition(event:TemplateEvent){
 return {category:event.category??'未分类',parameters:Object.fromEntries(event.parameters.map(parameter=>[
  parameter.key,parameterType(parameter)==='实体'?Object.keys(entityTypes).join('|'):parameterType(parameter),
 ]))};
}

function sameJson(left:unknown,right:unknown){
 const ordered=(value:unknown)=>record(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]])):value;
 return JSON.stringify(left,(_,value)=>ordered(value))===JSON.stringify(right,(_,value)=>ordered(value));
}

export function previewTemplateFileExport(source:unknown,raw:string,mode:'new'|'merge'){
 const incoming=parseTemplateFile(JSON.stringify(source));
 if(mode==='new'&&raw.length)throw new Error('目标文件已有内容，请使用「合并到已有文件」。');
 const target=mode==='merge'?parseTemplateFile(raw):null;
 const current=target?.document.groups??[];
 const groups=[...current];
 const positions=new Map(current.flatMap((row,index)=>validName(row.id)?[[row.id,index] as const]:[]));
 const replaced=new Set<number>();
 const changes=incoming.document.groups.map(row=>{
  const index=validName(row.id)?positions.get(row.id):undefined;
  if(index===undefined){groups.push(row);return {name:String(row.name),action:'add' as const};}
  replaced.add(index);
  if(sameJson(row,current[index]))return {name:String(row.name),action:'unchanged' as const};
  groups[index]=row;
  return {name:String(row.name),previousName:String(current[index].name),action:'replace' as const};
 });
 if(!target)return {document:incoming.document,changes,eventChanges:[],changed:true};
 if(Object.hasOwn(target.document,'condition_catalog')&&!target.snapshot.condition_catalog)
  throw new Error('目标文件包含无法识别的条件目录，请先修复目录后再合并。');

 const events=new Map(target.snapshot.events.map((event,index)=>[event.name,{event,row:target.document.events[index]}]));
 const referenced=new Set(incoming.document.groups.map(row=>row.event_name));
 incoming.snapshot.events.forEach((event,index)=>{
  if(!referenced.has(event.name))return;
  const row=incoming.document.events[index];
  const previous=events.get(event.name);
  if(previous){
   const parameters=(event:TemplateEvent)=>Object.entries(eventDefinition(event).parameters);
   const declared=(row:JsonObject)=>typeof row.signature==='string'?row.signature.replace(/\s/g,''):null;
   const previousSignature=declared(previous.row),incomingSignature=declared(row);
   const compatible=sameJson(parameters(previous.event),parameters(event))&&
    (!previousSignature||!incomingSignature||previousSignature===incomingSignature);
   if(compatible)return;
   if(current.some((group,index)=>group.event_name===event.name&&!replaced.has(index)))
    throw new Error(`事件「${event.name}」参数签名不同，目标文件中仍有其他模板组使用原定义。`);
  }
  events.set(event.name,{event,row});
 });

 const typed=[...events.values()].filter(({row})=>!target.document.events.includes(row));
 const hasChanges=changes.some(change=>change.action!=='unchanged')||typed.length>0;
 if(!hasChanges)return {document:target.document,changes,eventChanges:[],changed:false};
 const targetCatalog=target.snapshot.condition_catalog,sourceCatalog=incoming.snapshot.condition_catalog;
 const sharedFields=['types','roots','aliases','operations','unit_types','enums'] as const;
 if(targetCatalog&&sourceCatalog&&sharedFields.some(field=>!sameJson(targetCatalog[field],sourceCatalog[field])))
  throw new Error('来源与目标文件的条件目录不兼容，无法安全合并。');
 const catalog=targetCatalog??sourceCatalog;
 const catalogEvents={...target.snapshot.condition_catalog?.events};
 if(catalog){
  for(const {event} of typed){
   const types=Object.values(eventDefinition(event).parameters).flatMap(type=>type.replace(/Array<([^>]+)>/g,'$1').split('|'));
   if(types.some(type=>!['string','int','number','bool'].includes(type)&&!Object.hasOwn(catalog.types,catalog.aliases[type]??type)))
    throw new Error(`目标文件的条件目录无法识别事件「${event.name}」的参数类型。`);
  }
  for(const {event,row} of events.values()){
   if(target.document.events.includes(row)&&Object.hasOwn(catalogEvents,event.name))continue;
   const origin=target.document.events.includes(row)?target:incoming;
   const definition=origin.snapshot.condition_catalog?.events[event.name]??eventDefinition(event);
   Object.defineProperty(catalogEvents,event.name,{value:definition,enumerable:true,configurable:true,writable:true});
  }
 }
 const document:FileDocument={...target.document,groups,events:[...events.values()].map(({row})=>row),
  ...(catalog?{condition_catalog:{...catalog,events:catalogEvents}}:{})};
 parseTemplateFile(JSON.stringify(document));
 return {document,changes,eventChanges:typed.map(({event})=>event.name),changed:true};
}

export function writeTemplateDocument(file:TemplateFile,changes:TemplateChange[],lookups:FileLookups={}):FileDocument{
 const events=new Map(file.snapshot.events.map((event,index)=>[event.id,{value:event,row:file.document.events[index]}]));
 const groups=new Map(file.snapshot.groups.map((group,index)=>[group.id,{value:group,row:file.document.groups[index]}]));
 const catalog=file.snapshot.condition_catalog?structuredClone(file.snapshot.condition_catalog):undefined;
 for(const change of changes){
  if(change.kind!=='event')continue;
  const previous=events.get(change.id);
  if(change.action==='delete'){
   events.delete(change.id);
   if(catalog?.events&&previous)delete catalog.events[previous.value.name];
   continue;
  }
  const value=change.value as TemplateEvent;
  const parameters=Object.fromEntries(value.parameters.map(parameter=>[
   parameter.key,parameter.type==='entity'&&!parameter.dsl_type&&!parameter.entity_categories?.length?Object.keys(entityTypes).join('|'):parameterType(parameter),
  ]));
  const row={...previous?.row,name:value.name,category:value.category,signature:value.name+'('+Object.entries(parameters).map(([key,type])=>key+': '+type).join(', ')+')',
   parameters:value.parameters.map(({id:_,...parameter})=>({...parameter,suggestions:parameter.suggestions?.map(suggestion=>
    parameter.type==='entity'&&record(suggestion)?suggestion.name:suggestion)}))};
  events.set(change.id,{value,row});
  if(catalog?.events){
   if(previous&&previous.value.name!==value.name)delete catalog.events[previous.value.name];
   const definition={category:value.category??'未分类',parameters};
   catalog.events[value.name]=definition;
  }
 }
 for(const change of changes){
  if(change.kind!=='group')continue;
  if(change.action==='delete'){groups.delete(change.id);continue;}
  const value=change.value as TemplateGroup,previous=groups.get(change.id);
  const event=events.get(value.event_id)?.value;
  if(!event)throw new Error('模板组引用了文件中不存在的事件。');
  const scope={
   player:value.scope.player_id===null?null:lookups.entities?.find(entity=>entity.id===value.scope.player_id)?.name??file.snapshot.scope_names?.[value.scope.player_id]??value.scope.player_id,
   lineup:value.scope.lineup_note_id===null?null:lookups.lineups?.find(note=>note.id===value.scope.lineup_note_id)?.title??file.snapshot.scope_names?.[value.scope.lineup_note_id]??value.scope.lineup_note_id,
  };
  const row:JsonObject={...(previous?.row??{id:value.id}),name:value.name,event_name:event.name,scope,expression:value.expression??'',effective_expression:effectiveExpression(scope.player,scope.lineup,value.expression??''),
   priority:value.priority??0,editor_mode:value.editor_mode??'text',condition_tree:value.condition_tree,
   utterances:value.utterances.map(utterance=>utterance.text),
  };
  if(value.conditions.length)row.conditions=value.conditions.map(({id:_,value,...condition})=>({...condition,value:record(value)?value.name:value}));
  else delete row.conditions;
  if(JSON.stringify(value.related_entities)!==JSON.stringify(previous?.value.related_entities??[])){
   const relations=new Map<string,JsonObject>();
   for(const ref of value.related_entities){
    const found=lookups.entities?.find(entity=>entity.id===ref.id);
    const type=canonicalTypes[found?.category??''];
    const prior=Array.isArray(previous?.row.related_entities)?previous.row.related_entities.find(row=>record(row)&&row.名称===ref.name):undefined;
    const relation=type?{名称:ref.name,类型:type}:prior;
    if(relation)relations.set(JSON.stringify(relation),relation);
   }
   if(relations.size)row.related_entities=[...relations.values()];else delete row.related_entities;
  }
  for(const key of metadata){
   if(value[key]===undefined)delete row[key];else row[key]=value[key];
  }
  groups.set(change.id,{value,row});
 }
 return {...file.document,...(catalog?{condition_catalog:catalog}:{}),events:[...events.values()].map(({row})=>row),groups:[...groups.values()].map(({value,row})=>{
  const event=events.get(value.event_id)?.value;
  if(!event)throw new Error('事件仍被模板组引用：'+value.name);
  return event.name===row.event_name?row:{...row,event_name:event.name};
 })};
}

export function reviewLocalGroup(group:TemplateGroup,username:string,action:'edit'|'final',at=new Date().toISOString()):TemplateGroup{
 if(action==='final')return {...group,review_status:'final_reviewed',reviewed_by:username,reviewed_at:at};
 const {reviewed_at:_,reviewed_by:__,...next}=group;
 return {...next,review_status:'initial_reviewed',last_modified_by:{kind:'user',username}};
}

export function writeLocalReviewStatus(file:TemplateFile,group:TemplateGroup):FileDocument{
 return {...file.document,groups:file.document.groups.map((row,index)=>{
  if(file.snapshot.groups[index].id!==group.id)return row;
  const {reviewed_by:_,reviewed_at:__,...content}=row;
  return {...content,review_status:group.review_status,
   ...(group.reviewed_by?{reviewed_by:group.reviewed_by,reviewed_at:group.reviewed_at}:{})};
 })};
}

export function withLocalEntitySnapshot(group:TemplateGroup,event:TemplateEvent|undefined,official:OfficialTemplateCatalog|undefined,linked:TemplateEntity[],catalog?:ConditionCatalog,fallback:Entity[]=[]):TemplateGroup{
 const season=templateGroupSeason(group),verified=official?.season===season?official:undefined;
 const items=verified?.items??fallback.filter((row):row is Entity&{category:string}=>typeof row.category==='string');
 const missing=new Map<string,string>();
 const treeRefs=group.condition_tree?treeEntities(group.condition_tree,listPaths(event,catalog),items,catalog?.unit_types):[];
 const argumentEntries=event?buildTemplateEntityIndex([group],[event],items,catalog,(name,categories)=>
  missing.set(localId('entity',JSON.stringify([categories,name])),name)).filter(entry=>entry.groupIds.has(group.id)):[];
 const argumentsMatched=new Set(argumentEntries.map(entry=>JSON.stringify([entry.category,entry.name])));
 const argumentRefs=items.filter(entity=>argumentsMatched.has(JSON.stringify([entity.category,entity.name])));
 const references=new Map([...linked,...treeRefs,...argumentRefs].map(ref=>[ref.id,ref.name]));
 const explicitNames=new Set(references.values());
 const remaining=[...missing].filter(([,name])=>!explicitNames.has(name));
 const byId=new Map(verified?.items.map(entity=>[entity.id,entity]));
 return {...group,entity_snapshot:{season,version:verified?.version,entities:Object.fromEntries(
  [...references,...remaining].map(([id,name])=>[id,byId.get(id)??{name,missing:true}]),
 )}};
}

export async function pickTemplateFile(){
 const choose=(window as Window&{showOpenFilePicker?:(options:unknown)=>Promise<LocalFileHandle[]>}).showOpenFilePicker;
 if(!choose)throw new Error('当前浏览器无法直接打开并写回文件。请使用 Chrome 或 Edge。');
 const [handle]=await choose.call(window,{multiple:false,types:[{description:'话术模板库 JSON',accept:{'application/json':['.json']}}]});
 if(!handle)throw new DOMException('未选择文件','AbortError');
 return handle;
}

export async function pickNewTemplateFile(name:string){
 const choose=(window as Window&{showSaveFilePicker?:(options:unknown)=>Promise<LocalFileHandle>}).showSaveFilePicker;
 if(!choose)throw new Error('当前浏览器无法直接保存文件。请使用 Chrome 或 Edge。');
 return choose.call(window,{suggestedName:name,types:[{description:'话术模板库 JSON',accept:{'application/json':['.json']}}]});
}

export async function readTemplateFile(handle:LocalFileHandle){
 return (await handle.getFile()).text();
}

export async function saveTemplateFile(handle:LocalFileHandle,expected:string,document:unknown){
 const raw=JSON.stringify(document,null,2)+'\n';
 const message='文件已在其他地方修改，请重新读取后再保存。';
 if(await readTemplateFile(handle)!==expected)throw new Error(message);
 const writable=await handle.createWritable({mode:'exclusive'});
 try{
  if(await readTemplateFile(handle)!==expected)throw new Error(message);
  await writable.write(raw);
  await writable.close();
 }catch(error){
  await writable.abort().catch(()=>{});
  throw error;
 }
 return raw;
}
