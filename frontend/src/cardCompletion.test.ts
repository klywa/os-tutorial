import {expect,test} from 'vitest';
import {cardQuery,completeCardName,rankCards} from './cardCompletionSearch';

test('ranks names ahead of aliases and effects, including noncontiguous matches',()=>{
 const cards=[
  {name:'大棒',aliases:[],effect:'征服'},
  {name:'宝剑',aliases:['征服'],effect:''},
  {name:'征战之服',aliases:[],effect:''},
  {name:'征服之剑',aliases:[],effect:''},
  {name:'征服',aliases:[],effect:''},
 ];
 expect(rankCards(cards,'征服').map(card=>card.name)).toEqual(['征服','征服之剑','征战之服','宝剑','大棒']);
 expect(rankCards(cards,'')).toEqual(cards);
});

test('uses the closest hash and preserves text on either side of the caret',()=>{
 const text='#旧，推荐#征服或其他';
 const query=cardQuery(text,8,8);
 expect(query).toEqual({start:5,end:8,text:'征服'});
 expect(completeCardName(text,query!,'征服之剑')).toEqual({value:'#旧，推荐征服之剑或其他',caret:9});
 expect(cardQuery('#征服，',4,4)).toBeNull();
 expect(cardQuery('#征服',1,3)).toBeNull();
 expect(cardQuery('#',1,1)?.text).toBe('');
});
