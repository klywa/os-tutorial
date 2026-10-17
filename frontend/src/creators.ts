import type {Creator,CrawlJob} from './types';
export function creatorUID(url:string){try{const u=new URL(url);return u.hostname==='space.bilibili.com'?u.pathname.match(/^\/(\d+)\/?$/)?.[1]:undefined;}catch{return undefined;}}
export function newCreator(seed:Partial<Creator>={}):Creator{return {name:seed.name??'',url:seed.url??'',date_from:'',keywords:[],enabled:true};}
export function creatorMatches(c:Creator,query:string){return `${c.name} ${c.uid}`.toLowerCase().includes(query.trim().toLowerCase());}
export function creatorJobs(jobs:CrawlJob[],tab:string,uid:string){return jobs.filter(j=>tab==='creators'?!!j.creator&&(!uid||j.creator===uid):!j.creator);}
export function creatorStatus(c:Creator){return c.checking?'正在检查':c.retry?'等待检查':c.error?'检查失败':c.last_success?'最近检查成功':'等待首次检查';}
