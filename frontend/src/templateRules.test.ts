import {describe,it,expect} from 'vitest';
import rawCatalog from '../../src/condition/catalog.json?raw';
import {completeTree,compatibleRight,listPaths,operatorsFor,renderRule,switchToText,treeEntities,type ConditionCatalog,type ConditionNode} from './templateRules';
const catalog:ConditionCatalog=JSON.parse(rawCatalog);
const paths=listPaths({id:'deploy',name:'解释为何上阵英雄',parameters:[]},catalog);
function leaf(left:string,operator:string,right:string):ConditionNode{return {kind:'leaf',left,operator,right};}
describe('visual condition editor',()=>{
 it('offers sums only for numeric fields shared by every array member type',()=>{
  const sum=paths.find(p=>p.path==='玩家.战场.求和(等级)')!;
  expect(sum.type).toBe('int');
  expect(operatorsFor(sum)).toContain('>');
  expect(paths.some(p=>p.path==='玩家.手牌.求和(等级)'||p.path==='玩家.战场.求和(名称)')).toBe(false);
 });
 it('offers card tags on event objects, board collections and nested heroes',()=>{
  const withTags={...catalog,card_tags:{card1:{type:'英雄',tags:['提供友军护盾']},card2:{type:'天赋',tags:['提供能量']}}};
  const paths=listPaths({id:'deploy',name:'解释为何上阵英雄',parameters:[]},withTags);
  for(const path of ['arg1.标签','玩家.战场.标签','对局.当前对手.主C.标签']){
   expect(paths.find(p=>p.path===path)).toMatchObject({type:'Array<string>',operations:['has'],choices:['提供友军护盾']});
   expect(renderRule(leaf(path,'has','"提供友军护盾"'))).toBe(path+' has "提供友军护盾"');
  }
 });
 it('offers the two hero name paths and builds the three-part acceptance rule',()=>{
  const main=paths.find(p=>p.path==='玩家.主C.名称')!,arg=paths.find(p=>p.path==='arg1.名称')!;
  expect(compatibleRight(main.type,arg.type,'is')).toBe(true);
  expect(compatibleRight(main.type,'int','is')).toBe(false);
  const rule:ConditionNode={kind:'all',children:[leaf(main.path,'is',arg.path),leaf('玩家.主C.等级','>=','10'),leaf('玩家.剩余能量','<=','3')]};
  expect(renderRule(rule)).toBe('(玩家.主C.名称 is arg1.名称 and 玩家.主C.等级 >= 10 and 玩家.剩余能量 <= 3)');
  expect(completeTree(rule)).toBe(true);
 });
 it('offers the same lineup-name membership condition on arguments and intermediate objects',()=>{
  const options=listPaths({id:'lineup',name:'解释为何建议向某阵容发展',parameters:[]},catalog);
  for(const path of ['arg1.阵容名','对局.当前对手.当前阵容.阵容名']){
   const option=options.find(p=>p.path===path)!;
   expect(option.type).toBe('Array<string>');
   expect(operatorsFor(option)).toEqual(['has']);
   expect(compatibleRight(option.type,'string','has')).toBe(true);
  }
 });
 it('honors grouping, boolean leaves, and empty root semantics',()=>{
  const tree:ConditionNode={kind:'not',children:[{kind:'any',children:[leaf('arg1.已觉醒','',''),leaf('玩家.等级','==','5')]}]};
  expect(renderRule(tree)).toBe('not ((arg1.已觉醒 or 玩家.等级 == 5))');
  expect(renderRule({kind:'all',children:[]})).toBe('');
  expect(completeTree({kind:'all',children:[{kind:'any',children:[]}]})).toBe(false);
  expect(completeTree(leaf('玩家.等级','>=',''))).toBe(false);
 });
 it('keeps a recoverable complete tree while freeing text from an incomplete draft',()=>{
  const saved=leaf('玩家.等级','>=','5');
  const partial:ConditionNode={kind:'all',children:[saved,leaf('玩家.血量','<=','')]};
  const text=renderRule(partial);
  expect(switchToText(partial,saved,text)).toEqual({expression:text,condition_tree:saved,editor_mode:'text'});
  expect(switchToText(partial,null,text).condition_tree).toBeNull();
  expect(switchToText(saved,null,renderRule(saved)).condition_tree).toEqual(saved);
 });
 it('limits equipment types and matches compatible array member paths',()=>{
  const option=listPaths({id:'wear',name:'解释为何穿戴装备',parameters:[]},catalog).find(p=>p.path==='arg2.类型')!;
  expect(operatorsFor(option)).toEqual(['is']);
  expect(compatibleRight('Array<英雄|效果牌>','英雄','has')).toBe(true);
  expect(compatibleRight('英雄','Array<单位>','in',catalog.aliases)).toBe(true);
  expect(compatibleRight('string','Array<英雄>','in')).toBe(false);
 });
 it('links literal names in matching categories and ignores path-to-path comparisons',()=>{
  const cards=[{id:'h1',name:'弈星',category:'heroes'},{id:'h2',name:'弈星',category:'heroes'},{id:'e1',name:'弈星',category:'equipment'}];
  expect(treeEntities(leaf('arg1.名称','is','"弈星"'),paths,cards).map(e=>e.id)).toEqual(['h1','h2']);
  expect(treeEntities(leaf('arg1.名称','is','玩家.主C.名称'),paths,cards)).toEqual([]);
  expect(treeEntities(leaf('商店.商店列表','has','{"类型":"装备","名称":"弈星"}'),paths,cards).map(e=>e.id)).toEqual(['e1']);
 });
});
