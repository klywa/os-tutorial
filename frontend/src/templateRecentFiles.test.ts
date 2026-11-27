import {expect,it} from 'vitest';
import {addRecentTemplateFile,type RecentTemplateFile} from './templateRecentFiles';
import type {LocalFileHandle} from './templateFile';
import {templateFilesInDirectory} from './templateFile';

it('deduplicates by file identity, keeps same names in different folders and caps history at ten',async()=>{
 const handle=(identity:string):LocalFileHandle=>{
  const result={name:'模板.json',identity,isSameEntry:async(other:LocalFileHandle)=>'identity' in other&&other.identity===identity,
   getFile:async()=>({text:async()=>''}),createWritable:async()=>{throw new Error('测试句柄只读');}};
  return result;
 };
 let entries:RecentTemplateFile[]=[];
 for(let index=0;index<11;index++){
  entries=await addRecentTemplateFile(entries,{id:String(index),openedAt:index,handle:handle(String(index))});
 }
 expect(entries.map(row=>row.id)).toEqual(['10','9','8','7','6','5','4','3','2','1']);
 entries=await addRecentTemplateFile(entries,{id:'replacement',openedAt:12,handle:handle('5')});
 expect(entries.map(row=>row.id)).toEqual(['5','10','9','8','7','6','4','3','2','1']);
 expect(entries[0].openedAt).toBe(12);
});

it('lists main JSON handles from the authorized directory without reading any file',async()=>{
 const unreadable=async()=>{throw new Error('directory listing must not read file contents');};
 const names=['乙.json','甲-detail.json','丙.txt','甲.json'];
 const handles=names.map(name=>({kind:'file' as const,name,getFile:unreadable,createWritable:unreadable}));
 const directory={kind:'directory' as const,name:'实验',getFileHandle:unreadable,async *values(){
  yield this;
  yield* handles;
 }};
 expect(await templateFilesInDirectory(directory)).toEqual([handles[3],handles[0]].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN',{numeric:true})));
});
