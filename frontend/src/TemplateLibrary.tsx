import {parameterType} from './templateRules';
import {fixedArguments,parameterRole,templateAction} from './templateAction';
import {useCallback,useEffect,useId,useMemo,useRef,useState} from 'react';
import {useAuth} from './auth';
import {api} from './model';
import {EntityChip,ReadingCards,useCards} from './EntityCards';
import TemplateEditor,{TemplateDialog} from './TemplateEditor';
import TemplateSettings from './TemplateSettings';
import TemplateProposals from './TemplateProposals';
import TemplateConflicts from './TemplateConflicts';
import TemplateUtterances,{type UtteranceChange} from './TemplateUtterances';
import TemplateJsonExport from './TemplateJsonExport';
import TemplateHelp from './TemplateHelp';
import {deriveTemplateEntities,downloadTemplates,filterTemplateGroups,lineupPlayer,operators,templateId,valueText,type TemplateChange,type TemplateEntity,type TemplateEvent,type TemplateFilters,type TemplateGroup,type TemplateSnapshot,type PortableTemplateLibrary,type TemplateWarning,type WarningSnapshot} from './templates';
import type {Note,Options} from './types';
import './templates.css';

function GroupExplanation({text}:{text:string}){
 const id=useId(),container=useRef<HTMLSpanElement>(null);
 const [state,setState]=useState<'closed'|'preview'|'pinned'>('closed');
 const leaveTimer=useRef<number|undefined>(undefined);
 const open=state!=='closed';
 useEffect(()=>()=>window.clearTimeout(leaveTimer.current),[]);
 useEffect(()=>{
  if(!open)return;
  function outside(e:PointerEvent){if(!container.current?.contains(e.target as Node))setState('closed');}
  function escape(e:KeyboardEvent){if(e.key==='Escape')setState('closed');}
  document.addEventListener('pointerdown',outside);
  document.addEventListener('keydown',escape);
  return ()=>{
   document.removeEventListener('pointerdown',outside);
   document.removeEventListener('keydown',escape);
  };
 },[open]);
 function preview(){window.clearTimeout(leaveTimer.current);setState(current=>current==='closed'?'preview':current);}
 return <span ref={container} className="template-explanation" onPointerEnter={e=>{if(e.pointerType==='mouse')preview();}}
  onPointerLeave={()=>{leaveTimer.current=window.setTimeout(()=>{
   if(!container.current?.contains(document.activeElement))setState(current=>current==='pinned'?current:'closed');
  },180);}}
  onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setState('closed');}}>
  <button type="button" aria-expanded={open} aria-controls={id} aria-describedby={open?id:undefined} onFocus={preview}
   onClick={()=>setState(current=>current==='pinned'?'closed':'pinned')}>说明与依据</button>
  <span id={id} className="template-explanation-popup" role="tooltip" hidden={!open}>{text}</span>
 </span>;
}

