import {expect,it} from 'vitest';
import {noteJsonExport} from './noteExport';
import type {Note,ReadingDocument} from './types';
const note={id:'n',title:'中文笔记',type:'other',private:'secret'} as unknown as Note;
it('preserves nested, repeated and skipped headings, entries, leading text and empty sections',()=>{
 const reading={document:{schema_version:6,leading:'前言',nodes:[
  {id:'a',type:'entry',key:'隐藏',show_key:false,value:'标题前正文'},
  {id:'h',type:'heading',level:1,title:'中文笔记'},
  {id:'x',type:'heading',level:3,title:'重复'},
  {id:'b',type:'entry',key:'要点',show_key:true,value:'**正文**\n\n- 列表'},
  {id:'y',type:'heading',level:3,title:'重复'},
  {id:'z',type:'heading',level:2,title:'空章'},
 ],supporting_nodes:[{id:'private',type:'entry',key:'secret',value:'不应导出'}]}} as ReadingDocument;
 expect(noteJsonExport(note,reading)).toEqual({schema_version:1,note:{id:'n',title:'中文笔记',type:'other'},sections:[
  {title:'',level:0,items:[{title:'',text:'前言'},{title:'',text:'标题前正文'}],sections:[]},
  {title:'中文笔记',level:1,items:[],sections:[
   {title:'重复',level:3,items:[{title:'要点',text:'**正文**\n\n- 列表'}],sections:[]},
   {title:'重复',level:3,items:[],sections:[]},
   {title:'空章',level:2,items:[],sections:[]},
  ]},
 ]});
});
it('exports legacy opening and sections without dropping Markdown',()=>{
 const reading={opening:'开篇',sections:[{id:'one',title:'机制',markdown:'正文\n\n### 子节\n\n- 明细'}]} as ReadingDocument;
 const out=noteJsonExport(note,reading);
 expect(out.sections[0].items[0].text).toBe('开篇');
 expect(out.sections[1]).toMatchObject({title:'机制',items:[{title:'',text:'正文\n\n### 子节\n\n- 明细'}]});
 expect(JSON.stringify(out)).not.toContain('secret');
});
it('keeps markdown-only legacy data and empty documents',()=>{
 expect(noteJsonExport(note,{markdown:'# 旧正文',sections:[]} as unknown as ReadingDocument).sections[0].items[0].text).toBe('# 旧正文');
 expect(noteJsonExport(note,{document:{nodes:[]}} as unknown as ReadingDocument).sections).toEqual([]);
});
