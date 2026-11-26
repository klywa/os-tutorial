import type {LocalFileHandle} from './templateFile';

type Fields=Record<string,unknown>;
type Attempt=Fields&{id:string};
export type TraceNode=Fields&{stage:string;selected_version:string;input:unknown;output:unknown;attempts:Attempt[];revisions:Attempt[]};
type Sentence={text:string;point_id:string;event_id:string;condition_id:string;candidate_id?:string;node_ids:string[];node_versions?:Record<string,string>};
export type TemplateTrace={schema_version:1;run_id:string;library_sha256:string;groups:Record<string,{sentences:Record<string,Sentence>}>;nodes:Record<string,TraceNode>};
export type LoadedTrace={trace:TemplateTrace;name:string;modified?:boolean};

const object=(value:unknown):value is Fields=>!!value&&typeof value==='object'&&!Array.isArray(value);
const versions=(value:unknown)=>Array.isArray(value)&&value.every(item=>object(item)&&typeof item.id==='string');

export function parseTemplateTrace(raw:string):TemplateTrace{
 const data:unknown=JSON.parse(raw);
 if(!object(data)||data.schema_version!==1||typeof data.run_id!=='string'||typeof data.library_sha256!=='string'||!object(data.groups)||!object(data.nodes))
  throw new Error('溯源文件格式无效，请选择工作流生成的 -detail.json。');
 const nodes=data.nodes;
 for(const [id,node] of Object.entries(nodes)){
  if(!object(node)||typeof node.stage!=='string'||typeof node.selected_version!=='string'||!versions(node.attempts)||!versions(node.revisions))
   throw new Error('溯源节点格式无效：'+id);
 }
 for(const [id,group] of Object.entries(data.groups)){
  if(!object(group)||!object(group.sentences))throw new Error('缺少模板组的句级索引：'+id);
  for(const [sentenceId,sentence] of Object.entries(group.sentences)){
   if(!object(sentence)||!['point_id','event_id','condition_id','text'].every(key=>typeof sentence[key]==='string')||
    (sentence.candidate_id!==undefined&&typeof sentence.candidate_id!=='string')||!Array.isArray(sentence.node_ids)||!sentence.node_ids.length||!sentence.node_ids.every(ref=>typeof ref==='string'&&Object.hasOwn(nodes,ref)))
    throw new Error('句级溯源记录不完整：'+sentenceId);
   if(sentence.node_versions!==undefined){
    const used=sentence.node_versions;
    if(!object(used)||!sentence.node_ids.every(ref=>{
     const node=nodes[ref] as TraceNode;
     return typeof used[ref]==='string'&&[...node.attempts,...node.revisions].some(version=>version.id===used[ref]);
    }))throw new Error('找不到这句话采用的节点版本：'+sentenceId);
   }
  }
 }
 return data as TemplateTrace;
}

export const detailFileName=(name:string)=>name.replace(/\.json$/i,'')+'-detail.json';

export async function loadTemplateTrace(handle:Pick<LocalFileHandle,'name'|'getFile'>,library?:{name:string;raw:string}):Promise<LoadedTrace>{
 if(library&&handle.name!==detailFileName(library.name))throw new Error('请选择对应的 '+detailFileName(library.name));
 const trace=parseTemplateTrace(await (await handle.getFile()).text());
 if(!library)return {trace,name:handle.name};
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(library.raw));
 const digest=Array.from(new Uint8Array(bytes),byte=>byte.toString(16).padStart(2,'0')).join('');
 return {trace,name:handle.name,modified:digest!==trace.library_sha256};
}
