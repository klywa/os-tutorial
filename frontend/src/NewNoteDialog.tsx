import {useEffect,useRef,useState,type ChangeEvent} from 'react';
import SeasonFields from './SeasonFields';
import type {Season} from './seasons';
import {api} from './model';
import type {Note,Entity} from './types';
import {describeNewNoteJson,readNoteJson} from './noteUpload';
export function playerNoteFor(notes:Note[],player:string){
 if(!player)return undefined;
 return notes.find(n=>n.type==='player'&&(n.player_id===player||(!n.player_id&&n.entities.filter(e=>e.startsWith('player:')).length===1&&n.entities.includes(player))));
}
export default function NewNoteDialog({defaultType,onClose,onCreated,entities,notes,onOpen,season='S1'}:{season?:Season;defaultType:string;onClose:()=>void;onCreated:(note:Note,imported?:boolean)=>void;entities:Entity[];notes:Note[];onOpen:(id:string)=>void}){
 const [type,setType]=useState<Note['type']>(['lineup','player','other'].includes(defaultType)?defaultType as Note['type']:'lineup');
 const [title,setTitle]=useState(''),[aliases,setAliases]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [selectedSeasons,setSelectedSeasons]=useState<Season[]>([season]);
 const [player,setPlayer]=useState('');
 const [upload,setUpload]=useState<{name:string;document:unknown;preview:string;truncated:boolean}|null>(null);
 const [reading,setReading]=useState(false);
 const locked=busy||reading;
 const players=entities.filter(e=>e.category==='players');
 const chosen=players.find(p=>p.id===player);
 const existing=type==='player'?playerNoteFor(notes.filter(n=>(n.seasons??['S1'] as Season[]).some(s=>selectedSeasons.includes(s))),player):undefined;
 const dialog=useRef<HTMLDialogElement>(null),name=useRef<HTMLInputElement>(null),request=useRef({key:'',id:''});
 useEffect(()=>{dialog.current?.showModal();name.current?.focus();},[]);
 async function selectFile(event:ChangeEvent<HTMLInputElement>){
  const file=event.currentTarget.files?.[0];
  event.currentTarget.value='';
  if(!file)return;
  setError('');setReading(true);
  try{
   const document=await readNoteJson(file);
   const {metadata,title,preview,truncated}=describeNewNoteJson(document);
   setTitle(title);
   if(metadata.type==='lineup'||metadata.type==='player'||metadata.type==='other')setType(metadata.type);
   if(typeof metadata.player_id==='string')setPlayer(metadata.player_id);
   if(Array.isArray(metadata.seasons)){
    const seasons=[...new Set(metadata.seasons.filter((value):value is Season=>value==='S1'||value==='S2'))];
    if(seasons.length)setSelectedSeasons(seasons);
   }
   if(Array.isArray(metadata.aliases))setAliases(metadata.aliases.filter(value=>typeof value==='string').join('、'));
   setUpload({name:file.name,document,preview,truncated});
  }catch(e){setError((e as Error).message);}finally{setReading(false);}
 }
 async function create(){if(locked||!selectedSeasons.length||(type!=='other'&&!chosen)||(type==='player'&&existing))return;setError('');setBusy(true);try{
  const body={type,seasons:selectedSeasons,title:type==='player'?chosen!.name:title.trim(),...(type!=='other'?{player_id:player}:{}),aliases:[...new Set(aliases.split(/[、,，\n]/).map(x=>x.trim()).filter(Boolean))],...(upload?{document:upload.document}:{})};
  const key=JSON.stringify(body);if(key!==request.current.key)request.current={key,id:crypto.randomUUID()};
  const note=await api<Note>('notes','POST',{...body,request_id:request.current.id});onCreated(note,!!upload);
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="new-note-dialog" aria-label="新建笔记" onCancel={e=>{e.preventDefault();if(!locked)onClose();}}><form onKeyDown={e=>{if(e.key==='Enter'&&e.nativeEvent.isComposing)e.preventDefault();}} onSubmit={e=>{e.preventDefault();void create();}}>
  <div className="section-heading"><h2>新建笔记</h2><button type="button" aria-label="关闭新建笔记" disabled={locked} onClick={onClose}>×</button></div>
  <label>选择 JSON 文件<input type="file" accept=".json,application/json" disabled={locked} onChange={event=>void selectFile(event)}/></label>
  {reading&&<p role="status">正在读取 JSON…</p>}
  {upload&&<><div className="new-note-file"><span>{upload.name}</span><button type="button" disabled={locked} onClick={()=>{setUpload(null);setError('');}}>移除文件</button></div>
   <details open><summary>正文预览{upload.truncated?'（节选）':''}</summary><pre className="new-note-preview">{upload.preview}</pre></details></>}
  <p className="muted">{type==='player'?'每个赛季每位棋手保留一份笔记，名称与棋手一致。':!upload?'先记下名称，正文、英雄与棋手资料可以后补。':null}</p>
  {error&&<p className="error" role="alert">{error}</p>}
  <label>笔记类型<select aria-label="新笔记类型" value={type} disabled={busy} onChange={e=>setType(e.target.value as Note['type'])}><option value="lineup">阵容</option><option value="player">棋手</option><option value="other">其他知识</option></select></label>
  {type==='player'?<><label>棋手<select aria-label="笔记棋手" required value={player} disabled={busy} onChange={e=>{setPlayer(e.target.value);setError('');}}><option value="">请选择棋手</option>{players.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>{existing&&<div className="muted">该棋手已有笔记。<button type="button" disabled={busy} onClick={()=>{onClose();onOpen(existing.id);}}>打开已有笔记</button></div>}</>:<label>笔记名称<input data-card-completion ref={name} aria-label="笔记名称" placeholder="常用名称，需包含中文" required value={title} disabled={busy} onChange={e=>setTitle(e.target.value)}/></label>}
  {type==='lineup'&&<label>关联棋手<select aria-label="阵容棋手" required value={player} disabled={busy} onChange={e=>setPlayer(e.target.value)}><option value="">请选择棋手</option>{players.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
  <SeasonFields value={selectedSeasons} disabled={busy} onChange={setSelectedSeasons}/>
  <label>别名<input data-card-completion aria-label="笔记别名" placeholder="可选，用顿号或逗号分隔" value={aliases} disabled={busy} onChange={e=>setAliases(e.target.value)}/></label>
  <div className="action-line"><button type="button" disabled={locked} onClick={onClose}>取消</button><button className="primary" type="submit" disabled={locked||!selectedSeasons.length||(type!=='other'&&!chosen)||(type==='player'?!!existing:!title.trim())}>{busy?'正在创建…':upload?'导入并创建':'创建并编辑'}</button></div>
 </form></dialog>;
}
