import {seasons,type Season} from './seasons';
import type {KnowledgeDocument,Note} from './types';

export type WorkbenchSource='database'|'file';
type PermissionMode='read'|'readwrite';
export interface BrowserDirectory {
 readonly name:string;
 getDirectoryHandle(name:string):Promise<BrowserDirectory>;
 getFileHandle(name:string,options?:{create?:boolean}):Promise<{
  getFile():Promise<{text():Promise<string>}>;
  createWritable():Promise<{write(value:string):Promise<void>;close():Promise<void>;abort():Promise<void>}>;
 }>;
 removeEntry(name:string):Promise<void>;
 requestPermission?(options:{mode:PermissionMode}):Promise<PermissionState>;
}

type JsonObject=Record<string,unknown>;
export type FileNoteEntry=JsonObject&Pick<Note,'id'|'type'|'title'|'path'|'revision'|'player_id'|'seasons'>;
type FileNoteIndex=JsonObject&{schema_version:6;storage_version?:number;notes:FileNoteEntry[]};
type FileMetadata=FileNoteEntry&{body_sha256:string};
type NoteFiles=readonly [string,string,string];
export type FileNote={body:KnowledgeDocument;metadata:FileMetadata;files:NoteFiles};
export type FileNoteDraft={document:KnowledgeDocument;seasons:Season[];title?:string;aliases?:string[]};
type Journal={version:1;paths:NoteFiles;before:NoteFiles;after:NoteFiles};

const indexPath='index.meta.json';
export const notesJournal='pending-browser-note-save.json';
const folders={lineup:'lineups',player:'players',other:'other'} as const;
const missing=(error:unknown)=>error instanceof DOMException&&error.name==='NotFoundError';
const outsideChange=()=>new Error('笔记文件或索引已被外部修改。草稿仍然保留，请重新核对文件后编辑。');

export function browserDirectoryPicker(){
 return (window as Window&{showDirectoryPicker?:(options:{id:string;mode:PermissionMode})=>Promise<BrowserDirectory>}).showDirectoryPicker?.bind(window);
}

function localNotePath(path:string){
 if(!/^knowledge\/(?:lineups|players|other)\/[^/\\]+\.json$/.test(path)||path.endsWith('.meta.json'))throw new Error('索引包含无效的笔记文件路径');
 return path.slice('knowledge/'.length);
}

async function target(directory:BrowserDirectory,path:string){
 const parts=path.split('/');const name=parts.pop()!;
 for(const part of parts)directory=await directory.getDirectoryHandle(part);
 return {directory,name};
}
async function read(directory:BrowserDirectory,path:string){
 const file=await target(directory,path);
 return (await (await file.directory.getFileHandle(file.name)).getFile()).text();
}
async function readOptional(directory:BrowserDirectory,path:string){
 try{return await read(directory,path);}catch(e){if(!missing(e))throw e;return null;}
}
async function write(directory:BrowserDirectory,path:string,value:string,create=false){
 const file=await target(directory,path);
 const stream=await (await file.directory.getFileHandle(file.name,{create})).createWritable();
 try{await stream.write(value);await stream.close();}
 catch(error){await stream.abort().catch(()=>{});throw error;}
}

