import {describe,it,expect,vi,afterEach} from 'vitest';
import {api} from './model';
import {renderToStaticMarkup} from 'react-dom/server';
import {AuthContext,AuthProvider,capabilitiesFor} from './auth';
import NoteHeading from './NoteHeading';
import {appUrl} from './urls';
describe('public access',()=>{
 it('limits guests and administrators to authorized capabilities',()=>{
  expect(capabilitiesFor({mode:'public',role:'guest',username:null,base_path:'/os-tutorial'})).toMatchObject({editNotes:false,reviews:false,localTools:false,manageMatches:false});
  expect(capabilitiesFor({mode:'public',role:'admin',username:'admin',base_path:'/os-tutorial'})).toMatchObject({editNotes:true,reviews:false,localTools:false,manageMatches:true});
 });
 it('hides guest editing while preserving copy and export',()=>{
  const html=renderToStaticMarkup(<AuthContext.Provider value={{session:{mode:'public',role:'guest',username:null,base_path:'/os-tutorial'},refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><NoteHeading note={{id:'one',type:'other',title:'公开笔记',meta:null} as any} reading={{markdown:'正文',document:{nodes:[]}} as any} name={s=>s} dirty={false} editing={false} onEdit={()=>{}} onPlayer={()=>{}} onExport={()=>{}}/></AuthContext.Provider>);
  expect(html).not.toContain('编辑笔记');expect(html).toContain('复制整篇');expect(html).toContain('导出整篇');
 });
 it('waits for an authenticated mode before mounting application children',()=>{
  let mounted=false;function Child(){mounted=true;return <div>application</div>;}
  const html=renderToStaticMarkup(<AuthProvider><Child/></AuthProvider>);
  expect(mounted).toBe(false);expect(html).toContain('正在确认访问权限');
 });
 it('prefixes local URLs and preserves remote URLs',()=>{
  expect(appUrl('/api/notes','/os-tutorial/')).toBe('/os-tutorial/api/notes');
  expect(appUrl('/os-tutorial/api/notes','/os-tutorial/')).toBe('/os-tutorial/api/notes');
  expect(appUrl('https://example.com/image.png','/os-tutorial/')).toBe('https://example.com/image.png');
 });
});

afterEach(()=>vi.unstubAllGlobals());
it.each(['pending','conflict','pending-deploy'])('pauses admin writes during %s while keeping local mode editable',state=>{
 const session={mode:'public' as const,role:'admin' as const,username:'admin',base_path:'/os-tutorial',sync:{state,message:'等待同步'}};
 expect(capabilitiesFor(session)).toMatchObject({editNotes:false,manageMatches:false});
 expect(capabilitiesFor({...session,mode:'local'})).toMatchObject({editNotes:true,manageMatches:true});
});
it('announces successful mutations so authentication can refresh sync status immediately',async()=>{
 const events=new EventTarget();let changes=0;events.addEventListener('wxq:sync-changed',()=>changes++);
 vi.stubGlobal('window',events);vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:200})));
 await api('notes/n','PUT',{document:{}});expect(changes).toBe(1);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:200})));
 await api('notes/n');expect(changes).toBe(1);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"error":"blocked"}',{status:423})));
 await expect(api('notes/n','PUT',{})).rejects.toThrow('blocked');expect(changes).toBe(1);
});
