import type {LocalFileHandle} from './templateFile';

type Fields=Record<string,unknown>;
type KnowledgeItem={original:string;type:string;prerequisite:string;related_knowledge:string};
type Writing={limited:string;not_limited:string;expected:string;wording:string};
type TraceEvent={id:string;event:string;expected:string};
type RejectedEvent={event_id:string;reason:string};
type TraceCondition=Writing&{id:string;event_id:string;extra_key?:string;expression:string;reason:string};
type TracePoint={type?:string;knowledge:string;events:TraceEvent[];conditions:TraceCondition[];rejected?:RejectedEvent[]};
const stages=['identify','enrich','events','conditions','phrases'] as const;
export type TraceStage=typeof stages[number];
type TraceGroup={point_id:string;event_id:string;condition_id:string;knowledge_list_id:string;prompt_ids:Partial<Record<TraceStage,string>>;writing:Writing;sentences:Record<string,string>};
export type TemplateTrace={
 schema_version:2;run_id:string;library_name:string;library_sha256:string;
 knowledge_lists:Record<string,KnowledgeItem[]>;prompts:Record<string,string>;
 points:Record<string,TracePoint>;groups:Record<string,TraceGroup>;
};
export type LoadedTrace={trace:TemplateTrace;name:string;modified:boolean};
type LibraryIdentity={name:string;raw:string;groups?:readonly {id:string;utterances:readonly {id:string}[]}[]};

const object=(value:unknown):value is Fields=>!!value&&typeof value==='object'&&!Array.isArray(value);
const hasStrings=(value:unknown,...keys:string[]):value is Fields=>object(value)&&keys.every(key=>typeof value[key]==='string');
const stringMap=(value:unknown):value is Record<string,string>=>object(value)&&Object.values(value).every(text=>typeof text==='string');
const writingKeys=['limited','not_limited','expected','wording'];

export function parseTemplateTrace(raw:string):TemplateTrace{
 const invalid='溯源文件格式无效，请将本次生成的同名 -detail.json 放回模板目录。';
 let data:unknown;
 try{data=JSON.parse(raw);}catch{throw new Error(invalid);}
 if(!hasStrings(data,'run_id','library_name','library_sha256')||data.schema_version!==2||
  !object(data.knowledge_lists)||!stringMap(data.prompts)||!object(data.points)||!object(data.groups))throw new Error(invalid);
 const {knowledge_lists:lists,prompts,points,groups}=data;
 for(const list of Object.values(lists)){
  if(!Array.isArray(list)||!list.every(item=>hasStrings(item,'original','type','prerequisite','related_knowledge')))throw new Error(invalid);
 }
 for(const point of Object.values(points)){
  if(!hasStrings(point,'knowledge')||(point.type!==undefined&&(typeof point.type!=='string'||!point.type.trim()))||
   !Array.isArray(point.events)||!point.events.every(event=>hasStrings(event,'id','event','expected'))||
   !Array.isArray(point.conditions)||!point.conditions.every(condition=>hasStrings(condition,'id','event_id','expression','reason',...writingKeys)&&
    (condition.extra_key===undefined||typeof condition.extra_key==='string'))||
   (point.rejected!==undefined&&(!Array.isArray(point.rejected)||!point.rejected.every(event=>hasStrings(event,'event_id','reason')))))throw new Error(invalid);
 }
 for(const [id,group] of Object.entries(groups)){
  if(!hasStrings(group,'point_id','event_id','condition_id','knowledge_list_id')||!hasStrings(group.writing,...writingKeys)||!stringMap(group.sentences)||!stringMap(group.prompt_ids))
   throw new Error('溯源文件的模板组记录不完整：'+id);
  const item=group as TraceGroup,point=Object.hasOwn(points,item.point_id)?points[item.point_id] as TracePoint:undefined;
  const sentences=Object.values(item.sentences);
  if(!point||!point.events.some(event=>event.id===item.event_id)||!point.conditions.some(condition=>condition.id===item.condition_id&&condition.event_id===item.event_id)||
   !Object.hasOwn(lists,item.knowledge_list_id)||sentences.length!==6||sentences.some(text=>!text.trim())||
   Object.entries(item.prompt_ids).some(([stage,ref])=>!stages.includes(stage as TraceStage)||!Object.hasOwn(prompts,ref)))
   throw new Error('溯源文件的模板组记录不完整：'+id);
 }
 return data as TemplateTrace;
}

export const detailFileName=(name:string)=>name.replace(/\.json$/i,'')+'-detail.json';

export async function loadTemplateTrace(handle:Pick<LocalFileHandle,'name'|'getFile'>,library:LibraryIdentity):Promise<LoadedTrace>{
 const trace=parseTemplateTrace(await (await handle.getFile()).text());
 const mismatch='溯源文件与当前主库不匹配，请将本次生成的同名 -detail.json 放回模板目录。';
 if(handle.name!==detailFileName(library.name)||trace.library_name!==library.name)throw new Error(mismatch);
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(library.raw));
 const digest=Array.from(new Uint8Array(bytes),byte=>byte.toString(16).padStart(2,'0')).join('');
 const modified=digest!==trace.library_sha256;
 if(modified&&library.groups&&Object.keys(trace.groups).length&&!library.groups.some(group=>{
  const entry=Object.hasOwn(trace.groups,group.id)?trace.groups[group.id]:undefined;
  return entry&&group.utterances.some(sentence=>Object.hasOwn(entry.sentences,sentence.id));
 }))throw new Error(mismatch);
 return {trace,name:handle.name,modified};
}
