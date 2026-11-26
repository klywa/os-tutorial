import {describe,expect,it} from 'vitest';
import {changeTemplateArgument,templateTriggerParameters} from './templateInlineTrigger';
import {fixedArguments,type TemplateEvent,type TemplateGroup,type TemplateParameter} from './templates';

const hero:TemplateParameter={id:'hero',key:'arg1',name:'目标英雄',type:'entity'};
const event:TemplateEvent={id:'wear',name:'解释为何穿戴装备',parameters:[hero]};
const group:TemplateGroup={id:'group',event_id:event.id,name:'解释为何给刘禅穿戴极寒风暴',
 scope:{player_id:null,lineup_note_id:null},conditions:[],utterances:[{id:'a',text:'保留原话术。'}],related_entities:[]};

describe('清除模板组参数的固定值',()=>{
 it('uses a wildcard and removes the matching binding from the trigger',()=>{
  const source:TemplateGroup={...group,syntax_version:'0.4',extra_key:'刘禅-极寒风暴',
   expression:'(动作.目标英雄.名称 == "刘禅") and 我方.等级 >= 3 and 动作.装备.名称 == "极寒风暴"'};
  const parameter=templateTriggerParameters(source,event)[0];
  const cleared=changeTemplateArgument(source,event,parameter,null);
  expect(cleared.extra_key).toBe('*-极寒风暴');
  expect(cleared.name).toBe('解释为何给英雄穿戴极寒风暴');
  expect(cleared.expression).toBe('我方.等级 >= 3 and 动作.装备.名称 == "极寒风暴"');
  expect(cleared.utterances).toEqual(group.utterances);
  expect(fixedArguments(cleared,event).has(hero.key)).toBe(false);
 });

 it('preserves legacy comparisons and removes only the parameter binding',()=>{
  const source:TemplateGroup={...group,expression:'arg1.名称 is "刘禅" and (arg2 >= 3 or arg2 == 1)'};
  expect(changeTemplateArgument(source,event,hero,null).expression).toBe('(arg2 >= 3 or arg2 == 1)');
  const structured:TemplateGroup={...group,conditions:[
   {id:'fixed',parameter_key:'arg1',operator:'eq',value:{id:'hero-lc',name:'刘禅'}},
   {id:'other',parameter_key:'arg2',operator:'gte',value:3},
  ]};
  expect(changeTemplateArgument(structured,event,hero,null).conditions).toEqual([structured.conditions[1]]);
 });

 it('saves a manually entered entity without requiring a catalog ID',()=>{
  const source:TemplateGroup={...group,syntax_version:'0.4',extra_key:'*-极寒风暴'};
  expect(changeTemplateArgument(source,event,hero,' 敖隐 ')).toMatchObject({extra_key:'敖隐-极寒风暴'});
  const legacy:TemplateGroup={...group,conditions:[
   {id:'fixed',parameter_key:'arg1',operator:'eq',value:{id:'hero-lc',name:'刘禅'}},
   {id:'other',parameter_key:'arg2',operator:'gte',value:3},
  ]};
  expect(changeTemplateArgument(legacy,event,hero,'新英雄')).toMatchObject({
   expression:'arg1.名称 == "新英雄" and arg2 >= 3',conditions:[],editor_mode:'text',
  });
 });
});
