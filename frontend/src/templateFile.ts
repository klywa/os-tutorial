import {effectiveExpression,resolveTemplateEntities,templateId,templateRangeKey,templateRangeValues,templateVersionValues,type TemplateChange,type TemplateEntity,type TemplateEvent,type TemplateGroup,type TemplateParameter,type TemplateSnapshot} from './templates';
import {listPaths,parameterType,renderRule,treeEntities,type ConditionCatalog,type ConditionNode} from './templateRules';
import {buildTemplateEntityIndex} from './templateEntityIndex';
import {validateExtraKey,validateV04,validateV04Template,v04ConditionKey} from './templateV04';

type JsonObject=Record<string,unknown>;
type FileDocument={kind:'speech-template-library';schema_version:3;events:JsonObject[];groups:unknown[]}&JsonObject;
export type LocalFileHandle={
 name:string;
 isSameEntry?:(other:LocalFileHandle)=>Promise<boolean>;
 requestPermission?:(options:{mode:'read'})=>Promise<PermissionState>;
 getFile:()=>Promise<{text:()=>Promise<string>}>;
 createWritable:(options?:{mode:'exclusive'})=>Promise<{write:(text:string)=>Promise<void>;close:()=>Promise<void>;abort:()=>Promise<void>}>;
};
export type OfficialTemplateCatalog={season:string;version?:string;items:(TemplateEntity&{category:string;aliases?:string[]})[]};
type Entity=TemplateEntity&{category?:string;aliases?:string[]};
type FileLookups={entities?:Entity[];lineups?:{id:string;title:string;player_id?:string|null}[]};
type CommentMessage={id:string;by:string;at:string;body:string};
export type LocalTemplateComment=CommentMessage&{utterance_id?:string;original_text?:string;target_text?:string;detached?:boolean};
export type TemplateFile={document:FileDocument;snapshot:TemplateSnapshot;groupIndexes:number[];groupErrors:{index:number;message:string}[];comments:Map<string,LocalTemplateComment[]>};
const entityTypes:Record<string,string>={'英雄':'heroes','装备':'equipment','效果牌':'effect-cards','棋手':'players','天赋':'talents','棋手技能':'player-skills','衍生物':'derivatives'};
const canonicalTypes=Object.fromEntries(Object.entries(entityTypes).map(([type,category])=>[category,type]));
const metadata=['version','mode','tags','batch','explanation','explanation_before','explanation_source','explanation_after','wording_brief','review_status','last_modified_by','reviewed_by','reviewed_at','entity_snapshot'] as const;
const record=(value:unknown):value is JsonObject=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const validName=(value:unknown):value is string=>typeof value==='string'&&!!value.trim();
const localId=(kind:string,identity:string)=>'file-'+kind+'-'+encodeURIComponent(identity);
type ScopeKind='player'|'lineup';
const scopeDraftPrefix='file-scope-draft-';
export function fileTemplateScopeId(kind:ScopeKind,name:string){
 return name?scopeDraftPrefix+kind+':'+name:null;
}
export function fileTemplateScopeName(kind:ScopeKind,id:string){
 const prefix=scopeDraftPrefix+kind+':';
 return id.startsWith(prefix)?id.slice(prefix.length):undefined;
}
const legacyUtteranceId=(index:number)=>localId('utterance',String(index));
function legacyUtterance(text:string,index:number,flags:unknown):TemplateGroup['utterances'][number]{
 const stored=record(flags)?flags[String(index)]:undefined;
 return {id:legacyUtteranceId(index),text,...(record(stored)&&stored.text===text?{
  ...(stored.ignored===true?{ignored:true}:{}),...(stored.fixed===true?{fixed:true}:{}),
 }:{})};
}
function legacyFlags(utterances:TemplateGroup['utterances']){
 const flags=Object.fromEntries(utterances.flatMap(({text,ignored,fixed},index)=>
  ignored||fixed?[[index,{text,...(ignored?{ignored}:{}),...(fixed?{fixed}:{})}]]:[]));
 return Object.keys(flags).length?flags:undefined;
}
function storedComments(row:JsonObject):unknown[]{
 return Array.isArray(row.file_comments)?row.file_comments:[];
}
function isLocalComment(value:unknown):value is LocalTemplateComment{
 return record(value)&&validName(value.id)&&validName(value.by)&&validName(value.at)&&validName(value.body)&&
  (value.utterance_id===undefined||validName(value.utterance_id)&&typeof value.original_text==='string');
}
export function templateGroupSeasons(group:{version?:unknown}):('S1'|'S2')[]{
 return [...new Set(templateVersionValues(group.version).map(version=>version==='S2'?'S2' as const:'S1' as const))].sort();
}
export function templateGroupSeason(group:{version?:unknown},selected?:string):'S1'|'S2'{
 const seasons=templateGroupSeasons(group);
 return seasons.find(season=>season===selected)??seasons[0];
}
function validScopeList(value:unknown,version:boolean){
 if(typeof value==='string')return true;
 if(!Array.isArray(value)||!value.length||!value.every(item=>validName(item)&&item===item.trim()&&item.length<=80))return false;
 const allowed=version?value.map(item=>item.toUpperCase()):value;
 return new Set(allowed).size===allowed.length&&(!version||allowed.every(item=>item==='S1'||item==='S2'));
}
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
  !Array.isArray(candidate.events)||!candidate.events.every(record)||!Array.isArray(candidate.groups))
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
 const readGroup=(row:JsonObject):TemplateGroup=>{
  const event=typeof row.event_name==='string'?namedEvents.get(row.event_name):undefined;
  if(!event)throw new Error('文件中未定义事件：'+String(row.event_name??''));
  const v04=row.syntax_version==='0.4';
  if(row.syntax_version!==undefined&&!v04)throw new Error('不支持模板语法版本。');
  const validUtterance=(value:unknown)=>v04?record(value)&&validName(value.id)&&validName(value.text)
   &&['ignored','fixed'].every(key=>value[key]===undefined||typeof value[key]==='boolean'):validName(value);
  if(!validName(row.name)||typeof row.expression!=='string'||!Array.isArray(row.utterances)||!row.utterances.length||
   !row.utterances.every(validUtterance)||row.condition_tree!=null&&!validTree(row.condition_tree))
   throw new Error('模板组无效：'+String(row.name??''));
  if(v04){
   if(typeof row.extra_key!=='string')throw new Error('模板组需要额外信息键。');
   if(row.editor_mode==='tree'||row.condition_tree||Array.isArray(row.conditions)&&row.conditions.length)
    throw new Error('v0.4 模板使用文本条件。');
   validateExtraKey(event.name,row.extra_key);
   validateV04(event.name,row.expression);
   const rows=row.utterances as {id:string;text:string}[];
   if(new Set(rows.map(item=>item.id)).size!==rows.length)throw new Error('话术 ID 重复。');
   for(const entry of rows)validateV04Template(event.name,entry.text);
  }
  const versions=templateVersionValues(row.version);
  const identity=[event.name,row.name,versions.length===1?versions[0]:templateRangeKey(versions)];
  if(Array.isArray(row.mode))identity.push(templateRangeKey(templateRangeValues(row.mode)));
  const id=typeof row.id==='string'?row.id:localId('group',JSON.stringify(identity));
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
  const invalidMetadata=(['explanation','explanation_before','explanation_source','explanation_after','reviewed_by','reviewed_at'] as const)
   .some(key=>Object.hasOwn(row,key)&&typeof row[key]!=='string')||
   (['version','mode'] as const).some(key=>Object.hasOwn(row,key)&&!validScopeList(row[key],key==='version'))||
   (['batch','tags'] as const).some(key=>Object.hasOwn(row,key)&&(!Array.isArray(row[key])||!(row[key] as unknown[]).every(validName)))||
   (Object.hasOwn(row,'review_status')&&row.review_status!==null&&!['ai_generated','initial_reviewed','final_reviewed'].includes(String(row.review_status)))||
   (Object.hasOwn(row,'last_modified_by')&&(!record(row.last_modified_by)||
    !(row.last_modified_by.kind==='ai'||row.last_modified_by.kind==='user'&&validName(row.last_modified_by.username))))||
   (Object.hasOwn(row,'entity_snapshot')&&(!record(row.entity_snapshot)||!validName(row.entity_snapshot.season)||
    !record(row.entity_snapshot.entities)||!Object.values(row.entity_snapshot.entities).every(record)));
  if(Object.hasOwn(row,'wording_brief')&&typeof row.wording_brief!=='string')
   throw new Error('话术构思须为文本：'+row.name);
  if(invalidMetadata)throw new Error('模板组的标记或审核资料无效：'+row.name);
  return {id,name:row.name,event_id:event.id,scope:{player_id,lineup_note_id},conditions,related_entities,expression:row.expression,
   ...(typeof row.ignored==='boolean'?{ignored:row.ignored}:{}),
   editor_mode:row.editor_mode==='tree'?'tree':'text',condition_tree:row.condition_tree as ConditionNode|null|undefined,
   priority:typeof row.priority==='number'?row.priority:0,
   ...(v04?{syntax_version:'0.4' as const,extra_key:row.extra_key as string}:{}),
   ...(typeof row.publication_hold==='string'?{publication_hold:row.publication_hold}:{}),
   utterances:v04?row.utterances as TemplateGroup['utterances']:row.utterances.map((text,index)=>legacyUtterance(text,index,row.legacy_utterance_flags)),
   ...Object.fromEntries(metadata.filter(key=>Object.hasOwn(row,key)).map(key=>[key,row[key]])),
  };
 };
 const groups:TemplateGroup[]=[],groupIndexes:number[]=[],groupErrors:TemplateFile['groupErrors']=[],ids=new Set<string>();
 const comments:TemplateFile['comments']=new Map();
 document.groups.forEach((row,index)=>{
  try{
   if(!record(row))throw new Error('模板组必须是对象。');
   const group=readGroup(row);
   if(ids.has(group.id))throw new Error('文件中有重名或重复编号的模板组：'+group.name);
   ids.add(group.id);
   groups.push(group);
   groupIndexes.push(index);
   const visible=storedComments(row).filter(isLocalComment).filter(comment=>!comment.detached&&
    (!comment.utterance_id||group.utterances.some(entry=>entry.id===comment.utterance_id&&
     (group.syntax_version==='0.4'||entry.text===comment.target_text))));
   if(visible.length)comments.set(group.id,visible);
  }catch(error){
   const label=record(row)&&validName(row.name)?'「'+row.name+'」':'';
   groupErrors.push({index,message:'第 '+(index+1)+' 组'+label+'：'+(error as Error).message});
  }
 });
 const portableCatalog=document.condition_catalog;
 const condition_catalog=record(portableCatalog)&&record(portableCatalog.events)&&Object.values(portableCatalog.events).every(event=>record(event)&&record(event.parameters))&&record(portableCatalog.aliases)&&record(portableCatalog.types)&&
  record(portableCatalog.operations)&&record(portableCatalog.roots)?portableCatalog as ConditionCatalog:undefined;
 return {document,groupIndexes,groupErrors,comments,snapshot:{schema_version:3,revision:'local-file',groups,events,scope_names:scopeNames,condition_catalog}};
}

