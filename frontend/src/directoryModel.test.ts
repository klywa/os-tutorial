import {it,expect} from 'vitest';
import {filterNotes,noteCounts,restoreNoteSelection,normalizeDirectoryType} from './directoryModel';
import type {Note} from './types';
const rows=[{id:'a',title:'河洛花木兰',type:'lineup',aliases:['复生'],entities:[],core:[],claims:[],meta:{players:['p'],core_heroes:['h']},lineup_links:[{lineup:'old',role:'primary'}]},
 {id:'b',title:'棋手',type:'player',aliases:[],entities:['p'],core:[],claims:[]}] as unknown as Note[];
it('filters and counts by the same query and entity semantics',()=>{
 const criteria={query:'复生',player:'p',hero:'h',type:''};
 expect(filterNotes(rows,criteria,[]).map(n=>n.id)).toEqual(['a']);
 expect(noteCounts(rows,criteria,[])).toEqual({'':1,tactics:1,other:0});
 expect(filterNotes(rows,{...criteria,type:'player'},[])).toEqual([]);
 expect(criteria.query).toBe('复生');
});
it('combines lineup and player notes without adding unmatched player notes',()=>{
 const criteria={query:'',player:'',hero:'',type:'tactics'};
 expect(filterNotes(rows,criteria,[]).map(n=>n.id)).toEqual(['a','b']);
 expect(noteCounts(rows,criteria,[])).toEqual({'':2,tactics:2,other:0});
 expect(filterNotes(rows,{...criteria,hero:'h'},[]).map(n=>n.id)).toEqual(['a']);
 expect(filterNotes(rows,{...criteria,query:'河洛'},[]).map(n=>n.id)).toEqual(['a']);
});
it('restores both old directory categories to tactics',()=>{
 for(const old of ['lineup','player'])expect(normalizeDirectoryType(old)).toBe('tactics');
 for(const type of ['','tactics','other'])expect(normalizeDirectoryType(type)).toBe(type);
});
it('restores real note, legacy primary or unique note and safe fallback',()=>{
 expect(restoreNoteSelection(rows,'b')).toBe('b');expect(restoreNoteSelection(rows,'old')).toBe('a');
 expect(restoreNoteSelection(rows,'missing')).toBe('a');expect(restoreNoteSelection([],'missing')).toBe('');
 const linked=rows.map(n=>({...n,lineup_links:n.id==='b'?[{lineup:'unique',role:'variant'}]:[]})) as Note[];
 expect(restoreNoteSelection(linked,'unique')).toBe('b');
});
