import {describe,expect,it} from 'vitest';
import {parseTemplateFile} from './templateFile';
import {validateExtraKey,validateV04,validateV04Template} from './templateV04';

const event='解释为何转移装备';

describe('v0.4 template authoring',()=>{
 it('validates event-specific paths and nullable reads in all branches',()=>{
  expect(()=>validateV04(event,'any(我方.场上英雄列表, .名称 == 动作.目标英雄.名称)')).not.toThrow();
  expect(()=>validateV04(event,'对手 == nil or 对手.主C.等级 > 40')).toThrow(/守卫/);
  expect(()=>validateV04(event,'对手 == nil or (对手.主C != nil and 对手.主C.等级 > 40)')).not.toThrow();
  expect(()=>validateV04(event,'动作.选中.名称 == "花木兰"')).toThrow(/未声明/);
 });
 it('accepts guarded scalar results for hero merges',()=>{
  const merge='解释为何合成英雄';
  expect(()=>validateV04(merge,'动作.合成后等级 != nil and 动作.合成后等级 >= 40')).not.toThrow();
  expect(()=>validateV04(merge,'动作.合成后已觉醒 != nil and 动作.合成后已觉醒')).not.toThrow();
  expect(()=>validateV04(merge,'动作.合成后等级 != nil and (动作.合成后等级 == nil or 动作.合成后等级 >= 40)')).not.toThrow();
  expect(()=>validateV04(merge,'动作.合成后等级 >= 40')).toThrow();
 });
 it('requires a type guard for mixed cards and a name path for single card slots',()=>{
  expect(()=>validateV04('解释为何购买英雄','动作.选中.等级 >= 10')).toThrow(/卡牌类型/);
  expect(()=>validateV04('解释为何购买英雄','动作.选中.卡牌类型 == "英雄" and 动作.选中.等级 >= 10')).not.toThrow();
  expect(()=>validateV04Template(event,'{{动作.装备}}')).toThrow(/名称/);
  expect(()=>validateV04Template(event,'{普通} {{动作.装备.名称}}')).not.toThrow();
  expect(()=>validateExtraKey('解释为何棋手升级','06')).toThrow();
 });
 it('round trips a portable group with stable and fixed utterance identity',()=>{
  const result=parseTemplateFile(JSON.stringify({
   kind:'speech-template-library',schema_version:3,events:[{name:event,parameters:[]}],
   groups:[{id:'group1',name:'转出驱雷',event_name:event,syntax_version:'0.4',extra_key:'*-司空震-驱雷',
    expression:'我方.等级 > 3',utterances:[{id:'utterance1',text:'转给{{动作.目标英雄.名称}}。',fixed:true}]}],
  }));
  expect(result.groupErrors).toEqual([]);
  expect(result.snapshot.groups[0]).toMatchObject({syntax_version:'0.4',extra_key:'*-司空震-驱雷',
   utterances:[{id:'utterance1',fixed:true}]});
 });
});
