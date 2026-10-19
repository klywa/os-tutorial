import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {mergeInstruction,linkRoleLabel} from './NoteLinks';
it('builds chapter-level instructions without submitting or automatically merging',()=>{
 const text=mergeInstruction({id:'l1',name:'阵容',common_name:'常用'} as never,{id:'main',title:'主笔记'} as never,{id:'other',title:'来源'} as never);
 expect(text).toContain('wanxiangqi-knowledge');expect(text).toContain('main');expect(text).toContain('other');expect(text).toContain('人工');expect(text).toContain('不直接拼接');
});
it('labels relation roles without creating lineup variants',()=>{
 expect(linkRoleLabel('primary')).toBe('主笔记');expect(linkRoleLabel('variant')).toBe('变体笔记');expect(linkRoleLabel('legacy')).toBe('主次待指定');
});
