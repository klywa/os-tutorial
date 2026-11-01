import {expect,it,vi,afterEach} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {AuthContext} from './auth';
import {AccountControls} from './Proposals';
import {syncLabel,syncPollMs} from './syncStatus';
import {api} from './model';

afterEach(()=>vi.unstubAllGlobals());
it('polls pending jobs quickly and completed/local sessions infrequently',()=>{
 expect(syncPollMs({mode:'public',role:'admin',sync:{state:'pending'}})).toBe(2000);
 expect(syncPollMs({mode:'public',role:'admin',sync:{state:'synced'}})).toBe(60000);
 expect(syncPollMs({mode:'local',role:'admin',sync:{state:'pending'}})).toBe(60000);
});
it('uses actual phases and never implies an approved write was rolled back',()=>{
 expect(syncLabel({state:'pending',phase:'validating'})).toContain('校验');
 expect(syncLabel({state:'pending',phase:'pushing'})).toContain('推送');
 expect(syncLabel({state:'pending',phase:'waiting-retry'})).toContain('已保存');
 expect(syncLabel({state:'synced'})).toContain('已同步');
});
it('shows administrator retry action without exposing it to annotators',()=>{
 const session={mode:'public' as const,role:'admin' as const,username:'a',base_path:'/',sync:{state:'pending',phase:'waiting-retry'}};
 const html=(role:'admin'|'annotator')=>renderToStaticMarkup(<AuthContext.Provider value={{session:{...session,role},refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><AccountControls beforeChange={()=>true}/></AuthContext.Provider>);
 expect(html('admin')).toContain('重试同步');expect(html('annotator')).not.toContain('重试同步');
});
it('write responses deliver immediate persisted sync status to the account UI',async()=>{
 const dispatchEvent=vi.fn();vi.stubGlobal('window',{dispatchEvent});
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({status:'approved',sync:{state:'pending',phase:'queued'}}),{status:200})));
 await api('proposals/one/approve','POST',{revision:1});
 expect(dispatchEvent.mock.calls[0][0].detail).toMatchObject({state:'pending',phase:'queued'});
});
