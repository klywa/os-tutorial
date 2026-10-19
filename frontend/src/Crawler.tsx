import LinkInput from './LinkInput';
import SearchConditions,{searchKeywords} from './SearchConditions';
import {creatorUID,newCreator,creatorMatches,creatorJobs,creatorStatus} from './creators';
import RetryStatus from './RetryStatus';
import TaskIcon from './TaskIcon';
import TaskError from './TaskError';
import CreatorEditor from './CreatorEditor';
import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import TaskControls from './TaskControls';
import {progressLabel,taskNames} from './acquisition';
import type {Creator,CrawlJob,CrawlSettings,SearchConfig} from './types';

const defaults:SearchConfig={keywords:[],strict_match:true,order:'totalrank',mode:'auto',scan_limit:100,process_limit:50};
export default function Crawler({seed,onSeedUsed}:{seed?:Partial<Creator>;onSeedUsed:()=>void}){
  const [editingCreator,setEditingCreator]=useState<Creator|null>(null);
  const [tab,setTab]=useState(seed?'creators':'search');
  const [form,setForm]=useState<SearchConfig>(defaults),[keywords,setKeywords]=useState<string[]>(['']);
  const [settings,setSettings]=useState<CrawlSettings>({clock:'09:00',cookies:'',search:defaults,parallelism:2});
  const [creators,setCreators]=useState<Creator[]>([]),[creatorFilter,setCreatorFilter]=useState(''),[creatorQuery,setCreatorQuery]=useState('');
  const [jobs,setJobs]=useState<CrawlJob[]>([]),[active,setActive]=useState(''),[detail,setDetail]=useState<CrawlJob|null>(null),[selected,setSelected]=useState<string[]>([]);
  const activeRef=useRef(active);activeRef.current=active;
  function showDetail(job:CrawlJob){if(activeRef.current===job.id)setDetail(job);}
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  async function refresh(){const [j,c]=await Promise.all([api<CrawlJob[]>('crawler/jobs'),api<Creator[]>('crawler/creators')]);setJobs(j);setCreators(c);}
  useEffect(()=>{
    let alive=true;
    void api<CrawlSettings>('crawler/settings').then(s=>{if(alive){setSettings(s);setForm({...s.search,strict_match:s.search.strict_match??true});setKeywords(s.search.keywords.length?s.search.keywords:['']);}}).catch(e=>setError(e.message));
    void refresh().catch(e=>setError(e.message));
    const timer=setInterval(()=>void refresh().catch(e=>setError(e.message)),2000);
    return()=>{alive=false;clearInterval(timer);};
  },[]);
  useEffect(()=>{if(seed){
    setTab('creators');setActive('');setDetail(null);setSelected([]);
    void api<Creator[]>('crawler/creators').then(list=>{setCreators(list);const existing=list.find(c=>c.uid===creatorUID(seed.url??''));
      if(existing){setCreatorFilter(existing.uid!);setEditingCreator(null);setMessage('已监听此UP主，可点击编辑调整配置。');}
      else setEditingCreator(newCreator(seed));onSeedUsed();
    }).catch(e=>setError(e.message));
  }},[seed]);
  function selectCreator(uid:string){activeRef.current='';setCreatorFilter(uid);setActive('');setDetail(null);setSelected([]);}
  function selectTab(value:string){activeRef.current='';setTab(value);setActive('');setDetail(null);setSelected([]);}
  const visibleJobs=creatorJobs(jobs,tab,creatorFilter);
  const currentCreator=creators.find(c=>c.uid===creatorFilter);

  useEffect(()=>{
    if(!active)return;
    let alive=true;
    const fetch=()=>void api<CrawlJob>('crawler/jobs/'+active).then(d=>{if(alive)setDetail(d);}).catch(e=>{if(!alive)return;if(e.message.includes('已删除')){setActive('');setDetail(null);}else setError(e.message);});
    setDetail(null);setSelected([]);fetch();const timer=setInterval(fetch,2000);
    return()=>{alive=false;clearInterval(timer);};
  },[active]);
  async function act(action:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await action();await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const config=()=>({...form,keywords:searchKeywords(keywords)});
  async function start(){await act(async()=>{const job=await api<CrawlJob>('crawler/searches','POST',config());setActive(job.id);setMessage('采集任务已创建，关闭网页后服务会继续处理。');});}
  async function jobAction(op:string,bvids?:string[]){await act(async()=>{const job=await api<CrawlJob>(`crawler/jobs/${active}/${op}`,'POST',{bvids});showDetail(job);if(activeRef.current===job.id)setSelected([]);});}
  async function deleteJob(id:string){await act(async()=>{await api(`crawler/jobs/${id}`,'DELETE',{});if(active===id){setActive('');setDetail(null);setSelected([]);}setMessage('任务已删除；已采集内容和文字稿保留，共用视频继续处理。');});}
  async function videoAction(bvid:string,action:string){await act(async()=>{await api(`crawler/tasks/${bvid}/${action}`,'POST',{});if(active)showDetail(await api<CrawlJob>('crawler/jobs/'+active));setMessage(action==='delete'?'视频任务已删除，已有内容保留。':action==='resume'?'已重新排队；若批次已停止，请恢复批次派发。':'已停止，保留已有文件和转写检查点。');});}
  async function phaseAction(id:string,action:string){await act(async()=>{const j=await api<CrawlJob>(`crawler/jobs/${id}/${action}`,'POST',{});showDetail(j);setMessage('已停止本批次继续派发，并停止对应阶段的视频；共用视频同步停止。');});}
  function searchNumber(key:keyof SearchConfig,label:string){return <label>{label}<input type="number" min="0" value={String(form[key]??'')} onChange={e=>setForm({...form,[key]:e.target.value===''?null:Number(e.target.value)})}/></label>;}
  function nextCheck(){const now=new Date(),bj=new Date(now.toLocaleString('en-US',{timeZone:'Asia/Shanghai'}));const [h,m]=settings.clock.split(':').map(Number);const next=new Date(bj);next.setHours(h,m,0,0);if(next<=bj)next.setDate(next.getDate()+1);return `${next.getMonth()+1}月${next.getDate()}日 ${settings.clock} 北京时间`;}
  return <div className="acquisition-page"><div className="page-heading"><div><h1>爬取</h1><p>从B站收集视频，把完整文字稿留在本地。</p></div><span className="badge">本地 large-v3 转写</span></div>
    <div className="acquisition-tabs" role="tablist" aria-label="采集方式"><button role="tab" aria-selected={tab==='search'} className={tab==='search'?'selected':''} onClick={()=>selectTab('search')}>关键词搜索</button><button role="tab" aria-selected={tab==='links'} className={tab==='links'?'selected':''} onClick={()=>selectTab('links')}>链接采集</button><button role="tab" aria-selected={tab==='creators'} className={tab==='creators'?'selected':''} onClick={()=>selectTab('creators')}>UP主监听</button></div>
    {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="notice" role="status">{message}</p>}
    <div className={"acquisition-layout "+(tab==='creators'?'creator-layout':'')}><section className={"acquisition-config "+(tab==='creators'?'creator-sidebar':'')}>
      {tab==='search'?<form onSubmit={e=>{e.preventDefault();void start();}}><h2>搜索条件</h2><SearchConditions rows={keywords} strict={form.strict_match??true} onRows={setKeywords} onStrict={strict_match=>setForm({...form,strict_match})}/>
        <div className="field-pair"><label>发布起始日期<input type="date" value={form.date_from??''} onChange={e=>setForm({...form,date_from:e.target.value})}/></label><label>发布结束日期<input type="date" value={form.date_to??''} onChange={e=>setForm({...form,date_to:e.target.value})}/></label></div>
        <div className="field-pair">{searchNumber('min_views','最低播放量')}{searchNumber('max_views','最高播放量')}{searchNumber('min_duration','最短时长（秒）')}{searchNumber('max_duration','最长时长（秒）')}</div>
        <div className="field-pair"><label>排序<select value={form.order} onChange={e=>setForm({...form,order:e.target.value})}><option value="totalrank">综合排序</option><option value="pubdate">最新发布</option><option value="click">最多播放</option></select></label><label>处理方式<select value={form.mode} onChange={e=>setForm({...form,mode:e.target.value})}><option value="auto">自动处理命中视频</option><option value="preview">预览后勾选处理</option></select></label>{searchNumber('scan_limit','每个关键词扫描上限')}{searchNumber('process_limit','本次处理视频上限')}</div>
        <p className="muted">日期包含当天，按北京时间筛选。每条“或”条件独享扫描额度，处理上限由本批次共享，重复视频只处理一次。</p><div className="action-line"><button className="primary" disabled={busy||!searchKeywords(keywords).length}>开始采集</button><button type="button" disabled={busy} onClick={()=>void act(async()=>{await api('crawler/searches','PUT',config());setMessage('搜索条件已保存');})}>保存条件</button></div>
      </form>:tab==='links'?<LinkInput onStarted={job=>{setActive(job.id);setMessage('链接任务已创建；可在右侧查看进度。');void refresh();}}/>:<>
        <div className="creator-list-heading"><h2>UP主监听（{creators.length}）</h2><button className="primary" disabled={busy} onClick={()=>setEditingCreator(newCreator())}>添加UP主</button></div>
        <label>搜索UP主<input type="search" placeholder="名称或UID" value={creatorQuery} onChange={e=>setCreatorQuery(e.target.value)}/></label>
        <button className={'creator-all '+(!creatorFilter?'selected':'')} aria-pressed={!creatorFilter} onClick={()=>selectCreator('')}>全部UP主 <small>含历史监听任务</small></button>
        <div className="creator-list" aria-label="已添加UP主">
        {creators.filter(c=>creatorMatches(c,creatorQuery)).map(c=><article className={'creator-entry '+(creatorFilter===c.uid?'active':'')} key={c.uid}>
          <button className="creator-select" aria-pressed={creatorFilter===c.uid} onClick={()=>selectCreator(c.uid!)}><span className="creator-identity"><strong>{c.name||c.uid}</strong><span className="badge">{c.enabled?'监听中':'已停用'}</span></span><span className="creator-meta"><small>UID {c.uid}</small><small>{creatorStatus(c)}</small></span><small className="creator-checked">最近检查 {c.last_checked?.replace('T',' ').slice(0,19)||'尚未检查'}</small></button>
          <RetryStatus retry={c.retry} compact/><div className="creator-actions">
          <button disabled={busy} onClick={()=>setEditingCreator({...c})}>编辑</button>
          <button disabled={busy} onClick={()=>void act(async()=>{const j=await api<CrawlJob>(`crawler/creators/${c.uid}/check`,'POST',{});selectCreator(c.uid!);setActive(j.id);})}>立即检查</button>
          <button disabled={busy} onClick={()=>void act(async()=>{await api(`crawler/creators/${c.uid}`,'PUT',{...c,enabled:!c.enabled});})}>{c.enabled?'停用':'启用'}</button>
          <button className="danger-quiet" disabled={busy} onClick={()=>void act(async()=>{await api(`crawler/creators/${c.uid}`,'DELETE',{});if(creatorFilter===c.uid)selectCreator('');setMessage('监听已删除；已派发视频、历史批次和文字稿保留。');})}>删除</button></div>
        </article>)}
        {!creators.length&&<p className="muted">尚未添加UP主，点击上方按钮开始监听。</p>}
        {!!creators.length&&!creators.some(c=>creatorMatches(c,creatorQuery))&&<p className="muted">没有匹配的UP主。</p>}</div>
        <details className="schedule-config"><summary>每日检查设置</summary><label>北京时间<input type="time" value={settings.clock} onChange={e=>setSettings({...settings,clock:e.target.value})}/></label><button disabled={busy} onClick={()=>void act(async()=>{await api('crawler/settings','PUT',{clock:settings.clock});setMessage('每日时间已保存');})}>保存时间</button><p className="muted">下次：{nextCheck()}。本地服务需运行；重启后自动补查。</p><button disabled={busy} onClick={()=>void act(async()=>{await api('crawler/creators/check','POST',{});setMessage('已安排所有启用UP主检查');})}>立即检查全部UP主</button></details>
      </>}
      <details className="connection-settings"><summary>B站连接设置</summary><label>本机cookies文件路径<input value={settings.cookies} onChange={e=>setSettings({...settings,cookies:e.target.value})} placeholder="留空使用匿名访问"/></label><button disabled={busy} onClick={()=>void act(async()=>{await api('crawler/settings','PUT',{cookies:settings.cookies});setMessage('连接设置已保存');})}>保存连接设置</button><p className="muted">使用Netscape格式cookies文件。遇到登录或风控错误后可配置，再重试任务。</p></details>
    </section><section className="acquisition-work"><div className="section-heading"><h2>{tab==='creators'?(currentCreator?.name||'全部UP主')+' · 任务':'任务进度'}</h2><span className="muted">每2秒刷新</span></div>
      {tab==='creators'&&currentCreator&&<section className="creator-status"><a href={currentCreator.url} target="_blank" rel="noreferrer">{currentCreator.name} · UID {currentCreator.uid}</a><p className="muted">起始 {currentCreator.date_from} · {currentCreator.keywords.filter(Boolean).join('、')||'全部投稿'} · {creatorStatus(currentCreator)}</p>{!currentCreator.checking&&<TaskError error={currentCreator.error} retry={currentCreator.retry}/>}</section>}
      <div className="concurrency-settings"><label>同时处理视频数<select aria-label="同时处理视频数" value={settings.parallelism} disabled={busy} onChange={e=>{const value=Number(e.target.value);void act(async()=>{setSettings(await api<CrawlSettings>('crawler/settings','PUT',{parallelism:value}));setMessage(`并行处理上限已设为 ${value}；搜索扫描独立运行。`);});}}>{[1,2,3,4].map(n=><option value={n} key={n}>{n} 个视频</option>)}</select></label><p className="muted">搜索扫描与下载转写并行运行。降低上限会在当前视频结束后生效。</p></div>
      <div className="job-history" aria-label="采集任务列表">{visibleJobs.map(j=><article className={'job-history-item '+(active===j.id?'active':'')} key={j.id}><button className={active===j.id?'selected':''} onClick={()=>setActive(j.id)}><strong>{j.creator?(creators.find(c=>c.uid===j.creator)?.name||'UP主 '+j.creator):(j.config.kind==='links'?`链接采集（${j.matched}）`:j.config.keywords.join('、'))}</strong>{j.creator&&<small>UID {j.creator}</small>}<small>{j.created.replace('T',' ').slice(0,19)} · {taskNames[j.state]||j.state}</small><small>处理中 {j.counts.running} · 排队 {j.counts.queued} · 已停止 {j.counts.paused??0}</small></button><RetryStatus retry={j.retry}/><div className="task-controls"><TaskIcon icon="download" label="停止下载" disabled={busy||!j.counts.downloading} onClick={()=>void phaseAction(j.id,'stop-download')}/><TaskIcon icon="transcribe" label="停止转录" disabled={busy||!j.counts.transcribing} onClick={()=>void phaseAction(j.id,'stop-transcribe')}/><TaskIcon icon="delete" label={`删除任务 ${j.id}`} className="danger-quiet" disabled={busy} onClick={()=>void deleteJob(j.id)}/></div></article>)}</div>
      {!visibleJobs.length&&<div className="empty">配置搜索条件或添加UP主，开始收集文字稿。</div>}
      {!active&&!!visibleJobs.length&&<p className="muted">选择任务查看结果与处理进度。</p>}
      {detail&&visibleJobs.some(j=>j.id===detail.id)&&<><div className="job-summary" aria-live="polite"><span>已扫描 <b>{detail.scanned}</b></span><span>符合条件 <b>{detail.matched}</b></span><span>重复跳过 <b>{detail.duplicates}</b></span>{!detail.creator&&detail.config.kind!=='links'&&<span>标题不匹配 <b>{detail.title_skipped??0}</b></span>}<span>待处理 <b>{detail.counts.queued}</b></span><span>已生成 <b>{detail.counts.succeeded}</b></span><span>失败 <b>{detail.counts.failed}</b></span></div>
        {!detail.creator&&detail.scan_counts&&<div className="keyword-progress" aria-label="各条件扫描进度">{Object.entries(detail.scan_counts).map(([keyword,count])=><span key={keyword}>{keyword}：{count} / {detail.config.scan_limit}</span>)}</div>}
        <p className="muted">{taskNames[detail.state]||detail.state} · 仅覆盖本次实际扫描结果{detail.limited?'；已达到扫描或处理上限':''}</p><TaskError error={detail.error} retry={detail.retry}/>
        <div className="batch-toolbar"><span>已选 {selected.length}</span><button className="danger-quiet" disabled={busy} onClick={()=>void deleteJob(detail.id)}>删除当前任务</button><button onClick={()=>setSelected((detail.items??[]).filter(i=>i.state==='preview').map(i=>i.bvid))}>选择待处理结果</button><button disabled={busy||!selected.length||detail.state==='stopped'} onClick={()=>void jobAction('start',selected)}>处理所选</button><button disabled={busy||(!detail.counts.failed&&detail.state!=='failed')} onClick={()=>void jobAction('retry')}>重试失败项</button><button disabled={busy} onClick={()=>void jobAction(detail.state==='stopped'?'resume':'stop')}>{detail.state==='stopped'?'恢复采集与派发':'停止继续采集与派发'}</button></div>
        <div className="crawl-results">{detail.items?.map(i=><article className="crawl-result" key={i.bvid}><input type="checkbox" aria-label={'选择 '+(i.title||i.bvid)} checked={selected.includes(i.bvid)} onChange={e=>setSelected(e.target.checked?[...selected,i.bvid]:selected.filter(v=>v!==i.bvid))}/><div><a href={i.url} target="_blank" rel="noreferrer">{i.title||i.bvid}</a><p className="muted">{i.author||'UP主未知'} · {i.published||'发布日期未知'} · {i.view_count?.toLocaleString()??'未知'}次播放</p><div className="chips">{detail.config.kind==='links'&&<span className="badge">{i.requested_parts?i.requested_parts.map(p=>'P'+p).join('、'):'全部分P'}</span>}{i.keywords.map(k=><span className="badge" key={k}>{k}</span>)}<span className="badge">{i.state==='running'?progressLabel(i.progress):taskNames[i.state]||i.state}</span></div><TaskError error={i.error} retry={i.progress.next_retry_at?{attempt:i.progress.attempt??1,next_retry_at:i.progress.next_retry_at}:null}/>{i.state!=='preview'&&<TaskControls item={i} busy={busy} onAction={a=>void videoAction(i.bvid,a)} onRetry={()=>void jobAction('retry',[i.bvid])}/>}</div></article>)}</div>
      </>}
    </section></div>{editingCreator&&<CreatorEditor creator={editingCreator} busy={busy} onClose={()=>setEditingCreator(null)} onSave={async draft=>{setBusy(true);try{const saved=await api<Creator>(draft.uid?`crawler/creators/${draft.uid}`:'crawler/creators',draft.uid?'PUT':'POST',draft);await refresh();if(!draft.uid)selectCreator(saved.uid!);setEditingCreator(null);setMessage(draft.uid?'监听配置已更新。':'UP主已添加，已有监听保持不变。');}finally{setBusy(false);}}}/>}</div>;
}
