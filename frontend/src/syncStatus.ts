export type SyncStatus={state:string;phase?:string;message?:string;job_id?:string;updated_at?:string;next_retry_at?:number|null};
export function syncLabel(sync:SyncStatus){
 if(sync.state==='synced')return '已同步';
 if(sync.state==='pending-deploy')return '已同步，等待发布新版本';
 if(sync.state==='conflict')return '正文已保存，同步需要管理员处理';
 const labels:Record<string,string>={queued:'正文已保存，等待同步',validating:'正在校验',committing:'正在保存同步版本',fetching:'正在检查远端',merging:'正在合并远端',pushing:'正在推送','waiting-retry':'同步失败，正文已保存，等待重试'};
 return labels[sync.phase??'']??sync.message??'正文已保存，等待同步';
}
export function syncPollMs(session:{mode:string;role:string;sync?:SyncStatus}|null){return session?.mode==='public'&&session.role!=='guest'&&session.sync?.state==='pending'?2000:60000;}