type NumericToken={value:number;source:string};
type NumberTokens=Map<string,NumericToken>;
function valuePath(path:string[],key:string,owner:object,value:unknown){
 // Moving a body node must also move its unknown fields' original JSON numbers.
 if(Array.isArray(owner)&&['nodes','supporting_nodes'].includes(path.at(-1)??'')&&value&&typeof value==='object'&&'id' in value&&typeof value.id==='string')return [...path,'id:'+value.id];
 return [...path,key];
}
// JSON keeps values convenient for React. The original numeric spellings are needed for the Python store's canonical hashes.
function parse<T>(text:string){
 const tokens:NumberTokens=new Map();
 const numbers=new WeakMap<object,Map<string,NumericToken>>();
 const value=JSON.parse(text.replace(/^\uFEFF/,''),function(this:object,key:string,item:unknown,context?:{source?:string}){
  if(typeof item==='number'&&context?.source){
   if(!numbers.has(this))numbers.set(this,new Map());
   numbers.get(this)!.set(key,{value:item,source:context.source});
  }
  return item;
 }) as T;
 function collect(item:unknown,path:string[]){
  if(!item||typeof item!=='object')return;
  for(const [key,child] of Object.entries(item)){
   const next=valuePath(path,key,item,child);const token=numbers.get(item)?.get(key);
   if(token)tokens.set(JSON.stringify(next),token);else collect(child,next);
  }
 }
 collect(value,[]);
 return {value,tokens};
}
function combineNumbers(...entries:{prefix:string[];tokens:NumberTokens}[]){
 const tokens:NumberTokens=new Map();
 for(const entry of entries)for(const [path,token] of entry.tokens)tokens.set(JSON.stringify([...entry.prefix,...JSON.parse(path)]),token);
 return tokens;
}
const codePointOrder=(a:string,b:string)=>{
 const left=[...a],right=[...b];
 for(let i=0;i<Math.min(left.length,right.length);i++){
  const diff=left[i].codePointAt(0)!-right[i].codePointAt(0)!;
  if(diff)return diff;
 }
 return left.length-right.length;
};
function pythonNumber(value:number,raw?:string){
 if(raw&&!/[.eE]/.test(raw))return raw==='-0'?'0':raw;
 if(raw||!Number.isInteger(value)){
  if(Object.is(value,-0))return '-0.0';
  if(value!==0&&(Math.abs(value)<0.0001||Math.abs(value)>=1e16))return value.toExponential().replace(/e([+-])(\d)$/,'e$10$2');
  return Number.isInteger(value)?value.toFixed(1):String(value);
 }
 return BigInt(value).toString();
}
function encode(value:unknown,tokens:NumberTokens,pretty=false){
 function part(item:unknown,path:string[]):string{
  if(typeof item==='number'){
   const token=tokens.get(JSON.stringify(path));
   return pythonNumber(item,token&&Object.is(token.value,item)?token.source:undefined);
  }
  if(!item||typeof item!=='object')return JSON.stringify(item);
  const entries=Object.entries(item);
  if(!pretty&&!Array.isArray(item))entries.sort(([a],[b])=>codePointOrder(a,b));
  const rendered=entries.map(([key,child])=>(Array.isArray(item)?'':JSON.stringify(key)+': ')+part(child,valuePath(path,key,item,child)));
  const indent='  '.repeat(path.length);
  const content=pretty&&rendered.length?'\n'+indent+'  '+rendered.join(',\n'+indent+'  ')+'\n'+indent:rendered.join(', ');
  return Array.isArray(item)?'['+content+']':'{'+content+'}';
 }
 return part(value,[])+(pretty?'\n':'');
}
async function digest(value:unknown,tokens:NumberTokens){
 const hashed=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(encode(value,tokens)));
 return Array.from(new Uint8Array(hashed),byte=>byte.toString(16).padStart(2,'0')).join('');
}

function checkIndex(value:FileNoteIndex){
 if(value?.schema_version!==6||!Array.isArray(value.notes))throw new Error('请选择包含版本 6 笔记索引的项目或 knowledge 目录');
 const ids=new Set<string>(),paths=new Set<string>();
 for(const row of value.notes){
  if(!row||!row.id||!row.title||typeof row.path!=='string'||!Object.hasOwn(folders,row.type)||!row.path.startsWith('knowledge/'+folders[row.type]+'/'))throw new Error('笔记索引项目无效');
  const path=localNotePath(row.path).toLowerCase();
  if(ids.has(row.id)||paths.has(path))throw new Error('笔记索引有重复的身份或文件名');
  ids.add(row.id);paths.add(path);
 }
 return value;
}
function checkRecord(body:KnowledgeDocument,metadata:FileMetadata){
 if(typeof metadata?.title!=='string'||!metadata.title.trim()||!Array.isArray(body?.nodes)||body.schema_version!==6)throw new Error('笔记标题或正文格式无效');
 const ids=new Set<string>();
 for(const node of [...body.nodes,...(body.supporting_nodes??[])]){
  if(typeof node.id!=='string'||!node.id||ids.has(node.id))throw new Error('正文节点 ID 缺失或重复');
  ids.add(node.id);
  if(node.type==='heading'){
   if(!Number.isInteger(node.level)||node.level<1||node.level>6||typeof node.title!=='string'||node.title.includes('\n'))throw new Error('章节标题格式无效');
  }else if(node.type!=='entry'||typeof node.key!=='string'||!node.key.trim()||typeof node.value!=='string'||typeof node.show_key!=='boolean'||(!node.show_key&&node.key!=='正文'))throw new Error('知识条目格式无效');
 }
 const top=body.nodes.filter(node=>node.type==='heading'&&node.level===1);
 if(top.length!==1||top[0].type!=='heading'||top[0].title!==metadata.title)throw new Error('笔记必须包含与标题一致的唯一一级标题');
 function checkRefs(value:unknown){
  if(!value||typeof value!=='object')return;
  if('$text' in value&&!ids.has(String(value.$text)))throw new Error('有知识引用指向已删除的条目');
  Object.values(value).forEach(checkRefs);
 }
 checkRefs(body.semantics);
 if(Array.isArray(metadata.claim_annotations)&&metadata.claim_annotations.some(claim=>!ids.has(claim.text_ref)))throw new Error('有证据关联指向已删除的条目');
 if(metadata.type==='lineup'&&JSON.stringify(body.semantics?.players)!==JSON.stringify([metadata.player_id]))throw new Error('阵容适用棋手必须与笔记绑定一致');
}

