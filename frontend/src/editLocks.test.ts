import {expect,it,vi,afterEach} from 'vitest';
import {resourceKey,leaseRef,type Lease} from './editLocks';
import {api} from './model';

afterEach(()=>vi.unstubAllGlobals());
it('keeps insertion positions distinct even when canonical IDs contain separators',()=>{
 expect(resourceKey({kind:'slot',section_id:'a:b',left_id:'c'})).not.toBe(resourceKey({kind:'slot',section_id:'a',left_id:'b:c'}));
 expect(resourceKey({kind:'entry',id:'a'})).not.toBe(resourceKey({kind:'slot',section_id:'a',left_id:'a'}));
});
it('sends only fencing credentials rather than baselines or private presence',()=>{
 expect(leaseRef({id:'one',token:'secret',baseline:{node:{value:'draft'}}} as Lease)).toEqual({id:'one',token:'secret'});
});
it('lease heartbeats do not trigger authentication polling and retain revocation reasons',async()=>{
 const events=new EventTarget();let refreshes=0;events.addEventListener('wxq:sync-changed',()=>refreshes++);
 vi.stubGlobal('window',events);vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:200})));
 await api('edit-locks/renew','POST',{});expect(refreshes).toBe(0);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:'已接管',reason:'admin_takeover',resource:{kind:'entry',id:'a'}}),{status:423})));
 await expect(api('edit-locks/acquire','POST',{})).rejects.toMatchObject({status:423,reason:'admin_takeover',resource:{kind:'entry',id:'a'}});
});