function selectedFileDocument(file:TemplateFile,groups:JsonObject[]){
 const eventNames=new Set(groups.map(group=>group.event_name));
 return {kind:'speech-template-library' as const,schema_version:3 as const,groups,events:file.document.events.filter((_,index)=>eventNames.has(file.snapshot.events[index].name))};
}

function withFileSelection(file:TemplateFile,selection:ReturnType<typeof selectedFileDocument>):FileDocument{
 const catalog=file.snapshot.condition_catalog;
 const names=new Set(selection.groups.map(group=>group.event_name));
 return {...file.document,...selection,...(catalog?{condition_catalog:{...catalog,
  events:Object.fromEntries(Object.entries(catalog.events).filter(([name])=>names.has(name)))}}:{})};
}

function deliveryGroups(file:TemplateFile,ids:Iterable<string>|undefined,includeComments:boolean){
 const selected=ids===undefined?undefined:new Set(ids);
 return file.snapshot.groups.flatMap((group,index)=>{
  if(group.ignored||selected&&!selected.has(group.id))return [];
  const source=file.document.groups[file.groupIndexes[index]] as JsonObject;
  const {ignored:_,legacy_utterance_flags:__,file_comments:___,...row}=source;
  const live=group.utterances.filter(utterance=>!utterance.ignored);
  if(!live.length)return [];
  const ids=new Map(live.map((utterance,index)=>[utterance.id,group.syntax_version==='0.4'?utterance.id:legacyUtteranceId(index)]));
  const comments=includeComments?file.comments.get(group.id)?.flatMap(comment=>{
   if(!comment.utterance_id)return [comment];
   const id=ids.get(comment.utterance_id);
   return id?[{...comment,utterance_id:id}]:[];
  }):undefined;
  const flags=includeComments&&group.syntax_version!=='0.4'?legacyFlags(live):undefined;
  return [{...row,utterances:group.syntax_version==='0.4'?live:live.map(utterance=>utterance.text),
   ...(flags?{legacy_utterance_flags:flags}:{}),
   ...(comments?.length?{file_comments:comments}:{})}];
 });
}

