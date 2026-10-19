import {it,expect} from 'vitest';
import {filterNotes,noteCounts,restoreNoteSelection} from './directoryModel';
import type {Note} from './types';
const rows=[{id:'a',title:'河洛花木兰',type:'lineup',aliases:['复生'],entities:[],core:[],claims:[],meta:{players:['p'],core_heroes:['h']},lineup_links:[{lineup:'old',role:'primary'}]},
 {id:'b',title:'棋手',type:'player',aliases:[],entities:['p'],core:[],claims:[]}] as unknown as Note[];
it('filters and counts by the same query and entity semantics',()=>{
 const criteria={query:'复生',player:'p',hero:'h',type:''};
 expect(filterNotes(rows,criteria,[]).map(n=>n.id)).toEqual(['a']);
 expect(noteCounts(rows,criteria,[])).toEqual({'':1,lineup:1,player:0,other:0});
 expect(filterNotes(rows,{...criteria,type:'player'},[])).toEqual([]);
 expect(criteria.query).toBe('复生');
});
it('restores real note, legacy primary or unique note and safe fallback',()=>{
 expect(restoreNoteSelection(rows,'b')).toBe('b');expect(restoreNoteSelection(rows,'old')).toBe('a');
 expect(restoreNoteSelection(rows,'missing')).toBe('a');expect(restoreNoteSelection([],'missing')).toBe('');
 const linked=rows.map(n=>({...n,lineup_links:n.id==='b'?[{lineup:'unique',role:'variant'}]:[]})) as Note[];
 expect(restoreNoteSelection(linked,'unique')).toBe('b');
});
