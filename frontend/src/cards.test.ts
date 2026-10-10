import {describe, expect, it} from 'vitest';
import {cardMatches} from './model';
import type {CardSummary} from './types';
const card={id:'card:1191',name:'扁鹊',category:'heroes',aliases:['毒奶'],effect:'护盾被击破造成法术伤害',tier:4,awakened:false,faction:{id:'faction:zhulu',name:'逐鹿'}} as CardSummary;
const filters={query:'',category:'',faction:'',tier:'',awakened:''};
describe('card library filters',()=>{
  it('searches aliases and card effects',()=>{
    expect(cardMatches(card,{...filters,query:'毒奶'})).toBe(true);
    expect(cardMatches(card,{...filters,query:'护盾'})).toBe(true);
    expect(cardMatches(card,{...filters,query:'复生'})).toBe(false);
  });
  it('combines faction, hero tier and awakened filters',()=>{
    expect(cardMatches(card,{...filters,faction:'faction:zhulu',tier:'4',awakened:'normal'})).toBe(true);
    expect(cardMatches(card,{...filters,tier:'5'})).toBe(false);
    expect(cardMatches(card,{...filters,awakened:'awakened'})).toBe(false);
  });
});
