import {expect,it,vi} from 'vitest';
import {DockSelection} from './dockSelection';
import {cardIndex,splitEntities} from './entityText';
import type {CardSummary} from './types';

it('notifies only old and new card anchors and the dock when selection changes',()=>{
 const store=new DockSelection(),a=vi.fn(),b=vi.fn(),other=vi.fn(),dock=vi.fn();
 store.subscribe('a',a);store.subscribe('b',b);store.subscribe('other',other);store.subscribe('',dock);
 store.select('a',false);store.select('b',true);store.select('other',false);
 expect(a).toHaveBeenCalledTimes(2);expect(b).toHaveBeenCalledTimes(1);expect(other).not.toHaveBeenCalled();
 expect(store.snapshot()).toEqual({active:'b',pinned:true});expect(dock).toHaveBeenCalledTimes(2);
 store.close();expect(b).toHaveBeenCalledTimes(2);expect(store.snapshot().active).toBe('');
});
it('does not notify on unchanged selection and unsubscribes discarded anchors',()=>{
 const store=new DockSelection(),listener=vi.fn();const off=store.subscribe('a',listener);
 store.select('a',false);store.select('a',false);off();store.close();expect(listener).toHaveBeenCalledTimes(1);
});
it('indexes hero versions once and invalidates on a new card collection',()=>{
 const cards=[{id:'a',name:'李信',category:'heroes',awakened:false},{id:'b',name:'李信',category:'heroes',awakened:true}] as CardSummary[];
 const index=cardIndex(cards);expect(index.byId.get('a')?.name).toBe('李信');expect(index.heroes.get('李信')?.map(c=>c.id)).toEqual(['a','b']);
 expect(cardIndex(cards)).toBe(index);expect(cardIndex([...cards])).not.toBe(index);
 expect(splitEntities('李信',cards)).toEqual([{text:'李信',ids:['a','b']}]);
 expect(splitEntities('李信',[{...cards[0],name:'新名字'}])).toEqual([{text:'李信'}]);
});
