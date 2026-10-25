import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {ReviewProvider} from './NoteReview';
import JsonReading from './JsonReading';
import {DiffText,ValueEditor} from './ReviewFields';
import type {Note,KnowledgeDocument} from './types';

it('renders edit and annotation beside copy for deep headings and named paragraphs',()=>{
 const body:KnowledgeDocument={schema_version:6,nodes:[{id:'h',type:'heading',level:4,title:'条件'},
  {id:'p',type:'entry',key:'弈星',show_key:true,value:'工具英雄'}]};
 const note={id:'n',title:'笔记',revision:'r',document:body,related:[]} as unknown as Note;
 const html=renderToStaticMarkup(<ReviewProvider note={note} onSaved={()=>{}} onDirty={()=>{}}><JsonReading body={body} nodes={body.nodes} note={note} onNote={()=>{}}/></ReviewProvider>);
 expect(html).toContain('编辑章节：条件');expect(html).toContain('批注：弈星');expect(html).toContain('<h4');
});
it('diff markup distinguishes additions and deletions without color alone',()=>{
 const html=renderToStaticMarkup(<DiffText before="原文" after="新文"/>);
 expect(html).toContain('<del');expect(html).toContain('<ins');expect(html).toContain('删除');expect(html).toContain('增加');
});
it('disables history text input while a save is in flight',()=>{
 const html=renderToStaticMarkup(<ValueEditor value="正文" label="合并结果" onChange={()=>{}} disabled/>);
 expect(html).toContain('disabled');
});
