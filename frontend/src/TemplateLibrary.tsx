import {TemplateConditionPreview} from './TemplateConditionPreview';
import {loadTemplateWarnings} from './TemplateWarnings';
import {parameterType} from './templateRules';
import {argumentCardIds,fixedArguments,parameterRole,templateAction} from './templateAction';
import {useCallback,useEffect,useId,useMemo,useRef,useState,type UIEvent} from 'react';
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
import TemplateFeedback,{activityLabel,type Activity,type FeedbackTarget} from './TemplateFeedback';
import {effectiveExpression,deriveTemplateEntities,downloadTemplates,filterTemplateGroups,lineupPlayer,operators,templateId,valueText,type TemplateChange,type TemplateEntity,type TemplateEvent,type TemplateFilters,type TemplateGroup,type TemplateSnapshot,type PortableTemplateLibrary,type TemplateWarning} from './templates';
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

export function TemplateGroupCard({group,event,entities:archivedEntities=[],scopeName,editable,onEdit,onDelete,onExport,onFeedback,commentCounts,lastActivity,onToggleIgnored,onToggleFixed,savingIgnore,warning,onConfirm,onSaveUtterances,onUtteranceDirty,annotator=false,interactionLocked=false,otherEditing=false}:{group:TemplateGroup;event?:TemplateEvent;entities?:TemplateEntity[];scopeName:(id:string|null)=>string;editable:boolean;onEdit:()=>void;onDelete:()=>void;onExport?:()=>void;onFeedback?:(id?:string)=>void;commentCounts?:Record<string,number>;lastActivity?:Activity;onToggleIgnored?:(utteranceId?:string)=>void;onToggleFixed?:(utteranceId:string)=>void;savingIgnore?:{group:boolean;rows:string[]};warning?:TemplateWarning;onConfirm?:()=>void;onSaveUtterances?:(change:UtteranceChange)=>Promise<void>;onUtteranceDirty?:(dirty:boolean)=>void;annotator?:boolean;interactionLocked?:boolean;otherEditing?:boolean}){
 const cards=useCards(),entities=deriveTemplateEntities(group,event,cards,archivedEntities);
 const actionValues=fixedArguments(group);
 const {player_id:player,lineup_note_id:lineup}=group.scope;
 const expression=effectiveExpression(player&&scopeName(player),lineup&&scopeName(lineup),group.expression??'');
 return <article data-feedback-group={group.id} tabIndex={-1} className={'template-group '+(warning?'template-needs-check ':'')+(group.ignored?'template-group-ignored':'')} aria-label={group.name}>
  <header><div><h2>{group.name}</h2>{group.explanation?.trim()&&<GroupExplanation text={group.explanation}/>}<div className="template-scope"><span>{event?.name??group.event_id}</span><span>优先级 {group.priority??0}</span>{group.ignored&&<span className="template-ignored">已忽略</span>}</div></div>{lastActivity&&<small>最近管理员操作 · {activityLabel(lastActivity)}</small>}<div className="template-card-actions">{onFeedback&&<button disabled={interactionLocked} onClick={()=>onFeedback()}>组批注与记录 <span className="template-comment-count">{commentCounts?.['']??0}</span></button>}<button aria-label={'导出json：'+group.name} disabled={interactionLocked||group.ignored||group.utterances.every(row=>row.ignored)} onClick={onExport}>导出json</button>{editable&&<><button aria-label={'编辑模板'+group.name} disabled={interactionLocked} onClick={onEdit}>编辑条件</button>{onToggleIgnored&&<button disabled={interactionLocked} onClick={()=>onToggleIgnored()}>{savingIgnore?.group?"保存中…":group.ignored?"取消忽略":"忽略"}</button>}<button aria-label={'删除模板'+group.name} disabled={interactionLocked||group.utterances.some(row=>row.fixed)} title={group.utterances.some(row=>row.fixed)?'先取消固定再删除模板组':undefined} onClick={onDelete}>删除模板</button></>}</div></header>
  {warning&&<div className="template-warning" role="status"><strong>关联资料已变化，待检查</strong><span>{warning.entities.map(e=>e.name).join('、')}</span>{editable&&!annotator&&onConfirm&&<button disabled={interactionLocked} onClick={onConfirm}>已检查，无需修改</button>}</div>}
  <div className="template-group-body"><section className="template-read-conditions" aria-label="卡牌与条件">
   <p className="template-action"><strong>触发动作</strong> {templateAction(group,event,actionValues)}</p>
   {!!event?.parameters.length && <dl aria-label="动作参数" className="template-action-parameters">{event.parameters.map(p=>{
    const value=actionValues.get(p.key),ids=value?argumentCardIds(p,value,cards):[];
    return <div key={p.key}><dt><code>{p.key}</code></dt><dd>{parameterRole(event,p)} <small>（{parameterType(p)}）</small>
     {value&&(ids.length?<EntityChip ids={ids} label={value} portrait/>:<strong> · {value}</strong>)}</dd></div>;
   })}</dl>}
   <div className="template-condition-scopes"><span>棋手：{scopeName(group.scope.player_id)}</span><span>阵容：{scopeName(group.scope.lineup_note_id)}</span></div>
   {entities.length>0&&<div className="template-chips" aria-label="关联卡牌">{entities.map(e=><EntityChip key={e.id} ids={[e.id]} label={e.name} portrait/>)}</div>}
   {(group.expression!==undefined||expression)&&<TemplateConditionPreview expression={expression}/>}
   {group.expression===undefined&&group.conditions.length>0&&<><h3>同时满足</h3><dl>{group.conditions.map(c=>{const parameter=event?.parameters.find(p=>p.key===c.parameter_key);const entity=c.value as TemplateEntity;return <div key={c.id}><dt>{parameter?.name??c.parameter_key}</dt><dd><span>{operators[c.operator]} </span>{parameter?.type==='entity'&&entity?.id?<EntityChip ids={deriveTemplateEntities({...group,scope:{player_id:null,lineup_note_id:null},conditions:[c]},event,cards).map(e=>e.id)} label={entity.name}/>:valueText(c.value)}</dd></div>;})}</dl></>}{group.expression===undefined&&!expression&&!group.conditions.length&&<p className="muted">不限制条件</p>}
  </section><TemplateUtterances commentCounts={commentCounts} onFeedback={onFeedback} utterances={group.utterances} parameters={event?.parameters} editable={editable} annotator={annotator} disabled={otherEditing||!!savingIgnore?.group} savingIgnoreIds={savingIgnore?.rows} onToggleIgnored={onToggleIgnored} onToggleFixed={onToggleFixed} onSave={onSaveUtterances} onDirty={onUtteranceDirty}/></div>
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
type Preview={revision:string;changes:TemplateChange[];summary:unknown;errors:unknown[];preserved_fixed?:{group_id:string;utterance_id:string;group_name:string;text:string}[]};
export default function TemplateLibrary({notes,options,onDirty,season='S1'}:{season?:Season;notes:Note[];options:Options;onDirty?:(dirty:boolean)=>void}){
 const {session}=useAuth(),editable=season==='S1'&&(session.role==='admin'||session.role==='annotator'),annotator=session.role==='annotator';const cards=useCards();
 const [snapshot,setSnapshot]=useState<TemplateSnapshot|null>(null),[filters,setFilters]=useState<TemplateFilters>({event:'',player:'',lineup:'',query:''}),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[drawer,setDrawer]=useState(false),[editor,setEditor]=useState<TemplateGroup|null>(null),[settings,setSettings]=useState(false),[proposals,setProposals]=useState(false),[importOpen,setImportOpen]=useState(false),[importText,setImportText]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[warnings,setWarnings]=useState<TemplateWarning[]>([]),[conflicted,setConflicted]=useState<string[]>([]);
 const [pendingIgnores,setPendingIgnores]=useState<IgnoreChange[]>([]);
 const [pendingFixed,setPendingFixed]=useState<{groupId:string;utteranceId:string}[]>([]);
 const [queuedWrites,setQueuedWrites]=useState(0);
 const queue=useRef<Promise<void>>(Promise.resolve());
 const queueSize=useRef(0);
 const queueSnapshot=useRef<TemplateSnapshot|null>(null);
 const editorBase=useRef<TemplateGroup|undefined>(undefined);
 const ignoreKeys=useRef(new Set<string>());
 const [help,setHelp]=useState(false);
 const [feedback,setFeedback]=useState<FeedbackTarget|null>(null),[feedbackRevision,setFeedbackRevision]=useState(0);
 const [focusTarget,setFocusTarget]=useState<{group:string;utterance?:string}|null>(null);
 const [commentCounts,setCommentCounts]=useState<Record<string,Record<string,number>>>({});
 useEffect(()=>{
  if(!editable)return;
  let active=true;
  async function read(){
   try{
    const {items}=await api<{items:{group_id:string;utterance_id:string|null;count:number}[]}>('templates/comments?counts=1');
    const counts:Record<string,Record<string,number>>=Object.create(null);
    for(const row of items)(counts[row.group_id]??=Object.create(null))[row.utterance_id??'']=row.count;
    if(active)setCommentCounts(counts);
   }catch(e){if(active)setError('批注条数读取失败：'+(e as Error).message);}
  }
  void read();
  return ()=>{active=false;};
 },[editable,feedbackRevision,snapshot?.read_generation]);
 const [lastActivity,setLastActivity]=useState<Record<string,Activity>>({});
 const [bypass,setBypass]=useState(false),[reason,setReason]=useState('');
 useEffect(()=>{
  if(!editable||!snapshot?.revision)return;
  let active=true;api<{items:Activity[]}>('templates/history?latest=1').then(data=>{if(active)setLastActivity(Object.fromEntries(data.items.map(a=>[a.group_id,a])));}).catch(e=>{if(active)setError('管理员操作记录读取失败：'+e.message);});return()=>{active=false;};
 },[editable,snapshot?.revision,feedbackRevision]);
 const [utteranceEditing,setUtteranceEditing]=useState<string|null>(null),[jsonGroup,setJsonGroup]=useState<{id:string;name:string}|null>(null);
 const drawerRef=useRef<HTMLElement>(null),drawerButton=useRef<HTMLButtonElement>(null),epoch=useRef(0);
 const load=useCallback(async(knownGeneration?:string)=>{
  const current=++epoch.current;
  if(!knownGeneration){setLoading(true);setError('');}
  try{
   const data=await api<TemplateSnapshot|{unchanged:true}>('templates'+(knownGeneration?'?if_generation='+encodeURIComponent(knownGeneration):''));
   if(current!==epoch.current||'unchanged' in data)return;
   setSnapshot(data);
   void loadTemplateWarnings().then(warning=>{if(current===epoch.current)setWarnings(warning.items);})
    .catch(e=>{if(current===epoch.current)setError('关联资料变化检查失败：'+e.message);});
  }catch(e){if(current===epoch.current)setError((e as Error).message);}
  finally{if(current===epoch.current)setLoading(false);}
 },[]);
 useEffect(()=>{void load();return()=>{epoch.current++;};},[load]);
 const checkingAllowed=!busy&&!queuedWrites&&!editor&&!settings&&!proposals&&!importOpen&&!utteranceEditing;
 useEffect(()=>{
  const generation=snapshot?.read_generation;
  if(!checkingAllowed||!generation)return;
  let pending=false;
  function check(){
   if(pending||document.hidden)return;
   pending=true;
   void load(generation).finally(()=>{pending=false;});
  }
  const timer=window.setInterval(check,15000);
  window.addEventListener('focus',check);
  return()=>{window.clearInterval(timer);window.removeEventListener('focus',check);};
 },[checkingAllowed,snapshot?.read_generation,load]);
 useEffect(()=>{if(!drawer)return;drawerRef.current?.querySelector<HTMLElement>('button')?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){setDrawer(false);drawerButton.current?.focus();}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);},[drawer]);
 const players=useMemo(()=>{const map=new Map([...options.entities,...cards].filter(e=>['players','player'].includes(e.category??'')).map(e=>[e.id,{id:e.id,name:e.name}]));for(const n of notes)if(n.type==='player'&&n.player_id&&!map.has(n.player_id))map.set(n.player_id,{id:n.player_id,name:n.title});return Array.from(map.values());},[options.entities,cards,notes]);
 const lineups=notes.filter(n=>n.type==='lineup'),scopeName=(id:string|null)=>id?(players.find(p=>p.id===id)?.name??notes.find(n=>n.id===id)?.title??snapshot?.scope_names?.[id]??id):'通用';
 const searchLabels={events:snapshot?.events,scopeName,links:snapshot?.entity_links};
 const countGroups=filterTemplateGroups(snapshot?.groups??[],{...filters,event:''},[...options.entities,...cards],searchLabels),groups=filters.event?countGroups.filter(group=>group.event_id===filters.event):countGroups,categories=Array.from(new Set(snapshot?.events.map(e=>e.category||'未分类')??[]));
 const [visibleCount,setVisibleCount]=useState(20);
 const groupList=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(focusTarget)return;setVisibleCount(20);if(groupList.current)groupList.current.scrollTop=0;},[filters]);
 useEffect(()=>{
  if(!focusTarget)return;
  const index=groups.findIndex(row=>row.id===focusTarget.group);
  if(index>=visibleCount){setVisibleCount(index+1);return;}
  const card=document.querySelector<HTMLElement>('[data-feedback-group="'+CSS.escape(focusTarget.group)+'"]');
  const node=focusTarget.utterance?card?.querySelector<HTMLElement>('[data-feedback-utterance="'+CSS.escape(focusTarget.utterance)+'"]'):card;
  node?.focus();node?.scrollIntoView({block:'center'});setFocusTarget(null);
 },[focusTarget,visibleCount,groups]);
 const showMore=()=>setVisibleCount(count=>Math.min(count+20,groups.length));
 function moreOnScroll(event:UIEvent<HTMLElement>){
  const list=event.currentTarget;
  if(visibleCount<groups.length&&list.scrollHeight-list.scrollTop-list.clientHeight<400)showMore();
 }
 function patch(value:Partial<TemplateFilters>){setFilters(f=>{const next={...f,...value};if(value.lineup&&value.lineup!=='common'){const n=lineups.find(n=>n.id===value.lineup);if(n)next.player=lineupPlayer(n)??next.player;}if(value.player!==undefined&&next.lineup&&next.lineup!=='common'){const n=lineups.find(n=>n.id===next.lineup);if(n&&lineupPlayer(n)!==value.player)next.lineup='';}return next;});}
 function enqueueWrite(run:(current:TemplateSnapshot)=>Promise<TemplateSnapshot|{proposal:unknown}>,notice:string,groupIds:string[]){
  if(!snapshot)return Promise.reject(new Error('模板库尚未载入'));
  if(!queueSize.current)queueSnapshot.current=snapshot;
  setQueuedWrites(++queueSize.current);
  const save=queue.current.then(async()=>{
   const current=queueSnapshot.current!;
   try{
    const result=await run(current);
    if('proposal' in result){setNotice('修改已提交，待审核。');return;}
    // The read projection also carries legacy editor rules. Keep those
    // on untouched groups until the refreshed projection arrives.
    const previous=new Map(current.groups.map(g=>[g.id,g]));
    const changed=new Set(groupIds);
    const next={...current,...result,groups:result.groups.map(g=>changed.has(g.id)?g:previous.get(g.id)??g)};
    queueSnapshot.current=next;
    epoch.current++;
    setLoading(false);
    setSnapshot(next);
    setNotice(notice);
    if(queueSize.current===1&&current.read_generation)void load(current.read_generation);
   }catch(error){
    if((error as {status?:number}).status===409){
     // Use the server revision for the next queued operation. An editor's
     // draft and the record it started from remain independent of this read.
     const latest=await api<TemplateSnapshot>('templates');
     queueSnapshot.current=latest;
     epoch.current++;
     setLoading(false);
     setSnapshot(latest);
    }
    throw error;
   }
  }).finally(()=>{setQueuedWrites(--queueSize.current);});
  queue.current=save.catch(()=>{});
  return save;
 }
 function write(changes:TemplateChange[],original?:TemplateGroup){
  return enqueueWrite(current=>{
   if(original&&JSON.stringify(current.groups.find(row=>row.id===original.id))!==JSON.stringify(original))
    throw new Error('该模板组已有修改，请核对最新内容后重新编辑。当前草稿已保留。');
   return api('templates/changes','POST',{revision:current.revision,changes});
  },'模板库已保存。',changes.filter(c=>c.kind==='group').map(c=>c.id));
 }
 async function remove(group:TemplateGroup){if(!confirm('确定删除模板组“'+group.name+'”及其中全部话术吗？'))return;setBusy(true);setError('');try{await write([{kind:'group',action:'delete',id:group.id}],group);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 function enqueueGroupChange(groupId:string,update:(group:TemplateGroup)=>TemplateGroup){
  return enqueueWrite(current=>{
   const group=current.groups.find(row=>row.id===groupId);
   if(!group)throw new Error('模板组已不存在，请刷新后重试');
   return api('templates/changes','POST',{revision:current.revision,changes:[{kind:'group',action:'put',id:groupId,value:update(group)}]});
  },'模板库已保存。',[groupId]);
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
 async function toggleFixed(group:TemplateGroup,utteranceId:string){
  if(!snapshot||session.role!=='admin'||busy||utteranceEditing)return;
  const row=group.utterances.find(u=>u.id===utteranceId);
  if(!row)return;
  const key=JSON.stringify([group.id,utteranceId]);
  if(ignoreKeys.current.has(key))return;
  ignoreKeys.current.add(key);
  setPendingFixed(old=>[...old,{groupId:group.id,utteranceId}]);
  try{
   await enqueueWrite(current=>api('templates/utterances/fixed','POST',{
    revision:current.revision,group_id:group.id,utterance_id:row.id,fixed:!row.fixed,
   }),row.fixed?'已取消固定。':'已固定话术。',[group.id]);
  }catch(error){setError((error as Error).message);}
  finally{
   ignoreKeys.current.delete(key);
   setPendingFixed(old=>old.filter(p=>p.groupId!==group.id||p.utteranceId!==utteranceId));
  }
 }
 async function confirmWarning(warning:TemplateWarning){if(!confirm('已检查“'+warning.group_name+'”的关联资料，确认无需修改？'))return;setBusy(true);setError('');try{await api('templates/warnings/confirm','POST',{group_id:warning.group_id,revision:warning.revision});await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function exportData(filtered=false){setError('');try{if(filtered&&!groups.length)throw new Error('当前筛选没有可导出的模板');const suffix=filtered?'?group_ids='+encodeURIComponent(groups.map(g=>g.id).join(',')):'';downloadTemplates(await api<PortableTemplateLibrary>('templates/export'+suffix),filtered?'话术模板库-当前筛选.json':'话术模板库.json');}catch(e){setError((e as Error).message);}}
 function setImport(value:string){setImportText(value);setPreview(null);onDirty?.(!!value);}
 function closeImport(){if(importText&&!confirm('关闭后将放弃本次导入内容，继续吗？'))return;setImportOpen(false);setImportText('');setPreview(null);onDirty?.(false);}
 async function previewImport(){setError('');setBusy(true);try{const document=JSON.parse(importText);setPreview(await api<Preview>('templates/import/preview','POST',{document}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function commitImport(){if(!preview||preview.errors.length)return;setError('');setBusy(true);try{const result=await api<TemplateSnapshot|{proposal:unknown}>('templates/import/commit','POST',{revision:preview.revision,changes:preview.changes,source:'web-import',...(bypass?{bypass_review:true,reason}:{})});if('proposal' in result)setNotice('导入已提交为私有提案，审核通过后生效。');else setSnapshot(result);setImportOpen(false);setImportText('');setPreview(null);onDirty?.(false);await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 function create(){editorBase.current=undefined;if(!snapshot?.events.length){setNotice('请先在事件与参数设置中添加事件。');setSettings(true);return;}setEditor({id:templateId('group'),name:'',event_id:filters.event||snapshot.events[0].id,scope:{player_id:filters.player&&filters.player!=='common'?filters.player:null,lineup_note_id:filters.lineup&&filters.lineup!=='common'?filters.lineup:null},priority:0,condition_tree:{kind:'all',children:[]},expression:'',editor_mode:'tree',conditions:[],utterances:[{id:templateId('utterance'),text:''}],related_entities:[]});}
 return <main className="templates-page" onScroll={moreOnScroll}><div className="template-page-heading"><div><h1>话术模板库</h1><p>按事件整理条件与表达，查看同组全部等概率话术。</p></div><fieldset className="template-toolbar" disabled={!!utteranceEditing||queuedWrites>0}><button onClick={()=>setHelp(true)}>帮助</button>{season==='S1'&&session.role==='admin'&&<TemplateConflicts events={snapshot?.events??[]} scopeName={scopeName} onResolved={()=>void load()} onConflicts={setConflicted}/>}{season==='S1'&&<><button onClick={()=>void exportData()}>导出全库</button><button disabled={!groups.length} onClick={()=>void exportData(true)}>导出当前筛选</button></>}{editable&&<><button onClick={()=>{setError('');setBypass(false);setReason('');setImportOpen(true);}}>导入 JSON</button><button onClick={()=>setSettings(true)}>事件与参数</button><button onClick={()=>setFeedback({})}>全库批注与记录</button><button onClick={()=>setProposals(true)}>{annotator?'我的提案':'提案审核'}</button><button className="primary" disabled={busy||!snapshot} onClick={create}>＋ 新建模板组</button></>}</fieldset></div>{notice&&<div className="template-notice" role="status">{notice}<button aria-label="关闭提示" onClick={()=>setNotice('')}>×</button></div>}{error&&!importOpen&&<div role="alert" className="error template-error">{error}<button onClick={()=>void load()}>重新载入</button></div>}<div className="template-workspace"><button ref={drawerButton} className="template-mobile-events" disabled={!!utteranceEditing} aria-expanded={drawer} aria-controls="template-events" onClick={()=>setDrawer(true)}>☰ 事件分类</button>{drawer&&<button className="template-drawer-backdrop" aria-label="关闭事件分类" onClick={()=>setDrawer(false)}/>}<aside ref={drawerRef} id="template-events" inert={!!utteranceEditing} className={'template-events '+(drawer?'template-events-open':'')} aria-label="事件分类"><button className="template-mobile-close" onClick={()=>{setDrawer(false);drawerButton.current?.focus();}}>收起事件分类</button><button className={!filters.event?'selected':''} onClick={()=>{patch({event:''});setDrawer(false);}}><span>全部事件</span><span>{countGroups.length}</span></button>{categories.map(category=><section key={category}><h2>{category}</h2>{snapshot?.events.filter(e=>(e.category||'未分类')===category).map(event=><button key={event.id} className={event.id===filters.event?'selected':''} onClick={()=>{patch({event:event.id});setDrawer(false);}}><span>{event.name}</span><span>{countGroups.filter(g=>g.event_id===event.id).length}</span></button>)}</section>)}</aside><div className="template-results"><fieldset className="template-filters" disabled={!!utteranceEditing}><label>棋手<select value={filters.player} onChange={e=>patch({player:e.target.value})}><option value="">全部棋手</option><option value="common">仅通用棋手</option>{players.map(p=><option key={p.id} value={p.id}>{p.name}（含通用）</option>)}</select></label><label>阵容棋手组合<select value={filters.lineup} onChange={e=>patch({lineup:e.target.value})}><option value="">全部组合</option><option value="common">仅通用组合</option>{lineups.filter(n=>lineupPlayer(n)&&(!filters.player||(filters.player!=='common'&&lineupPlayer(n)===filters.player))).map(n=><option key={n.id} value={n.id}>{n.title}（含通用）</option>)}</select></label><label className="template-search">搜索模板<input type="search" placeholder="属性、实体名称或话术（逗号表示同时包含）" value={filters.query} onChange={e=>patch({query:e.target.value})}/></label><button onClick={()=>setFilters({event:'',player:'',lineup:'',query:''})}>清除筛选</button></fieldset><div className="template-result-heading"><h2>{snapshot?.events.find(e=>e.id===filters.event)?.name??'全部模板'}</h2><span className="muted">{groups.length} 个模板组</span><button disabled={loading||!!utteranceEditing} onClick={()=>void load()} aria-label="刷新模板库">↻</button></div><ReadingCards><div className="template-group-list" ref={groupList} onScroll={moreOnScroll}>{loading&&!snapshot?<p className="empty" role="status">正在载入模板库…</p>:!groups.length?<div className="empty"><p>{snapshot?.groups.length?'没有符合筛选的模板组。':season==='S1'?'还没有模板组。先配置事件，再添加条件与话术。':'暂无 '+season+' 模板数据'}</p>{editable&&<button onClick={create}>新建模板组</button>}</div>:groups.slice(0,visibleCount).map(group=>{
 const pending=pendingIgnores.filter(change=>change.groupId===group.id);
 const displayed=pending.reduce(applyIgnore,group);
 const saving=[...pending,...pendingFixed.filter(item=>item.groupId===group.id)];
 return <TemplateGroupCard key={group.id} group={displayed} commentCounts={commentCounts[group.id]} lastActivity={lastActivity[group.id]} onFeedback={editable?utteranceId=>setFeedback({group,utteranceId}):undefined} savingIgnore={{group:pending.some(change=>!change.utteranceId),rows:saving.flatMap(change=>change.utteranceId?[change.utteranceId]:[])}} entities={snapshot?.entity_links?.[group.id]} event={snapshot?.events.find(e=>e.id===group.event_id)} scopeName={scopeName} interactionLocked={!!utteranceEditing||saving.length>0} otherEditing={!!utteranceEditing&&utteranceEditing!==group.id} annotator={annotator} onSaveUtterances={change=>saveUtterance(group.id,change)} onUtteranceDirty={dirty=>{setUtteranceEditing(current=>dirty?group.id:current===group.id?null:current);onDirty?.(dirty);}} editable={editable&&!busy&&!conflicted.includes(group.id)&&!conflicted.includes(group.event_id)} onExport={()=>setJsonGroup({id:group.id,name:group.name})} onEdit={()=>{editorBase.current=group;setEditor(group);}} onDelete={()=>void remove(group)} onToggleIgnored={utteranceId=>void toggleIgnored(displayed,utteranceId)} onToggleFixed={session.role==='admin'?utteranceId=>void toggleFixed(group,utteranceId):undefined} warning={warnings.find(w=>w.group_id===group.id)} onConfirm={()=>{const warning=warnings.find(w=>w.group_id===group.id);if(warning)void confirmWarning(warning);}}/>;})}{visibleCount<groups.length&&<button type="button" onClick={showMore}>显示更多模板（{visibleCount} / {groups.length}）</button>}</div></ReadingCards></div></div>
 {feedback&&<TemplateFeedback groups={snapshot?.groups??[]} revision={snapshot?.revision} onLocate={(group,utterance)=>{setFeedback(null);setFilters({event:'',player:'',lineup:'',query:''});setFocusTarget({group,utterance});}} target={feedback} admin={!annotator} onClose={()=>setFeedback(null)} onChanged={()=>setFeedbackRevision(n=>n+1)}/>}
 {help&&<TemplateHelp onClose={()=>setHelp(false)}/>}
 {jsonGroup&&<TemplateJsonExport key={jsonGroup.id} groupId={jsonGroup.id} groupName={jsonGroup.name} onClose={()=>setJsonGroup(null)}/>}{editor&&snapshot&&<TemplateEditor group={editor} scopeName={scopeName} catalog={snapshot.condition_catalog} conditionLinks={snapshot.entity_condition_links?.[editor.id]} entities={snapshot.entity_links?.[editor.id]} events={snapshot.events} players={players} lineups={lineups} annotator={annotator} onDirty={onDirty} onClose={()=>setEditor(null)} onSave={(group,event)=>write([...(event?[{kind:'event' as const,action:'put' as const,id:event.id,value:event}]:[]),{kind:'group',action:'put',id:group.id,value:group}],editorBase.current)}/>}{settings&&snapshot&&<TemplateSettings events={snapshot.events} annotator={annotator} onDirty={onDirty} onClose={()=>setSettings(false)} onSave={write}/ >}{proposals&&snapshot&&<TemplateProposals snapshot={snapshot} players={players} lineups={lineups} scopeName={scopeName} admin={!annotator} onClose={()=>setProposals(false)} onChanged={()=>{setFeedbackRevision(n=>n+1);void load();}}/>}
 {importOpen&&<TemplateDialog title="导入话术模板库" onClose={closeImport} wide><div className="template-form"><p>按事件名称及组名匹配现有模板。预览后提交审核，采纳后生效。</p><label>选择 JSON 文件<input type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)void file.text().then(setImport).catch(e=>setError(e.message));}}/></label><label>或粘贴 JSON<textarea rows={10} value={importText} disabled={busy} onChange={e=>setImport(e.target.value)} spellCheck={false}/></label>{error&&<p className="error" role="alert">{error}</p>}{preview&&<section><h3>导入预览</h3><p>新增 {(preview.summary as {created?:number}).created??0} 项，更新 {(preview.summary as {updated?:number}).updated??0} 项，无变化 {(preview.summary as {unchanged?:number}).unchanged??0} 项。</p><p>共 {preview.changes.length} 项修改</p>{!!preview.preserved_fixed?.length&&<details><summary>保留 {preview.preserved_fixed.length} 条固定话术</summary>{preview.preserved_fixed.map(row=><p key={row.group_id+':'+row.utterance_id}>{row.group_name} · {row.text}</p>)}</details>}{preview.errors.length>0&&<div className="error" role="alert">{preview.errors.map((e,i)=><p key={i}>{typeof e==='string'?e:JSON.stringify(e)}</p>)}</div>}<details><summary>查看全部修改</summary>{preview.changes.map((change,i)=><p key={i}>{change.action==='delete'?'删除':'新增或更新'}{change.kind==='event'?'事件':'模板组'}：{change.value?.name??change.id}</p>)}</details></section>}{!annotator&&<><label><input type="checkbox" checked={bypass} onChange={e=>setBypass(e.target.checked)}/>跳过审核，直接导入</label>{bypass&&<label>直接导入原因<input required maxLength={4000} value={reason} onChange={e=>setReason(e.target.value)}/></label>}</>}<footer><button onClick={closeImport}>取消</button><button disabled={busy||!importText.trim()} onClick={()=>void previewImport()}>检查并预览</button><button className="primary" disabled={busy||!preview||!!preview.errors.length||!preview.changes.length||(bypass&&!reason.trim())} onClick={()=>void commitImport()}>{busy?'处理中…':bypass?'确认直接导入':'确认提交导入提案'}</button></footer></div></TemplateDialog>}</main>;
}
