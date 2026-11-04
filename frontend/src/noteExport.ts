import type {Note,ReadingDocument} from './types';

export type ExportSection={title:string;level:number;items:{title:string;text:string}[];sections:ExportSection[]};
const section=(title='',level=0):ExportSection=>({title,level,items:[],sections:[]});

/** A reading artifact, deliberately independent from the editable storage schema. */
export function noteJsonExport(note:Note,reading:ReadingDocument){
 const sections:ExportSection[]=[],stack:ExportSection[]=[];
 const intro=()=>{if(!sections.length||sections[0].level!==0)sections.unshift(section());return sections[0];};
 if(reading.document){
  const body=reading.document;
  if(body.leading)intro().items.push({title:'',text:body.leading});
  for(const node of body.nodes){
   if(node.type==='heading'){
    const next=section(node.title,node.level);
    while(stack.length&&stack.at(-1)!.level>=node.level)stack.pop();
    (stack.at(-1)?.sections??sections).push(next);stack.push(next);
   }else (stack.at(-1)??intro()).items.push({title:node.show_key?node.key:'',text:node.value});
  }
 }else{
  if(reading.opening)intro().items.push({title:'',text:reading.opening});
  for(const row of reading.sections??[])sections.push({...section(row.title,2),items:[{title:'',text:row.markdown}]});
  if(!sections.length&&reading.markdown)intro().items.push({title:'',text:reading.markdown});
 }
 return {schema_version:1 as const,note:{id:note.id,title:note.title,type:note.type},sections};
}

export function downloadNoteJson(note:Note,reading:ReadingDocument){
 const url=URL.createObjectURL(new Blob([JSON.stringify(noteJsonExport(note,reading),null,2)+'\n'],{type:'application/json;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download=note.title.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_')+'.json';
 link.click();setTimeout(()=>URL.revokeObjectURL(url),0);
}
