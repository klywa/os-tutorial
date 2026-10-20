import {expect,it} from 'vitest';
import {buildSourcePrompt,keepSelection,copyOrFallback} from './sourceTools';
it('prompt keeps every staged item with title, local path or URL and optional single-line notes',()=>{
 const value=buildSourcePrompt('李信牺牲流',[
  {id:'a',title:'教学甲',location:'D:\\raw\\one.md',notes:'  关注前期\n转阵  '},
  {id:'b',title:'教学乙',location:'https://example.com/video',notes:''},
  {id:'c',title:'',location:'https://example.com/other',notes:'  '},
 ]);
 expect(value).toContain('整理【李信牺牲流】');expect(value).toContain('若有冲突，则让用户裁决');
 expect(value).toContain('- 教学甲：D:\\raw\\one.md（关注前期 转阵）\n- 教学乙：https://example.com/video\n- c：https://example.com/other');
});
it('selection survives page slicing and drops only ignored or absent IDs',()=>{
 expect(keepSelection(['a','b','a'],[{id:'a'},{id:'b'},{id:'c',ignored:true}])).toEqual(['a','b']);
 expect(keepSelection(['a','c'],[{id:'a'},{id:'c',ignored:true}])).toEqual(['a']);
});

it('clipboard rejection preserves complete editable text for manual copying',async()=>{const text='自定义prompt\n- D:/raw/a.md';expect(await copyOrFallback(text,async()=>{throw new Error('denied');})).toBe(text);expect(await copyOrFallback(text,async()=>{})).toBe('');});
