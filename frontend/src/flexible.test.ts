import {describe,it,expect} from 'vitest';
import {availability,matches} from './model';
import type {Note} from './types';
const note={id:'flex',title:'通用打法',type:'lineup',core:[],entities:[],claims:[],meta:{required_factions:[],players:[],core_heroes:[],compositions:{early:[],middle:[],late:[]},ban_conditions:[],matchups:[],operation_routes:[{id:'r',name:'稳健运营',condition:'血量充足',advantages:'稳定',risks:'慢',transition:'调整',phases:{early:[],middle:[],late:[]},claim_refs:[],variant_ids:['a','b']}],late_variants:[{id:'a',name:'风筝组合',condition:'获得英雄',members:[{hero:'h1',necessity:'required',role:'输出'}],core_heroes:['h1'],required_factions:['dahe'],ban_conditions:[{faction:'sanfen',status:'playable',reason:'已确认'},{faction:'zhulu',status:'playable',reason:'单独确认'}],ban_combinations:[],claim_refs:[]},{id:'b',name:'另一组合',members:[],core_heroes:[],required_factions:['sanfen'],ban_conditions:[{faction:'dahe',status:'playable',reason:'确认'}],ban_combinations:[],claim_refs:[]}]}} as unknown as Note;
describe('flexible lineups',()=>{
 it('keeps playable alternatives and rejects joint bans without evidence',()=>{
  expect(availability(note,['dahe'])).toBe('playable');
  expect(availability(note,['dahe','sanfen'])).toBe('unplayable');
  expect(availability(note,['sanfen','zhulu'])).toBe('unknown');
 });
 it('searches route names, combinations and their heroes',()=>{
  expect(matches(note,'稳健运营',[])).toBe(true);
  expect(matches(note,'风筝组合',[])).toBe(true);
  expect(matches(note,'艾琳',[{id:'h1',name:'艾琳'}])).toBe(true);
 });
});

import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Tactics from './Tactics';
it('renders every combination and the route comparison with clear status',()=>{
 const html=renderToStaticMarkup(createElement(Tactics,{note,name:(id:string)=>id==='h1'?'艾琳':id,banned:['dahe'],routes:true,variants:true}));
 expect(html).toContain('稳健运营');
 expect(html).toContain('血量充足');
 expect(html).toContain('风筝组合');
 expect(html).toContain('另一组合');
 expect(html).toContain('艾琳');
 expect(html).toContain('不可玩');
 expect(html).not.toContain('claim_refs');
});

it('retains inference and condition on referenced advice',()=>{
 const copy=structuredClone(note);
 copy.claims=[{id:'c',section:'中期运营',kind:'conditional_strategy',text:'有条件建议',inference:true,condition:'经济充足',evidence:[]}];
 copy.meta!.late_variants![0].claim_refs=['c'];
 const html=renderToStaticMarkup(createElement(Tactics,{note:copy,name:(id:string)=>id,variants:true}));
 expect(html).toContain('推测');
 expect(html).toContain('适用条件：');
 expect(html).toContain('经济充足');
});
