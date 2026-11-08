import {useEffect,useRef,useState} from 'react';
import type {PortableTemplateLibrary} from './templates';
import {api} from './model';
import {TemplateDialog} from './TemplateEditor';

export default function TemplateJsonExport({groupId,groupName,onClose}:{groupId:string;groupName:string;onClose:()=>void}){
 const [code,setCode]=useState(''),[loading,setLoading]=useState(true),[loadError,setLoadError]=useState(''),[copyMessage,setCopyMessage]=useState(''),[copying,setCopying]=useState(false),[attempt,setAttempt]=useState(0);
 const field=useRef<HTMLTextAreaElement>(null);
 useEffect(()=>{
  let alive=true;setLoading(true);setLoadError('');setCode('');setCopyMessage('');
  void api<PortableTemplateLibrary>('templates/export?group_ids='+encodeURIComponent(groupId)).then(document=>{if(alive)setCode(JSON.stringify(document,null,2));}).catch(e=>{if(alive)setLoadError((e as Error).message);}).finally(()=>{if(alive)setLoading(false);});
  return()=>{alive=false;};
 },[groupId,attempt]);
 async function copy(){
  if(!code||copying)return;setCopying(true);setCopyMessage('');
  try{if(!navigator.clipboard?.writeText)throw new Error('clipboard unavailable');await navigator.clipboard.writeText(code);setCopyMessage('JSON 已复制');}
  catch{field.current?.focus();field.current?.select();setCopyMessage('复制失败，已选中全部 JSON，请按 Ctrl+C 或 ⌘C 复制。');}
  finally{setCopying(false);}
 }
 return <TemplateDialog title="导出模板组 JSON" onClose={onClose} wide><div className="template-form template-json-export">
  <p><strong>{groupName}</strong> · 当前已保存版本，包含本组及所需事件、参数定义。</p>
  {loading&&<p role="status">正在生成 JSON…</p>}
  {loadError&&<p role="alert" className="error">{loadError}<button onClick={()=>setAttempt(n=>n+1)}>重新加载</button></p>}
  {code&&<label>JSON 代码<textarea ref={field} aria-label="模板组 JSON" readOnly spellCheck={false} value={code} rows={18}/></label>}
  {copyMessage&&<p role="status" className="template-json-copy-status">{copyMessage}</p>}
  <footer><button onClick={onClose}>关闭</button><button className="primary" disabled={loading||!code||copying} onClick={()=>void copy()}>{copying?'复制中…':'一键复制'}</button></footer>
 </div></TemplateDialog>;
}