export function fileDeliveryDocument(file:TemplateFile,ids?:Iterable<string>):FileDocument{
 const groups=deliveryGroups(file,ids,true);
 if(ids===undefined)return {...file.document,groups};
 const {note:_,...document}=withFileSelection(file,selectedFileDocument(file,groups));
 return document;
}

export function fileImportDocument(file:TemplateFile,ids:Iterable<string>){
 return selectedFileDocument(file,deliveryGroups(file,ids,false));
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
 if(incoming.groupErrors.length)throw new Error(incoming.groupErrors[0].message);
 if(mode==='new'&&raw.length)throw new Error('目标文件已有内容，请使用「合并到已有文件」。');
 const target=mode==='merge'?parseTemplateFile(raw):null;
 const current=target?.document.groups??[];
 const groups=[...current];
 const positions=new Map(current.flatMap((row,index)=>record(row)&&validName(row.id)?[[row.id,index] as const]:[]));
 const replaced=new Set<number>();
 const validIncoming=incoming.document.groups.filter(record);
 const changes=validIncoming.map(row=>{
  const index=validName(row.id)?positions.get(row.id):undefined;
  if(index===undefined){groups.push(row);return {name:String(row.name),action:'add' as const};}
  replaced.add(index);
  const existing=current[index] as JsonObject;
  const notes=new Map([...storedComments(row),...storedComments(existing)].map(note=>[isLocalComment(note)?note.id:note,note]));
  const replacement:JsonObject=notes.size?{...row,file_comments:[...notes.values()]}:row;
  if(sameJson(replacement,existing))return {name:String(row.name),action:'unchanged' as const};
  groups[index]=replacement;
  return {name:String(row.name),previousName:String((current[index] as JsonObject).name??''),action:'replace' as const};
 });
 if(!target)return {document:incoming.document,changes,eventChanges:[],changed:true};
 if(Object.hasOwn(target.document,'condition_catalog')&&!target.snapshot.condition_catalog)
  throw new Error('目标文件包含无法识别的条件目录，请先修复目录后再合并。');

 const events=new Map(target.snapshot.events.map((event,index)=>[event.name,{event,row:target.document.events[index]}]));
 const referenced=new Set(validIncoming.map(row=>row.event_name));
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
   if(current.some((group,index)=>record(group)&&group.event_name===event.name&&!replaced.has(index)))
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
 const parsed=parseTemplateFile(JSON.stringify(document));
 assertNoNewGroupErrors(target,document,parsed);
 return {document,changes,eventChanges:typed.map(({event})=>event.name),changed:true};
}

