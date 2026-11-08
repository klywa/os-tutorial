import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {TemplateGroupCard} from './TemplateLibrary';
import {ConditionInput} from './TemplateEditor';
import type {TemplateEvent,TemplateGroup} from './templates';
describe('template group reading',()=>{
 it('retains a retired entity as the selected option without offering it as a new choice',()=>{
  const html=renderToStaticMarkup(<ConditionInput condition={{id:'c',parameter_key:'hero',operator:'eq',value:{id:'retired-hero',name:'旧版英雄'}}} parameter={{id:'p',key:'hero',name:'英雄',type:'entity'}} onChange={()=>{}}/>);
  expect(html).toContain('旧版英雄（资料暂缺/已下架）');
  expect(html).toMatch(/<option[^>]*value="retired-hero"[^>]*disabled=""[^>]*selected=""/);
 });
 it('shows every utterance, entity cards and readable AND conditions without editable controls for a viewer',()=>{
  const event:TemplateEvent={id:'buy',name:'购买英雄',category:'商店',parameters:[{id:'p',key:'hero',name:'目标英雄',type:'entity'},{id:'r',key:'round',name:'回合',type:'number'}]};
  const group:TemplateGroup={id:'g',name:'开局拿牌',event_id:'buy',scope:{player_id:null,lineup_note_id:null},conditions:[{id:'c',parameter_key:'hero',operator:'eq',value:{id:'heroes:1',name:'虞姬'}},{id:'r',parameter_key:'round',operator:'gte',value:3}],utterances:[{id:'u1',text:'第一条完整话术'},{id:'u2',text:'第二条完整话术'}],related_entities:[]};
  const html=renderToStaticMarkup(<TemplateGroupCard group={group} event={event} scopeName={()=>'通用'} editable={false} onEdit={()=>{}} onDelete={()=>{}}/>);
  for(const text of ['开局拿牌','虞姬','回合','≥','第一条完整话术','第二条完整话术','等概率','同时满足'])expect(html).toContain(text);
  expect(html).toContain('entity-chip');expect(html).not.toContain('编辑模板');expect(html).not.toContain('删除模板');
  expect(html).toContain('导出json');
  const left=html.match(/<section[^>]*aria-label="卡牌与条件"[^>]*>([\s\S]*?)<\/section>/)?.[1];
  expect(left).toContain('关联卡牌');expect(left).toContain('虞姬');expect(left).toContain('回合');
  expect(left).not.toContain('第一条完整话术');
 });
});
