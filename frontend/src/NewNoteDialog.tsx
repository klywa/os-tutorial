import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import type {Note} from './types';
export default function NewNoteDialog({defaultType,onClose,onCreated}:{defaultType:string;onClose:()=>void;onCreated:(note:Note)=>void}){
 const [type,setType]=useState<Note['type']>(['lineup','player','other'].includes(defaultType)?defaultType as Note['type']:'lineup');
 const [title,setTitle]=useState(''),[aliases,setAliases]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const dialog=useRef<HTMLDialogElement>(null),name=useRef<HTMLInputElement>(null),request=useRef({key:'',id:''});
 useEffect(()=>{dialog.current?.showModal();name.current?.focus();},[]);
 async function create(){setError('');setBusy(true);try{
  const body={type,title:title.trim(),aliases:[...new Set(aliases.split(/[、,，\n]/).map(x=>x.trim()).filter(Boolean))]};
  const key=JSON.stringify(body);if(key!==request.current.key)request.current={key,id:crypto.randomUUID()};
  const note=await api<Note>('notes','POST',{...body,request_id:request.current.id});onCreated(note);
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="new-note-dialog" aria-label="新建笔记" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><form onKeyDown={e=>{if(e.key==='Enter'&&e.nativeEvent.isComposing)e.preventDefault();}} onSubmit={e=>{e.preventDefault();void create();}}>
  <div className="section-heading"><h2>新建笔记</h2><button type="button" aria-label="关闭新建笔记" disabled={busy} onClick={onClose}>×</button></div>
  <p className="muted">先记下名称，正文、英雄与棋手资料可以后补。</p>
  {error&&<p className="error" role="alert">{error}</p>}
  <label>笔记类型<select aria-label="新笔记类型" value={type} disabled={busy} onChange={e=>setType(e.target.value as Note['type'])}><option value="lineup">阵容</option><option value="player">棋手</option><option value="other">其他知识</option></select></label>
  <label>笔记名称<input ref={name} aria-label="笔记名称" placeholder="常用名称，需包含中文" required value={title} disabled={busy} onChange={e=>setTitle(e.target.value)}/></label>
  <label>别名<input aria-label="笔记别名" placeholder="可选，用顿号或逗号分隔" value={aliases} disabled={busy} onChange={e=>setAliases(e.target.value)}/></label>
  <div className="action-line"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="primary" type="submit" disabled={busy||!title.trim()}>{busy?'正在创建…':'创建并编辑'}</button></div>
 </form></dialog>;
}
