import {describe,it,expect} from 'vitest';
import {insertKnowledgeNode,changeHeadingLevel,removeNode,moveNode,documentClipboard,sectionClipboard,copyEntry} from './jsonDocument';
import type {KnowledgeNode} from './types';
const h=(id:string,level:number):KnowledgeNode=>({id,type:'heading',level,title:id});
const e=(id:string):KnowledgeNode=>({id,type:'entry',key:id,show_key:true,value:'内容'});
const nodes=[h('root',1),h('a',2),e('x'),h('child',3),e('y'),h('b',2)];
describe('多级章节编辑',()=>{
 it('同级章节插入整个章节之后，子章节留在父章节内',()=>{
  const sibling=insertKnowledgeNode(nodes,'heading',1,false,true);
  expect(sibling[5]).toMatchObject({type:'heading',level:2});
  const child=insertKnowledgeNode(nodes,'heading',1,true,true);
  expect(child[5]).toMatchObject({type:'heading',level:3});
  expect(insertKnowledgeNode([h('root',1),h('max',6)],'heading',1,true,true)).toEqual([h('root',1),h('max',6)]);
 });
 it('四篇笔记默认显示 key，其他笔记仍兼容无标题条目',()=>{
  expect(insertKnowledgeNode(nodes,'entry',2,false,true)[3]).toMatchObject({show_key:true,key:'新条目'});
  expect(insertKnowledgeNode(nodes,'entry',2,false,false)[3]).toMatchObject({show_key:false,key:'正文'});
 });
 it('调整层级连同子章节，禁止产生额外一级标题或超出六级',()=>{
  expect(changeHeadingLevel(nodes,1,3)[3]).toMatchObject({level:4});
  expect(changeHeadingLevel(nodes,1,1)).toBe(nodes);
  expect(changeHeadingLevel(nodes,1,6)).toBe(nodes);
  expect(changeHeadingLevel(nodes,0,2)).toBe(nodes);
 });
 it('移动、删除和复制包含完整子章节及条目',()=>{
  expect(removeNode(nodes,1).map(n=>n.id)).toEqual(['root','b']);
  expect(moveNode(nodes,1,1).map(n=>n.id)).toEqual(['root','b','a','x','child','y']);
  const body={schema_version:6 as const,nodes};
  expect(sectionClipboard(body,'a')).toContain('### child');
  expect(sectionClipboard(body,'a')).not.toContain('## b');
  expect(documentClipboard(body)).toContain('# root');
  expect(copyEntry(nodes[2],body)).toBe('x：内容');
 });
});
