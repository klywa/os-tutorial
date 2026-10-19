import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import NoteHeading from './NoteHeading';
import type {Note,ReadingDocument} from './types';
it('keeps title, selected player, dependencies and all actions in one compact header',()=>{
 const note={title:'很长的河洛花木兰标题',type:'lineup',meta:{players:['player:1'],core_heroes:['card:1'],required_factions:['faction:heluo']}} as Note;
 const reading={player:'player:1',player_options:[{id:'player:1',name:'明先生'}]} as ReadingDocument;
 const html=renderToStaticMarkup(<NoteHeading note={note} reading={reading} name={x=>({'card:1':'花木兰','faction:heluo':'河洛'}[x]??x)} dirty={false} editing={false} onAssociate={()=>{}} onEdit={()=>{}} onPlayer={()=>{}} onExport={()=>{}}/>);
 expect(html).toContain('很长的河洛花木兰标题');expect(html).toContain('当前打法棋手');expect(html).toContain('必须阵营：');expect(html).toContain('河洛');
 for(const label of ['关联阵容','编辑笔记','导出当前棋手'])expect(html.match(new RegExp(label,'g'))).toHaveLength(1);
});
