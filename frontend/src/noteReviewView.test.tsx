import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {ReviewProvider} from './NoteReview';
import JsonReading from './JsonReading';
import {DiffText,ValueEditor} from './ReviewFields';
import type {Note,KnowledgeDocument} from './types';
import {copyEntry} from './jsonDocument';

it('highlights structured fields in reading without changing Markdown or clipboard text',()=>{
 const value='觉醒需求：普通卡可用。等级投入:定向培养；购买策略：先买一张。 比例：二比一；[出售时机：说明](https://example.com) 给出 `上阵时机：示例`；**获得途径：** 自然刷新。';
 const entry={id:'p',type:'entry' as const,key:'弈星',show_key:true,value};
 const body:KnowledgeDocument={schema_version:6,nodes:[entry]};
 const note={id:'n',title:'笔记',revision:'r',document:body,related:[],type:'lineup'} as unknown as Note;
 const render=(type:Note['type'],text=value)=>renderToStaticMarkup(<JsonReading body={body} nodes={[{...entry,value:text}]} note={{...note,type}} onNote={()=>{}}/>);
 const html=render('lineup');
 for(const field of ['觉醒需求：','等级投入:','购买策略：','获得途径：'])expect(html).toContain('<strong>'+field+'</strong>');
 expect(html).toContain('<strong>比例：</strong>');
 for(const field of ['出售时机：','上阵时机：'])expect(html).not.toContain('<strong>'+field+'</strong>');
 expect(html).toContain('<code>上阵时机：示例</code>');
 expect(html.match(/<strong>获得途径：<\/strong>/g)).toHaveLength(1);
 const player=render('player','必须阵营：三分 定阵条件：曹操到位；阶段强度：条件明确。');
 expect(player).toContain('<strong>定阵条件：</strong>');
 expect(player).toContain('<strong>阶段强度：</strong>');
 const suitable='满足以下条件中的一条或多条可以考虑使用该阵容';
 const unsuitable='以下情况不适合使用该阵容';
 for(const type of ['player','lineup'] as const){
  const conditions=render(type,`关键成员：花木兰。 ${suitable}：1）核心到位。${unsuitable}:1）同行争抢。`);
  expect(conditions).toContain(`<strong>${suitable}：</strong>1）核心到位`);
  expect(conditions).toContain(`<strong>${unsuitable}:</strong>1）同行争抢`);
  expect(render(type,'定阵条件：核心到位')).toContain('<strong>定阵条件：</strong>');
 }
 const other=render('other','作用：正文；**使用技巧：** 正文');
 expect(other).toContain('<strong>作用：</strong>');
 expect(other).toContain('<strong>使用技巧：</strong>');
 expect(copyEntry(entry,body,note.title)).toContain('觉醒需求：普通卡可用。等级投入:定向培养');
});

it('bolds full condition keys in a tactics paragraph and leaves the actions plain',()=>{
 const first='场上只有1名要转等级的三分英雄，目标三分主C尚未吃等级，手中有1张换帅且主C至少有1张：';
 const second='场上有4名供级英雄，其中至少2名三分英雄可以留到遗志前，目标主C够觉醒且还能额外上场1张：';
 const entry={id:'p',type:'entry' as const,key:'传承、遗志、换帅的使用技巧',show_key:true,value:first+'上主C。'+second+'先传承。'};
 const body:KnowledgeDocument={schema_version:6,nodes:[entry]};
 const note={id:'n',title:'常用技巧',type:'other',related:[],document:body} as unknown as Note;
 const html=renderToStaticMarkup(<JsonReading body={body} nodes={body.nodes} note={note} onNote={()=>{}}/>);
 expect(html).toContain('<strong>'+first+'</strong>上主C。');
 expect(html).toContain('<strong>'+second+'</strong>先传承。');
 expect(copyEntry(entry,body,note.title)).toContain(first+'上主C。'+second+'先传承。');
});

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
