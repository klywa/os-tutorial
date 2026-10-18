import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect,vi} from 'vitest';
import NoteDirectory from './NoteDirectory';
vi.mock('./EntityCards',()=>({useCards:()=>[],CardImage:()=>null}));
describe('classified directory',()=>{
 it('searches and displays the common name without promoting variants to entries',()=>{
  const html=renderToStaticMarkup(<NoteDirectory notes={[]} roster={[{id:'l',name:'网站原名',common_name:'大河龙蛇',heroes:[],variants:[{id:'v',heroes:['card:1']}],note_ids:[],enabled:true}]} query="大河龙蛇" hero="" player="" type="" active="" onSelect={()=>{}} onLineup={()=>{}} onManage={()=>{}}/>);
  expect(html).toContain('大河龙蛇');expect(html).toContain('1 套');expect(html).not.toContain('card:1');
 });
 it('shows roster placeholders without manufacturing notes',()=>{
  const html=renderToStaticMarkup(<NoteDirectory notes={[]} roster={[{id:'lineup:a',name:'甲阵容',heroes:['card:1'],note_ids:[],enabled:true}]} query="" hero="" player="" type="" active="" onSelect={()=>{}} onLineup={()=>{}} onManage={()=>{}}/>);
  expect(html).toContain('甲阵容');expect(html).toContain('暂无笔记');expect(html).toContain('棋手');
 });
 it('keeps linked notes visible when searching the lineup name',()=>{
  const note={id:'n',title:'已有攻略',type:'lineup' as const,aliases:[],claims:[],entities:[],revision:'',path:'',core:[],manual_sections:[],conflicts:[],related:[]};
  const html=renderToStaticMarkup(<NoteDirectory notes={[note]} roster={[{id:'l',name:'甲阵容',heroes:[],note_ids:['n'],enabled:true}]} query="甲阵容" hero="" player="" type="" active="" onSelect={()=>{}} onLineup={()=>{}} onManage={()=>{}}/>);
  expect(html).toContain('已有攻略');
 });
});
