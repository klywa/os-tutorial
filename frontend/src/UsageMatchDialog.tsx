import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import {initialMatch,matchingOptions,type UsageMatchData,type UsagePair} from './usageMatchModel';
import './usageMatches.css';

type FieldsProps={data:UsageMatchData;pair:UsagePair;noteId:string;query:string;busy:boolean;available?:boolean;onQuery:(v:string)=>void;onNote:(v:string)=>void;onPair:(id:string)=>void;onSave:()=>void;onRestore:()=>void;onClose:()=>void};
export function UsageMatchFields({data,pair,noteId,query,busy,available=true,onQuery,onNote,onPair,onSave,onRestore,onClose}:FieldsProps){
 const choices=matchingOptions(data,pair,query),chosen=data.notes.find(n=>n.id===noteId&&n.player_id===pair.player_id);
 return <form onSubmit={e=>{e.preventDefault();if(chosen&&available&&!busy)onSave();}} onKeyDown={e=>{if(e.key==='Enter'&&e.target instanceof HTMLInputElement)e.preventDefault();}}>
  <div className="usage-match-body"><label>外网阵容＋棋手<select aria-label="外网阵容＋棋手" value={pair.id} disabled={busy} onChange={e=>onPair(e.target.value)}>{!available&&<option value={pair.id}>{pair.source_name}－{pair.player_name}（已退出当前榜单）</option>}{data.pairs.map(p=><option key={p.id} value={p.id}>第{p.rank}名　{p.source_name}－{p.player_name}</option>)}</select></label>
   <div className="usage-match-columns"><section className="usage-match-source"><h3>外网英雄组成</h3><p>{pair.hero_names?.join('、')||pair.heroes.join('、')}</p><dl><dt>棋手</dt><dd>{pair.player_name}</dd><dt>目前指定</dt><dd>{pair.manual_note_id?(data.notes.find(n=>n.id===pair.manual_note_id)?.title??'原笔记已不可用'):'自动匹配'}</dd></dl>{pair.manual_error&&<p className="usage-match-warning">{pair.manual_error}</p>}<p className="muted">指定后优先使用你的选择。网站每日更新会保留指定；组成变化时会提醒重新确认。</p></section>
    <section><h3 id="usage-match-options-title">知识库匹配项</h3><p className="muted">只列出同一棋手的阵容笔记。</p><input aria-label="搜索知识库阵容笔记" type="search" value={query} disabled={busy} onChange={e=>onQuery(e.target.value)} placeholder="搜索阵容名称" autoFocus/>
     <div className="usage-match-options" role="radiogroup" aria-labelledby="usage-match-options-title">{choices.map(note=><label key={note.id} className={'usage-match-option '+(note.id===noteId?'chosen':'')}><input type="radio" name="usage-match-note" value={note.id} checked={note.id===noteId} disabled={busy} onChange={()=>onNote(note.id)}/><span>{note.title}{pair.candidates?.includes(note.title)&&<small>候选</small>}</span></label>)}{!choices.length&&<p className="empty">{data.notes.some(n=>n.player_id===pair.player_id)?'没有符合搜索条件的笔记':'知识库暂无该棋手的阵容笔记'}</p>}</div>
     <div className="usage-match-selection"><strong>已选择：{chosen?.title??(noteId?'此前选择已不可用':'尚未选择')}</strong>{chosen?.formations.slice(0,3).map((heroes,i)=><p key={i}>组成：{heroes.join('、')}</p>)}{chosen&&chosen.formations.length>3&&<small>另有{chosen.formations.length-3}组组成</small>}{chosen&&!chosen.formations.length&&<p className="muted">该笔记未配置结构化组成，可按正文判断后指定。</p>}</div>
    </section></div>{!available&&<p className="usage-match-warning">该组合已退出当前榜单，选择仍保留；可切换到其他外网阵容。</p>}
  </div><footer className="usage-match-footer"><button type="button" disabled={busy||!available||!pair.manual_note_id} onClick={onRestore}>恢复自动匹配</button><span/><button type="button" disabled={busy} onClick={onClose}>关闭</button><button type="submit" className="primary" disabled={busy||!available||!chosen}>{busy?'正在保存…':'保存匹配'}</button></footer>
 </form>;
}

