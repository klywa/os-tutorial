import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {matchingOptions,type UsageMatchData} from './usageMatchModel';
import {UsageMatchFields} from './UsageMatchDialog';

const data:UsageMatchData={revision:'r',pairs:[{id:'g@p1',source_id:'g',source_name:'网站名字',player_id:'p1',player_name:'香香',heroes:['a','b'],hero_names:['公孙离','虞姬'],rank:1,pair_revision:'p',manual_note_id:null,candidates:['推荐阵容－香香']}],
 notes:[{id:'wrong',title:'同名阵容－嬴律',player_id:'p2',formations:[]},{id:'other',title:'其他阵容－香香',player_id:'p1',formations:[]},{id:'right',title:'推荐阵容－香香',player_id:'p1',formations:[['公孙离','虞姬','瑶']]}]};
it('only offers the same player, puts suggestions first and searches titles',()=>{
 expect(matchingOptions(data,data.pairs[0],'').map(n=>n.id)).toEqual(['right','other']);
 expect(matchingOptions(data,data.pairs[0],'其他').map(n=>n.id)).toEqual(['other']);
 expect(matchingOptions(data,data.pairs[0],'嬴律')).toEqual([]);
});
it('renders both source and target formations and explicit save/restore controls',()=>{
 const html=renderToStaticMarkup(<UsageMatchFields data={data} pair={data.pairs[0]} noteId="right" query="" busy={false} onQuery={()=>{}} onNote={()=>{}} onPair={()=>{}} onSave={()=>{}} onRestore={()=>{}} onClose={()=>{}}/>);
 for(const text of ['外网阵容＋棋手','网站名字','香香','公孙离','虞姬','知识库匹配项','推荐阵容－香香','只列出同一棋手','保存匹配','恢复自动匹配'])expect(html).toContain(text);
 expect(html).not.toContain('同名阵容－嬴律');expect(html).toContain('type="radio"');
});
it('does not lose the selected item when the search hides its row',()=>{
 const html=renderToStaticMarkup(<UsageMatchFields data={data} pair={data.pairs[0]} noteId="right" query="找不到" busy={false} onQuery={()=>{}} onNote={()=>{}} onPair={()=>{}} onSave={()=>{}} onRestore={()=>{}} onClose={()=>{}}/>);
 expect(html).toContain('没有符合搜索条件的笔记');expect(html).toContain('已选择：');expect(html).toContain('推荐阵容－香香');
});
