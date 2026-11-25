import {expect,it} from 'vitest';
import {addRecentTemplateFile,type RecentTemplateFile} from './templateRecentFiles';
import type {LocalFileHandle} from './templateFile';

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
