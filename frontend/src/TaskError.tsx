import {taskError} from './errorSummary';
import RetryStatus from './RetryStatus';
import type {RiskRetry,TaskErrorInfo} from './types';
export default function TaskError({error,retry,detail}:{error?:string;retry?:RiskRetry|null;detail?:TaskErrorInfo|null}){
 if(!error&&!retry)return null;
 const reason=error||retry?.error||'';
 const info=taskError(reason,detail);
 return <div className={'task-error'+(retry?' retry-wait':'')} role="status">
  <strong>{info.summary}</strong>
  {retry?<RetryStatus retry={retry}/>:<p>{info.hint}</p>}
  {['risk','login'].includes(info.category)&&<button className="link-button" onClick={()=>{const el=document.querySelector<HTMLDetailsElement>('.connection-settings');if(el){el.open=true;el.scrollIntoView({block:'center',behavior:'smooth'});}}}>打开B站连接设置</button>}
  {reason&&<details><summary>技术详情</summary><pre>{reason}</pre></details>}
 </div>;
}

