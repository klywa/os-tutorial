import {describe,expect,it} from 'vitest';
import {fixedArguments,parameterRole,templateAction} from './templateAction';
import type {TemplateGroup,TemplateEvent} from './templates';

const event:TemplateEvent={id:'equip',name:'穿戴装备',parameters:[
 {key:'arg1',id:'a',name:'arg1',type:'entity'}, {key:'arg2',id:'b',name:'arg2',type:'entity'},
]};
const group:TemplateGroup={id:'g',name:'装备组',event_id:event.id,scope:{player_id:null,lineup_note_id:null},conditions:[],utterances:[],related_entities:[]};
describe('template action and parameters',()=>{
 it('uses only guaranteed participants and preserves their parameter roles',()=>{
  const expression='(arg2 is "驱雷" and not (arg1 is "司空震")) and 玩家.战场 has "司空震"';
  expect(templateAction({...group,expression},event)).toBe('给英雄穿戴驱雷');
  expect(parameterRole(event,event.parameters[1])).toBe('穿上的装备');
  expect(templateAction({...group,expression:'arg1.名称 is "诸葛亮" and arg2 is "自然法杖"'},event)).toBe('给诸葛亮穿戴自然法杖');
 });
 it('describes a recommended lineup from its required name',()=>{
  const recommendation={...event,name:'解释为何建议向某阵容发展'};
  expect(templateAction({...group,expression:'arg1.阵容名 has "甲队"'},recommendation)).toBe('向甲队方向发展');
 });
 it('leaves alternatives and dynamic arguments open',()=>{
  expect(fixedArguments({...group,expression:'arg1 is "弈星" or arg1 is "苏烈"'}).size).toBe(0);
  expect(templateAction({...group,expression:'arg1 is 玩家.主C and arg2 is "驱雷"'},event)).toBe('给英雄穿戴驱雷');
 });
});
