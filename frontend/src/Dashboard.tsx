import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import UsageMatchDialog from './UsageMatchDialog';
import {formatRate,sortNotes,startDashboardPolling,readDashboard,type DashboardData,type CoverageOrder,type CoverageScope,type UsageStatus} from './dashboardModel';
import './dashboard.css';

type OpenNote=(id:string,nodeId?:string|null,section?:string|null)=>void;
type ViewProps={data:DashboardData|null;error:string;busy:boolean;checkedAt:string;order:CoverageOrder;onOrder:(order:CoverageOrder)=>void;onRefresh:()=>void;onOpen:OpenNote;scope?:CoverageScope;onScope?:(scope:CoverageScope)=>void;usageBusy?:boolean;usageError?:string;onUsageRefresh?:()=>void;onMatch?:(id?:string)=>void};
const timeLabel=(value:string)=>new Date(value).toLocaleTimeString('zh-CN',{hour12:false});
const dateLabel=(value:string)=>new Date(value).toLocaleString('zh-CN',{hour12:false});

export function DashboardView({data,error,busy,checkedAt,order,onOrder,onRefresh,onOpen,scope:requestedScope,onScope,usageBusy=false,usageError='',onUsageRefresh,onMatch}:ViewProps){
 const scope=requestedScope??data?.scope??'all',top=scope!=='all',topLabel='Top-'+scope.replace('usage_top',''),usage=data?.usage;
 const updating=usageBusy||['running','queued'].includes(usage?.state??'');
 const ready=!top||usage?.ready;
 return <main className="dashboard" aria-label="知识看板">
  <header className="dashboard-heading"><div><h1>看板</h1><p>当前仓库的笔记数量与内容覆盖情况</p></div><div className="dashboard-refresh"><span role="status">{busy?'正在更新…':checkedAt?`最近检查 ${timeLabel(checkedAt)}`:''}</span><button onClick={onRefresh} disabled={busy}>刷新看板</button></div></header>
  <div className="dashboard-scope"><div role="group" aria-label="阵容范围">{([['all','全部阵容'],['usage_top10','使用率 Top-10'],['usage_top20','使用率 Top-20'],['usage_top50','使用率 Top-50']] as const).map(([value,label])=><button key={value} aria-pressed={scope===value} className={scope===value?'selected':''} onClick={()=>onScope?.(value)}>{label}</button>)}</div>{top&&<div className="dashboard-scope-actions"><button onClick={()=>onMatch?.()} disabled={!data?.notes.length}>管理匹配</button><button onClick={onUsageRefresh} disabled={updating}>{updating?'正在更新使用率…':'更新使用率'}</button></div>}</div>
  {top&&<section className="dashboard-usage" aria-label="使用率来源与更新状态"><div><strong>{usage?.scope?.version??'最新版本'}</strong><span>万象大赛 · 最近7天 · 每个组合至少50场</span><a href="https://www.datawxq.com/lineups" target="_blank" rel="noreferrer">查看统计来源</a></div><p>每天北京时间09:00更新，服务重新启动后补刷。{usage?.last_success&&` 上次成功：${dateLabel(usage.last_success)}。`}</p>{!usage?.ready&&<p role="status">使用率数据尚未就绪{updating?'，正在获取完整榜单及棋手分布…':'，请更新使用率。'}</p>}{(usageError||usage?.error)&&<p className="dashboard-usage-warning" role="alert">使用率更新失败：{usageError||usage?.error}。{usage?.ready?'保留上次成功榜单。':'请重试。'}</p>}{usage?.stale&&usage.ready&&<p className="dashboard-usage-warning">当前为上次成功数据，榜单尚未更新至本次刷新周期。</p>}</section>}
  {error&&<div className="dashboard-error" role="alert">更新失败：{error}。{data?'以下保留上次成功结果。':'请刷新重试。'}</div>}
  {!data?<p className="empty">{error?'暂时无法读取看板。':'正在汇总笔记…'}</p>:<>
   <dl className="dashboard-totals"><div><dt>棋手笔记</dt><dd>{data.counts.player}<span>篇</span></dd></div><div><dt>阵容笔记</dt><dd>{data.counts.lineup}<span>篇</span></dd></div><div className="dashboard-overall"><dt>{top?`${topLabel} 已确认覆盖率`:'整体覆盖率'}</dt><dd>{ready?formatRate(data.summary.rate):'—'}</dd><small>{ready?`${data.summary.covered} / ${data.summary.total} 项已覆盖`:'等待使用率数据'}</small></div></dl>
   <section className="dashboard-fields" aria-labelledby="dashboard-fields-title"><h2 id="dashboard-fields-title">分项覆盖率</h2><div className="dashboard-field-bars">{data.fields.map(field=><div className="dashboard-field" key={field.id}><div><span>{field.label}</span><strong>{ready?formatRate(field.rate):'—'}</strong></div><div className="dashboard-bar" aria-hidden="true"><span style={{width:`${ready?(field.rate??0)*100:0}%`}}/></div><small>{ready?`${field.covered} / ${field.total} ${top?'个组合':'篇'}`:'等待数据'}</small></div>)}</div></section>
   <section className="dashboard-matrix" aria-labelledby="dashboard-matrix-title"><div className="dashboard-matrix-heading"><h2 id="dashboard-matrix-title">{top?`${topLabel} 阵容＋棋手覆盖明细`:'阵容笔记覆盖明细'}</h2><label>排序<select aria-label="覆盖率排序" value={order} onChange={e=>onOrder(e.target.value as CoverageOrder)}>{top&&<option value="usage">登场率从高到低</option>}<option value="asc">覆盖率从低到高</option><option value="desc">覆盖率从高到低</option></select></label></div>
    <p className="dashboard-rule">每项至少一条实质内容即算覆盖；仅有“待补充”等说明不计。覆盖率反映已有内容，不代表完整程度。克制方法指如何克制本阵容。{top&&' 组合登场率 = 阵容登场率 × 该棋手在阵容内的场次占比。'}{top&&!!usage?.ambiguous&&` ${usage.ambiguous}个组合匹配待确认，暂未计入已确认覆盖。`}</p>
    {!data.notes.length?<p className="empty">{top?(usage?.ready?'当前统计范围内暂无满足50场门槛的组合。':'使用率数据尚未就绪'):'暂无阵容笔记'}</p>:<div className="dashboard-table-scroll" tabIndex={0} role="region" aria-label="阵容笔记七项覆盖矩阵，可横向滚动"><table className={`dashboard-table${top?' dashboard-table-usage':''}`}><caption className="dashboard-sr-only">{order==='usage'?'按组合登场率从高到低排列':`按覆盖率${order==='asc'?'从低到高':'从高到低'}排列`}的阵容笔记</caption><thead><tr><th scope="col" className="dashboard-name">{top?'阵容＋棋手':'阵容笔记'}</th><th scope="col" className="dashboard-rate">覆盖率</th>{data.fields.map(field=><th scope="col" key={field.id}>{field.label}</th>)}</tr></thead><tbody>{sortNotes(data.notes,order).map(note=>{
     const linked=!top||note.match_status==='matched',pending=top&&note.match_status==='ambiguous',noteId=note.note_id??note.id;
     const matchHint=[`点击指定知识库匹配`,note.source_name&&`网站：${note.source_name}`,note.hero_names?.join('、'),pending?`待确认；候选：${note.candidates?.join('、')||'无'}`:!linked?'未建笔记':note.manual_status==='valid'?'手动指定':'自动匹配',note.manual_error].filter(Boolean).join('\n');
     return <tr key={note.id}><th scope="row" className="dashboard-name">{top&&<small className="dashboard-rank">第{note.rank}名　登场率 {formatRate(note.usage??null)}</small>}<button className="dashboard-note-link" title={top?matchHint:undefined} aria-label={top?`指定${note.title}的知识库匹配`:undefined} onClick={()=>top?onMatch?.(note.id):onOpen(noteId)}>{note.title}</button></th><td className="dashboard-rate"><strong>{formatRate(note.rate)}</strong><small>{pending?'待确认':`${note.covered} / ${data.fields.length} 项`}</small></td>{data.fields.map(field=>{const cell=note.fields[field.id],label=pending?'待确认':cell.covered?'已覆盖':'缺失',className='dashboard-cell '+(pending?'pending':cell.covered?'covered':'missing');return <td key={field.id}>{linked?<button className={className} aria-label={`打开${note.title}的${field.label}，${label}`} onClick={()=>onOpen(noteId,cell.node_id,cell.section)}><span aria-hidden="true">{cell.covered?'●':'○'}</span> {label}</button>:<span className={className}>{label}</span>}</td>;})}</tr>;
    })}</tbody></table></div>}
   </section>
   <footer className="dashboard-foot">{top?'已确认覆盖率 = 已确认覆盖项数 ÷（实际入榜组合数 × 7）。':'整体覆盖率 = 已覆盖项数 ÷（阵容笔记数 × 7）。'}<span>覆盖数据更新于 {dateLabel(data.generated_at)}</span></footer>
  </>}
 </main>;
}

