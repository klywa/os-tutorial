import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import {activeWorkspace,cachedEntry,cachedGet,forgetMissingNotes,putCached} from './readerCache';
import {restoreNoteSelection} from './directoryModel';
import type {Note,Options,ReadingDocument} from './types';
export type Catalog={workspace_id:string;format:number;revision:string;ready:boolean;notes:Note[]};
const empty:Options={entities:[],factions:[],sections:{}};
export const detailPath=(id:string,player?:string)=>'notes/'+encodeURIComponent(id)+(player?'?player='+encodeURIComponent(player):'');
export const readingPath=(id:string,player?:string)=>'notes/'+encodeURIComponent(id)+'/reading'+(player?'?player='+encodeURIComponent(player):'');
export function useReaderLoader({selected,player,dirty,onSelect}:{selected:string;player?:string;dirty:boolean;onSelect:(id:string)=>void}){
 const [notes,setNotes]=useState<Note[]>([]),[options,setOptions]=useState<Options>(empty),[detail,setDetail]=useState<Note>(),[reader,setReader]=useState<ReadingDocument|null>(null);
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[readerError,setReaderError]=useState(''),[verified,setVerified]=useState(false),[checking,setChecking]=useState(true),[ready,setReady]=useState(false),[pending,setPending]=useState(false),[catalogRevision,setCatalogRevision]=useState('');
 const [catalogEpoch,bumpCatalog]=useState(0),[noteEpoch,bumpNote]=useState(0),[workspace,setWorkspace]=useState(activeWorkspace);
 const dirtyRef=useRef(dirty),selectedRef=useRef(selected),selectRef=useRef(onSelect),detailRef=useRef(detail),freshCatalog=useRef(false),scopeRef=useRef(''),workspaceRef=useRef(workspace),verifiedRef=useRef(verified);
 dirtyRef.current=dirty;selectedRef.current=selected;selectRef.current=onSelect;detailRef.current=detail;workspaceRef.current=workspace;verifiedRef.current=verified;
 useEffect(()=>{let live=true;const controller=new AbortController();
  function apply(cat:Catalog,fresh:boolean){if(!live||!cat||!Array.isArray(cat.notes)||typeof cat.workspace_id!=='string')return;if(!fresh&&freshCatalog.current)return;
   if(fresh&&workspaceRef.current&&workspaceRef.current!==cat.workspace_id&&dirtyRef.current){setVerified(false);setPending(true);setError('工作区已变化；现有草稿保留，请取消或导出草稿后重试。');return;}if(fresh)freshCatalog.current=true;
   setWorkspace(cat.workspace_id);setCatalogRevision(cat.revision);setNotes(cat.notes);setReady(cat.ready);setLoading(false);
   const next=restoreNoteSelection(cat.notes,selectedRef.current,player);
   if(!dirtyRef.current&&next!==selectedRef.current)selectRef.current(next);
   if(fresh)void forgetMissingNotes(new Set(cat.notes.map(n=>n.id)),cat.workspace_id);
  }
  if(!freshCatalog.current)void cachedEntry<Catalog>('notes/catalog').then(c=>{if(c)apply(c.value,false);});
  void cachedEntry<Options>('options').then(c=>{if(live&&c&&!freshCatalog.current)setOptions(c.value);});
  const refresh=async()=>{try{const cat=await cachedGet<Catalog>('notes/catalog',{signal:controller.signal});if(!live)return;apply(cat,true);setError('');void cachedGet<Options>('options',{workspace:cat.workspace_id,signal:controller.signal}).then(o=>{if(live)setOptions(o);}).catch(()=>{});}catch(e){if(live&&!controller.signal.aborted){setError((e as Error).message);setLoading(false);}}};
  void refresh();const timer=setInterval(()=>void refresh(),15000);
  return()=>{live=false;controller.abort();clearInterval(timer);};
 },[catalogEpoch]);
 useEffect(()=>{if(!ready&&!loading&&!error){const timer=setTimeout(()=>bumpCatalog(n=>n+1),1000);return()=>clearTimeout(timer);}},[ready,loading,error,catalogEpoch]);
 useEffect(()=>{if(!selected){setDetail(undefined);setReader(null);setChecking(false);return;}let live=true;const controller=new AbortController();const notePath=detailPath(selected,player),viewPath=readingPath(selected,player);let networkDone=false;
  const previous=detailRef.current;const scope=workspace+'|'+selected+'|'+(player??'');const same=previous?.id===selected&&scopeRef.current===scope;scopeRef.current=scope;
  if(!same){setDetail(undefined);setReader(null);setVerified(false);}setChecking(true);setReaderError('');setPending(false);
  void Promise.all([cachedEntry<Note>(notePath,workspace),cachedEntry<ReadingDocument>(viewPath,workspace)]).then(([n,v])=>{if(!live||networkDone||dirtyRef.current)return;if(n?.value?.id&&v?.value?.note_id===n.value.id&&v.value.revision===n.value.revision&&Array.isArray(v.value.sections)){setDetail(n.value);setReader(v.value);setVerified(false);}});
  const refresh=async()=>{try{let [note,view]=await Promise.all([cachedGet<Note>(notePath,{workspace,signal:controller.signal}),cachedGet<ReadingDocument>(viewPath,{workspace,signal:controller.signal})]);if(note.revision!==view.revision){[note,view]=await Promise.all([cachedGet<Note>(notePath,{workspace,signal:controller.signal}),cachedGet<ReadingDocument>(viewPath,{workspace,signal:controller.signal})]);}
   if(!live)return;networkDone=true;if(workspace&&activeWorkspace()&&workspace!==activeWorkspace())throw new Error('工作区已变化，草稿已保留');if(note.revision!==view.revision)throw new Error('笔记正在更新，请重试');
   if(dirtyRef.current){if(note.revision!==detailRef.current?.revision)setPending(true);else setVerified(true);return;}
   setDetail(note);setReader(view);setVerified(true);setReaderError('');
  }catch(e){if(live&&!controller.signal.aborted){networkDone=true;setVerified(false);setReaderError((e as Error).message+'；缓存可继续阅读，确认最新版本后可编辑。');}}finally{if(live)setChecking(false);}};
  void refresh();const timer=setInterval(()=>{void api<{revision:string}>('notes/'+encodeURIComponent(selected)+'/revision').then(row=>{if(!live)return;if(row.revision!==detailRef.current?.revision){if(dirtyRef.current)setPending(true);else void refresh();}else if(!verifiedRef.current){void refresh();}else{setReaderError('');}}).catch(()=>{if(live){setVerified(false);setReaderError('连接中断，缓存可继续阅读；请重试后编辑。');}});},3000);
  return()=>{live=false;controller.abort();clearInterval(timer);};
 },[selected,player,workspace,noteEpoch]);
 useEffect(()=>{if(!dirty&&pending){bumpCatalog(n=>n+1);bumpNote(n=>n+1);}},[dirty,pending]);
 function accept(note:Note){scopeRef.current=workspace+'|'+note.id+'|'+(note.id===selected?(player??''):'');setDetail(note);setVerified(true);setPending(false);setNotes(rows=>rows.some(n=>n.id===note.id)?rows.map(n=>n.id===note.id?note:n):[...rows,note]);void putCached(detailPath(note.id,note.id===selected?player:undefined),note,workspace);bumpNote(n=>n+1);bumpCatalog(n=>n+1);}
 return {notes,setNotes,options,detail,reader,setReader,loading,error,readerError,verified,checking,ready,pending,workspace,catalogRevision,reload:()=>{bumpCatalog(n=>n+1);bumpNote(n=>n+1);},accept};
}
