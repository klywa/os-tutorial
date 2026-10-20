import TopicPicker from './TopicPicker';
import {TagInput} from './SourceAnnotations';
import type {SaveSource} from './annotationSaving';
import {normalizeTags} from './annotationSaving';
import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import type {Source,TopicCatalog,TopicKey} from './types';
type Transcript={text:string;revision:string;manual_edit:boolean};
const fields=[['title','标题'],['url','内容链接'],['author','UP主名称'],['uid','UID'],['space_url','空间URL'],['published','发布日期'],['view_count','播放量'],['duration','时长（秒）'],['collected_at','采集时间']] as const;
export default function SourceEditor({source,onClose,onRefresh,catalog,onSave,tagChoices}:{source:Source;onClose:()=>void;onRefresh:()=>Promise<void>;catalog:TopicCatalog;onSave:SaveSource;tagChoices:string[]}){
 const dialog=useRef<HTMLDialogElement>(null);
 const baseline=useRef(source);
 const [dirtyTopics,setDirtyTopics]=useState<TopicKey[]>([]),[manualTopics,setManualTopics]=useState(source.topic_manual??[]);
 const topicLabels:Record<TopicKey,string>={topic_players:'主题棋手',topic_lineups:'主题阵容',topic_heroes:'主题英雄',topic_cards:'主题卡牌'};
 async function restore(key:TopicKey){setBusy(true);setError('');try{const saved=await onSave({...source,revision},{restore_topics:[key]});setRevision(saved.revision??'');setDraft(d=>({...d,[key]:saved[key]}));setManualTopics(saved.topic_manual??[]);setDirtyTopics(d=>d.filter(k=>k!==key));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const [tab,setTab]=useState('metadata'),[draft,setDraft]=useState({...source}),[revision,setRevision]=useState(source.revision??'');
 const [keywords,setKeywords]=useState((source.keywords??[]).join('\n')),[batches,setBatches]=useState((source.batches??[]).join('\n'));
 const [transcript,setTranscript]=useState<Transcript|null>(null),[text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>{dialog.current?.showModal();},[]);
 useEffect(()=>{if(tab!=='transcript'||transcript||!source.transcript_path)return;let alive=true;setBusy(true);void api<Transcript>(`sources/${encodeURIComponent(source.id)}/transcript`).then(t=>{if(alive){setTranscript(t);setText(t.text);}}).catch(e=>{if(alive)setError(e.message);}).finally(()=>{if(alive)setBusy(false);});return()=>{alive=false;};},[tab]);
 async function save(){setBusy(true);setError('');setMessage('');try{
  if(tab==='metadata'){
   const values=Object.fromEntries(fields.map(([key])=>[key,draft[key]??(['view_count','duration'].includes(key)?null:'')]));
   const all={...values,...Object.fromEntries(dirtyTopics.map(k=>[k,draft[k]??[]])),ignored:!!draft.ignored,keywords:normalizeTags(keywords.split('\n')),batches:normalizeTags(batches.split('\n')),notes:draft.notes??'',tags:normalizeTags(draft.tags??[])};
   const changed=Object.fromEntries(Object.entries(all).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(baseline.current[key as keyof Source]??(Array.isArray(value)?[]:typeof value==='boolean'?false:value===null?null:''))));
   const saved=await onSave({...source,revision},changed);
   baseline.current=saved;setDraft({...saved});setKeywords((saved.keywords??[]).join('\n'));setBatches((saved.batches??[]).join('\n'));setRevision(saved.revision??'');setManualTopics(saved.topic_manual??[]);setDirtyTopics([]);setMessage('资料已保存');
  }else if(transcript){const saved=await api<Transcript>(`sources/${encodeURIComponent(source.id)}/transcript`,'PUT',{text,revision:transcript.revision});setTranscript(saved);setMessage('文字稿已保存，人工编辑内容待核对。');}
  if(tab==='transcript')await onRefresh();
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 function value(key:typeof fields[number][0]){if(key==='collected_at')return draft.collected_at?.replace(/(?:Z|[+-]\d\d:\d\d)$/,'').slice(0,19)??'';return draft[key]??'';}
 return <dialog ref={dialog} className="source-editor creator-dialog" aria-label="编辑内容" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><div className="section-heading"><h2>编辑内容</h2><button aria-label="关闭编辑内容" disabled={busy} onClick={onClose}>×</button></div><small className="muted">{source.id}</small>
  <div className="acquisition-tabs" role="tablist" aria-label="编辑内容类型">{[['metadata','资料'],['transcript','文字稿']].map(([id,label])=><button type="button" role="tab" aria-selected={tab===id} className={tab===id?'selected':''} disabled={busy} key={id} onClick={()=>{setTab(id);setError('');setMessage('');}}>{label}</button>)}</div>
  {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="notice" role="status">{message}</p>}
  <form onSubmit={e=>{e.preventDefault();void save();}}><fieldset className="source-editor-form" disabled={busy}>{tab==='metadata'?<><div className="source-editor-fields">{fields.map(([key,label])=><label key={key}>{label}<input aria-label={label} type={['view_count','duration'].includes(key)?'number':key==='published'?'date':key==='collected_at'?'datetime-local':['url','space_url'].includes(key)?'url':'text'} min={['view_count','duration'].includes(key)?0:undefined} step={key==='duration'?'any':undefined} required={key==='url'} value={value(key)} onChange={e=>setDraft({...draft,[key]:['view_count','duration'].includes(key)?(e.target.value===''?null:Number(e.target.value)):e.target.value})}/></label>)}<label>关键词，每行一个<textarea value={keywords} onChange={e=>setKeywords(e.target.value)}/></label><label>展示批次，每行一个<textarea value={batches} onChange={e=>setBatches(e.target.value)}/></label></div><div className="source-topic-fields">{(Object.keys(topicLabels) as TopicKey[]).map(key=><div key={key}><TopicPicker label={topicLabels[key]} choices={catalog[key]} value={draft[key]??[]} onChange={ids=>{setDraft({...draft,[key]:ids});setDirtyTopics([...new Set([...dirtyTopics,key])]);}}/>{['topic_players','topic_lineups'].includes(key)&&manualTopics.includes(key)&&<button type="button" className="link-button" disabled={busy} onClick={()=>void restore(key)}>恢复自动值</button>}</div>)}</div><label className="check-label"><input type="checkbox" checked={!!draft.ignored} onChange={e=>setDraft({...draft,ignored:e.target.checked})}/>忽略此内容（不进入筛选、全选和路径复制）</label><div className="source-editor-tags"><strong>标签</strong><TagInput value={draft.tags??[]} choices={tagChoices} onChange={tags=>setDraft({...draft,tags})}/></div><label>备注<textarea rows={3} value={draft.notes??''} onChange={e=>setDraft({...draft,notes:e.target.value})}/></label><p className="muted">展示批次不改变任务归属；其他视频请新增为独立内容。</p></>:source.transcript_path?<><p className="muted">保存前备份原文，保留ASR材料；人工修改仍需核对。</p><label>文字稿正文<textarea className="transcript-input" rows={18} disabled={!transcript} value={text} onChange={e=>setText(e.target.value)}/></label></>:<p className="muted">文字稿尚未生成，完成转写后可编辑。</p>}
  <div className="source-editor-actions"><button className="primary" disabled={busy||(tab==='transcript'&&!transcript)}>{busy?'保存中…':tab==='metadata'?'保存资料':'保存文字稿'}</button><button type="button" disabled={busy} onClick={onClose}>关闭</button></div></fieldset></form></dialog>;
}