export function TemplateGroupCard({group,event,entities:archivedEntities=[],scopeName,editable,onEdit,onDelete,onExport,onToggleIgnored,savingIgnore,warning,onConfirm,onSaveUtterances,onUtteranceDirty,annotator=false,interactionLocked=false,otherEditing=false}:{group:TemplateGroup;event?:TemplateEvent;entities?:TemplateEntity[];scopeName:(id:string|null)=>string;editable:boolean;onEdit:()=>void;onDelete:()=>void;onExport?:()=>void;onToggleIgnored?:(utteranceId?:string)=>void;savingIgnore?:{group:boolean;rows:string[]};warning?:TemplateWarning;onConfirm?:()=>void;onSaveUtterances?:(change:UtteranceChange)=>Promise<void>;onUtteranceDirty?:(dirty:boolean)=>void;annotator?:boolean;interactionLocked?:boolean;otherEditing?:boolean}){
 const cards=useCards(),entities=deriveTemplateEntities(group,event,cards,archivedEntities);
 const actionValues=fixedArguments(group);
 return <article className={'template-group '+(warning?'template-needs-check ':'')+(group.ignored?'template-group-ignored':'')} aria-label={group.name}>
  <header><div><h2>{group.name}</h2>{group.explanation?.trim()&&<GroupExplanation text={group.explanation}/>}<div className="template-scope"><span>{event?.name??group.event_id}</span><span>优先级 {group.priority??0}</span>{group.ignored&&<span className="template-ignored">已忽略</span>}</div></div><div className="template-card-actions"><button aria-label={'导出json：'+group.name} disabled={interactionLocked||group.ignored||group.utterances.every(row=>row.ignored)} onClick={onExport}>导出json</button>{editable&&<><button aria-label={'编辑模板'+group.name} disabled={interactionLocked} onClick={onEdit}>编辑条件</button>{onToggleIgnored&&<button disabled={interactionLocked} onClick={()=>onToggleIgnored()}>{savingIgnore?.group?"保存中…":group.ignored?"取消忽略":"忽略"}</button>}<button aria-label={'删除模板'+group.name} disabled={interactionLocked} onClick={onDelete}>删除模板</button></>}</div></header>
  {warning&&<div className="template-warning" role="status"><strong>关联资料已变化，待检查</strong><span>{warning.entities.map(e=>e.name).join('、')}</span>{editable&&onConfirm&&<button disabled={interactionLocked} onClick={onConfirm}>已检查，无需修改</button>}</div>}
  <div className="template-group-body"><section className="template-read-conditions" aria-label="卡牌与条件">
   <p className="template-action"><strong>触发动作</strong> {templateAction(group,event,actionValues)}</p>
   {!!event?.parameters.length && <dl aria-label="动作参数" className="template-action-parameters">{event.parameters.map(p=><div key={p.key}>
    <dt><code>{p.key}</code></dt><dd>{parameterRole(event,p)} <small>（{parameterType(p)}）</small>{actionValues.has(p.key) && <strong> · {actionValues.get(p.key)}</strong>}</dd>
   </div>)}</dl>}
   <div className="template-condition-scopes"><span>棋手：{scopeName(group.scope.player_id)}</span><span>阵容：{scopeName(group.scope.lineup_note_id)}</span></div>
   {entities.length>0&&<div className="template-chips" aria-label="关联卡牌">{entities.map(e=><EntityChip key={e.id} ids={[e.id]} label={e.name} portrait/>)}</div>}
   <h3>{group.expression?'触发条件':'同时满足'}</h3>{group.expression?<pre className="rule-expression">{group.expression}</pre>:group.conditions.length?<dl>{group.conditions.map(c=>{const parameter=event?.parameters.find(p=>p.key===c.parameter_key);const entity=c.value as TemplateEntity;return <div key={c.id}><dt>{parameter?.name??c.parameter_key}</dt><dd><span>{operators[c.operator]} </span>{parameter?.type==='entity'&&entity?.id?<EntityChip ids={deriveTemplateEntities({...group,scope:{player_id:null,lineup_note_id:null},conditions:[c]},event,cards).map(e=>e.id)} label={entity.name}/>:valueText(c.value)}</dd></div>;})}</dl>:<p className="muted">不限制条件</p>}
  </section><TemplateUtterances utterances={group.utterances} parameters={event?.parameters} editable={editable} annotator={annotator} disabled={otherEditing||!!savingIgnore?.group} savingIgnoreIds={savingIgnore?.rows} onToggleIgnored={onToggleIgnored} onSave={onSaveUtterances} onDirty={onUtteranceDirty}/></div>
 </article>;
}

