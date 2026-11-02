import {expect,it,vi} from 'vitest';
import {createCrawlerListRefresh} from './crawlerLists';
import type {Creator,CrawlJob} from './types';

const creators:Creator[]=[{uid:'17214680',name:'奇妙',url:'https://space.bilibili.com/17214680',date_from:'2026-10-01',keywords:[],enabled:true}];
const jobs=[{id:'job1'}] as CrawlJob[];
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

it('任务读取未完成时，已经取得的UP主立即显示',async()=>{
 let finish!:(jobs:CrawlJob[])=>void;
 const onCreators=vi.fn(),onJobs=vi.fn();
 const refresh=createCrawlerListRefresh({fetchJobs:()=>new Promise(resolve=>{finish=resolve;}),fetchCreators:async()=>creators,onCreators,onJobs,onCreatorsError:vi.fn(),onJobsError:vi.fn()});
 const pending=refresh();await tick();
 expect(onCreators).toHaveBeenCalledWith(creators);expect(onJobs).not.toHaveBeenCalled();
 finish(jobs);await pending;expect(onJobs).toHaveBeenCalledWith(jobs);
});

it('慢任务请求不堆积，也不阻止继续刷新UP主',async()=>{
 let finish!:(jobs:CrawlJob[])=>void;
 const fetchJobs=vi.fn(()=>new Promise<CrawlJob[]>(resolve=>{finish=resolve;}));
 const fetchCreators=vi.fn(async()=>creators);
 const refresh=createCrawlerListRefresh({fetchJobs,fetchCreators,onCreators:vi.fn(),onJobs:vi.fn(),onCreatorsError:vi.fn(),onJobsError:vi.fn()});
 const a=refresh(),b=refresh();await tick();
 expect(fetchJobs).toHaveBeenCalledTimes(1);expect(fetchCreators).toHaveBeenCalledTimes(1);
 const c=refresh();await tick();expect(fetchJobs).toHaveBeenCalledTimes(1);expect(fetchCreators).toHaveBeenCalledTimes(2);
 finish(jobs);await Promise.all([a,b,c]);
});

it('任务读取失败不影响UP主，UP主读取失败也不会清空已加载列表',async()=>{
 let visible:Creator[]=[];const onCreatorsError=vi.fn(),onJobsError=vi.fn();
 const fetchCreators=vi.fn().mockResolvedValueOnce(creators).mockRejectedValueOnce(new Error('断网'));
 const refresh=createCrawlerListRefresh({fetchJobs:async()=>{throw new Error('任务列表超时');},fetchCreators,onCreators:value=>{visible=value;},onJobs:vi.fn(),onCreatorsError,onJobsError});
 await refresh();expect(visible).toEqual(creators);expect(onJobsError).toHaveBeenCalled();
 await refresh();expect(visible).toEqual(creators);expect(onCreatorsError).toHaveBeenCalled();
});
