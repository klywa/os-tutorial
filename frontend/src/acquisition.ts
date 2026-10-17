import type {Source,Progress} from './types';
export type SourceFilters=Partial<Record<'query'|'keyword'|'author'|'batch'|'stage'|'deposit'|'date_from'|'date_to'|'min_views'|'max_views'|'min_duration'|'max_duration'|'collected_from'|'collected_to',string>>;
export function sourceMatches(s:Source,f:SourceFilters){
  if(f.query&&![s.title,s.author,s.notes,s.url,...s.keywords??[]].join(' ').toLowerCase().includes(f.query.toLowerCase()))return false;
  if(f.keyword&&!s.keywords?.includes(f.keyword))return false;
  if(f.author&&s.author!==f.author)return false;
  if(f.batch&&!s.batches?.includes(f.batch))return false;
  if(f.stage&&(f.stage==='ready'?!['ready','no_speech'].includes(s.transcript_status??''):![s.stage,s.acquisition_state].includes(f.stage)))return false;
  if(f.deposit&&s.knowledge_status!==f.deposit)return false;
  for(const [from,to,value] of [['date_from','date_to',s.published],['collected_from','collected_to',s.collected_at?.slice(0,10)]] as const){
    if(f[from]&&(!value||value<f[from]!))return false;
    if(f[to]&&(!value||value>f[to]!))return false;
  }
  for(const [lo,hi,value] of [['min_views','max_views',s.view_count],['min_duration','max_duration',s.duration]] as const){
    if(f[lo]&&(value==null||value<Number(f[lo])))return false;
    if(f[hi]&&(value==null||value>Number(f[hi])))return false;
  }
  return true;
}
export function visibleSelection(selected:string[],rows:Source[]){return [...new Set([...selected,...rows.map(s=>s.id)])];}
export const taskNames:Record<string,string>={retry_wait:'排队中',paused:'已停止，可继续',exporting:'整理文字稿',frames:'提取关键帧',pending:'等待采集',scanning:'采集中',scanned:'采集结束',stopped:'已停止派发',deleted:'已删除',cancelled:'已取消',failed:'失败',preview:'待选择',queued:'排队中',running:'处理中',succeeded:'文字稿已生成',registered:'待整理',downloading:'下载中',transcribing:'转写中',prepared:'待核对',complete:'处理完成',ready:'文字稿已生成'};
export function progressLabel(p:Progress){
  const base=taskNames[p.phase??'']??p.phase??'处理中';
  const [value,total]=p.phase==='downloading'?[p.downloaded_bytes,p.total_bytes]:[p.processed_seconds,p.total_seconds];
  return value!=null&&total&&total>0?`${base} ${Math.min(100,Math.round(value/total*100))}%`:base;
}