const lastSnapshots:Partial<Record<CoverageScope,DashboardData>>={};
export default function Dashboard({onOpen}:{onOpen:OpenNote}){
 const [scope,setScope]=useState<CoverageScope>('all');
 const [data,setData]=useState<DashboardData|null>(lastSnapshots.all??null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[checkedAt,setCheckedAt]=useState('');
 const [order,setOrder]=useState<CoverageOrder>('asc'),[usageBusy,setUsageBusy]=useState(false),[usageError,setUsageError]=useState('');
 const [matchingPair,setMatchingPair]=useState<string|null>(null);
 const polling=useRef<ReturnType<typeof startDashboardPolling>|null>(null),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 useEffect(()=>{
  const live=startDashboardPolling({read:signal=>readDashboard(signal,scope),onData:value=>{lastSnapshots[scope]=value;setData(value);setCheckedAt(new Date().toISOString());},onError:setError,onBusy:setBusy});
  polling.current=live;
  return()=>{live.stop();polling.current=null;};
 },[scope]);
 function changeScope(value:CoverageScope){if(value===scope)return;setScope(value);setData(lastSnapshots[value]??null);setOrder(value!=='all'?'usage':'asc');setError('');setCheckedAt('');setUsageError('');}
 async function refreshUsage(){
  setUsageBusy(true);setUsageError('');
  try{await api<UsageStatus>('dashboard/usage/refresh','POST',{});if(mounted.current)void polling.current?.refresh();}
  catch(e){if(mounted.current)setUsageError((e as Error).message);}
  finally{if(mounted.current)setUsageBusy(false);}
 }
 return <><DashboardView data={data} error={error} busy={busy} checkedAt={checkedAt} order={order} onOrder={setOrder} onRefresh={()=>void polling.current?.refresh()} onOpen={onOpen} scope={scope} onScope={changeScope} usageBusy={usageBusy} usageError={usageError} onUsageRefresh={()=>void refreshUsage()} onMatch={id=>setMatchingPair(id??data?.notes.find(n=>n.match_status!=='matched')?.id??data?.notes[0]?.id??'')}/>{matchingPair!==null&&<UsageMatchDialog initialPairId={matchingPair} onClose={()=>setMatchingPair(null)} onSaved={()=>void polling.current?.refresh()}/>}</>;
}
