import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {TemplateGroupCard} from './TemplateLibrary';
import {ConditionInput} from './TemplateEditor';
import {effectiveExpression} from './templates';
import type {TemplateEvent,TemplateGroup} from './templates';
describe('template group reading',()=>{
 it('shows condition slot candidates while preserving escaped and event parameter references',()=>{
  const group:TemplateGroup={id:'g',name:'槽位示例',event_id:'buy',scope:{player_id:null,lineup_note_id:null},conditions:[],
   utterances:[{id:'u',text:'保留{arg1.名称}，原样{{arg1.名称}}，提示{hero}，括号{{{arg1.名称}}}'}],related_entities:[]};
  const html=renderToStaticMarkup(<TemplateGroupCard group={group} utteranceBindings={{'arg1.名称':['虞姬','李白']}} scopeName={()=>'通用'} editable={false} onEdit={()=>{}} onDelete={()=>{}}/>);
  expect(html).toContain('保留虞姬/李白，原样{{arg1.名称}}，提示{hero}，括号{{虞姬/李白}}');
 });
 it('shows fixed and ignored independently and guards fixed deletion and editing',()=>{
  const group:TemplateGroup={id:'g',name:'固定示例',event_id:'buy',scope:{player_id:null,lineup_note_id:null},conditions:[],
   utterances:[{id:'u',text:'固定原句',fixed:true,ignored:true},{id:'v',text:'其他原句'}],related_entities:[]};
  const html=renderToStaticMarkup(<TemplateGroupCard group={group} scopeName={()=>'通用'} editable onEdit={()=>{}} onDelete={()=>{}}
   onToggleFixed={()=>{}} onToggleIgnored={()=>{}} onSaveUtterances={async()=>{}}/>);
  expect(html).toContain('已固定');
  expect(html).toContain('已忽略');
  expect(html).toMatch(/aria-label="取消固定话术2" aria-pressed="true"/);
  expect(html).toMatch(/aria-label="编辑话术2" disabled=""/);
  expect(html).toMatch(/aria-label="删除模板固定示例" disabled=""/);
  expect(html).not.toMatch(/aria-label="取消忽略话术2" disabled=""/);
 });
 it('keeps bindings independent of the event target and quotes the complete condition',()=>{
  const body='arg1.阵容名 has "目标队" or 玩家.等级 >= 10';
  expect(effectiveExpression('甲"棋手','当前队',body)).toBe('玩家.使用棋手 is "甲\\"棋手" and 玩家.使用阵容 is "当前队" and ('+body+')');
  expect(effectiveExpression(null,null,body)).toBe(body);
  expect(effectiveExpression('新棋手',null,'')).toBe('玩家.使用棋手 is "新棋手"');
 });
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
  expect(html).not.toContain('说明与依据');
  const explained=renderToStaticMarkup(<TemplateGroupCard group={{...group,explanation:'换牌依据\n<纯文本>'}} event={event} scopeName={()=>'通用'} editable={false} onEdit={()=>{}} onDelete={()=>{}}/>);
  expect(explained).toContain('说明与依据</button>');
  expect(explained).toContain('role="tooltip" hidden="">换牌依据\n&lt;纯文本&gt;');
  expect(html).toContain('导出json');
  const left=html.match(/<section[^>]*aria-label="卡牌与条件"[^>]*>([\s\S]*?)<\/section>/)?.[1];
  expect(left).toContain('关联卡牌');expect(left).toContain('虞姬');expect(left).toContain('回合');
  expect(left).not.toContain('第一条完整话术');
 });
});
