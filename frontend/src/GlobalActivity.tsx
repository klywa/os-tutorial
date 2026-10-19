import {contentTitle} from './acquisition';
import {useEffect,useState} from 'react';
import {api} from './model';
import {progressLabel,taskNames} from './acquisition';
import TaskControls from './TaskControls';
import type {CrawlItem} from './types';
type Activity=CrawlItem&{jobs:{id:string;name:string}[]};
export default function GlobalActivity(){
  const [items,setItems]=useState<Activity[]>([]),[expanded,setExpanded]=useState<boolean|null>(null),[queued,setQueued]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function refresh(){setItems(await api<Activity[]>('crawler/activity'));}
  useEffect(()=>{let alive=true;const load=()=>void api<Activity[]>('crawler/activity').then(rows=>{if(alive)setItems(rows);}).catch(e=>{if(alive)setError(e.message);});load();const timer=setInterval(load,2000);return()=>{alive=false;clearInterval(timer);};},[]);
  async function control(item:Activity,action:string){setBusy(true);setError('');try{await api(`crawler/tasks/${item.bvid}/${action}`,'POST',{});await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const downloading=items.filter(i=>i.state==='running'&&['downloading','checking_subtitles','fetching_subtitles'].includes(i.progress.phase??'')).length;
  const transcribing=items.filter(i=>i.state==='running'&&i.progress.phase==='transcribing').length;
  const other=items.filter(i=>i.state==='running'&&!['downloading','checking_subtitles','fetching_subtitles','transcribing'].includes(i.progress.phase??'')).length;
  const open=expanded??items.some(i=>i.state==='running');
  const setOpen=(value:boolean)=>setExpanded(value);
  const visible=items.filter(i=>queued||i.state!=='queued');
  return <section className="global-activity" aria-label="全局任务监控"><div className="activity-heading"><button aria-expanded={open} onClick={()=>setOpen(!open)}><strong>全局任务</strong> <span>正在下载 {downloading} · 正在转录 {transcribing}{other?` · 整理中 ${other}`:''} · 排队 {items.filter(i=>i.state==='queued').length} · 已停止 {items.filter(i=>i.state==='paused').length}</span></button><button onClick={()=>setOpen(!open)}>{open?'收起':'展开'}</button></div>
    {open&&<div className="activity-body">{error&&<p className="error" role="alert">{error}</p>}<div className="activity-caption"><span>所有批次共享此队列，每2秒刷新。停止保留恢复材料；删除保留已生成内容。共用视频的操作影响所有关联批次。</span><label><input type="checkbox" checked={queued} onChange={e=>setQueued(e.target.checked)}/>显示排队视频</label></div>
      {!visible.length&&<p className="muted">当前没有正在下载、转录或已停止的视频。</p>}
      <div className="activity-grid">{visible.slice(0,50).map(i=><article className="activity-row" key={i.bvid}><div><a href={i.url||`https://www.bilibili.com/video/${i.bvid}`} target="_blank" rel="noreferrer">{contentTitle(i.title,i.bvid)}</a><small>{i.jobs.map(j=>j.name).join(' / ')} · {i.bvid}</small></div><span className="badge">{i.state==='running'?progressLabel(i.progress):taskNames[i.state]||i.state}</span><TaskControls item={i} busy={busy} onAction={a=>void control(i,a)}/></article>)}</div>
      {visible.length>50&&<p className="muted">显示前50条，共 {visible.length} 条；可在爬取页逐批管理。</p>}
    </div>}
  </section>;
}
