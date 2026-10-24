import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {documentMarkdown,sectionMarkdown,copyEntry,playerGroups,moveNode,removeNode} from './jsonDocument';
import NoteDirectory from './NoteDirectory';
import type {KnowledgeDocument,Note} from './types';

const body:KnowledgeDocument={schema_version:6,leading:'',nodes:[
 {id:'title',type:'heading',level:1,title:'测试',separator:'\n\n'},
 {id:'chapter',type:'heading',level:2,title:'推荐天赋',separator:'\n\n'},
 {id:'intro',type:'entry',key:'正文',show_key:false,value:'选择说明。',separator:'\n\n'},
 {id:'talent',type:'entry',key:'暴君归来',show_key:true,value:'复生增强。',separator:'\n\n'},
 {id:'sub',type:'heading',level:3,title:'条件',separator:'\n\n'},
 {id:'v',type:'entry',key:'正文',show_key:false,value:'成型之后。',separator:'\n'},
 {id:'next',type:'heading',level:2,title:'装备',separator:'\n'}]};

describe('JSON knowledge exports',()=>{
 it('moves and removes whole chapters with their descendants',()=>{
  const moved=moveNode(body.nodes,1,1);
  expect(moved.map(n=>n.id)).toEqual(['title','next','chapter','intro','talent','sub','v']);
  expect(removeNode(body.nodes,1).map(n=>n.id)).toEqual(['title','next']);
  expect(moveNode(body.nodes,1,-1)).toBe(body.nodes);
 });
 it('copies exact Markdown without brackets and includes descendant chapters',()=>{
  expect(copyEntry(body.nodes[3])).toBe('**暴君归来：** 复生增强。');
  expect(copyEntry(body.nodes[2])).toBe('**正文：** 选择说明。');
  expect(sectionMarkdown(body,'chapter')).toBe('## 推荐天赋\n\n选择说明。\n\n**暴君归来：** 复生增强。\n\n### 条件\n\n成型之后。\n');
  expect(documentMarkdown(body)).toMatch(/^# 测试\n/);
 });
 it('groups by bound player and preserves lineup-only players',()=>{
  const notes=[{id:'p',type:'player',title:'明先生',player_id:'player:39',entities:[],related:[]},
   {id:'l',type:'lineup',title:'花木兰-明先生',player_id:'player:39',meta:{players:['player:39']},entities:[],related:[]},
   {id:'s',type:'lineup',title:'刘邦-班叔',player_id:'player:51',meta:{players:['player:51']},entities:[],related:[]} ] as unknown as Note[];
  expect(playerGroups(notes).map(g=>[g.name,g.notes.map(n=>n.id)])).toEqual([['明先生',['p','l']],['班叔',['s']]]);
  const complete=notes.map(n=>({...n,core:[],meta:n.meta?{...n.meta,core_heroes:[],compositions:{early:[],middle:[],late:[]}}:undefined}));
  const html=renderToStaticMarkup(<NoteDirectory notes={complete} active="l" onSelect={()=>{}}/>);
  expect(html).toContain('棋手笔记');expect(html).toContain('花木兰-明先生');
 });
});
