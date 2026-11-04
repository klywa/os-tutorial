import {afterEach,expect,it,vi} from 'vitest';
import {loadCardCatalog} from './cardCatalog';
import {resetSessionRequests} from './sessionRequest';
afterEach(()=>{resetSessionRequests();vi.unstubAllGlobals();});
it('shares concurrent card reads in the same generation and workspace',async()=>{
 let finish!:(r:Response)=>void;const fetcher=vi.fn(()=>new Promise<Response>(resolve=>{finish=resolve;}));vi.stubGlobal('fetch',fetcher);
 const a=loadCardCatalog('w'),b=loadCardCatalog('w');await vi.waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(1));finish(new Response('[]'));
 expect(await a).toEqual([]);expect(await b).toEqual([]);
});
it('separates workspaces and allows retries after a failure',async()=>{
 const fetcher=vi.fn().mockImplementation(async()=>new Response('[]'));vi.stubGlobal('fetch',fetcher);
 await Promise.all([loadCardCatalog('one'),loadCardCatalog('two')]);expect(fetcher).toHaveBeenCalledTimes(2);
 fetcher.mockRejectedValueOnce(new Error('offline'));await expect(loadCardCatalog('one')).rejects.toThrow('offline');
 expect(await loadCardCatalog('one')).toEqual([]);expect(fetcher).toHaveBeenCalledTimes(4);
});
it('does not reuse an old session request or let its cleanup remove a new request',async()=>{
 const finish:((r:Response)=>void)[]=[];const fetcher=vi.fn(()=>new Promise<Response>(resolve=>finish.push(resolve)));vi.stubGlobal('fetch',fetcher);
 const old=loadCardCatalog('w');const oldResult=expect(old).rejects.toThrow();await vi.waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(1));resetSessionRequests();
 const next=loadCardCatalog('w');await vi.waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(2));finish[0](new Response('[]'));await oldResult;
 const shared=loadCardCatalog('w');finish[1](new Response('[]'));await Promise.all([next,shared]);expect(fetcher).toHaveBeenCalledTimes(2);
});