function markManualChanges(before:KnowledgeDocument,body:KnowledgeDocument,metadata:FileMetadata){
 const emptyTokens:NumberTokens=new Map();
 const same=(left:unknown,right:unknown)=>encode(left,emptyTokens)===encode(right,emptyTokens);
 const oldNodes=new Map([...before.nodes,...(before.supporting_nodes??[])].map(node=>[node.id,node]));
 const newNodes=new Map([...body.nodes,...(body.supporting_nodes??[])].map(node=>[node.id,node]));
 const changed=new Set([...oldNodes.keys(),...newNodes.keys()].filter(id=>!same(oldNodes.get(id),newNodes.get(id))));
 if(changed.size){
  const sections=new Map<string,string>();
  let section='知识内容';
  for(const node of body.nodes){
   if(node.type==='heading'&&node.level===2)section=node.title;
   if(node.type==='entry')sections.set(node.id,section);
  }
  const oldAnnotations=metadata.node_annotations as Record<string,JsonObject>|undefined;
  const updates=Object.fromEntries([...changed].map(id=>[id,{...oldAnnotations?.[id],origin:'manual',...(sections.has(id)?{section:sections.get(id)}:{})}]));
  metadata.node_annotations={...oldAnnotations,...updates};
  if(Array.isArray(metadata.claim_annotations))metadata.claim_annotations=metadata.claim_annotations.map(claim=>changed.has(claim.text_ref)?{...claim,origin:'manual',evidence:[],inference:false}:claim);
 }
 if(!same(before.semantics,body.semantics))metadata.manual_semantics=true;
 if(!same(before,body))metadata.review_receipts=[];
}

function journalFrom(text:string|null):Journal|null{
 if(!text)return null;
 const value=JSON.parse(text) as Journal;
 const list=(items:unknown)=>Array.isArray(items)&&items.length===3&&items.every(item=>typeof item==='string');
 if(value?.version!==1||!list(value.paths)||!list(value.before)||!list(value.after)||value.paths[2]!==indexPath||value.paths[0]!==localNotePath('knowledge/'+value.paths[0])||value.paths[1]!==value.paths[0].replace(/\.json$/,'.meta.json'))throw new Error('笔记恢复记录格式无效');
 return value;
}