type FileGroupRow={value:TemplateGroup;row:JsonObject};
const groupMergeFamily=(group:TemplateGroup)=>JSON.stringify([group.event_id,group.name.trim()]);
function fileGroupKey({value:group,row}:FileGroupRow,event:TemplateEvent|undefined){
 const scope=record(row.scope)?row.scope:{};
 const player=typeof scope.player==='string'?scope.player:null,lineup=typeof scope.lineup==='string'?scope.lineup:null;
 const expression=group.editor_mode==='tree'&&group.condition_tree?renderRule(group.condition_tree):group.expression??'';
 const effective=effectiveExpression(player,lineup,expression,group.syntax_version);
 const condition=(source:string)=>{
  if(group.syntax_version==='0.4'){
   try{return v04ConditionKey(source);}
   catch{return source;}
  }
  return source.match(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[\p{L}\p{N}_]+|>=|<=|==|!=|[^\s]/gu)??[];
 };
 const parameters=event?.parameters.map(({key,type,dsl_type,entity_categories,min,max})=>
  JSON.stringify([key,type,dsl_type,[...(entity_categories??[])].sort(),min,max])).sort();
 const clauses=group.conditions.map(({parameter_key,operator,value})=>
  JSON.stringify([parameter_key,operator,record(value)?value.name??value:value])).sort();
 return JSON.stringify([group.name.trim(),group.event_id,event?.name,parameters,group.syntax_version,group.extra_key,
  condition(effective),clauses,
  templateRangeKey(templateVersionValues(group.version)),templateRangeKey(templateRangeValues(group.mode)),!!group.ignored,group.publication_hold??'']);
}