import type {Season} from './seasons';
type IgnoreChange={groupId:string;utteranceId?:string;ignored:boolean};
function applyIgnore(group:TemplateGroup,change:IgnoreChange):TemplateGroup{
 const update=<T extends {ignored?:boolean}>(row:T)=>{
  const next={...row};
  if(change.ignored)next.ignored=true;else delete next.ignored;
  return next;
 };
 return change.utteranceId
  ? {...group,utterances:group.utterances.map(row=>row.id===change.utteranceId?update(row):row)}
  : update(group);
}
type Preview={revision:string;changes:TemplateChange[];summary:unknown;errors:unknown[]};
export default function TemplateLibrary({notes,options,onDirty,season='S1'}:{season?:Season;notes:Note[];options:Options;onDirty?:(dirty:boolean)=>void}){
 const {session}=useAuth(),editable=season==='S1'&&(session.role==='admin'||session.role==='annotator'),annotator=session.role==='annotator';const cards=useCards();
 const [snapshot,setSnapshot]=useState<TemplateSnapshot|null>(null),[filters,setFilters]=useState<TemplateFilters>({event:'',player:'',lineup:'',query:''}),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[drawer,setDrawer]=useState(false),[editor,setEditor]=useState<TemplateGroup|null>(null),[settings,setSettings]=useState(false),[proposals,setProposals]=useState(false),[importOpen,setImportOpen]=useState(false),[importText,setImportText]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[warnings,setWarnings]=useState<TemplateWarning[]>([]),[conflicted,setConflicted]=useState<string[]>([]);
 const [pendingIgnores,setPendingIgnores]=useState<IgnoreChange[]>([]);
 const [queuedWrites,setQueuedWrites]=useState(0);
 const queue=useRef<Promise<void>>(Promise.resolve());
 const queueSize=useRef(0);
 const queueSnapshot=useRef<TemplateSnapshot|null>(null);
 const ignoreKeys=useRef(new Set<string>());
 const [help,setHelp]=useState(false);
 const [utteranceEditing,setUtteranceEditing]=useState<string|null>(null),[jsonGroup,setJsonGroup]=useState<{id:string;name:string}|null>(null);
 const drawerRef=useRef<HTMLElement>(null),drawerButton=useRef<HTMLButtonElement>(null),epoch=useRef(0);
 const load=useCallback(async()=>{const current=++epoch.current;setLoading(true);setError('');try{const [data,warning]=await Promise.all([api<TemplateSnapshot>('templates'),api<WarningSnapshot>('templates/warnings').catch(e=>{if(current===epoch.current)setError('关联资料变化检查失败：'+e.message);return null;})]);if(current===epoch.current){setSnapshot(data);if(warning)setWarnings(warning.items);}}catch(e){if(current===epoch.current)setError((e as Error).message);}finally{if(current===epoch.current)setLoading(false);}},[]);
 useEffect(()=>{void load();return()=>{epoch.current++;};},[load]);
 useEffect(()=>{if(!drawer)return;drawerRef.current?.querySelector<HTMLElement>('button')?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){setDrawer(false);drawerButton.current?.focus();}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);},[drawer]);
 const players=useMemo(()=>{const map=new Map([...options.entities,...cards].filter(e=>['players','player'].includes(e.category??'')).map(e=>[e.id,{id:e.id,name:e.name}]));for(const n of notes)if(n.type==='player'&&n.player_id&&!map.has(n.player_id))map.set(n.player_id,{id:n.player_id,name:n.title});return Array.from(map.values());},[options.entities,cards,notes]);
 const lineups=notes.filter(n=>n.type==='lineup'),scopeName=(id:string|null)=>id?(players.find(p=>p.id===id)?.name??notes.find(n=>n.id===id)?.title??id):'通用';
 const searchLabels={events:snapshot?.events,scopeName,links:snapshot?.entity_links};
 const groups=filterTemplateGroups(snapshot?.groups??[],filters,[...options.entities,...cards],searchLabels),countGroups=filterTemplateGroups(snapshot?.groups??[],{...filters,event:''},[...options.entities,...cards],searchLabels),categories=Array.from(new Set(snapshot?.events.map(e=>e.category||'未分类')??[]));
 function patch(value:Partial<TemplateFilters>){setFilters(f=>{const next={...f,...value};if(value.lineup&&value.lineup!=='common'){const n=lineups.find(n=>n.id===value.lineup);if(n)next.player=lineupPlayer(n)??next.player;}if(value.player!==undefined&&next.lineup&&next.lineup!=='common'){const n=lineups.find(n=>n.id===next.lineup);if(n&&lineupPlayer(n)!==value.player)next.lineup='';}return next;});}
 async function write(changes:TemplateChange[]){if(!snapshot)throw new Error('模板库尚未载入');const result=await api<TemplateSnapshot|{proposal:unknown}>('templates/changes','POST',{revision:snapshot.revision,changes});if('proposal' in result)setNotice('已提交私有提案，审核通过后生效。');else{setSnapshot(result);setNotice('模板库已保存。');}void load();}
 async function remove(group:TemplateGroup){if(!confirm('确定删除模板组“'+group.name+'”及其中全部话术吗？'))return;setBusy(true);setError('');try{await write([{kind:'group',action:'delete',id:group.id}]);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 function enqueueGroupChange(groupId:string,update:(group:TemplateGroup)=>TemplateGroup) {
  if(!snapshot||busy)return Promise.reject(new Error('模板库正在保存其他修改'));
  if(!queueSize.current)queueSnapshot.current=snapshot;
  queueSize.current++;
  setQueuedWrites(queueSize.current);
  const save=queue.current.then(async()=>{
   const current=queueSnapshot.current;
   const group=current?.groups.find(row=>row.id===groupId);
   if(!current||!group)throw new Error('模板组已不存在，请刷新后重试');
   const value=update(group);
   const result=await api<TemplateSnapshot|{proposal:unknown}>('templates/changes','POST',{
    revision:current.revision,changes:[{kind:'group',action:'put',id:groupId,value}],
   });
   if('proposal' in result)setNotice('修改已提交，待审核。');
   else{
    epoch.current++;
    setLoading(false);
    const next={...current,revision:result.revision,groups:current.groups.map(row=>row.id===groupId?value:row)};
    queueSnapshot.current=next;
    setSnapshot(next);
   }
  });
  const finished=save.finally(()=>{
   queueSize.current--;
   setQueuedWrites(queueSize.current);
  });
  queue.current=finished.catch(()=>{});
  return finished;
 }
 function saveUtterance(groupId:string,change:UtteranceChange){
  return enqueueGroupChange(groupId,group=>{
   const rows=group.utterances;
   if(change.kind==='delete'&&rows.length<=1)throw new Error('每组至少保留一条话术');
   const utterances=change.kind==='add'? [...rows,change.row]:
    change.kind==='delete'?rows.filter(row=>row.id!==change.id):
    rows.map(row=>row.id===change.id?{...row,text:change.text}:row);
   return {...group,utterances};
  });
 }
 async function toggleIgnored(group:TemplateGroup,utteranceId?:string){
  const key=JSON.stringify([group.id,utteranceId]);
  if(!snapshot||busy||ignoreKeys.current.has(key))return;
  const target=utteranceId?group.utterances.find(row=>row.id===utteranceId):group;
  if(!target)return;
  const change={groupId:group.id,utteranceId,ignored:!target.ignored};
  ignoreKeys.current.add(key);
  setPendingIgnores(rows=>[...rows,change]);
  setError('');setNotice('');
  try{
   await enqueueGroupChange(group.id,row=>applyIgnore(row,change));
  }catch(error){
   setError('保存忽略状态失败：'+(error as Error).message);
  }finally{
   ignoreKeys.current.delete(key);
   setPendingIgnores(rows=>rows.filter(row=>row!==change));
  }
 }
 async function confirmWarning(warning:TemplateWarning){if(!confirm('已检查“'+warning.group_name+'”的关联资料，确认无需修改？'))return;setBusy(true);setError('');try{await api('templates/warnings/confirm','POST',{group_id:warning.group_id,revision:warning.revision});await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function exportData(filtered=false){setError('');try{if(filtered&&!groups.length)throw new Error('当前筛选没有可导出的模板');const suffix=filtered?'?group_ids='+encodeURIComponent(groups.map(g=>g.id).join(',')):'';downloadTemplates(await api<PortableTemplateLibrary>('templates/export'+suffix),filtered?'话术模板库-当前筛选.json':'话术模板库.json');}catch(e){setError((e as Error).message);}}
 function setImport(value:string){setImportText(value);setPreview(null);onDirty?.(!!value);}
 function closeImport(){if(importText&&!confirm('关闭后将放弃本次导入内容，继续吗？'))return;setImportOpen(false);setImportText('');setPreview(null);onDirty?.(false);}
 async function previewImport(){setError('');setBusy(true);try{const document=JSON.parse(importText);setPreview(await api<Preview>('templates/import/preview','POST',{document}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function commitImport(){if(!preview||preview.errors.length)return;setError('');setBusy(true);try{const result=await api<TemplateSnapshot|{proposal:unknown}>('templates/import/commit','POST',{revision:preview.revision,changes:preview.changes});if('proposal' in result)setNotice('导入已提交为私有提案，审核通过后生效。');else setSnapshot(result);setImportOpen(false);setImportText('');setPreview(null);onDirty?.(false);await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 function create(){if(!snapshot?.events.length){setNotice('请先在事件与参数设置中添加事件。');setSettings(true);return;}setEditor({id:templateId('group'),name:'',event_id:filters.event||snapshot.events[0].id,scope:{player_id:filters.player&&filters.player!=='common'?filters.player:null,lineup_note_id:filters.lineup&&filters.lineup!=='common'?filters.lineup:null},priority:0,condition_tree:{kind:'all',children:[]},expression:'',editor_mode:'tree',conditions:[],utterances:[{id:templateId('utterance'),text:''}],related_entities:[]});}
 return <main className="templates-page"><div className="template-page-heading"><div><h1>话术模板库</h1><p>按事件整理条件与表达，查看同组全部等概率话术。</p></div><fieldset className="template-toolbar" disabled={!!utteranceEditing||queuedWrites>0}><button onClick={()=>setHelp(true)}>帮助</button>{season==='S1'&&session.role==='admin'&&<TemplateConflicts events={snapshot?.events??[]} scopeName={scopeName} onResolved={()=>void load()} onConflicts={setConflicted}/>}{season==='S1'&&<><button onClick={()=>void exportData()}>导出全库</button><button disabled={!groups.length} onClick={()=>void exportData(true)}>导出当前筛选</button></>}{editable&&<><button onClick={()=>{setError('');setImportOpen(true);}}>导入 JSON</button><button onClick={()=>setSettings(true)}>事件与参数</button><button onClick={()=>setProposals(true)}>{annotator?'我的提案':'提案审核'}</button><button className="primary" disabled={busy||!snapshot} onClick={create}>＋ 新建模板组</button></>}</fieldset></div>{notice&&<div className="template-notice" role="status">{notice}<button aria-label="关闭提示" onClick={()=>setNotice('')}>×</button></div>}{error&&!importOpen&&<div role="alert" className="error template-error">{error}<button onClick={()=>void load()}>重新载入</button></div>}<div className="template-workspace"><button ref={drawerButton} className="template-mobile-events" disabled={!!utteranceEditing} aria-expanded={drawer} aria-controls="template-events" onClick={()=>setDrawer(true)}>☰ 事件分类</button>{drawer&&<button className="template-drawer-backdrop" aria-label="关闭事件分类" onClick={()=>setDrawer(false)}/>}<aside ref={drawerRef} id="template-events" inert={!!utteranceEditing} className={'template-events '+(drawer?'template-events-open':'')} aria-label="事件分类"><button className="template-mobile-close" onClick={()=>{setDrawer(false);drawerButton.current?.focus();}}>收起事件分类</button><button className={!filters.event?'selected':''} onClick={()=>{patch({event:''});setDrawer(false);}}><span>全部事件</span><span>{countGroups.length}</span></button>{categories.map(category=><section key={category}><h2>{category}</h2>{snapshot?.events.filter(e=>(e.category||'未分类')===category).map(event=><button key={event.id} className={event.id===filters.event?'selected':''} onClick={()=>{patch({event:event.id});setDrawer(false);}}><span>{event.name}</span><span>{countGroups.filter(g=>g.event_id===event.id).length}</span></button>)}</section>)}</aside><div className="template-results"><fieldset className="template-filters" disabled={!!utteranceEditing}><label>棋手<select value={filters.player} onChange={e=>patch({player:e.target.value})}><option value="">全部棋手</option><option value="common">仅通用棋手</option>{players.map(p=><option key={p.id} value={p.id}>{p.name}（含通用）</option>)}</select></label><label>阵容棋手组合<select value={filters.lineup} onChange={e=>patch({lineup:e.target.value})}><option value="">全部组合</option><option value="common">仅通用组合</option>{lineups.filter(n=>lineupPlayer(n)&&(!filters.player||(filters.player!=='common'&&lineupPlayer(n)===filters.player))).map(n=><option key={n.id} value={n.id}>{n.title}（含通用）</option>)}</select></label><label className="template-search">搜索模板<input type="search" placeholder="属性、实体名称或话术（逗号表示同时包含）" value={filters.query} onChange={e=>patch({query:e.target.value})}/></label><button onClick={()=>setFilters({event:'',player:'',lineup:'',query:''})}>清除筛选</button></fieldset><div className="template-result-heading"><h2>{snapshot?.events.find(e=>e.id===filters.event)?.name??'全部模板'}</h2><span className="muted">{groups.length} 个模板组</span><button disabled={loading||!!utteranceEditing} onClick={()=>void load()} aria-label="刷新模板库">↻</button></div><ReadingCards><div className="template-group-list">{loading&&!snapshot?<p className="empty" role="status">正在载入模板库…</p>:!groups.length?<div className="empty"><p>{snapshot?.groups.length?'没有符合筛选的模板组。':season==='S1'?'还没有模板组。先配置事件，再添加条件与话术。':'暂无 '+season+' 模板数据'}</p>{editable&&<button onClick={create}>新建模板组</button>}</div>:groups.map(group=>{
 const pending=pendingIgnores.filter(change=>change.groupId===group.id);
 const displayed=pending.reduce(applyIgnore,group);
 return <TemplateGroupCard key={group.id} group={displayed} savingIgnore={{group:pending.some(change=>!change.utteranceId),rows:pending.flatMap(change=>change.utteranceId?[change.utteranceId]:[])}} entities={snapshot?.entity_links?.[group.id]} event={snapshot?.events.find(e=>e.id===group.event_id)} scopeName={scopeName} interactionLocked={!!utteranceEditing||queuedWrites>0} otherEditing={!!utteranceEditing&&utteranceEditing!==group.id} annotator={annotator} onSaveUtterances={change=>saveUtterance(group.id,change)} onUtteranceDirty={dirty=>{setUtteranceEditing(current=>dirty?group.id:current===group.id?null:current);onDirty?.(dirty);}} editable={editable&&!busy&&!conflicted.includes(group.id)&&!conflicted.includes(group.event_id)} onExport={()=>setJsonGroup({id:group.id,name:group.name})} onEdit={()=>setEditor(group)} onDelete={()=>void remove(group)} onToggleIgnored={utteranceId=>void toggleIgnored(displayed,utteranceId)} warning={warnings.find(w=>w.group_id===group.id)} onConfirm={()=>{const warning=warnings.find(w=>w.group_id===group.id);if(warning)void confirmWarning(warning);}}/>;})}</div></ReadingCards></div></div>
 {help&&<TemplateHelp onClose={()=>setHelp(false)}/>}
 {jsonGroup&&<TemplateJsonExport key={jsonGroup.id} groupId={jsonGroup.id} groupName={jsonGroup.name} onClose={()=>setJsonGroup(null)}/>}{editor&&snapshot&&<TemplateEditor group={editor} catalog={snapshot.condition_catalog} conditionLinks={snapshot.entity_condition_links?.[editor.id]} entities={snapshot.entity_links?.[editor.id]} events={snapshot.events} players={players} lineups={lineups} annotator={annotator} onDirty={onDirty} onClose={()=>setEditor(null)} onSave={(group,event)=>write([...(event?[{kind:'event' as const,action:'put' as const,id:event.id,value:event}]:[]),{kind:'group',action:'put',id:group.id,value:group}])}/>}{settings&&snapshot&&<TemplateSettings events={snapshot.events} annotator={annotator} onDirty={onDirty} onClose={()=>setSettings(false)} onSave={write}/ >}{proposals&&<TemplateProposals scopeName={scopeName} admin={!annotator} onClose={()=>setProposals(false)} onChanged={()=>void load()}/>}
 {importOpen&&<TemplateDialog title="导入话术模板库" onClose={closeImport} wide><div className="template-form"><p>按事件名称及组名匹配现有模板。先检查预览，再确认{annotator?'提交提案':'导入'}。</p><label>选择 JSON 文件<input type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)void file.text().then(setImport).catch(e=>setError(e.message));}}/></label><label>或粘贴 JSON<textarea rows={10} value={importText} disabled={busy} onChange={e=>setImport(e.target.value)} spellCheck={false}/></label>{error&&<p className="error" role="alert">{error}</p>}{preview&&<section><h3>导入预览</h3><p>新增 {(preview.summary as {created?:number}).created??0} 项，更新 {(preview.summary as {updated?:number}).updated??0} 项，无变化 {(preview.summary as {unchanged?:number}).unchanged??0} 项。</p><p>共 {preview.changes.length} 项修改</p>{preview.errors.length>0&&<div className="error" role="alert">{preview.errors.map((e,i)=><p key={i}>{typeof e==='string'?e:JSON.stringify(e)}</p>)}</div>}<details><summary>查看全部修改</summary>{preview.changes.map((change,i)=><p key={i}>{change.action==='delete'?'删除':'新增或更新'}{change.kind==='event'?'事件':'模板组'}：{change.value?.name??change.id}</p>)}</details></section>}<footer><button onClick={closeImport}>取消</button><button disabled={busy||!importText.trim()} onClick={()=>void previewImport()}>检查并预览</button><button className="primary" disabled={busy||!preview||!!preview.errors.length||!preview.changes.length} onClick={()=>void commitImport()}>{busy?'处理中…':annotator?'确认提交导入提案':'确认导入'}</button></footer></div></TemplateDialog>}</main>;
}
