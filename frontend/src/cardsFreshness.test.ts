import {afterEach,expect,it,vi} from 'vitest';
import {sessionFetch} from './sessionRequest';
afterEach(()=>vi.unstubAllGlobals());
it('notifies readers to refresh when the requested card snapshot expired',async()=>{
 const dispatchEvent=vi.fn();vi.stubGlobal('window',{dispatchEvent});
 vi.stubGlobal('fetch',async()=>new Response(JSON.stringify({reason:'cards_version_changed'}),{status:409}));
 const response=await sessionFetch('/api/cards/hero?version=old');await response.json();
 expect(dispatchEvent).toHaveBeenCalledOnce();expect(dispatchEvent.mock.calls[0][0].type).toBe('cards-version-changed');
});
it('does not refresh cards for unrelated conflicts',async()=>{
 const dispatchEvent=vi.fn();vi.stubGlobal('window',{dispatchEvent});
 vi.stubGlobal('fetch',async()=>new Response(JSON.stringify({reason:'edit_locked'}),{status:409}));
 await (await sessionFetch('/api/notes/n')).json();expect(dispatchEvent).not.toHaveBeenCalled();
});
