import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import type {Note,Entity} from './types';
export function playerNoteFor(notes:Note[],player:string){
 if(!player)return undefined;
 return notes.find(n=>n.type==='player'&&(n.player_id===player||(!n.player_id&&n.entities.filter(e=>e.startsWith('player:')).length===1&&n.entities.includes(player))));
}
export default function NewNoteDialog({defaultType,onClose,onCreated,entities,notes,onOpen}:{defaultType:string;onClose:()=>void;onCreated:(note:Note)=>void;entities:Entity[];notes:Note[];onOpen:(id:string)=>void}){
 const [type,setType]=useState<Note['type']>(['lineup','player','other'].includes(defaultType)?defaultType as Note['type']:'lineup');
 const [title,setTitle]=useState(''),[aliases,setAliases]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [player,setPlayer]=useState('');
 const players=entities.filter(e=>e.category==='players');
 const chosen=players.find(p=>p.id===player);
 const existing=type==='player'?playerNoteFor(notes,player):undefined;
 const dialog=useRef<HTMLDialogElement>(null),name=useRef<HTMLInputElement>(null),request=useRef({key:'',id:''});
 useEffect(()=>{dialog.current?.showModal();name.current?.focus();},[]);
 async function create(){if(busy||(type!=='other'&&!chosen)||(type==='player'&&existing))return;setError('');setBusy(true);try{
  const body={type,title:type==='player'?chosen!.name:title.trim(),...(type!=='other'?{player_id:player}:{}),aliases:[...new Set(aliases.split(/[、,，\n]/).map(x=>x.trim()).filter(Boolean))]};
  const key=JSON.stringify(body);if(key!==request.current.key)request.current={key,id:crypto.randomUUID()};
  const note=await api<Note>('notes','POST',{...body,request_id:request.current.id});onCreated(note);
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="new-note-dialog" aria-label="新建笔记" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><form onKeyDown={e=>{if(e.key==='Enter'&&e.nativeEvent.isComposing)e.preventDefault();}} onSubmit={e=>{e.preventDefault();void create();}}>
  <div className="section-heading"><h2>新建笔记</h2><button type="button" aria-label="关闭新建笔记" disabled={busy} onClick={onClose}>×</button></div>
  <p className="muted">{type==='player'?'每位棋手保留一份笔记，名称与棋手一致。':'先记下名称，正文、英雄与棋手资料可以后补。'}</p>
  {error&&<p className="error" role="alert">{error}</p>}
  <label>笔记类型<select aria-label="新笔记类型" value={type} disabled={busy} onChange={e=>setType(e.target.value as Note['type'])}><option value="lineup">阵容</option><option value="player">棋手</option><option value="other">其他知识</option></select></label>
  {type==='player'?<><label>棋手<select aria-label="笔记棋手" required value={player} disabled={busy} onChange={e=>{setPlayer(e.target.value);setError('');}}><option value="">请选择棋手</option>{players.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>{existing&&<div className="muted">该棋手已有笔记。<button type="button" disabled={busy} onClick={()=>{onClose();onOpen(existing.id);}}>打开已有笔记</button></div>}</>:<label>笔记名称<input ref={name} aria-label="笔记名称" placeholder="常用名称，需包含中文" required value={title} disabled={busy} onChange={e=>setTitle(e.target.value)}/></label>}
  {type==='lineup'&&<label>关联棋手<select aria-label="阵容棋手" required value={player} disabled={busy} onChange={e=>setPlayer(e.target.value)}><option value="">请选择棋手</option>{players.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
  <label>别名<input aria-label="笔记别名" placeholder="可选，用顿号或逗号分隔" value={aliases} disabled={busy} onChange={e=>setAliases(e.target.value)}/></label>
  <div className="action-line"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="primary" type="submit" disabled={busy||(type!=='other'&&!chosen)||(type==='player'?!!existing:!title.trim())}>{busy?'正在创建…':'创建并编辑'}</button></div>
 </form></dialog>;
}
