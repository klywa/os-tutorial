import {it,expect,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {ConflictEditor,RetainedDrafts} from './SyncConflicts';
import {conflictPayload,refreshConflictDrafts,resolveConflict,type ConflictGroup} from './syncConflictModel';
import {capabilitiesFor,canEditNote,type Session} from './auth';
const body={schema_version:6 as const,nodes:[{id:'p',type:'entry' as const,key:'节奏',show_key:true,value:'网站上下文'}]};
const group:ConflictGroup={note_id:'n',title:'节奏笔记',revision:'g1',note_revision:'r1',request_ids:['q'],current:{variant_id:'site',body},variants:[{variant_id:'v1',body},{variant_id:'v2',body}],conflicts:[{id:'c',path:'body/nodes/p/value',reason:'text',base:'共同原文',current:'网站当前文',incoming:'另一端文',variant_id:'v1',variants:[{variant_id:'v1',value:'另一端文'},{variant_id:'v2',value:'第三版'}]}]};
it('keeps stale drafts visible after a third version changes conflict identity',()=>{
 const newer={...group,conflicts:[{...group.conflicts[0],id:'new-id',path:'body/nodes/p'}]};
 const html=renderToStaticMarkup(<RetainedDrafts group={newer} drafts={refreshConflictDrafts({c:{action:'manual',text:'不能丢的旧稿'}})}/>);
 expect(html).toContain('不能丢的旧稿');expect(html).toContain('冲突范围已变化');
});
it('shows alias values as names instead of unnamed paragraph ids',()=>{
 const g={...group,conflicts:[{...group.conflicts[0],path:'metadata/aliases',base:[],current:['site-alias'],incoming:['local-alias'],variants:[{variant_id:'v1',value:['local-alias']}]}]};
 const html=renderToStaticMarkup(<ConflictEditor group={g} drafts={{}} onChange={()=>{}}/>);
 expect(html).toContain('site-alias');expect(html).toContain('local-alias');expect(html).not.toContain('未命名段落');
});
it('shows three versions, multiple candidates and a retained manual merge',()=>{
 const html=renderToStaticMarkup(<ConflictEditor group={group} drafts={{c:{action:'manual',text:'我的合并稿',variant_id:'v2'}}} onChange={()=>{}}/>);
 for(const text of ['共同原文','网站当前版','另一端版本','第三版','我的合并稿','手工合并'])expect(html).toContain(text);
 expect(conflictPayload(group,{c:{action:'manual',text:'我的合并稿'}})).toEqual({revision:'g1',note_revision:'r1',choices:[{conflict_id:'c',action:'manual',text:'我的合并稿'}]});
 expect(()=>conflictPayload(group,{c:{action:'incoming'}})).toThrow();
 expect(conflictPayload(group,{c:{action:'incoming',variant_id:'v2'}}).choices[0]).toMatchObject({variant_id:'v2'});
});
it('retains text but requires reviewing choices when a 409 brings another version',async()=>{
 const drafts={c:{action:'manual' as const,text:'不能丢的稿'}};
 const next={...group,revision:'g2'};
 const request=vi.fn().mockRejectedValueOnce(Object.assign(new Error('更新'),{status:409})).mockResolvedValueOnce(next);
 const result=await resolveConflict(group,drafts,request);
 expect(result).toMatchObject({stale:true,group:next});
 expect(refreshConflictDrafts(drafts)).toEqual({c:{text:'不能丢的稿'}});
 expect(request.mock.calls[1][0]).toBe('sync-conflicts/n');
});
it('renders deletion, node order and readable associated context without JSON editing',()=>{
 const g={...group,conflicts:[{...group.conflicts[0],id:'order',path:'body/nodes/order',base:['p'],current:['p'],incoming:[],variants:[{variant_id:'v1',value:[]}]},{...group.conflicts[0],id:'meta',path:'metadata/records',base:null,current:'关联信息发生变化',incoming:null,variants:[{variant_id:'v1',value:null}]}]};
 const html=renderToStaticMarkup(<ConflictEditor group={g} drafts={{}} onChange={()=>{}}/>);
 expect(html).toContain('节奏');expect(html).toContain('已删除');expect(html).toContain('关联信息');expect(html).toContain('网站上下文');expect(html).not.toContain('<textarea');expect(html).not.toContain('metadata/records');expect(html).not.toContain('schema_version');
 expect(()=>conflictPayload(g,{order:{action:'manual',text:'x'},meta:{action:'current'}})).toThrow();
});
it('only locks the conflicted note and leaves annotator proposals available',()=>{
 const session:Session={mode:'public',role:'admin',username:'a',base_path:'/',sync:{state:'pending-deploy',conflict_note_ids:['n'],conflict_count:1}};
 expect(capabilitiesFor(session).editNotes).toBe(true);expect(canEditNote(session,'n')).toBe(false);expect(canEditNote(session,'other')).toBe(true);
 expect(capabilitiesFor({...session,role:'annotator'}).proposeNotes).toBe(true);
 expect(canEditNote({...session,role:'guest'},'other')).toBe(false);
 expect(capabilitiesFor({...session,sync:{state:'conflict'}}).editNotes).toBe(false);
});
import {AuthContext} from './auth';
import SyncConflicts from './SyncConflicts';
import NoteHeading from './NoteHeading';
import {ReviewProvider,NodeActions} from './NoteReview';
import type {Note} from './types';
it.each(['admin','annotator','guest'] as const)('only admin has sync conflict access, with note-specific edit actions for %s',role=>{
 const session:Session={mode:'public',role,username:'a',base_path:'/',sync:{state:'pending',conflict_note_ids:['n']}};
 const note={id:'n',title:'笔记',revision:'r',type:'other',document:body} as Note;
 const html=renderToStaticMarkup(<AuthContext.Provider value={{session,refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><SyncConflicts onResolved={()=>{}}/><NoteHeading note={note} name={x=>x} dirty={false} editing={false} onEdit={()=>{}} onPlayer={()=>{}} onExport={()=>{}}/><ReviewProvider note={note} onSaved={()=>{}} onDirty={()=>{}}><NodeActions node={body.nodes[0]}/></ReviewProvider></AuthContext.Provider>);
 expect(html.includes('同步冲突')).toBe(role==='admin');expect(html).not.toContain('编辑笔记');
 if(role==='admin')expect(html).toMatch(/disabled=""[^>]*aria-label="编辑段落/);
 if(role==='annotator')expect(html).not.toContain('disabled=""');
});
