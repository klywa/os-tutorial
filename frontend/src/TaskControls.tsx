import type {CrawlItem} from './types';
export default function TaskControls({item,busy,onAction}:{item:CrawlItem;busy:boolean;onAction:(action:string)=>void}){
  return <div className="task-controls">
    <button disabled={busy||item.state!=='running'||item.progress.phase!=='downloading'} onClick={()=>onAction('stop-download')}>停止下载</button>
    <button disabled={busy||item.state!=='running'||item.progress.phase!=='transcribing'} onClick={()=>onAction('stop-transcribe')}>停止转录</button>
    {item.state==='paused'&&<button disabled={busy} onClick={()=>onAction('resume')}>继续处理</button>}
    <button className="danger-quiet" disabled={busy||item.state==='cancelled'} onClick={()=>onAction('delete')}>删除视频任务</button>
  </div>;
}