function mergeFileGroup(target:FileGroupRow,source:FileGroupRow,original:TemplateGroup|undefined):FileGroupRow{
 const value={...target.value,utterances:[...target.value.utterances]},row={...target.row};
 const sourcePriority=source.value.priority??0;
 if(sourcePriority>(value.priority??0))value.priority=row.priority=sourcePriority;
 const v04=value.syntax_version==='0.4';
 const texts=new Map<string,number>(),ids=new Set<string>();
 value.utterances.forEach((utterance,index)=>{
  if(!texts.has(utterance.text))texts.set(utterance.text,index);
  ids.add(utterance.id);
 });
 const targets=new Map<string,{id:string;text:string}>();
 const legacyIds=(utterance:TemplateGroup['utterances'][number],index:number)=>v04?utterance.id:legacyUtteranceId(index);
 source.value.utterances.forEach((incoming,index)=>{
  const matched=texts.get(incoming.text);
  if(matched!==undefined){
   const retained=value.utterances[matched];
   if(incoming.fixed&&!retained.fixed)value.utterances[matched]={...retained,fixed:true,ignored:false};
   if(retained.ignored&&!incoming.ignored)value.utterances[matched]={...value.utterances[matched],ignored:false};
   targets.set(legacyIds(incoming,index),{id:legacyIds(retained,matched),text:incoming.text});
   return;
  }
  const next={...incoming,id:v04&&ids.has(incoming.id)?templateId('utterance'):incoming.id};
  targets.set(legacyIds(incoming,index),{id:legacyIds(next,value.utterances.length),text:incoming.text});
  texts.set(next.text,value.utterances.length);
  ids.add(next.id);
  value.utterances.push(next);
 });
 row.utterances=v04?value.utterances:value.utterances.map(utterance=>utterance.text);
 const flags=v04?undefined:legacyFlags(value.utterances);
 if(flags)row.legacy_utterance_flags=flags;else delete row.legacy_utterance_flags;
 const comments=[...storedComments(row)],commentIds=new Set(comments.filter(isLocalComment).map(comment=>comment.id));
 for(const comment of storedComments(source.row)){
  if(!isLocalComment(comment)){comments.push(comment);continue;}
  if(commentIds.has(comment.id))continue;
  commentIds.add(comment.id);
  const target=comment.utterance_id&&targets.get(comment.utterance_id);
  comments.push(comment.detached||!comment.utterance_id?comment:
   target&&(v04||comment.target_text===target.text)?{...comment,utterance_id:target.id}:{...comment,detached:true});
 }
 if(comments.length)row.file_comments=comments;
 const previous=original??target.value;
 const previouslySelectable=new Set(previous.utterances.filter(utterance=>!utterance.ignored).map(utterance=>utterance.text));
 if(value.utterances.some(utterance=>!utterance.ignored&&!previouslySelectable.has(utterance.text))){
  value.review_status=row.review_status=null;
  if(source.value.last_modified_by)value.last_modified_by=row.last_modified_by=source.value.last_modified_by;
  delete value.reviewed_by;delete row.reviewed_by;
  delete value.reviewed_at;delete row.reviewed_at;
 }else if(previous.review_status==='initial_reviewed'||previous.review_status==='final_reviewed'){
  for(const key of ['review_status','reviewed_by','reviewed_at'] as const){
   if(previous[key]===undefined){delete value[key];delete row[key];}
   else{Object.assign(value,{[key]:previous[key]});row[key]=previous[key];}
  }
 }
 return {value,row};
}

