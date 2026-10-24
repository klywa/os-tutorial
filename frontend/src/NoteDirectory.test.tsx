import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect,vi} from 'vitest';
import NoteDirectory from './NoteDirectory';
import type {Note} from './types';
vi.mock('./EntityCards',()=>({useCards:()=>[],CardImage:()=>null}));
const note=(id:string,title:string,type:Note['type']='lineup')=>({id,title,type,aliases:[],claims:[],entities:[],revision:'',path:'',core:[],manual_sections:[],conflicts:[],related:[]}) as Note;
describe('note directory',()=>{
 it('places the bound player note first and expands the selected lineup group',()=>{
  const rows=[{...note('l','花木兰-昭君'),player_id:'player:1'},{...note('p','昭君','player'),player_id:'player:1'}];
  const html=renderToStaticMarkup(<NoteDirectory notes={rows} active="l" onSelect={()=>{}}/>);
  expect(html.indexOf('aria-label="昭君"')).toBeLessThan(html.indexOf('aria-label="花木兰-昭君"'));
  expect(html).toContain('open=""');expect(html).toContain('aria-current="page"');
  const filtered=renderToStaticMarkup(<NoteDirectory notes={[rows[0]]} active="l" onSelect={()=>{}}/>);
  expect(filtered).not.toContain('aria-label="昭君"');
 });
 it('opens actual notes in knowledge groups without roster management',()=>{
  const html=renderToStaticMarkup(<NoteDirectory notes={[note('a','河洛花木兰'),note('b','明先生','player')]} active="a" onSelect={()=>{}}/>);
  expect(html).toContain('河洛花木兰');expect(html).toContain('明先生');
  for(const absent of ['管理阵容名单','未归类阵容笔记','暂无笔记'])expect(html).not.toContain(absent);
  expect(html).toContain('<details');expect(html).toContain('其他知识');
  expect(html).toContain('aria-current="page"');
 });
 it('has an explicit empty result without fabricating lineup entries',()=>{
  const html=renderToStaticMarkup(<NoteDirectory notes={[]} active="" onSelect={()=>{}}/>);
  expect(html).toContain('没有符合条件的笔记');expect(html).not.toContain('阵容名单');
 });
});
