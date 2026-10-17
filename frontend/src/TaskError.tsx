import {taskError} from './errorSummary';
import RetryStatus from './RetryStatus';
import type {RiskRetry} from './types';
export default function TaskError({error,retry}:{error?:string;retry?:RiskRetry|null}){if(!error||retry)return null;const info=taskError(error);return <div className="task-error" role="status"><strong>{retry?'正在自动处理B站风控':info.summary}</strong>{retry?<RetryStatus retry={retry}/>:<p>{info.hint}</p>}{['risk','login'].includes(info.category)&&<button className="link-button" onClick={()=>{const el=document.querySelector<HTMLDetailsElement>('.connection-settings');if(el){el.open=true;el.scrollIntoView({block:'center',behavior:'smooth'});}}}>打开B站连接设置</button>}<details><summary>技术详情</summary><pre>{error}</pre></details></div>;}

