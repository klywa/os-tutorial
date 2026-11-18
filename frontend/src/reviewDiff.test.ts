import {afterEach,expect,it,vi} from 'vitest';
import {calculateReviewDiff,initialDiff,needsDiffWorker} from './reviewDiff';

afterEach(()=>vi.unstubAllGlobals());

it('keeps small diffs synchronous and never computes an expensive initial diff',()=>{
 expect(needsDiffWorker('甲','乙')).toBe(false);
 expect(initialDiff('甲','乙')).toEqual([{kind:'remove',text:'甲'},{kind:'add',text:'乙'}]);
 const long='新'.repeat(2200);
 const prefix='前文'.repeat(1100);
 expect(initialDiff(prefix+'删除',prefix+'保留')).toEqual([
  {kind:'same',text:prefix},{kind:'remove',text:'删除'},{kind:'add',text:'保留'},
 ]);
 expect(initialDiff(long,long)).toEqual([{kind:'same',text:long}]);
});

it('discards a stale worker result while delivering the next request',()=>{
 let worker:FakeWorker;
 class FakeWorker {
  ids:number[]=[];
  onmessage?:(event:{data:{id:number;parts:{kind:'add';text:string}[]}})=>void;
  constructor(){worker=this;}
  postMessage(data:{id:number}){this.ids.push(data.id);}
  reply(index:number,text:string){this.onmessage?.({data:{id:this.ids[index],parts:[{kind:'add',text}]}});}
 }
 vi.stubGlobal('Worker',FakeWorker);
 const receive=vi.fn(),before='旧'.repeat(5000);
 const cancel=calculateReviewDiff(before,'草稿一',receive);
 cancel();
 calculateReviewDiff(before,'草稿二',receive);
 worker!.reply(0,'草稿一');
 worker!.reply(1,'草稿二');
 expect(receive).toHaveBeenCalledExactlyOnceWith([{kind:'add',text:'草稿二'}]);
});
