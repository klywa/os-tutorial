import type {CrawlItem} from './types';
import TaskIcon from './TaskIcon';
export default function TaskControls({item,busy,onAction,onRetry}:{item:CrawlItem;busy:boolean;onAction:(action:string)=>void;onRetry?:()=>void}){
  return <div className="task-controls">
    <TaskIcon icon="download" label="停止下载" disabled={busy||item.state!=='running'||!['downloading','checking_subtitles','fetching_subtitles'].includes(item.progress.phase??'')} onClick={()=>onAction('stop-download')}/>
    <TaskIcon icon="transcribe" label="停止转录" disabled={busy||item.state!=='running'||item.progress.phase!=='transcribing'} onClick={()=>onAction('stop-transcribe')}/>
    {item.state==='paused'&&<TaskIcon icon="resume" label="继续处理" disabled={busy} onClick={()=>onAction('resume')}/>}
    {item.state==='failed'&&onRetry&&<TaskIcon icon="retry" label="重试此视频" disabled={busy} onClick={onRetry}/>}
    <TaskIcon icon="delete" label="删除视频任务" className="danger-quiet" disabled={busy||item.state==='cancelled'} onClick={()=>onAction('delete')}/>
  </div>;
}
