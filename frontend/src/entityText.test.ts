import {describe,it,expect} from 'vitest';
import {splitEntities,resolveCandidates,selectedCandidate} from './entityText';
import type {CardSummary} from './types';
const cards=[{id:'a',name:'瑶',aliases:['瑶妹']},{id:'b',name:'李信',aliases:[]},{id:'c',name:'李信',aliases:[],awakened:true},{id:'d',name:'李信之剑',aliases:[]} ] as unknown as CardSummary[];
describe('strict entity text',()=>{
 it('matches full official names and protects nicknames',()=>{
  expect(splitEntities('瑶妹与瑶的装备、李信之剑',cards).filter(t=>t.ids).map(t=>t.text)).toEqual(['瑶','李信之剑']);
  expect(splitEntities('瑶妹',cards)).toEqual([{text:'瑶妹'}]);
 });
 it('preserves all ambiguous cards unless a unique reference exists',()=>{
  expect(resolveCandidates(['b','c'],['c'])).toEqual(['c']);
  expect(resolveCandidates(['b','c'],['b','c'])).toEqual(['b','c']);
  expect(selectedCandidate(['b','c'],'')).toBe('');
  expect(selectedCandidate(['b','c'],'c')).toBe('c');
  expect(selectedCandidate(['b'],'')).toBe('b');
 });
 it('never resolves a shorter name inside a protected longer label',()=>{
  expect(splitEntities('超级瑶妹，使用李信打前排',cards).filter(t=>t.ids).map(t=>t.text)).toEqual(['李信']);
 });
});
