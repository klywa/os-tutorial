import {useEffect,useRef,useState} from 'react';
import {api} from './model';
type State={enabled:boolean;state:string;last_check?:string;last_success?:string;next_check?:string;error?:string;requested?:boolean;report?:{changed_ids:string[];updated_notes:number}};
const time=(s?:string)=>s?new Date(s).toLocaleString('zh-CN'):'尚无记录';
export default function OfficialSync({onUpdated}:{onUpdated?:()=>void}={}){
  const [state,setState]=useState<State|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const lastSuccess=useRef<string|undefined>(undefined),seenStatus=useRef(false),onUpdate=useRef(onUpdated);onUpdate.current=onUpdated;
  useEffect(()=>{if(state){if(seenStatus.current&&state.last_success&&lastSuccess.current!==state.last_success&&state.report?.changed_ids.length)onUpdate.current?.();lastSuccess.current=state.last_success;seenStatus.current=true;}},[state]);
  useEffect(()=>{let alive=true;const refresh=()=>void api<State>('official-sync/status').then(s=>{if(alive)setState(s);}).catch(e=>{if(alive)setError(e.message);});refresh();const timer=setInterval(refresh,5000);return()=>{alive=false;clearInterval(timer);};},[]);
  async function act(path:string,value:{enabled?:boolean}){const previous=state;if(value.enabled!==undefined)setState(s=>s?{...s,enabled:value.enabled!}:s);setBusy(true);setError('');try{setState(await api<State>('official-sync/'+path,'POST',value));}catch(e){setState(previous);setError((e as Error).message);}finally{setBusy(false);}}
  return <details className="official-sync schedule-config"><summary>官网资料同步{state?.state==='running'?' · 检查中':state?.state==='failed'?' · 检查失败':''}</summary>
    <label><input type="checkbox" checked={state?.enabled??true} disabled={busy||!state} onChange={e=>void act('settings',{enabled:e.target.checked})}/>每日自动检查官网</label>
    <p className="muted">覆盖全部卡牌和棋手技能；沿用爬取的北京时间设置。本地服务启动后补检一次。</p>
    <p>最近检查：{time(state?.last_check)}<br/>最近成功：{time(state?.last_success)}<br/>下次检查：{state?.enabled?time(state.next_check):'已暂停'}</p>
    <p className="muted">检查只更新本地官网资料，正式笔记需明确修改后保存。</p>
    {!!state?.report?.changed_ids.length&&<p>最近更新 {state.report.changed_ids.length} 项官网资料。</p>}
    {(error||state?.error)&&<p className="error" role="alert">{error||state?.error}</p>}
    <button disabled={busy||state?.state==='running'||state?.requested} onClick={()=>void act(state?.state==='failed'?'retry':'run',{})}>{state?.requested?'已安排检查':state?.state==='failed'?'重试':'立即检查'}</button>
  </details>;
}
