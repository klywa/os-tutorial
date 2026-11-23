import {describe,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import TemplateBoard,{buildTemplateEntityIndex,TemplateEntityList} from './TemplateBoard';
import type {TemplateEvent,TemplateGroup} from './templates';

const events:TemplateEvent[]=[
 {id:'buy',name:'购买英雄',parameters:[
  {id:'p1',key:'arg1',name:'arg1',type:'entity',dsl_type:'英雄',entity_categories:['heroes']},
  {id:'p2',key:'arg2',name:'arg2',type:'text',dsl_type:'Array<英雄|效果牌>'},
 ]},
 {id:'use',name:'对目标使用效果牌',parameters:[
  {id:'p3',key:'arg1',name:'arg1',type:'entity',dsl_type:'单位'},
  {id:'p4',key:'arg2',name:'arg2',type:'entity',dsl_type:'效果牌'},
 ]},
];
const entities=[
 {id:'h',name:'同名',category:'heroes',aliases:['别名']},
 {id:'e',name:'同名',category:'effect-cards'},
 {id:'d',name:'机关',category:'derivatives'},
 {id:'x',name:'提及',category:'heroes'},
];
const makeGroup=(id:string,event_id:string,expression?:string):TemplateGroup=>({
 id,event_id,name:'模板'+id,expression,scope:{player_id:'x',lineup_note_id:null},conditions:[],
 utterances:[{id:id+'-row',text:'提及整句'}],related_entities:[entities[3]],explanation:'提及',
});

describe('template entity board',()=>{
 it('uses event parameter identities and discriminants, excluding other mentions and ambiguous union names',()=>{
  const groups=[
   makeGroup('buy','buy','(arg1.名称 is "别名" or arg2 has {"类型":"效果牌","名称":"同名"}) and 玩家.战场 has "提及" and arg1.标签 has "提及"'),
   makeGroup('target','use','arg1 in [{"类型":"衍生物","名称":"机关"}] and arg2 is "同名"'),
   makeGroup('names','buy','arg2 has "同名" and 玩家.主C is "提及"'),
  ];
  const index=buildTemplateEntityIndex(groups,events,entities);
  const match=(id:string)=>index.find(entry=>entry.id===id)!;
  expect([...match('h').groupIds]).toEqual(['buy']);
  expect([...match('e').groupIds]).toEqual(['buy','target']);
  expect(match('e').roles.get('buy')).toEqual(['商店中未选择的牌']);
  expect(match('e').roles.get('target')).toEqual(['使用的效果牌']);
  expect(match('d').roles.get('target')).toEqual(['效果牌作用的目标']);
  expect(match('x').groupIds.size).toBe(0);
 });

 it('honors a legacy typed id even when names overlap',()=>{
  const group={...makeGroup('legacy','use'),conditions:[
   {id:'c',parameter_key:'arg2',operator:'eq' as const,value:{id:'e',name:'同名'}},
   {id:'x',parameter_key:'arg1',operator:'eq' as const,value:{id:'h',name:'同名'}},
  ]};
  const index=buildTemplateEntityIndex([group],events,entities);
  expect(index.find(entry=>entry.id==='h')?.groupIds.has('legacy')).toBe(true);
  expect(index.find(entry=>entry.id==='e')?.groupIds.has('legacy')).toBe(true);
 });

 it('renders one selectable row per group, explicit details, event headings and category labels',()=>{
  const groups=[makeGroup('buy','buy','arg1 is "同名"'),makeGroup('target','use','arg2 is "同名"')];
  const index=buildTemplateEntityIndex(groups,events,entities);
  const html=renderToStaticMarkup(<><TemplateEntityList entries={index} selected="" onSelect={vi.fn()}/>
   <TemplateBoard groups={groups} events={events} selected={new Set(['buy'])} onSelectionChange={vi.fn()} onDetail={vi.fn()} byEvent/>
  </>);
  expect(html).toContain('英雄');
  expect(html).toContain('效果牌');
  expect(html).toContain('购买英雄');
  expect(html).toContain('对目标使用效果牌');
  expect(html.match(/data-template-board-row=/g)).toHaveLength(2);
  expect(html).toContain('aria-label="选择模板buy"');
  expect(html).toContain('aria-label="查看模板target详情"');
  expect(html).not.toContain('提及整句');
 });
});
