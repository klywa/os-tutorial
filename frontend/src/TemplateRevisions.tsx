import {useEffect,useState} from 'react';
import {api} from './model';
import {TemplateDialog} from './TemplateEditor';
import {describeTemplateRecord,templateReviewLabel,type TemplateGroup,type TemplateSnapshot} from './templates';

type Revision={id:string;at?:string|null;by?:string|null;value?:TemplateGroup|null;before?:TemplateGroup|null;current?:boolean;restorable:boolean;restored_from?:string|null};
type RestorePreview={revision:string;change:{value:TemplateGroup}|null};
type RestoreResult=TemplateSnapshot|{proposal:unknown};
type Props={group:TemplateGroup;revision:string;canRestore:boolean;onClose:()=>void;onSaved:(result:RestoreResult)=>void};

function describe(group:TemplateGroup|null|undefined){
 if(!group)return '无可显示内容';
 const state=templateReviewLabel(group.review_status);
 const modifier=group.last_modified_by?.kind==='user'?group.last_modified_by.username:'AI';
 return [describeTemplateRecord(group),`审核 ${state}`,`最后修改人 ${modifier??'用户'}`].join('\n');
}

export function TemplateOfficialDescriptions({group}:{group:TemplateGroup}){
 const snapshot=group.entity_snapshot;
 if(!snapshot||!Object.keys(snapshot.entities).length)return null;
 return <details className="template-diff"><summary>保存时的官方描述</summary>
  <p>{snapshot.season} · {snapshot.version??'官方版本未记录'}</p>
  {Object.entries(snapshot.entities).map(([id,data])=>{
   const row=data as {name?:string;missing?:boolean;description?:string;skills?:unknown[]};
   return <section key={id}><strong>{row.name??id}</strong>{row.missing?<p>该赛季官方资料缺失</p>:<><p>{row.description}</p><pre>{JSON.stringify(data,null,2)}</pre></>}</section>;
  })}
 </details>;
}

export default function TemplateRevisions({group,revision,canRestore,onClose,onSaved}:Props){
 const [items,setItems]=useState<Revision[]>([]),[selected,setSelected]=useState<Revision|null>(null);
 const [preview,setPreview]=useState<RestorePreview|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const route='templates/groups/'+encodeURIComponent(group.id);
 useEffect(()=>{
  let active=true;
  void api<{items:Revision[]}>(route+'/revisions').then(result=>{
   if(active){setItems(result.items);setSelected(result.items[0]??null);}
  }).catch(error=>{if(active)setError((error as Error).message);}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;};
 },[route]);
 async function restore(commit=false){
  if(!selected||busy)return;
  setBusy(true);setError('');
  try{
   const body={revision:commit?preview?.revision:revision,revision_id:selected.id};
   if(commit){const result=await api<RestoreResult>(route+'/restore','POST',body);onSaved(result);onClose();}
   else setPreview(await api<RestorePreview>(route+'/restore/preview','POST',body));
  }catch(error){setError((error as Error).message);}
  finally{setBusy(false);}
 }
 return <TemplateDialog title={'修订历史 · '+group.name} wide onClose={()=>{if(!busy)onClose();}}>
  {loading&&<p role="status">正在读取修订历史…</p>}
  {error&&<p role="alert" className="error">{error}</p>}
  {!!items.length&&<label>修订版本<select value={selected?.id??''} disabled={busy} onChange={event=>{setSelected(items.find(item=>item.id===event.target.value)??null);setPreview(null);setError('');}}>
   {items.map(item=><option key={item.id} value={item.id}>{[item.current?'当前版本':item.at?new Date(item.at).toLocaleString():'早期版本',item.by,item.restored_from?'来自回退':null].filter(Boolean).join(' · ')}</option>)}
  </select></label>}
  {selected&&<section className="template-diff"><div>
   <section><h3>{preview?'当前内容':'修改前'}</h3><pre>{describe(preview?group:selected.before)}</pre></section>
   <section><h3>{preview?'回退后内容':'该修订内容'}</h3><pre>{describe(preview?.change?.value??selected.value)}</pre></section>
  </div></section>}
  {selected?.value&&<TemplateOfficialDescriptions group={selected.value}/>}
  {preview&&!preview.change&&<p role="status">该版本与当前内容相同。</p>}
  {selected&&!selected.restorable&&!selected.current&&<p>此记录没有可回退的完整模板内容。</p>}
  <footer>
   <button disabled={busy} onClick={onClose}>关闭</button>
   {canRestore&&selected?.restorable&&(preview?<button className="primary" disabled={busy||!preview.change} onClick={()=>void restore(true)}>确认回退</button>:<button disabled={busy} onClick={()=>void restore()}>预览回退</button>)}
  </footer>
 </TemplateDialog>;
}
