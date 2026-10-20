import {expect,it} from 'vitest';
import {SourceSaveQueue,normalizeTags} from './annotationSaving';
import type {Source} from './types';
const source={id:'one',revision:'r0',tags:[],notes:''} as unknown as Source;
it('normalizes custom tags without splitting names or case folding',()=>{
 expect(normalizeTags([' 教学 ','','教学','A B','a b'])).toEqual(['教学','A B','a b']);
});
it('serializes one row with the last locally accepted revision while other rows stay independent',async()=>{
 let release!:()=>void;const wait=new Promise<void>(r=>release=r);const calls:{id:string;revision:unknown}[]=[];
 const queue=new SourceSaveQueue(async(s,changes,revision)=>{
  calls.push({id:s.id,revision});if(calls.length===1)await wait;
  return {...s,...changes,revision:s.id==='one'?(revision==='r0'?'r1':'r2'):'other1'};
 },()=>{});
 const first=queue.save(source,{tags:['教学']});const second=queue.save(source,{notes:'备注'});
 await queue.save({...source,id:'two'},{notes:'另一条'});
 expect(calls.map(c=>c.id)).toEqual(['one','two']);release();await first;await second;
 expect(calls.at(-1)).toEqual({id:'one',revision:'r1'});
});
it('does not silently retry a conflict or replace an external revision',async()=>{
 let count=0;const revisions:string[]=[];
 const queue=new SourceSaveQueue(async(s,c,r)=>{count++;revisions.push(r);if(count===1)throw Error('资料已修改');return {...s,...c,revision:'accepted'};},()=>{});
 await expect(queue.save(source,{tags:['草稿']})).rejects.toThrow('资料已修改');expect(count).toBe(1);
 await queue.save({...source,revision:'external'},{notes:'重新核对'});expect(revisions).toEqual(['r0','external']);
});
