import {afterEach,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {AuthContext,SessionGate,capabilitiesFor,type Session} from './auth';
import {cachedEntry,cachedGet,configureReaderCache,putCached} from './readerCache';
import {sessionFetch,resetSessionRequests} from './sessionRequest';
import {AccountControls} from './Proposals';
import {api} from './model';
import {getCard} from './EntityCards';
const session:Session={mode:'public',role:'viewer',username:'reader',base_path:'/os-tutorial'};
afterEach(async()=>{await configureReaderCache('local','local');vi.unstubAllGlobals();});
it('mounts only the login screen for a public guest',()=>{
 const guest={...session,role:'guest' as const,username:null};let mounted=false;
 function Child(){mounted=true;return <div>secret</div>;}
 const html=renderToStaticMarkup(<AuthContext.Provider value={{session:guest,refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><SessionGate session={guest}><Child/></SessionGate></AuthContext.Provider>);
 expect(mounted).toBe(false);expect(html).toContain('账号登录');expect(html).not.toContain('secret');
});
it('gives viewers read-only controls without proposals',()=>{
 expect(capabilitiesFor(session)).toMatchObject({editNotes:false,inlineEdit:false,proposeNotes:false,localTools:false,manageMatches:false});
 const html=renderToStaticMarkup(<AuthContext.Provider value={{session,refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><AccountControls beforeChange={()=>true}/></AuthContext.Provider>);
 expect(html).toContain('浏览者');expect(html).not.toContain('>提案<');expect(html).toContain('退出登录');
});
it('uses memory only for public content and clears on identity changes',async()=>{
 const open=vi.fn();vi.stubGlobal('indexedDB',{open});
 // Cleanup may open the old database, but later reads/writes must never use it.
 await configureReaderCache('public','reader');open.mockClear();
 await putCached('resource',{text:'private'},'w');expect(await cachedEntry('resource','w')).not.toBeNull();
 expect(open).not.toHaveBeenCalled();
 await configureReaderCache('public',null);expect(await cachedEntry('resource','w')).toBeNull();
});
it('discards a successful response arriving after logout',async()=>{
 await configureReaderCache('public','reader');
 let finish!:(response:Response)=>void;
 vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(resolve=>{finish=resolve;})));
 const pending=cachedGet('resource',{workspace:'w'});await vi.waitFor(()=>expect(finish).toBeDefined());
 await configureReaderCache('public',null);finish(new Response('{"private":true}'));
 await expect(pending).rejects.toThrow();expect(await cachedEntry('resource','w')).toBeNull();
});
it('announces unauthorized reads and ignores stale unauthorized responses',async()=>{
 const events=new EventTarget();let expired=0;events.addEventListener('wxq:session-expired',()=>expired++);vi.stubGlobal('window',events);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:401})));
 await sessionFetch('/api/notes');expect(expired).toBe(1);
 let finish!:(response:Response)=>void;vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(r=>{finish=r;})));
 const pending=sessionFetch('/api/notes');resetSessionRequests();finish(new Response('{}',{status:401}));
 await expect(pending).rejects.toThrow();expect(expired).toBe(1);
});
it('rejects delayed response bodies before old mutations can emit events or refill caches',async()=>{
 const events=new EventTarget();let changes=0;events.addEventListener('wxq:sync-changed',()=>changes++);vi.stubGlobal('window',events);
 let finish!:(value:unknown)=>void;
 const response=new Response('{}');response.json=()=>new Promise(resolve=>{finish=resolve;});
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response));
 const pending=api('notes/n','PUT',{});await vi.waitFor(()=>expect(finish).toBeDefined());
 resetSessionRequests();finish({id:'old-note',sync:{state:'conflict'}});
 await expect(pending).rejects.toThrow();expect(changes).toBe(0);
});
it('clears the shared card detail cache when the session changes',async()=>{
 const fetcher=vi.fn().mockImplementation(async()=>new Response('{"id":"card"}'));vi.stubGlobal('fetch',fetcher);
 await getCard('card');await getCard('card');expect(fetcher).toHaveBeenCalledTimes(1);
 resetSessionRequests();await getCard('card');expect(fetcher).toHaveBeenCalledTimes(2);
});
