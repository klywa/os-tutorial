import {expect,it} from 'vitest';
import {buildSourcePrompt,keepSelection,copyOrFallback} from './sourceTools';
it('prompt preserves user rules and uses Markdown absolute paths',()=>{
 const value=buildSourcePrompt('李信牺牲流',['D:\\raw\\one.md','D:\\raw\\two.md']);
 expect(value).toContain('整理【李信牺牲流】');expect(value).toContain('若有冲突，则让用户裁决');expect(value).toContain('- D:\\raw\\one.md\n- D:\\raw\\two.md');
});
it('selection survives page slicing and drops only ignored or absent IDs',()=>{
 expect(keepSelection(['a','b','a'],[{id:'a'},{id:'b'},{id:'c',ignored:true}])).toEqual(['a','b']);
 expect(keepSelection(['a','c'],[{id:'a'},{id:'c',ignored:true}])).toEqual(['a']);
});

it('clipboard rejection preserves complete editable text for manual copying',async()=>{const text='自定义prompt\n- D:/raw/a.md';expect(await copyOrFallback(text,async()=>{throw new Error('denied');})).toBe(text);expect(await copyOrFallback(text,async()=>{})).toBe('');});
