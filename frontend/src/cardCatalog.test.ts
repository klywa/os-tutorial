import {afterEach,expect,it,vi} from 'vitest';
import {loadCardCatalog,checkCardVersion,cardPath} from './cardCatalog';
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
it('pins details and catalog reads to the checked version and resets on logout',async()=>{
 const fetcher=vi.fn().mockImplementation(async(input:string)=>new Response(input.includes('status')?JSON.stringify({version:'a'.repeat(64),state:'success'}):'[]'));
 vi.stubGlobal('fetch',fetcher);
 await Promise.all([checkCardVersion(),checkCardVersion()]);
 expect(fetcher).toHaveBeenCalledTimes(1);
 expect(cardPath('hero:1')).toContain('?version='+ 'a'.repeat(64));
 await loadCardCatalog();expect(fetcher.mock.calls[1][0]).toContain('?version='+ 'a'.repeat(64));
 resetSessionRequests();expect(cardPath('hero:1')).toBe('cards/hero%3A1');
});
it('rejects a delayed status response after identity reset',async()=>{
 let finish!:(r:Response)=>void;vi.stubGlobal('fetch',()=>new Promise<Response>(resolve=>{finish=resolve;}));
 const pending=checkCardVersion(),result=expect(pending).rejects.toThrow();resetSessionRequests();
 finish(new Response(JSON.stringify({version:'b'.repeat(64)})));await result;
 expect(cardPath('hero:1')).not.toContain('version');
});
it('rejects an older catalog that finishes after a newer version was selected',async()=>{
 let selected='a'.repeat(64),finish!:(r:Response)=>void;
 vi.stubGlobal('fetch',vi.fn((input:string)=>{
  if(input.includes('status'))return Promise.resolve(new Response(JSON.stringify({version:selected,state:'success'})));
  if(input.includes('a'.repeat(64)))return new Promise<Response>(resolve=>{finish=resolve;});
  return Promise.resolve(new Response('[]'));
 }));
 await checkCardVersion();const old=loadCardCatalog(),rejected=expect(old).rejects.toThrow('卡牌版本已更新');
 await vi.waitFor(()=>expect(finish).toBeTypeOf('function'));
 selected='b'.repeat(64);await checkCardVersion();await loadCardCatalog();
 finish(new Response('[]'));await rejected;
});