export class FileNotesRepository {
 private constructor(private directory:BrowserDirectory,private project:BrowserDirectory|null,public index:FileNoteIndex,public hasPending:boolean){}
 get name(){return this.directory.name;}
 get entries(){return this.index.notes;}
 static async open(selected:BrowserDirectory){
  let directory=selected;let project:BrowserDirectory|null=null;
  if(await readOptional(selected,indexPath)===null){
   try{directory=await selected.getDirectoryHandle('knowledge');project=selected;}
   catch(e){if(!missing(e))throw e;throw new Error('请选择项目根目录或其中的 knowledge 目录');}
  }
  const index=checkIndex(parse<FileNoteIndex>(await read(directory,indexPath)).value);
  const pending=await readOptional(directory,notesJournal);
  journalFrom(pending);
  return new FileNotesRepository(directory,project,index,pending!==null);
 }
 async refresh(){
  const pending=await readOptional(this.directory,notesJournal);
  this.hasPending=pending!==null;
  journalFrom(pending);
  this.index=checkIndex(parse<FileNoteIndex>(await read(this.directory,indexPath)).value);
 }
 private async assertNativeIdle(){
  if(this.project&&(await readOptional(this.project,'raw/knowledge/pending-json-save.json')!==null||await readOptional(this.project,'raw/knowledge/pending-official-sync.json')!==null)){
   throw new Error('项目已有待完成的知识事务，请先在项目中完成恢复');
  }
 }
 async requestWrite(){
  if(this.directory.requestPermission&&await this.directory.requestPermission({mode:'readwrite'})!=='granted')throw new Error('浏览器尚未授予文件夹写入权限');
 }
 private transaction<T>(apply:()=>Promise<T>){
  return globalThis.navigator?.locks?navigator.locks.request('wxq-browser-note-save',apply):apply();
 }
 async load(id:string):Promise<FileNote>{
  if(this.hasPending)throw new Error('请先完成上次文件保存的恢复');
  const indexText=await read(this.directory,indexPath);
  const index=checkIndex(parse<FileNoteIndex>(indexText).value);
  const row=index.notes.find(entry=>entry.id===id);
  if(!row)throw new Error('所选笔记已不在索引中');
  const path=localNotePath(row.path);
  const [bodyText,metaText]=await Promise.all([read(this.directory,path),read(this.directory,path.replace(/\.json$/,'.meta.json'))]);
  const {value:body,tokens}=parse<KnowledgeDocument>(bodyText),{value:metadata}=parse<FileMetadata>(metaText);
  if(metadata?.id!==row.id||metadata.type!==row.type||metadata.path!==row.path||metadata.title!==row.title||metadata.revision!==row.revision||await digest(body,tokens)!==metadata.body_sha256)throw new Error('正文、附件与笔记索引版本不一致，请核对项目文件');
  checkRecord(body,metadata);
  return {body,metadata,files:[bodyText,metaText,indexText]};
 }
 private async publish(journal:Journal){
  const {paths,before,after}=journal;
  await this.assertNativeIdle();
  const check=async(i:number)=>{
   const current=await readOptional(this.directory,paths[i]);
   if(current!==before[i]&&current!==after[i])throw outsideChange();
   return current;
  };
  await Promise.all(paths.map((_,i)=>check(i)));
  for(let i=0;i<paths.length;i++)if(await check(i)!==after[i])await write(this.directory,paths[i],after[i]);
  await this.directory.removeEntry(notesJournal);
  this.hasPending=false;
  this.index=checkIndex(parse<FileNoteIndex>(after[2]).value);
 }
 async recover(){
  await this.transaction(async()=>{
   const text=await readOptional(this.directory,notesJournal);
   const journal=journalFrom(text);
   if(journal)await this.publish(journal);
   else{
    // An empty entry can remain if the browser closed before the journal stream committed.
    if(text==='')await this.directory.removeEntry(notesJournal);
    await this.refresh();
   }
  });
 }
 async save(note:FileNote,draft:FileNoteDraft){
  await this.transaction(async()=>{
   await this.assertNativeIdle();
   if(await readOptional(this.directory,notesJournal)!==null){this.hasPending=true;throw new Error('请先完成上次文件保存的恢复');}
   const path=localNotePath(note.metadata.path);
   const paths:NoteFiles=[path,path.replace(/\.json$/,'.meta.json'),indexPath];
   const [bodyFile,metadataFile,indexFile]=await Promise.all(paths.map(file=>readOptional(this.directory,file)));
   if(bodyFile!==note.files[0]||metadataFile!==note.files[1]||indexFile!==note.files[2])throw outsideChange();
   const {value:index,tokens:indexTokens}=parse<FileNoteIndex>(indexFile);
   const metadata={...note.metadata,title:draft.title?.trim()??note.metadata.title,seasons:seasons.filter(value=>draft.seasons.includes(value)),...(draft.aliases?{aliases:draft.aliases}:{})};
   if(!metadata.seasons.length)throw new Error('请选择至少一个有效的适用赛季');
   const body={...draft.document,nodes:draft.document.nodes.map(node=>node.type==='heading'&&node.level===1?{...node,title:metadata.title}:node)};
   checkRecord(body,metadata);
   markManualChanges(note.body,body,metadata);
   const bodyTokens=parse<KnowledgeDocument>(bodyFile).tokens,metaTokens=parse<FileMetadata>(metadataFile).tokens;
   metadata.body_sha256=await digest(body,bodyTokens);
   const ignored=new Set(index.storage_version===2?['revision','history','history_head','history_count']:['revision']);
   metadata.revision=(await digest({body,metadata:Object.fromEntries(Object.entries(metadata).filter(([key])=>!ignored.has(key)))},combineNumbers({prefix:['body'],tokens:bodyTokens},{prefix:['metadata'],tokens:metaTokens}))).slice(0,20);
   const nextIndex={...index,notes:index.notes.map(row=>row.id===metadata.id?{...row,title:metadata.title,revision:metadata.revision,seasons:metadata.seasons}:row)};
   const after:NoteFiles=[encode(body,bodyTokens,true),encode(metadata,metaTokens,true),encode(nextIndex,indexTokens,true)];
   const journal:Journal={version:1,paths,before:note.files,after};
   if((await Promise.all(paths.map(file=>readOptional(this.directory,file)))).some((text,i)=>text!==note.files[i]))throw outsideChange();
   try{await write(this.directory,notesJournal,JSON.stringify(journal),true);}
   finally{this.hasPending=(await readOptional(this.directory,notesJournal))!==null;}
   await this.publish(journal);
  });
 }
}

export function fileNoteView(row:FileNoteEntry,body?:KnowledgeDocument,entries:FileNoteEntry[]=[]):Note{
 const related=Array.isArray(row.related)?row.related.flatMap(id=>entries.filter(note=>note.id===id)):[];
 return {...row,aliases:Array.isArray(row.aliases)?row.aliases:[],core:[],claims:[],entities:Array.isArray(row.entities)?row.entities:[],manual_sections:[],conflicts:[],related,document:body};
}
