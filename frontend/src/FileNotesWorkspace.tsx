import {useEffect,useMemo,useRef,useState} from 'react';
import {ReadingCards,EntityScope} from './EntityCards';
import {browserDirectoryPicker,FileNotesRepository,fileNoteView,type FileNote,type FileNoteDraft} from './fileNotes';
import JsonReading from './JsonReading';
import FloatingDocumentNote from './FloatingDocumentNote';
import NoteDirectory from './NoteDirectory';
import {StructuredFields} from './StructuredEditor';
import type {Season} from './seasons';
import './fileNotes.css';

type Position={selected:string;query:string;scroll:Record<string,number>};
export type FileNotesState={repo?:FileNotesRepository;positions:Partial<Record<Season,Position>>};
type Props={season:Season;state:FileNotesState;editable:boolean;mobile:boolean;directoryOpen:boolean;closeDirectory:()=>void;onDirty:(value:boolean)=>void;onDocumentNoteDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;allowLeave:()=>boolean};

export default function FileNotes({season,state,editable,mobile,directoryOpen,closeDirectory,onDirty,onDocumentNoteDirty,onBusy,allowLeave}:Props){
 const position=state.positions[season]??={selected:'',query:'',scroll:{}};
 const [selected,setSelected]=useState(position.selected),[query,setQuery]=useState(position.query);
 const [loaded,setLoaded]=useState<FileNote>(),[editing,setEditing]=useState(false),[working,setWorking]=useState(false);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[revision,invalidate]=useState(0);
 const [documentNoteDirty,setDocumentNoteDirty]=useState(false);
 const keepDraft=useRef(false);
 const content=useRef<HTMLDivElement>(null);
 const repo=state.repo,picker=browserDirectoryPicker();
 const entries=useMemo(()=>repo?.entries.filter(row=>(row.seasons??['S1']).includes(season))??[],[repo,revision,season]);
 const currentDraftId=documentNoteDirty&&loaded?.metadata.id===position.selected?loaded?.metadata.id:undefined;
 const displayed=currentDraftId??entries.find(row=>row.id===selected)?.id??entries[0]?.id;
 const documentMissing=!!currentDraftId&&!entries.some(row=>row.id===currentDraftId);
 const note=loaded?.metadata.id===displayed&&loaded?fileNoteView(loaded.metadata,loaded.body,repo?.entries):undefined;
 const rows=useMemo(()=>entries.filter(row=>!query.trim()||[row.title,...(Array.isArray(row.aliases)?row.aliases:[])].some(value=>value.toLowerCase().includes(query.trim().toLowerCase()))).map(row=>fileNoteView(row)),[entries,query]);
 useEffect(()=>{
  if(!repo||!displayed||repo.hasPending)return;
  position.selected=displayed;
  let live=true;
  void repo.load(displayed).then(value=>{if(live)setLoaded(value);}).catch(reason=>{if(live){setLoaded(current=>keepDraft.current&&current?.metadata.id===displayed?current:undefined);setError(reason.message);}});
  return()=>{live=false;};
 },[repo,displayed,revision,position]);
 useEffect(()=>{
  const element=content.current;
  if(!element||!note||editing)return;
  element.scrollTop=position.scroll[note.id]??0;
 },[position,note?.id,note?.revision,editing]);
 useEffect(()=>{if(!editable)setEditing(false);},[editable]);
 function select(id:string){
  if(id===displayed){closeDirectory();return;}
  if(!entries.some(row=>row.id===id)){setError('当前赛季没有这篇关联笔记');return;}
  if(!allowLeave())return;
  setEditing(false);onDirty(false);setError('');setNotice('');position.selected=id;setSelected(id);closeDirectory();
 }
 async function open(){
  if(!picker||!allowLeave())return;
  setWorking(true);onBusy(true);setError('');
  try{
   const directory=await picker({id:'wxq-notes',mode:'read'});
   const opened=await FileNotesRepository.open(directory);
   if(!opened.entries.some(row=>row.id===position.selected)){position.selected='';position.scroll={};}
   state.repo=opened;setSelected(position.selected);setLoaded(undefined);setEditing(false);setNotice('');onDirty(false);invalidate(n=>n+1);
  }catch(e){if(!(e instanceof DOMException&&e.name==='AbortError'))setError((e as Error).message);}
  finally{setWorking(false);onBusy(false);}
 }
 async function reload(){
  if(!repo||(documentNoteDirty?working||!confirm('重新读取文件？当前笔记草稿会保留。'):!allowLeave()))return;
  setWorking(true);onBusy(true);setError('');setNotice('');setEditing(false);onDirty(false);
  try{await repo.refresh();if(!documentNoteDirty)setLoaded(undefined);invalidate(n=>n+1);}catch(e){setError((e as Error).message);}
  finally{setWorking(false);onBusy(false);}
 }
 async function recover(){
  if(!repo||!editable)return;
  setWorking(true);onBusy(true);setError('');setNotice('');
  try{await repo.requestWrite();await repo.recover();setEditing(false);onDirty(false);setNotice('已补全上次保存');invalidate(n=>n+1);}
  catch(e){setError((e as Error).message);}
  finally{setWorking(false);onBusy(false);}
 }
 async function save(draft:FileNoteDraft){
  if(!repo||!loaded||!editable)return;
  await repo.requestWrite();
  try{await repo.save(loaded,draft);}catch(error){if(repo.hasPending)invalidate(n=>n+1);throw error;}
  setNotice('已保存到所选文件夹');setEditing(false);onDirty(false);invalidate(n=>n+1);
 }
 async function saveDocumentNote(text:string){
  if(!repo||!loaded||loaded.metadata.id!==displayed||!editable||editing||working)throw new Error('当前笔记暂时无法保存。');
  setWorking(true);onBusy(true);
  try{await repo.requestWrite();setLoaded(await repo.saveNote(loaded,text));}
  catch(error){if(repo.hasPending)invalidate(n=>n+1);throw error;}
  finally{setWorking(false);onBusy(false);}
 }
 function cancel(){if(allowLeave()){setEditing(false);onDirty(false);}}
 const buttons=<div className="file-note-actions"><button className={repo?'':'primary'} disabled={working||!picker} onClick={()=>void open()}>{repo?'更换文件夹':'选择笔记文件夹'}</button>{repo&&<button disabled={working} onClick={()=>void reload()}>重新读取文件</button>}</div>;
 return <div className="workspace file-notes-workspace">
  {note&&loaded&&<FloatingDocumentNote key={note.id} title={note.title} value={typeof loaded.body.note==='string'?loaded.body.note:''}
   editable={editable&&!editing} disabled={working||repo?.hasPending||documentMissing} onSave={saveDocumentNote}
   onDirty={value=>{keepDraft.current=value;setDocumentNoteDirty(value);onDocumentNoteDirty(value);}}/>}
  {mobile&&directoryOpen&&<div className="directory-backdrop" aria-hidden="true" onClick={closeDirectory}/>}
  <aside id="note-directory-drawer" aria-label="笔记目录" inert={mobile&&!directoryOpen} className={'library '+(directoryOpen?'directory-open':'')}>
   <button className="mobile-directory-close" aria-label="关闭目录" onClick={closeDirectory}>收起目录 ←</button>
   <div className="library-heading"><h2>文件笔记</h2>{repo&&<span>{entries.length} 篇</span>}</div>
   {repo&&<><p className="muted file-note-folder">{repo.name}</p>{buttons}<input className="search" aria-label="搜索文件笔记" placeholder="搜索笔记标题" value={query} onChange={event=>{position.query=event.target.value;setQuery(position.query);}}/><div className="note-list"><NoteDirectory notes={rows} active={displayed??''} onSelect={select}/></div></>}
  </aside>
  <main className="reading file-notes-reading">
   {!repo?<div className="empty file-note-prompt"><h1>打开笔记文件</h1><p>选择项目根目录或其中的 knowledge 文件夹。笔记在浏览器中读取和保存。</p>{picker?buttons:<p role="status">当前浏览器无法打开本地文件夹。请使用支持文件夹访问的 Chrome 或 Edge。</p>}</div>:null}
   {error&&<p role="alert" className="error">{error}</p>}
   {notice&&<p role="status" className="reader-cache-status">{notice}</p>}
   {repo?.hasPending&&<div className="error" role="status">上次保存尚未完成。{editable?<button disabled={working} onClick={()=>void recover()}>恢复上次保存</button>:null}</div>}
   {repo&&!repo.hasPending&&!note&&!error&&<p className="empty">{entries.length?'正在读取文件…':`暂无 ${season} 笔记`}</p>}
   {note&&loaded&&(!repo?.hasPending||editing)&&<EntityScope references={note.entities}>
    <div className="note-heading"><div><p className="note-kind">{({lineup:'阵容攻略',player:'棋手笔记',other:'知识笔记'})[note.type]}</p><h1>{note.title}</h1></div>{editable&&!editing&&<button className="edit-button" disabled={documentNoteDirty||working} onClick={()=>{setNotice('');setEditing(true);}}>编辑笔记</button>}</div>
    {editing&&editable?<div className="content-scroll"><StructuredFields local key={note.id+'|'+note.revision} note={note} onSave={save} onCancel={cancel} onDirty={onDirty} onBusy={onBusy}/></div>:<ReadingCards><div className="content-scroll" key={note.id} ref={content} onScroll={event=>{position.scroll[note.id]=event.currentTarget.scrollTop;}}><JsonReading interactive={false} body={loaded.body} nodes={loaded.body.nodes} note={note} onNote={select}/></div></ReadingCards>}
   </EntityScope>}
  </main>
 </div>;
}
