import {expect,it} from 'vitest';
import {creatorUID,newCreator,creatorMatches,creatorJobs,creatorStatus} from './creators';
import type {CrawlJob} from './types';
it('keeps UID strings and resets add drafts',()=>{
 expect(creatorUID('https://space.bilibili.com/3632302133348552')).toBe('3632302133348552');
 expect(newCreator({uid:'123',date_from:'2020-01-01',enabled:false}).uid).toBeUndefined();
 expect(newCreator().keywords).not.toBe(newCreator().keywords);
 expect(newCreator({enabled:false}).enabled).toBe(true);
});
it('filters listener history including deleted listeners',()=>{
 expect(creatorMatches({...newCreator(),uid:'123',name:'测试'},'123')).toBe(true);
 const jobs=[{id:'a',creator:'123'},{id:'b',creator:'deleted'},{id:'c'}] as CrawlJob[];
 expect(creatorJobs(jobs,'creators','').map(j=>j.id)).toEqual(['a','b']);
 expect(creatorJobs(jobs,'creators','123').map(j=>j.id)).toEqual(['a']);
 expect(creatorJobs(jobs,'search','').map(j=>j.id)).toEqual(['c']);
});
it('shows durable listener states and starts independent tag drafts',()=>{
 expect(newCreator().tags).toEqual([]);
 expect(creatorStatus({...newCreator(),monitor_state:'paused'})).toBe('已暂停');
 expect(creatorStatus({...newCreator(),monitor_state:'waiting'})).toBe('等待下次检查');
 expect(creatorStatus({...newCreator(),monitor_state:'disabled'})).toBe('已停用');
});
