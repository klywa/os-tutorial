import {useEffect,useRef,useState} from 'react';
import type {PointerEvent} from 'react';
import {api} from './model';
import './quickVideoSearch.css';

type Video={bvid:string;title:string;author:string;published:string|null;view_count:number|null;url:string};
type Page={items:Video[];next_cursor:string|null};
type Query={q:string;date_from:string};
const number=new Intl.NumberFormat('zh-CN');

export default function QuickVideoSearch(){
  const [q,setQ]=useState(''),[date,setDate]=useState('');
  const [videos,setVideos]=useState<Video[]>([]),[selected,setSelected]=useState(new Set<string>());
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[feedback,setFeedback]=useState('');
  const [manual,setManual]=useState(''),[cursor,setCursor]=useState<string|null>(null);
  const [autoLoad,setAutoLoad]=useState(false);
  const query=useRef<Query|null>(null),request=useRef(0),pending=useRef(false);
  const sentinel=useRef<HTMLButtonElement>(null),allBox=useRef<HTMLInputElement>(null);
  const drag=useRef<{pointer:number;start:number;end:number;checked:boolean;base:Set<string>}|null>(null);
  const copyAttempt=useRef(0);
  const all=videos.length>0&&selected.size===videos.length;
  useEffect(()=>{if(allBox.current)allBox.current.indeterminate=selected.size>0&&!all;},[selected,all]);
  useEffect(()=>()=>{request.current++;},[]);

  async function load(position:string,replace=false){
    if(!query.current||(!replace&&pending.current))return;
    const token=++request.current;
    const params=new URLSearchParams({...query.current,cursor:position});
    pending.current=true;setBusy(true);setError('');
    try{
      const page=await api<Page>('crawler/quick-search?'+params);
      if(token!==request.current)return;
      const previous=new Set(replace?[]:videos.map(video=>video.bvid));
      setAutoLoad(page.items.some(video=>!previous.has(video.bvid)));
      setVideos(current=>{
        const merged=new Map((replace?[]:current).map(video=>[video.bvid,video]));
        for(const video of page.items)if(!merged.has(video.bvid))merged.set(video.bvid,video);
        return [...merged.values()];
      });
      setCursor(page.next_cursor);
    }catch(e){
      if(token===request.current)setError(e instanceof Error?e.message:'搜索失败，请重试');
    }finally{
      if(token===request.current){pending.current=false;setBusy(false);}
    }
  }
  useEffect(()=>{
    const target=sentinel.current;
    if(!target||!cursor||busy||error||!autoLoad||!('IntersectionObserver' in window))return;
    const observer=new IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting))void load(cursor);
    },{rootMargin:'0px 0px 120px 0px'});
    observer.observe(target);
    return()=>observer.disconnect();
  },[cursor,busy,error,autoLoad,videos.length]);

  function changeSelection(next:Set<string>){
    copyAttempt.current++;setSelected(next);setFeedback('');setManual('');
  }
  function toggle(id:string,checked:boolean){
    const next=new Set(selected);
    if(checked)next.add(id);else next.delete(id);
    changeSelection(next);
  }
  function startDrag(e:PointerEvent<HTMLInputElement>,index:number){
    if(e.pointerType!=='mouse'||e.button!==0)return;
    e.preventDefault();
    e.currentTarget.focus();
    const id=videos[index].bvid, checked=!selected.has(id);
    drag.current={pointer:e.pointerId,start:index,end:index,checked,base:selected};
    e.currentTarget.setPointerCapture(e.pointerId);
    toggle(id,checked);
  }
  function moveDrag(e:PointerEvent<HTMLInputElement>){
    const state=drag.current;
    if(!state||state.pointer!==e.pointerId)return;
    const row=document.elementFromPoint(e.clientX,e.clientY)?.closest<HTMLElement>('[data-quick-row]');
    const limit=row?.dataset.quickRow;
    if(limit===undefined||Number(limit)===state.end)return;
    state.end=Number(limit);
    const next=new Set(state.base);
    for(let i=Math.min(state.start,state.end);i<=Math.max(state.start,state.end);i++){
      const id=videos[i].bvid;
      if(state.checked)next.add(id);else next.delete(id);
    }
    changeSelection(next);
  }
  async function copy(){
    const value=videos.filter(v=>selected.has(v.bvid)).map(v=>v.url).join('\n');
    if(!value)return;
    const attempt=++copyAttempt.current;
    try{
      await navigator.clipboard.writeText(value);
      if(attempt===copyAttempt.current){setManual('');setFeedback(`已复制 ${selected.size} 条链接`);}
    }catch{
      if(attempt===copyAttempt.current){setFeedback('无法访问剪贴板，请手动复制下方链接。');setManual(value);}
    }
  }

  return <section className="quick-video-search" aria-label="快速搜视频">
    <form className="quick-video-form" onSubmit={e=>{
      e.preventDefault();if(!q.trim())return;
      query.current={q:q.trim(),date_from:date};setVideos([]);changeSelection(new Set());setCursor(null);drag.current=null;
      void load('',true);
    }}>
      <label>关键词<input type="search" required maxLength={100} value={q} onChange={e=>setQ(e.target.value)} placeholder="例如：王者万象棋"/></label>
      <label>最早发布日期（可选）<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label>
      <button className="primary" disabled={!q.trim()}>搜索</button>
    </form>
    {!query.current&&<p className="muted">按 B 站综合排序。日期包含当天，按北京时间筛选。</p>}
    {videos.length>0&&<>
      <div className="quick-video-toolbar">
        <span role="status">已选 {selected.size} 条</span>
        <button type="button" className="primary" disabled={!selected.size} onClick={()=>void copy()}>一键复制链接列表</button>
      </div>
      <div role="status">{feedback}</div>
      {manual&&<label>视频链接<textarea readOnly value={manual} rows={4} onFocus={e=>e.target.select()}/></label>}
      <div className="quick-video-header">
        <label><input ref={allBox} type="checkbox" checked={all} onChange={()=>changeSelection(new Set(all?[]:videos.map(v=>v.bvid)))}/>全选</label>
        <span>视频标题</span><span>UP 主</span><span>发布时间</span><span>播放量</span>
      </div>
      <ul className="quick-video-rows" aria-label="视频结果">
        {videos.map((v,i)=><li key={v.bvid} data-quick-row={i} data-checked={selected.has(v.bvid)}>
          <label className="quick-video-check"><input type="checkbox" aria-label={`选择 ${v.title||v.bvid}`}
            checked={selected.has(v.bvid)} onChange={e=>{
              if((e.nativeEvent as globalThis.PointerEvent).pointerType!=='mouse')toggle(v.bvid,e.target.checked);
            }}
            onPointerDown={e=>startDrag(e,i)} onPointerMove={moveDrag} onLostPointerCapture={()=>{drag.current=null;}}
            onClick={e=>{if(e.detail>0&&(e.nativeEvent as globalThis.PointerEvent).pointerType==='mouse')e.preventDefault();}}/></label>
          <a href={v.url} target="_blank" rel="noreferrer">{v.title||v.bvid}</a>
          <span title={v.author}>{v.author||'未知 UP 主'}</span>
          <time dateTime={v.published??undefined}>{v.published||'日期未知'}</time>
          <span>{v.view_count==null?'播放量未知':number.format(v.view_count)}</span>
        </li>)}
      </ul>
    </>}
    <div className="quick-video-pagination">
      {busy&&<p role="status">{videos.length?'正在加载更多…':'正在搜索…'}</p>}
      {error&&<><p role="alert" className="error">{error}</p><button type="button" onClick={()=>void load(cursor??'')}>重试</button></>}
      {!busy&&!error&&query.current&&<p className="muted">{videos.length?(cursor?'':'已加载全部结果。'):(cursor?'这一批没有符合条件的视频，可继续搜索。':'没有找到符合条件的视频。')}</p>}
      {cursor&&!busy&&!error&&<button type="button" ref={sentinel} onClick={()=>void load(cursor)}>加载更多</button>}
    </div>
  </section>;
}