export function writeTemplateDocument(file:TemplateFile,changes:TemplateChange[],lookups:FileLookups={},mergedIds?:Map<string,string>):FileDocument{
 const events=new Map(file.snapshot.events.map((event,index)=>[event.id,{value:event,row:file.document.events[index]}]));
 const groups=new Map(file.snapshot.groups.map((group,index)=>[group.id,{value:group,row:file.document.groups[file.groupIndexes[index]] as JsonObject}]));
 const idsByIndex=new Map(file.groupIndexes.map((index,position)=>[index,file.snapshot.groups[position].id]));
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
  const existingDual=new Set(previous?.value.utterances.filter(row=>row.fixed&&row.ignored).map(row=>row.id));
  if(value.utterances.some(row=>row.fixed&&row.ignored&&!existingDual.has(row.id)))
   throw new Error('同一条话术只能固定或忽略。');
  const event=events.get(value.event_id)?.value;
  if(!event)throw new Error('模板组引用了文件中不存在的事件。');
  const scope={
   player:value.scope.player_id===null?null:lookups.entities?.find(entity=>entity.id===value.scope.player_id)?.name??file.snapshot.scope_names?.[value.scope.player_id]??((fileTemplateScopeName('player',value.scope.player_id)??value.scope.player_id).trim()||null),
   lineup:value.scope.lineup_note_id===null?null:lookups.lineups?.find(note=>note.id===value.scope.lineup_note_id)?.title??file.snapshot.scope_names?.[value.scope.lineup_note_id]??((fileTemplateScopeName('lineup',value.scope.lineup_note_id)??value.scope.lineup_note_id).trim()||null),
  };
  const scopeChanged=previous&&(['version','mode'] as const).some(field=>JSON.stringify(previous.value[field])!==JSON.stringify(value[field]));
  const row:JsonObject={...(previous?.row??{id:value.id}),...(mergedIds||scopeChanged?{id:value.id}:{}),
   name:value.name,event_name:event.name,scope,expression:value.expression??'',effective_expression:effectiveExpression(scope.player,scope.lineup,value.expression??'',value.syntax_version),
   priority:value.priority??0,editor_mode:value.editor_mode??'text',condition_tree:value.condition_tree,
   utterances:value.syntax_version==='0.4'?value.utterances:value.utterances.map(utterance=>utterance.text),
  };
  if(value.ignored)row.ignored=true;else delete row.ignored;
  const flags=value.syntax_version==='0.4'?undefined:legacyFlags(value.utterances);
  if(flags)row.legacy_utterance_flags=flags;else delete row.legacy_utterance_flags;
  for(const key of ['syntax_version','extra_key','publication_hold'] as const){
   if(value[key]===undefined)delete row[key];else row[key]=value[key];
  }
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
  if(previous&&previous.value.syntax_version!=='0.4'&&Array.isArray(row.file_comments)){
   const oldRows=new Map(previous.value.utterances.map(utterance=>[utterance.id,utterance.text]));
   const nextRows=new Map(value.utterances.map((utterance,index)=>[utterance.id,{utterance,index}]));
   row.file_comments=row.file_comments.map(comment=>{
    if(!isLocalComment(comment)||comment.detached||!comment.utterance_id)return comment;
    const next=nextRows.get(comment.utterance_id);
    if(!next||comment.target_text!==oldRows.get(comment.utterance_id))return {...comment,detached:true};
    return {...comment,utterance_id:value.syntax_version==='0.4'?next.utterance.id:legacyUtteranceId(next.index),target_text:next.utterance.text};
   });
  }
  groups.set(change.id,{value,row});
 }
 if(mergedIds){
  const originalEvents=new Map(file.snapshot.events.map(event=>[event.id,event]));
  const originalGroups=new Map(file.snapshot.groups.map(group=>[group.id,group]));
  const affected=new Set(changes.filter(change=>change.kind==='group'&&change.action==='put').map(change=>change.id));
  const keyFor=(group:FileGroupRow)=>fileGroupKey(group,affected.has(group.value.id)
   ?events.get(group.value.event_id)?.value:originalEvents.get(group.value.event_id));
  const families=new Set<string>(),keys=new Set<string>();
  for(const id of affected){
   const group=groups.get(id);
   if(group){families.add(groupMergeFamily(group.value));keys.add(keyFor(group));}
  }
  const targets=new Map<string,string>(),seen=new Set<string>();
  for(const [id,group] of groups){
   if(!families.has(groupMergeFamily(group.value)))continue;
   const key=keyFor(group);
   if(!keys.has(key))continue;
   const target=targets.get(key);
   if(target===undefined){targets.set(key,id);continue;}
   const canonical=groups.get(target)!;
   groups.set(target,mergeFileGroup(canonical,group,seen.has(target)?undefined:originalGroups.get(target)));
   seen.add(target);
   groups.delete(id);
   mergedIds.set(id,target);
  }
 }
 const groupRow=({value,row}:{value:TemplateGroup;row:JsonObject})=>{
  const event=events.get(value.event_id)?.value;
  if(!event)throw new Error('事件仍被模板组引用：'+value.name);
  return event.name===row.event_name?row:{...row,...(mergedIds?{id:value.id}:{}),event_name:event.name};
 };
 const rows=file.document.groups.flatMap((row,index)=>{
  const id=idsByIndex.get(index);
  if(id===undefined)return [row];
  const updated=groups.get(id);
  groups.delete(id);
  return updated?[groupRow(updated)]:[];
 });
 return {...file.document,...(catalog?{condition_catalog:catalog}:{}),events:[...events.values()].map(({row})=>row),
  groups:[...rows,...[...groups.values()].map(groupRow)]};
}

