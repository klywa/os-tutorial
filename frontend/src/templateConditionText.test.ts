import {describe,expect,it} from 'vitest';
import {parseFileConditionText,resolveConditionEdit} from './templateConditionText';
import type {TemplateGroup} from './templates';

describe('file condition text',()=>{
 it('removes scope restrictions when the user deletes them',()=>{
  expect(parseFileConditionText('(我方.等级 > 3)', '0.4')).toEqual({
   player:null,lineup:null,expression:'我方.等级 > 3',
  });
 });
 it('extracts simple scope restrictions around a rule, including quoted text and nested disjunctions',()=>{
  const text='我方.棋手名称 == "白歌" and (我方.等级 > 3 or 我方.等级 < 1) and 我方.阵容名称 == "甲 and 乙"';
  expect(parseFileConditionText(text, '0.4')).toEqual({
   player:'白歌',lineup:'甲 and 乙',expression:'我方.等级 > 3 or 我方.等级 < 1',
  });
 });
 it('keeps scope predicates within a disjunction as part of the rule',()=>{
  const text='我方.棋手名称 == "白歌" and 我方.等级 > 3 or 我方.等级 < 1';
  expect(parseFileConditionText(text, '0.4')).toEqual({player:null,lineup:null,expression:text});
 });
 it('accepts the legacy scope syntax',()=>{
  expect(parseFileConditionText('玩家.使用棋手 is "白歌" and (gold >= 2)')).toEqual({
   player:'白歌',lineup:null,expression:'gold >= 2',
  });
 });
});

it('resolves inline database scope names and preserves unresolved names as DSL predicates',()=>{
 const group:TemplateGroup={id:'id',event_id:'e',name:'测试',syntax_version:'0.4',conditions:[],utterances:[],related_entities:[],
  scope:{player_id:'old',lineup_note_id:null},expression:'我方.等级 > 3'};
 const options={players:[{id:'new',name:'安琪拉'}],lineups:[{id:'l',title:'新阵容',player_id:'new'}]};
 const edit='我方.棋手名称 == "安琪拉" and 我方.阵容名称 == "新阵容" and (我方.等级 > 3)';
 expect(resolveConditionEdit(edit,group,()=> '白歌',options)).toEqual({
  scope:{player_id:'new',lineup_note_id:'l'},expression:group.expression,
 });
 expect(resolveConditionEdit(edit,group,()=> '白歌',{})).toEqual({scope:{player_id:null,lineup_note_id:null},expression:edit});
 expect(resolveConditionEdit(group.expression!,group,()=> '白歌',options).scope.player_id).toBeNull();
});
