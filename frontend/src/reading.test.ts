import {describe,it,expect} from 'vitest';
import {resolveReadingSection} from './reading';
import type {ReadingDocument} from './types';
import type {Note} from './types';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Reading from './KnowledgeReader';
describe('shared reading navigation',()=>{
 const doc={note_id:'lixin',revision:'r1',profile:'shared',sections:[{id:'chapter-1',title:'阵容概览与成员清单',markdown:'概览'},{id:'chapter-7',title:'装备与站位',markdown:'装备'}],section_aliases:{推荐装备:'装备与站位'}} satisfies ReadingDocument;
 it('migrates old saved chapter names and falls back to overview',()=>{
  expect(resolveReadingSection(doc,'推荐装备')).toBe('装备与站位');
  expect(resolveReadingSection(doc,'装备与站位')).toBe('装备与站位');
  expect(resolveReadingSection(doc,'removed')).toBe('阵容概览与成员清单');
 });
 it('renders shared sections and GFM tables once, and scopes the play reader',()=>{
  const document={...doc,sections:[{id:'chapter-1',title:'阵容概览与成员清单',markdown:'唯一正文\n\n| 英雄 | 作用 |\n|---|---|\n| 李信 | 输出 |'},doc.sections[1]]};
  const note={related:[]} as unknown as Note;
  const html=renderToStaticMarkup(createElement(Reading,{document,section:doc.sections[0].title,full:true,note,onNote:()=>{}}));
  expect(html.match(/唯一正文/g)).toHaveLength(1);
  expect(html).toContain('<table>');expect(html).toContain('<td>李信</td>');
  expect(html).toContain('装备与站位');
  const scoped=renderToStaticMarkup(createElement(Reading,{document,section:'装备与站位',full:false,note,onNote:()=>{}}));
  expect(scoped).not.toContain('唯一正文');expect(scoped).toContain('装备与站位');
 });
});