export function assertNoNewGroupErrors(previous:TemplateFile,next:FileDocument,parsed:TemplateFile){
 const existing=new Set(previous.groupErrors.map(({index})=>previous.document.groups[index]));
 const error=parsed.groupErrors.find(({index})=>!existing.has(next.groups[index]));
 if(error)throw new Error(error.message);
}

export function writeLocalComment(file:TemplateFile,groupId:string,target:TemplateGroup['utterances'][number]|undefined,message:CommentMessage):FileDocument{
 const position=file.snapshot.groups.findIndex(group=>group.id===groupId);
 if(position===-1)throw new Error('模板组已不存在，请重新读取文件。');
 const group=file.snapshot.groups[position],utterance=target&&group.utterances.find(row=>row.id===target.id);
 if(target&&utterance?.text!==target.text)throw new Error('话术已有修改或已删除，请重新核对。');
 const body=message.body.trim();
 if(!body||body.length>4000)throw new Error('批注须为 1 至 4000 字。');
 const comment:LocalTemplateComment={...message,body,...(utterance?{
  utterance_id:utterance.id,original_text:utterance.text,...(group.syntax_version==='0.4'?{}:{target_text:utterance.text}),
 }:{})};
 const index=file.groupIndexes[position],row=file.document.groups[index] as JsonObject;
 const groups=[...file.document.groups];
 groups[index]={...row,file_comments:[...storedComments(row),comment]};
 return {...file.document,groups};
}

