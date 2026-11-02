import type {RiskRetry} from './types';
export default function RetryStatus({retry,compact=false}:{retry?:RiskRetry|null;compact?:boolean}){
 if(!retry)return null;
 const time=new Date(retry.next_retry_at);
 const next=Number.isNaN(time.getTime())?'等待安排':time.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
 const reasons:Record<string,string>={busy:'资料暂时占用',network:'网络或下载中断',extractor:'页面解析暂时失败',formats:'音频格式暂不可用',crash:'工作进程异常退出',risk:'B站访问冷却'};
 return <small className={'retry-status muted'+(compact?' compact':'')} role="status">等待自动重试 · 第 {retry.attempt} 次 · 下次 {next}（北京时间）{retry.category&&reasons[retry.category]?' · '+reasons[retry.category]:''}</small>;
}
