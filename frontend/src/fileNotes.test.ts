import {describe,expect,it} from 'vitest';
import {FileNotesRepository,notesJournal,type BrowserDirectory} from './fileNotes';

const path='other/例.json';
const metaPath='other/例.meta.json';
const body={schema_version:6,nodes:[{id:'title',type:'heading',level:1,title:'例'},{id:'original',type:'entry',key:'正文',show_key:false,value:'旧正文',extension:'保留'}],extension:{keep:true}};
const row={id:'example',type:'other',title:'例',path:'knowledge/'+path,revision:'old',extension:'保留'};
const metadata={...row,other_data:{keep:'原样'},body_sha256:'24ea5c3703a0b89ce583044e16bd6d74ef820ca5217da324c549ccfc202448ed'};

function fixture(){
 const files=new Map<string,string>([[path,JSON.stringify(body)],[metaPath,JSON.stringify(metadata).replace('"keep":"原样"','"keep":"原样","score":1.0')],['index.meta.json',JSON.stringify({schema_version:6,storage_version:2,notes:[row],aliases:{old:'example'},extension:[1]})]]);
 let fail='';
 const missing=()=>new DOMException('missing','NotFoundError');
 const directory=(prefix:string):BrowserDirectory=>({name:prefix||'knowledge',async getDirectoryHandle(name){const sub=prefix+name+'/';if(![...files.keys()].some(key=>key.startsWith(sub)))throw missing();return directory(sub);},async getFileHandle(name,options){const key=prefix+name;if(!files.has(key)){if(!options?.create)throw missing();files.set(key,'');}return {async getFile(){return {async text(){return files.get(key)??'';}};},async createWritable(){let text:string;return {async write(value){text=value;},async close(){if(fail===key)throw Error('interrupted');files.set(key,text);},async abort(){}};}};},async removeEntry(name){files.delete(prefix+name);}});
 return {files,open:()=>FileNotesRepository.open(directory('')),interrupt:(key:string)=>{fail=key;}};
}

describe('browser note files',()=>{
 it('writes the matching index, body and metadata without dropping extensions, numeric types or node IDs',async()=>{
  const workspace=fixture();const repo=await workspace.open();const note=await repo.load('example');
  const draft=structuredClone(note.body);draft.nodes[1]={...draft.nodes[1],value:'新正文'} as typeof draft.nodes[number];
  await repo.save(note,{document:draft,title:'新标题',seasons:['S2'],aliases:[]});
  const result=await repo.load('example');
  expect(result.body.nodes[1]).toMatchObject({id:'original',extension:'保留',value:'新正文'});
  expect(result.body).toHaveProperty('extension.keep',true);
  expect(result.metadata).toMatchObject({title:'新标题',seasons:['S2'],other_data:{keep:'原样',score:1}});
  expect(workspace.files.get(metaPath)).toContain('1.0');
  expect(result.body.nodes[0]).toMatchObject({id:'title',title:'新标题'});
  expect(repo.entries[0]).toMatchObject({revision:result.metadata.revision,extension:'保留'});
  expect(JSON.parse(workspace.files.get('index.meta.json')!)).toMatchObject({extension:[1],aliases:{old:'example'}});
 });
 it('reclassifies edited and new notes content without reusing old evidence or changing unaffected annotations',async()=>{
  const workspace=fixture();
  const before={...metadata,node_annotations:{title:{origin:'official'},original:{origin:'official',extra:'保留'}},claim_annotations:[{id:'old-claim',text_ref:'original',origin:'official',evidence:[{kind:'official'}],inference:true,custom:1},{id:'title-claim',text_ref:'title',origin:'official',evidence:[{kind:'official'}],inference:true}],review_receipts:[{id:'old'}]};
  workspace.files.set(metaPath,JSON.stringify(before));
  const repo=await workspace.open();const note=await repo.load('example');
  const draft=structuredClone(note.body);
  draft.nodes[1]={...draft.nodes[1],value:'新正文'} as typeof draft.nodes[number];
  draft.nodes.push({id:'new-section',type:'heading',level:2,title:'新章节'},{id:'new-entry',type:'entry',key:'正文',show_key:false,value:'新增'});
  draft.semantics={rules:'新规则'};
  await repo.save(note,{document:draft,seasons:['S1']});
  const result=await repo.load('example');
  expect(result.metadata.node_annotations).toEqual({title:before.node_annotations.title,original:{origin:'manual',section:'知识内容',extra:'保留'},'new-section':{origin:'manual'},'new-entry':{origin:'manual',section:'新章节'}});
  expect(result.metadata.claim_annotations).toEqual([{...before.claim_annotations[0],origin:'manual',inference:false,evidence:[]},before.claim_annotations[1]]);
  expect(result.metadata.manual_semantics).toBe(true);
  expect(result.metadata.review_receipts).toEqual([]);
 });
 it('blocks deletion of a referenced entry before writing files',async()=>{
  const workspace=fixture();
  workspace.files.set(metaPath,JSON.stringify({...metadata,claim_annotations:[{id:'old-claim',text_ref:'original'}]}));
  const repo=await workspace.open();const note=await repo.load('example');
  await expect(repo.save(note,{document:{...note.body,nodes:note.body.nodes.slice(0,1)},seasons:['S1']})).rejects.toThrow('有证据关联指向已删除的条目');
  expect(workspace.files.has(notesJournal)).toBe(false);
  expect(workspace.files.get(path)).toBe(note.files[0]);
 });
 it('rejects a changed document and leaves both the edited file and index untouched',async()=>{
  const workspace=fixture();const repo=await workspace.open();const note=await repo.load('example');
  const originalIndex=workspace.files.get('index.meta.json');workspace.files.set(path,workspace.files.get(path)!+'\n');
  await expect(repo.save(note,{document:note.body,title:'新标题',seasons:['S1']})).rejects.toThrow('外部');
  expect(workspace.files.get(path)).toContain('\n');expect(workspace.files.get('index.meta.json')).toBe(originalIndex);expect(workspace.files.has(notesJournal)).toBe(false);
 });
 it('recovers interrupted writes and refuses to replay over subsequent external changes',async()=>{
  const workspace=fixture();const repo=await workspace.open();const note=await repo.load('example');
  workspace.interrupt(metaPath);
  await expect(repo.save(note,{document:note.body,title:'新标题',seasons:['S1']})).rejects.toThrow('interrupted');
  const reopened=await workspace.open();expect(reopened.hasPending).toBe(true);
  const previous=workspace.files.get(metaPath)!;workspace.files.set(metaPath,previous+'\n');workspace.interrupt('');
  await expect(reopened.recover()).rejects.toThrow('外部');
  workspace.files.set(metaPath,previous);await reopened.recover();expect(reopened.hasPending).toBe(false);
  expect((await reopened.load('example')).metadata.title).toBe('新标题');
 });
 it('clears an interrupted journal creation without changing the note',async()=>{
  const workspace=fixture();const repo=await workspace.open();const note=await repo.load('example');
  workspace.interrupt(notesJournal);
  await expect(repo.save(note,{document:note.body,title:'新标题',seasons:['S1']})).rejects.toThrow('interrupted');
  const reopened=await workspace.open();expect(reopened.hasPending).toBe(true);
  workspace.interrupt('');await reopened.recover();expect(workspace.files.has(notesJournal)).toBe(false);
  expect((await reopened.load('example')).metadata.title).toBe('例');
 });
});