export default function UsageMatchDialog({initialPairId,onClose,onSaved}:{initialPairId:string;onClose:()=>void;onSaved:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),mounted=useRef(true),request=useRef(0),pairRef=useRef(initialPairId);
 const [data,setData]=useState<UsageMatchData|null>(null),[held,setHeld]=useState<UsagePair|null>(null),[pairId,setPairId]=useState(initialPairId);
 const [noteId,setNoteId]=useState(''),[baseline,setBaseline]=useState(''),[query,setQuery]=useState('');
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const noteRef=useRef('');
 const pair=data?.pairs.find(p=>p.id===pairId)??held,available=!!data?.pairs.some(p=>p.id===pairId);
 function chooseNote(id:string){noteRef.current=id;setNoteId(id);setMessage('');}
 function leave(){return !saving&&(noteRef.current===baseline||confirm('当前匹配选择尚未保存，是否放弃？'));}
 function close(){if(leave())onClose();}
 async function load(preserve:boolean){
  const ticket=++request.current;setLoading(true);
  try{
   const fresh=await api<UsageMatchData>('dashboard/usage/matches');if(!mounted.current||ticket!==request.current)return;
   const chosen=fresh.pairs.find(p=>p.id===pairRef.current)??(!preserve?fresh.pairs[0]:undefined);
   setData(fresh);setError('');
   if(chosen){pairRef.current=chosen.id;setPairId(chosen.id);setHeld(chosen);setBaseline(initialMatch(chosen));if(!preserve)chooseNote(initialMatch(chosen));}
   if(preserve)setMessage('列表已刷新，当前选择仍保留；请核对后保存。');
  }catch(e){if(mounted.current&&ticket===request.current)setError((e as Error).message);}
  finally{if(mounted.current&&ticket===request.current)setLoading(false);}
 }
 useEffect(()=>{mounted.current=true;dialog.current?.showModal();void load(false);return()=>{mounted.current=false;request.current++;};},[]);
 function changePair(id:string){
  if(!leave())return;const next=data?.pairs.find(p=>p.id===id);if(!next)return;
  pairRef.current=id;setPairId(id);setHeld(next);chooseNote(initialMatch(next));setBaseline(initialMatch(next));setQuery('');setError('');setMessage('');
 }
 async function save(restore=false){
  if(!data||!pair||!available||saving)return;setSaving(true);setError('');setMessage('');
  try{
   const saved=await api<{revision:string;assignment:{note_id:string}|null}>('dashboard/usage/matches','PUT',{revision:data.revision,pair_id:pair.id,pair_revision:pair.pair_revision,note_id:restore?null:noteId});
   if(!mounted.current)return;
   const updated={...pair,manual_note_id:saved.assignment?.note_id??null,manual_error:''};
   setData(current=>current?{...current,revision:saved.revision,pairs:current.pairs.map(p=>p.id===pair.id?updated:p)}:current);setHeld(updated);
   const selected=restore?(pair.automatic_note_id??''):noteId;chooseNote(selected);setBaseline(selected);
   onSaved();setMessage(restore?'已恢复自动匹配。':'匹配已保存，可以继续指定下一项。');
  }catch(e){if(mounted.current){const message=(e as Error).message;setError(message.includes('当前选择仍保留')?message:message+'；当前选择仍保留。');}}
  finally{if(mounted.current)setSaving(false);}
 }
 return <dialog ref={dialog} className="usage-match-dialog" aria-label="指定外网阵容匹配" onCancel={e=>{e.preventDefault();close();}}><header className="usage-match-heading"><div><h2>指定外网阵容匹配</h2><p>逐个选择知识库笔记，保存后立即更新覆盖情况。</p></div><button aria-label="关闭匹配浮窗" type="button" disabled={saving} onClick={close}>×</button></header>
  {error&&<div className="usage-match-feedback"><p className="error" role="alert">{error}</p><button disabled={saving||loading} onClick={()=>void load(true)}>刷新匹配列表，保留选择</button></div>}{message&&<p className="usage-match-message" role="status">{message}</p>}
  {data&&pair?<UsageMatchFields data={data} pair={pair} noteId={noteId} query={query} busy={saving||loading} available={available} onQuery={setQuery} onNote={chooseNote} onPair={changePair} onSave={()=>void save()} onRestore={()=>void save(true)} onClose={close}/>:<div className="usage-match-body"><p className="empty">{loading?'正在载入匹配列表…':'当前榜单没有可指定的外网组合。'}</p><button disabled={saving} onClick={close}>关闭</button></div>}
 </dialog>;
}
