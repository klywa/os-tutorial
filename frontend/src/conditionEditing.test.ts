import {expect,it} from 'vitest';
import {conditionBracketRanges,conditionCompletion,conditionPair,compactCondition,normalizeConditionInput,utteranceSlotCompletion,utteranceSlotInput} from './conditionEditing';
import {validateV04} from './templateV04';

const event={id:'equip',name:'解释为何穿戴装备',parameters:[]};
const config={event,v04:true};

it('renders nested conditions compactly while keeping literals and legacy decimals intact',()=>{
 const source='(我方.等级 >= 3\n and (动作.目标英雄.名称 in ["曹操", "赵云"] or 我方.等级 == 4))';
 const formatted=compactCondition(source);
 expect(formatted).toBe(source.replace('\n',''));
 expect(conditionBracketRanges(formatted).ranges.map(range=>range.depth)).toEqual([0,1,2]);
 expect(()=>validateV04(event.name,formatted)).not.toThrow();
 expect(compactCondition('(arg1.等级 >= 1.5 and arg1.名称 is "a\\\"(b。)")')).toContain('1.5');
});

it('opens syntax variable completion from each utterance trigger and replaces only the current slot',()=>{
 for(const text of ['给{保护','给{{保护','给「保护']){
  const trigger=text.indexOf('保');
  expect(utteranceSlotInput(text,trigger)).toEqual({value:'给{{保护',caret:3});
 }
 const text='给{{动作.目英.名}}加血',caret=text.indexOf('}');
 const match=utteranceSlotCompletion(text,caret,config);
 expect(match?.choices[0]).toMatchObject({label:'动作.目标英雄.名称',insert:'{{动作.目标英雄.名称}}'});
 expect(text.slice(match?.end)).toBe('加血');
 expect(utteranceSlotInput('给{{动作。',7).value).toBe('给{{动作.');
 expect(utteranceSlotInput('给{动作。目',6)).toEqual({value:'给{{动作.目',caret:7});
 expect(utteranceSlotCompletion('给#曹操',5,config)).toBeNull();
});

it('uses the same triggers in conditions and inserts a bare variable without touching its comparison',()=>{
 for(const trigger of ['{','{{','「']){
  const draft=`(${trigger}动作。目英.名 == "曹操")`;
  const caret=draft.indexOf(' ==');
  const normalized=utteranceSlotInput(draft,caret,false);
  expect(normalized.value).toBe('({{动作.目英.名 == "曹操")');
  const match=utteranceSlotCompletion(normalized.value,normalized.caret,config,false);
  expect(match?.choices[0]).toMatchObject({label:'动作.目标英雄.名称',insert:'动作.目标英雄.名称'});
  expect(normalized.value.slice(match?.end)).toBe(' == "曹操")');
 }
 const literal='动作.装备.名称 == "保留「类型"';
 const caret=literal.length-1;
 expect(utteranceSlotInput(literal,caret,false)).toEqual({value:literal,caret});
 const quoted='我方.棋手名称 == "{{白';
 expect(utteranceSlotCompletion(quoted,quoted.length,config,false)).toBeNull();
});

it('finds the pair around the caret and ignores brackets in quoted text',()=>{
 expect(conditionPair('(x in ["("])',7)).toEqual([6,10]);
 expect(conditionPair('(x in ["("])',9)).toEqual([6,10]);
 expect(conditionPair('("["',1)).toEqual([0]);
 expect(normalizeConditionInput('动作。装备。名称 == "测试。"')).toBe('动作.装备.名称 == "测试。"');
 expect(normalizeConditionInput('我方。阵容名称 == “测试。“')).toBe('我方.阵容名称 == "测试。"');
 expect(normalizeConditionInput('我方。阵容名称 == “测试。”')).toBe('我方.阵容名称 == "测试。"');
 expect(normalizeConditionInput('我方。阵容名称 == "测试。”')).toBe('我方.阵容名称 == "测试。"');
 expect(normalizeConditionInput('动作。选中。名称 == "“杠上了”模块"')).toBe('动作.选中.名称 == "“杠上了”模块"');
});

it('matches and replaces a corner-quoted variable with the caret inside or after the pair',()=>{
 for(const slots of [false,true]){
  const prefix=slots?'给':'(';
  const value=prefix+'「动作。目英.名」'+(slots?'装备':' == "曹操")');
  const closer=value.indexOf('」');
  for(const caret of [closer-1,closer,closer+1]){
   const input=utteranceSlotInput(value,caret,slots);
   const match=utteranceSlotCompletion(input.value,input.caret,config,slots);
   expect(match?.start).toBe(prefix.length);
   expect(match?.choices[0]?.insert).toBe(slots?'{{动作.目标英雄.名称}}':'动作.目标英雄.名称');
   expect(input.value.slice(match?.end)).toBe(value.slice(closer+1));
  }
  const empty=utteranceSlotInput('「」',2,slots);
  expect(utteranceSlotCompletion(empty.value,empty.caret,config,slots)?.choices.length).toBeGreaterThan(0);
 }
});

it('completes the current event field segment and recognizes scoped predicates',()=>{
 const value='动作.目英.名称 == "曹操"';
 expect(conditionCompletion(value,5,config)).toMatchObject({start:3,end:5,choices:[{label:'目标英雄'}]});
 const predicate='any(我方.场上英雄列表, .名';
 expect(conditionCompletion(predicate,predicate.length,config)?.choices.map(choice=>choice.label)).toContain('名称');
 const negation='any(我方.场上英雄列表, not .名';
 expect(conditionCompletion(negation,negation.length,config)?.choices.map(choice=>choice.label)).toContain('名称');
 expect(conditionCompletion('constructor.',12,config)).toBeNull();
 expect(conditionCompletion('"动作.目标"',5,config)).toBeNull();
 expect(conditionCompletion('1.5',2,config)).toBeNull();
});

it('finds v0.4 snippets using fuzzy matching and selects only the first replaceable value',()=>{
 const value='我方.等级 >= 3 and *场英等)';
 const match=conditionCompletion(value,value.length-1,config);
 expect(match).toMatchObject({snippet:true,start:value.indexOf('*'),end:value.length-1});
 const first=match?.choices[0];
 expect(first?.label).toBe('场上英雄等级');
 expect(first?.insert?.slice(first.selection?.start,first.selection?.end)).toBe('孙尚香');
 for(const choice of conditionCompletion('*',1,config)?.choices??[]){
  expect(()=>validateV04(event.name,choice.insert!)).not.toThrow();
 }
 const core=conditionCompletion('*主C',3,config)?.choices.find(choice=>choice.label==='我方主C等级');
 expect(core?.insert).toContain('我方.主C != nil');
 expect(core?.insert?.slice(core.selection?.start,core.selection?.end)).toBe('40');
});

it('keeps asterisks in quoted strings or multiplication separate from snippets',()=>{
 for(const value of ['我方.等级 *','2*20','动作.装备.名称 == "*英雄']){
  expect(conditionCompletion(value,value.length,config)).toBeNull();
 }
 expect(conditionCompletion('*',1,{event,v04:false})).toBeNull();
 const unknown='*不存在的片段';
 expect(conditionCompletion(unknown,unknown.length,config)?.choices).toEqual([]);
});