export function reviewLocalGroup(group:TemplateGroup,username:string,action:'edit'|'final',at=new Date().toISOString()):TemplateGroup{
 if(action==='final')return {...group,review_status:'final_reviewed',reviewed_by:username,reviewed_at:at};
 const {reviewed_at:_,reviewed_by:__,...next}=group;
 return {...next,review_status:null,last_modified_by:{kind:'user',username}};
}

export function writeLocalReviewStatus(file:TemplateFile,group:TemplateGroup):FileDocument{
 const targetIndex=file.groupIndexes[file.snapshot.groups.findIndex(row=>row.id===group.id)];
 return {...file.document,groups:file.document.groups.map((row,index)=>{
  if(index!==targetIndex||!record(row))return row;
  const {reviewed_by:_,reviewed_at:__,...content}=row;
  return {...content,review_status:group.review_status,
   ...(group.reviewed_by?{reviewed_by:group.reviewed_by,reviewed_at:group.reviewed_at}:{})};
 })};
}

export function withLocalEntitySnapshot(group:TemplateGroup,event:TemplateEvent|undefined,official:OfficialTemplateCatalog|undefined,linked:TemplateEntity[],catalog?:ConditionCatalog,fallback:Entity[]=[],selectedSeason?:string):TemplateGroup{
 const season=templateGroupSeason(group,selectedSeason??official?.season),verified=official?.season===season?official:undefined;
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

export function fixEditedLocalUtterances(previous:TemplateGroup,group:TemplateGroup):TemplateGroup{
 const originals=new Map(previous.utterances.map(row=>[row.id,row]));
 return {...group,utterances:group.utterances.map(row=>
  !row.ignored&&originals.get(row.id)?.text!==row.text?{...row,fixed:true}:row)};
}

async function pickJsonFiles(multiple:boolean,startIn?:LocalFileHandle){
 const choose=(window as Window&{showOpenFilePicker?:(options:unknown)=>Promise<LocalFileHandle[]>}).showOpenFilePicker;
 if(!choose)throw new Error('当前浏览器无法直接打开并写回文件。请使用 Chrome 或 Edge。');
 const handles=await choose.call(window,{...(startIn?{startIn}:{}),multiple,types:[{description:'话术模板库 JSON',accept:{'application/json':['.json']}}]});
 if(!handles.length)throw new DOMException('未选择文件','AbortError');
 return handles;
}

export async function pickTemplateFile(startIn?:LocalFileHandle){
 return (await pickJsonFiles(false,startIn))[0];
}

export async function pickTemplateLibrary(startIn?:LocalFileHandle){
 const handles=await pickJsonFiles(true,startIn);
 if(handles.length===1)return {handle:handles[0]};
 const handle=handles.find(item=>handles.some(other=>other.name===item.name.replace(/\.json$/i,'')+'-detail.json'));
 if(handles.length!==2||!handle)throw new Error('请选择一个模板库，可同时选择同名的 -detail.json。');
 return {handle,detail:handles.find(item=>item!==handle)};
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
