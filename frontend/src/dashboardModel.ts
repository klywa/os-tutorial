import {apiUrl} from './urls';
export type CoverageCell={covered:boolean;section:string|null;node_id:string|null};
export type CoverageScope='all'|'usage_top10'|'usage_top20'|'usage_top50';
export type UsageStatus={ready:boolean;state:string;stale?:boolean;error?:string;last_success?:string|null;next_check?:string;scope?:{version:string;time?:number;minimumCount?:number}|null;ambiguous?:number;missing?:number;selected_count?:number};
export type CoverageNote={id:string;title:string;covered:number;rate:number|null;fields:Record<string,CoverageCell>;note_id?:string;rank?:number;usage?:number;player_name?:string;source_name?:string;local_name?:string;hero_names?:string[];games?:number;match_status?:'matched'|'missing_note'|'ambiguous';candidates?:string[];manual_note_id?:string;manual_status?:'valid'|'invalid';manual_error?:string;match_basis?:string};
export type DashboardData={revision:string;generated_at:string;scope?:CoverageScope;usage?:UsageStatus;counts:{player:number;lineup:number};summary:{covered:number;total:number;rate:number|null};fields:{id:string;label:string;covered:number;total:number;rate:number|null}[];notes:CoverageNote[]};
export type CoverageOrder='asc'|'desc'|'usage';
export function formatRate(rate:number|null){return rate===null?'—':(rate*100).toFixed(1)+'%';}
export function sortNotes(notes:CoverageNote[],order:CoverageOrder){
 return [...notes].sort((a,b)=>(order==='usage'?(a.rank??Infinity)-(b.rank??Infinity):Number(a.rate===null)-Number(b.rate===null)||(order==='asc'?a.covered-b.covered:b.covered-a.covered))||a.title.localeCompare(b.title,'zh-CN')||a.id.localeCompare(b.id));
}

type PollingCallbacks={read:(signal:AbortSignal)=>Promise<DashboardData>;onData:(data:DashboardData)=>void;onError:(error:string)=>void;onBusy:(busy:boolean)=>void};
type PollingEnvironment={page:EventTarget;doc:EventTarget;isVisible:()=>boolean};
/** One in-flight request, one coalesced refresh, no hidden-page polling. */
export function startDashboardPolling(callbacks:PollingCallbacks,env:PollingEnvironment={page:window,doc:document,isVisible:()=>!document.hidden}){
 let stopped=false,inflight=false,queued=false,timer:ReturnType<typeof setInterval>|undefined;
 let controller:AbortController|undefined;
 async function refresh(){
  if(stopped)return;
  if(inflight){queued=true;return;}
  inflight=true;controller=new AbortController();callbacks.onBusy(true);
  try{const data=await callbacks.read(controller.signal);if(!stopped){callbacks.onData(data);callbacks.onError('');}}
  catch(e){if(!stopped)callbacks.onError(e instanceof Error?e.message:String(e));}
  finally{inflight=false;if(!stopped){callbacks.onBusy(false);if(queued&&env.isVisible()){queued=false;void refresh();}else queued=false;}}
 }
 function visibleRefresh(){if(env.isVisible())void refresh();}
 function visibility(){
  if(timer!==undefined){clearInterval(timer);timer=undefined;}
  if(env.isVisible()){visibleRefresh();timer=setInterval(visibleRefresh,3000);}
 }
 env.page.addEventListener('focus',visibleRefresh);
 env.page.addEventListener('wxq:knowledge-saved',visibleRefresh);
 env.doc.addEventListener('visibilitychange',visibility);
 visibility();
 return {refresh,stop:()=>{stopped=true;controller?.abort();if(timer!==undefined)clearInterval(timer);env.page.removeEventListener('focus',visibleRefresh);env.page.removeEventListener('wxq:knowledge-saved',visibleRefresh);env.doc.removeEventListener('visibilitychange',visibility);}};
}

export async function readDashboard(signal:AbortSignal,scope:CoverageScope='all'):Promise<DashboardData>{
 const response=await fetch(apiUrl('dashboard?scope='+scope),{signal,cache:'no-store'});
 const value=await response.json();
 if(!response.ok)throw new Error(value.error||'无法读取看板，请重试');
 return value;
}
