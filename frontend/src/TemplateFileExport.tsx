import {useRef,useState} from 'react';
import {TemplateDialog} from './TemplateEditor';
import {pickNewTemplateFile,pickTemplateFile,previewTemplateFileExport,readTemplateFile,saveTemplateFile,type LocalFileHandle} from './templateFile';

export type FileExportScope='selected'|'filtered'|'all';
type Target=ReturnType<typeof previewTemplateFileExport>&{handle:LocalFileHandle;expected:string;sameAsOpened:boolean};
type Props={
 groupName?:string;
 counts:{selected:number;filtered:number};
 opened?:{handle:LocalFileHandle;raw:string}|null;
 loadSource:(scope:FileExportScope)=>Promise<unknown>;
 onBusy:(busy:boolean)=>void;
 onClose:()=>void;
 onSaved:(handle:LocalFileHandle,raw:string,sameAsOpened:boolean)=>void;
};
const labels={add:'新增',replace:'覆盖',unchanged:'无变化'};

export default function TemplateFileExport({groupName,counts,opened,loadSource,onBusy,onClose,onSaved}:Props){
 const [scope,setScope]=useState<FileExportScope>(counts.selected?'selected':counts.filtered?'filtered':'all');
 const [target,setTarget]=useState<Target|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const lock=useRef(false);
 function start(){lock.current=true;setBusy(true);setError('');onBusy(true);}
 function stop(){lock.current=false;setBusy(false);onBusy(false);}
 async function choose(mode:'new'|'merge'){
  if(lock.current)return;
  start();setTarget(null);
  try{
   const name=groupName?.replace(/[\\/:*?"<>|]/g,'-');
   const handle=mode==='new'?await pickNewTemplateFile((name||'话术模板库')+'.json'):await pickTemplateFile();
   const expected=await readTemplateFile(handle);
   const sameAsOpened=!!opened&&(handle===opened.handle||(await handle.isSameEntry?.(opened.handle))===true);
   if(sameAsOpened&&expected!==opened?.raw)throw new Error('当前打开的文件已在其他地方修改，请重新读取后再导出。');
   const document=await loadSource(scope);
   setTarget({...previewTemplateFileExport(document,expected,mode),handle,expected,sameAsOpened});
  }catch(error){if((error as Error).name!=='AbortError')setError((error as Error).message);}
  finally{stop();}
 }
 async function write(){
  if(lock.current||!target?.changed)return;
  start();
  try{
   const raw=await saveTemplateFile(target.handle,target.expected,target.document);
   onSaved(target.handle,raw,target.sameAsOpened);
  }catch(error){setTarget(null);setError((error as Error).message);}
  finally{stop();}
 }
 const close=()=>{if(!lock.current)onClose();};
 return <TemplateDialog title="导出到文件" onClose={close}>
  <div className="template-form">
   {groupName?<p>模板组 · {groupName}</p>:<label>导出范围<select value={scope} disabled={busy} onChange={event=>{setScope(event.currentTarget.value as FileExportScope);setTarget(null);setError('');}}>
    <option value="selected" disabled={!counts.selected}>看板所选（{counts.selected}）</option>
    <option value="filtered" disabled={!counts.filtered}>当前筛选（{counts.filtered}）</option>
    <option value="all">全库</option>
   </select></label>}
   <div className="template-parameter-tools">
    <button type="button" disabled={busy} onClick={()=>void choose('new')}>新建文件</button>
    <button type="button" disabled={busy} onClick={()=>void choose('merge')}>合并到已有文件</button>
   </div>
   {error&&<p className="error" role="alert">{error}</p>}
   {target&&<section>
    <h3>写入预览</h3>
    <p>{target.handle.name}</p>
    <p>{Object.entries(labels).map(([key,label])=>`${label} ${target.changes.filter(change=>change.action===key).length} 组`).join(' · ')}</p>
    {!!target.eventChanges.length&&<p>事件定义变更 · {target.eventChanges.join('、')}</p>}
    {target.changes.length>0&&<details><summary>查看模板组明细</summary><ul>{target.changes.map((change,index)=><li key={index}>
     {labels[change.action]} · {change.previousName&&change.previousName!==change.name?`${change.previousName} → `:''}{change.name}
    </li>)}</ul></details>}
    {!target.changed&&<p role="status">目标文件没有变化。</p>}
   </section>}
   <footer><button type="button" onClick={close} disabled={busy}>取消</button>
    <button type="button" className="primary" disabled={busy||!target?.changed} onClick={()=>void write()}>确认写入</button></footer>
  </div>
 </TemplateDialog>;
}
