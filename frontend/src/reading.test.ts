import {describe,it,expect} from 'vitest';
import {resolveReadingSection,loadReaderData,claimMarkdown} from './reading';
import type {ReadingDocument} from './types';
import type {Note} from './types';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Reading from './KnowledgeReader';
import EntityMarkdown from './EntityMarkdown';
describe('shared reading navigation',()=>{
 it('hides internal inference labels only for v4 and keeps the factual condition',()=>{
  const c={text:'用古币提升花木兰等级。',condition:'古币体系已启动',inference:true};
  expect(claimMarkdown(c,4)).toBe('**古币体系已启动：** 用古币提升花木兰等级。');
  expect(c.inference).toBe(true);
  expect(claimMarkdown(c,3)).toContain('推测：');
 });
 it('renders Chinese condition and card labels as emphasis, without literal stars',()=>{
  const html=renderToStaticMarkup(createElement(EntityMarkdown,{children:claimMarkdown({text:'补控制。',condition:'决赛需要降级时'})+'\n\n'+claimMarkdown({text:'- **唤醒：**补资源。'})}));
  expect(html).toContain('<strong>决赛需要降级时：</strong>');expect(html).toContain('<strong>唤醒：</strong>');expect(html).not.toContain('**');
 });
 it('keeps conditions and uncertainty visible in overview claims',()=>{
  expect(claimMarkdown({text:'补控制。',condition:'决赛需要降级时',inference:true})).toBe('推测：**决赛需要降级时：** 补控制。');
  expect(claimMarkdown({text:'- **唤醒：**补资源。',condition:'',inference:false})).toBe('- **唤醒：** 补资源。');
 });
 it('can open knowledge even when the external source service never completes',async()=>{
  const paths:string[]=[];
  const request=<T,>(path:string):Promise<T>=>{paths.push(path);return path==='sources'?new Promise(()=>{}):Promise.resolve((path==='notes'?[]:{entities:[],factions:[],sections:{}}) as T);};
  const [notes,options]=await loadReaderData(request);
  expect(notes).toEqual([]);expect(options.entities).toEqual([]);expect(paths).not.toContain('sources');
 });
 const doc={note_id:'lixin',revision:'r1',profile:'shared',sections:[{id:'chapter-1',title:'阵容概览与成员清单',markdown:'概览'},{id:'chapter-7',title:'装备与站位',markdown:'装备'}],section_aliases:{推荐装备:'装备与站位'}} satisfies ReadingDocument;
 it('migrates old saved chapter names and falls back to overview',()=>{
  expect(resolveReadingSection(doc,'推荐装备')).toBe('装备与站位');
  expect(resolveReadingSection(doc,'装备与站位')).toBe('装备与站位');
  expect(resolveReadingSection(doc,'removed')).toBe('阵容概览与成员清单');
 });
 it('renders complete sections in both modes; navigation never filters content',()=>{
  const document={...doc,sections:[{id:'chapter-1',title:'阵容概览与成员清单',markdown:'唯一正文\n\n| 英雄 | 作用 |\n|---|---|\n| 李信 | 输出 |'},doc.sections[1]]};
  const note={related:[]} as unknown as Note;
  const html=renderToStaticMarkup(createElement(Reading,{document,section:doc.sections[0].title,full:true,note,onNote:()=>{}}));
  expect(html.match(/唯一正文/g)).toHaveLength(1);
  expect(html).toContain('<table>');expect(html).toContain('<td>李信</td>');
  expect(html).toContain('装备与站位');
  const scoped=renderToStaticMarkup(createElement(Reading,{document,section:'装备与站位',full:false,note,onNote:()=>{}}));
  expect(scoped).toContain('唯一正文');expect(scoped).toContain('装备与站位');
 });
});
