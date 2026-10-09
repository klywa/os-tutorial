import { describe, expect, it } from 'vitest';
import { availability, matches, sectionText } from './model';
import type { Note } from './types';
const note = {id:'a',type:'lineup',title:'昭君大河',aliases:['龙蛇'],core:[],entities:['h1'],claims:[{section:'后期',text:'保护图腾'}],meta:{required_factions:['dahe'],players:[],core_heroes:[],compositions:{early:[],middle:[],late:[]},ban_conditions:[{faction:'sanfen',status:'playable',reason:''}],matchups:[]}} as unknown as Note;
describe('knowledge queries',()=>{
  it('requires every ban to be confirmed playable',()=>{
    expect(availability(note,['dahe'])).toBe('unplayable');
    expect(availability(note,['sanfen'])).toBe('playable');
    expect(availability(note,['sanfen','zhulu'])).toBe('unknown');
  });
  it('searches aliases, prose and entity names',()=>{
    expect(matches(note,'龙蛇',[])).toBe(true);
    expect(matches(note,'图腾',[])).toBe(true);
    expect(matches(note,'东皇',[{id:'h1',name:'东皇太一'}])).toBe(true);
  });
  it('does not invent missing advice',()=>expect(sectionText(note,'未知')).toBe(''));
});
