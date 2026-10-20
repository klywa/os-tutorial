import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import NewNoteDialog,{playerNoteFor} from './NewNoteDialog';
import type {Note} from './types';
it('uses explicit player identity rather than titles or opponent mentions',()=>{
 const note={id:'one',type:'player',title:'旧标题',player_id:'player:1',entities:['player:1','player:2']} as Note;
 expect(playerNoteFor([note],'player:1')?.id).toBe('one');
 expect(playerNoteFor([note],'player:2')).toBeUndefined();
 expect(playerNoteFor([{...note,player_id:undefined}],'player:1')).toBeUndefined();
});
it('offers a player selector and keeps ordinary notes named by the user',()=>{
 const props={entities:[{id:'player:1',name:'昭君',category:'players'}],notes:[],onClose:()=>{},onCreated:()=>{},onOpen:()=>{}};
 const player=renderToStaticMarkup(createElement(NewNoteDialog,{...props,defaultType:'player'}));
 expect(player).toContain('笔记棋手');expect(player).toContain('昭君');expect(player).not.toContain('aria-label="笔记名称"');
 const other=renderToStaticMarkup(createElement(NewNoteDialog,{...props,defaultType:'other'}));
 expect(other).toContain('aria-label="笔记名称"');
});
