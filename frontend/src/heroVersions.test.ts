import {describe,it,expect} from 'vitest';
import {heroVersions} from './entityText';
import type {CardSummary} from './types';
const cards=[{id:'awake',name:'曹操',category:'heroes',awakened:true},{id:'normal',name:'曹操',category:'heroes',awakened:false},{id:'single',name:'单版本',category:'heroes',awakened:false},{id:'effect',name:'曹操',category:'effect-cards',awakened:false}] as CardSummary[];
describe('hero versions',()=>{
 it.each([['normal'],['awake'],['awake','normal']])('expands %s to normal then awakened',(...ids)=>{
  expect(heroVersions(cards,ids).map(c=>c.id)).toEqual(['normal','awake']);
 });
 it('keeps a single existing version',()=>expect(heroVersions(cards,['single']).map(c=>c.id)).toEqual(['single']));
 it('does not group nonheroes or ambiguous categories',()=>{
  expect(heroVersions(cards,['effect'])).toEqual([]);
  expect(heroVersions(cards,['normal','effect'])).toEqual([]);
  expect(heroVersions(cards,['missing'])).toEqual([]);
 });
});
