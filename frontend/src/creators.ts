import type {Creator,CrawlJob} from './types';
export function creatorUID(url:string){try{const u=new URL(url);return u.hostname==='space.bilibili.com'?u.pathname.match(/^\/(\d+)\/?$/)?.[1]:undefined;}catch{return undefined;}}
export function newCreator(seed:Partial<Creator>={}):Creator{return {name:seed.name??'',url:seed.url??'',date_from:'',keywords:[],tags:[],enabled:true};}
export function creatorMatches(c:Creator,query:string){return `${c.name} ${c.uid}`.toLowerCase().includes(query.trim().toLowerCase());}
export function creatorJobs(jobs:CrawlJob[],tab:string,uid:string){return jobs.filter(j=>tab==='creators'?!!j.creator&&(!uid||j.creator===uid):tab==='links'?j.config?.kind==='links':!j.creator&&j.config?.kind!=='links');}
export function creatorStatus(c:Pick<Creator,'monitor_state'|'checking'|'retry'|'error'|'last_success'>){return c.monitor_state?({waiting:'等待下次检查',scanning:'拉取中',pending:'等待拉取',paused:'已暂停',retry_wait:'重试等待',disabled:'已停用',failed:'拉取失败'}[c.monitor_state]??c.monitor_state):c.checking?'正在检查':c.retry?'等待检查':c.error?'检查失败':c.last_success?'最近检查成功':'等待首次检查';}
