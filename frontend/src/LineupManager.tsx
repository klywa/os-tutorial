import {lineupLabel} from './lineupNames';
import LineupNaming from './LineupNaming';
import WebsiteVariants from './WebsiteVariants';
import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import TopicPicker from './TopicPicker';
import LineupQuickList from './LineupQuickList';
import {useLineupConfirm} from './LineupConfirm';
import {changeNameDraft,filterManagedLineups,namePayload,detailAfterSave,prefillDetail} from './lineupEditing';
import type {NameDrafts,NameDraft,ListStatus} from './lineupEditing';
import {useCards} from './EntityCards';
import type {Lineup,Note} from './types';
type Preview={token:string;scanned:number;merged:number;variant_scanned?:number;variant_links?:number;variant_unique?:number;errors:{error:string}[];items:Lineup[];changes:{name:string;action:string}[];scope:{version:string;time:number}};
type Suggestion={lineup:string;note:string;title:string;reason:string};
export default function LineupManager({onChanged,onDirty,initialId}:{onChanged:()=>Promise<void>;onDirty?:(value:boolean)=>void;initialId?:string}){
 const [roster,setRoster]=useState<Lineup[]>([]),[notes,setNotes]=useState<Note[]>([]),[suggestions,setSuggestions]=useState<Suggestion[]>([]),[edit,setEdit]=useState<Lineup|null>(null),[aliases,setAliases]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[query,setQuery]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[target,setTarget]=useState('');
 const cards=useCards();const heroes=cards.filter(c=>c.category==='heroes'&&!c.awakened);const [variantHeroes,setVariantHeroes]=useState<string[]>([]);
 async function refresh(){const [r,n,s]=await Promise.all([api<Lineup[]>('topics/lineups'),api<Note[]>('notes'),api<Suggestion[]>('topics/lineup-suggestions')]);setRoster(r);setNotes(n);setSuggestions(s);}
 useEffect(()=>{void refresh().catch(e=>setError(e.message));},[]);
 async function act(fn:()=>Promise<unknown>){setBusy(true);setError('');try{await fn();await refresh();await onChanged();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const {ask,confirmation}=useLineupConfirm();
 const [drafts,setDrafts]=useState<NameDrafts>({}),[status,setStatus]=useState<ListStatus>('all'),[conflicts,setConflicts]=useState<string[]>([]),[notice,setNotice]=useState(''),[editBase,setEditBase]=useState('');
 const detailDirty=!!edit&&JSON.stringify({edit,aliases})!==editBase;
 const dirty=!!Object.keys(drafts).length||detailDirty;
 useEffect(()=>onDirty?.(dirty),[dirty,onDirty]);
 useEffect(()=>{if(!dirty)return;const handler=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',handler);return()=>window.removeEventListener('beforeunload',handler);},[dirty]);
 const seedUsed=useRef(false),detailForm=useRef<HTMLFormElement>(null);
 useEffect(()=>{if(initialId&&!seedUsed.current&&roster.length){const r=roster.find(r=>r.id===initialId&&!r.deleted_at&&!r.merged_into);if(r){seedUsed.current=true;choose(r);}}},[roster,initialId]);
 function clearDraft(id:string){setDrafts(d=>{const next={...d};delete next[id];return next;});setConflicts(c=>c.filter(x=>x!==id));}
 async function choose(r:Lineup,saved=false){
  if(!saved&&detailDirty&&!await ask('详细编辑有未保存修改，放弃这些修改吗？'))return;
  const prepared=prefillDetail(r,saved?undefined:drafts[r.id]);
  setEdit(prepared.edit);setAliases(prepared.aliases);setEditBase(prepared.base);setVariantHeroes([]);setTarget('');setError('');requestAnimationFrame(()=>detailForm.current?.scrollIntoView({block:'start'}));
 }
 function adoptRelated(row:Lineup,savedFields:string[]){
  if(!edit)return;const base=JSON.parse(editBase) as {edit:Lineup;aliases:string};const merged=detailAfterSave(edit,aliases,base.edit,base.aliases,row,savedFields);
  setEdit(merged.edit);setAliases(merged.aliases);setEditBase(JSON.stringify({edit:row,aliases:(row.aliases??[]).join('\n')}));
  setDrafts(d=>d[row.id]?{...d,[row.id]:{...d[row.id],revision:row.revision}}:d);
 }
 function updateDraft(row:Lineup,patch:Partial<Pick<NameDraft,'common_name'|'aliases'|'text'>>){setDrafts(d=>changeNameDraft(d,row,patch));setNotice('');}
 async function saveAll(){
  if(detailDirty){setError('请先保存或取消详细编辑，再批量保存名称。');return;}
  setBusy(true);setError('');setConflicts([]);
  try{
   const response=await fetch('/api/topics/lineups/batch',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:namePayload(drafts)})});const data=await response.json();
   if(!response.ok){setConflicts(data.lineup_ids??[]);throw new Error(data.error??'保存失败，草稿保留');}
   setDrafts({});setRoster(data);setNotice('全部名称修改已保存');if(edit){const r=(data as Lineup[]).find(r=>r.id===edit.id);if(r)choose(r,true);}await onChanged();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function trash(r:Lineup,restore=false){
  if(detailDirty){setError('请先保存或取消详细编辑，再删除或恢复。');return;}
  if(!restore&&!await ask('将“'+lineupLabel(r)+'”移入已删除？已有笔记、主题和文件保留。'+(drafts[r.id]?'此行未保存的名称修改将放弃。':'')))return;
  await act(async()=>{const rows=await api<Lineup[]>('topics/lineups/'+encodeURIComponent(r.id)+(restore?'/restore':''),restore?'POST':'DELETE',{revision:r.revision});setRoster(rows);clearDraft(r.id);if(edit?.id===r.id){setEdit(null);setEditBase('');}setNotice(restore?'阵容已恢复':'已移入已删除，可随时恢复');});
 }
 const visible=filterManagedLineups(roster,query,status,drafts);
 const commonCounts=new Map<string,number>();for(const r of roster.filter(r=>!r.deleted_at&&!r.merged_into)){const n=(drafts[r.id]?.common_name??r.common_name??'').trim();if(n)commonCounts.set(n,(commonCounts.get(n)??0)+1);}
 const duplicates=[...commonCounts].filter(([,n])=>n>1).map(([n])=>n);
 return <div className="lineup-manager">{confirmation}<p className="muted">直接填写常用名与别名，修改多行后统一保存。常用名为空时显示原名。</p>{error&&<p className="error" role="alert">{error}{conflicts.length>0&&<><br/>{conflicts.map(id=>roster.find(r=>r.id===id)?.name||id).join('、')}<button disabled={busy} onClick={()=>void act(async()=>{const rows=await api<Lineup[]>('topics/lineups');setRoster(rows);})}>刷新服务器资料，保留草稿</button>{conflicts.map(id=><button key={id} disabled={busy} onClick={async()=>{const latest=roster.find(r=>r.id===id);if(latest&&await ask('保留本行草稿，使用刚刷新的修订号再次提交？请先核对服务器资料。'))setDrafts(d=>({...d,[id]:{...d[id],revision:latest.revision}}));}}>核对后重试：{roster.find(r=>r.id===id)?.name||id}</button>)}</>}</p>}{notice&&<p role="status" className="jade">{notice}</p>}
 <div className="lineup-manager-toolbar"><input aria-label="搜索阵容名单" placeholder="搜索原名、常用名、别名或英雄" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="阵容状态" value={status} onChange={e=>setStatus(e.target.value as ListStatus)}><option value="all">全部未删除</option><option value="enabled">启用</option><option value="disabled">停用</option><option value="deleted">已删除</option></select><button disabled={busy} onClick={()=>choose({id:'',name:'',heroes:[],note_ids:[],enabled:true,sort_order:roster.length})}>新增阵容</button></div>
 <div className="lineup-batch-bar"><span>{Object.keys(drafts).length?`已修改 ${Object.keys(drafts).length} 套`:`${visible.length} 套阵容`}</span><button className="primary" disabled={busy||!Object.keys(drafts).length||detailDirty} onClick={()=>void saveAll()}>保存全部</button><button disabled={busy||!Object.keys(drafts).length} onClick={async()=>{if(await ask('放弃所有列表名称草稿？')){setDrafts({});setConflicts([]);}}}>放弃修改</button></div>
 {duplicates.length>0&&<p className="lineup-name-warning">同名提示：{duplicates.join('、')}。不同组成保留独立阵容，主题匹配有歧义时需确认。</p>}
 <LineupQuickList rows={visible} drafts={drafts} conflicts={conflicts} busy={busy} editingId={edit?.id} onDraft={updateDraft} onEdit={r=>choose(r)} onDelete={r=>void trash(r)} onRestore={r=>void trash(r,true)}/>
 <details className="lineup-advanced"><summary>网站同步与命名建议</summary><button disabled={busy||dirty} onClick={()=>void act(async()=>setPreview(await api<Preview>('topics/lineups/preview','POST',{})))}>从网站同步／预览</button>
 {preview&&<section className="lineup-import-preview"><h3>同步预览</h3><p>{preview.scope.version} · 最近{preview.scope.time}天 · 扫描{preview.scanned}，合并{preview.merged}，异常{preview.errors.length}，主阵容{preview.items.length}；变阵扫描{preview.variant_scanned??0}，有效关联{preview.variant_links??0}，去重组成{preview.variant_unique??0}</p><details><summary>查看差异与异常</summary>{preview.changes.map((c,i)=><p key={i}>{c.action}：{c.name}</p>)}{preview.errors.map((e,i)=><p key={i}>{e.error}</p>)}</details><button disabled={busy} onClick={()=>void act(async()=>{await api('topics/lineups/apply','POST',{token:preview.token});setPreview(null);})}>应用导入，保留人工值</button><button disabled={busy} onClick={()=>setPreview(null)}>取消</button></section>}
 <fieldset className="lineup-form-fields" disabled={busy||dirty}><LineupNaming roster={roster.filter(r=>!r.deleted_at&&!r.merged_into)} onChanged={async()=>{await refresh();await onChanged();}}/></fieldset></details>
 {edit&&<form ref={detailForm} className="lineup-form" onSubmit={e=>{e.preventDefault();void act(async()=>{const result=await api<Lineup[]>('topics/lineups',edit.id?'PUT':'POST',{...edit,aliases:aliases.split('\n')});const row=result.find(r=>r.id===edit.id)||result.find(r=>r.name===edit.name);if(row){clearDraft(edit.id);adoptRelated(row,['name','common_name','aliases','heroes','sort_order','enabled']);setNotice('阵容资料已保存；笔记及组合关联使用各自保存按钮。');}});}}><fieldset className="lineup-form-fields" disabled={busy}><h3>{edit.id?'编辑阵容':'新增阵容'}</h3><label>原网站名／登记名<input required value={edit.name} onChange={e=>setEdit({...edit,name:e.target.value})}/></label><label>常用名（优先显示）<input value={edit.common_name??''} onChange={e=>setEdit({...edit,common_name:e.target.value})}/></label><TopicPicker label="完整英雄成员" choices={heroes} value={edit.heroes} onChange={ids=>setEdit({...edit,heroes:ids})}/><label>已确认别称，每行一个<textarea value={aliases} onChange={e=>setAliases(e.target.value)}/></label><label>目录顺序<input type="number" min={0} value={edit.sort_order??0} onChange={e=>setEdit({...edit,sort_order:Number(e.target.value)})}/></label><label className="check-label"><input type="checkbox" checked={edit.enabled!==false} onChange={e=>setEdit({...edit,enabled:e.target.checked})}/>启用此阵容</label><div className="action-line"><button disabled={busy}>保存阵容资料</button><button type="button" disabled={busy} onClick={async()=>{if(!detailDirty||await ask('放弃详细编辑的未保存修改？')){setEdit(null);setEditBase('');}}}>取消编辑</button></div>
 {edit.id&&<><WebsiteVariants lineups={[edit]}/><details className="variant-editor"><summary>维护变阵成员与归属</summary><p className="muted">仅调整当前主阵容下的变阵，不建立独立笔记。</p>{(edit.variants??[]).map(v=><div className="action-line" key={v.id}><span>{v.heroes.map(id=>cards.find(c=>c.id===id)?.name||id).join('、')}</span><button type="button" onClick={()=>setEdit({...edit,variants:edit.variants!.filter(x=>x.id!==v.id)})}>移除此关联</button></div>)}<TopicPicker label="新增变阵成员" choices={heroes} value={variantHeroes} onChange={setVariantHeroes}/><button type="button" disabled={!variantHeroes.length} onClick={()=>{if(!(edit.variants??[]).some(v=>v.heroes.length===variantHeroes.length&&v.heroes.every(id=>variantHeroes.includes(id))))setEdit({...edit,variants:[...edit.variants??[],{id:'draft:'+variantHeroes.join(','),heroes:variantHeroes}]});setVariantHeroes([]);}}>加入当前主阵容</button><button type="button" disabled={busy} onClick={()=>void act(async()=>{const rows=await api<Lineup[]>('topics/lineups/variants','PUT',{lineup:edit.id,revision:edit.revision,variants:edit.variants??[]});adoptRelated(rows.find(r=>r.id===edit.id)!,['variants']);})}>保存变阵关联</button></details><h3>关联笔记</h3><div className="lineup-note-options">{notes.filter(n=>n.type==='lineup').map(n=><label className="check-label" key={n.id}><input type="checkbox" checked={edit.note_ids.includes(n.id)} onChange={e=>setEdit({...edit,note_ids:e.target.checked?[...edit.note_ids,n.id]:edit.note_ids.filter(id=>id!==n.id)})}/>{n.title}{suggestions.some(s=>s.lineup===edit.id&&s.note===n.id)&&<small>（建议关联，待确认）</small>}</label>)}</div><button type="button" disabled={busy} onClick={()=>void act(async()=>{const rows=await api<Lineup[]>('topics/lineups/bind','PUT',{lineup:edit.id,note_ids:edit.note_ids,revision:edit.revision});adoptRelated(rows.find(r=>r.id===edit.id)!,['note_ids']);})}>确认保存笔记关联</button><details className="lineup-merge"><summary>合并到其他阵容</summary><p>历史主题与笔记关联统一指向目标，当前项停用。</p><select aria-label="合并目标阵容" value={target} onChange={e=>setTarget(e.target.value)}><option value="">选择目标</option>{roster.filter(r=>r.id!==edit.id&&r.enabled&&!r.merged_into).map(r=><option key={r.id} value={r.id}>{lineupLabel(r)}（{r.heroes.map(id=>cards.find(c=>c.id===id)?.name||id).join('、')}）</option>)}</select><button type="button" disabled={busy||!target||detailDirty||!!drafts[edit.id]} onClick={()=>void act(async()=>{await api('topics/lineups/merge','POST',{source:edit.id,target,source_revision:edit.revision,target_revision:roster.find(r=>r.id===target)?.revision});setEdit(null);})}>确认合并并保留历史引用</button></details></>}
 </fieldset></form>}
 </div>;
}
export function LineupDialog({onClose,onChanged,initialId}:{onClose:()=>void;onChanged:()=>Promise<void>;initialId?:string}){const dialog=useRef<HTMLDialogElement>(null);const [dirty,setDirty]=useState(false);const {ask,confirmation}=useLineupConfirm();useEffect(()=>{dialog.current?.showModal();},[]);async function close(){if(!dirty||await ask('有未保存的阵容修改，放弃并关闭吗？'))onClose();}return <dialog className="creator-dialog lineup-dialog" aria-label="阵容名单管理" ref={dialog} onCancel={e=>{e.preventDefault();close();}}><div className="section-heading"><h2>阵容名单管理</h2><button aria-label="关闭阵容管理" onClick={close}>×</button></div><LineupManager onChanged={onChanged} onDirty={setDirty} initialId={initialId}/>{confirmation}</dialog>;}
