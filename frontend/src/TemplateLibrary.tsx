import {createPortal} from 'react-dom';
import {TemplateConditionPreview} from './TemplateConditionPreview';
import TemplateInlineMetadata from './TemplateInlineMetadata';
import TemplateBatchMetadata from './TemplateBatchMetadata';
import {loadTemplateWarnings} from './TemplateWarnings';
import {parameterType} from './templateRules';
import {argumentCardIds,fileTriggerChanged,fixedArguments,parameterRole,templateAction} from './templateAction';
import {useCallback,useEffect,useId,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {useAuth} from './auth';
import {api} from './model';
import {EntityChip,ReadingCards,useCards} from './EntityCards';
import TemplateFilterBar,{TemplateEventList} from './TemplateFilters';
import TemplateEditor,{TemplateDialog,type TemplateEditorScratch} from './TemplateEditor';
import type {ConditionCatalog} from './templateRules';
import TemplateSettings from './TemplateSettings';
import TemplateProposals from './TemplateProposals';
import {newestProposalFirst,projectProposalCard,proposalCardPreview,type TemplateProposalPreview} from './templateProposalPreview';
import TemplateConflicts from './TemplateConflicts';
import TemplateUtterances,{applyUtteranceChange,createUtteranceDraftStore,type UtteranceChange,type UtteranceDraftStore,type UtteranceFlagFeedback} from './TemplateUtterances';
import TemplateJsonExport from './TemplateJsonExport';
import TemplateFileExport,{type FileExportScope} from './TemplateFileExport';
import TemplateHelp from './TemplateHelp';
import TemplateFeedback,{activityLabel,type Activity,type FeedbackTarget} from './TemplateFeedback';
import TemplateBoard,{TemplateEntityList,buildTemplateEntityIndex} from './TemplateBoard';
import TemplateRevisions,{TemplateOfficialDescriptions} from './TemplateRevisions';
import {fileExportDocument,fileImportDocument,parseTemplateFile,pickTemplateFile,readTemplateFile,reviewLocalGroup,saveTemplateFile,templateGroupSeason,templateGroupVersion,withLocalEntitySnapshot,writeLocalReviewStatus,writeTemplateDocument,type LocalFileHandle,type OfficialTemplateCatalog,type TemplateFile} from './templateFile';
import {applyTemplateGroupFields,groupDiffKeys,appendTemplateMetadata,copyTemplateGroup,effectiveExpression,deriveTemplateEntities,downloadTemplates,effectiveReviewStatus,emptyTemplateFilters,filterTemplateGroups,lineupPlayer,templateExplanationFields,templateMetadataLabels,templateReviewLabels,templateReviewLabel,mergeTemplateWriteSnapshot,operators,templateId,valueText,type TemplateChange,type TemplateEntity,type TemplateEvent,type TemplateFilters,type TemplateGameMode,type TemplateGroup,type TemplateMetadataField,type TemplateProposal,type TemplateReviewStatus,type TemplateSnapshot,type PortableTemplateLibrary,type TemplateWarning,type UtteranceBindings} from './templates';
import type {Note,Options} from './types';
import './templates.css';

function GroupExplanation({entries}:{entries:{label?:string;text:string}[]}){
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
  <span id={id} className="template-explanation-popup" role="tooltip" hidden={!open}>{entries.map(({label,text})=>label?<span key={label} className="template-explanation-entry"><strong>{label}</strong>{text}</span>:text)}</span>
 </span>;
}

type PendingReview={button:TemplateReviewStatus;status:TemplateReviewStatus|null};
type CardProposal=ReturnType<typeof projectProposalCard>;
type GroupEditorOperation={group?:TemplateGroup;event?:TemplateEvent;status?:TemplateReviewStatus|null;
 delete?:boolean;ignore?:{id:string;value:boolean};fixed?:{id:string;value:boolean};resolve_conditions?:string};
type EditFlag='ignored'|'fixed';
type FlagIntent={value:boolean;confirmed:boolean;error?:string;retry:()=>void};
type CardEditor={base:TemplateGroup;proposal?:TemplateProposalPreview;scratch:TemplateEditorScratch};
function groupFields(before:TemplateGroup,after:TemplateGroup){
 const set:Partial<TemplateGroup>={},remove:string[]=[];
 for(const key of new Set([...Object.keys(before),...Object.keys(after)])){
  const field=key as keyof TemplateGroup;
  if(JSON.stringify(before[field])===JSON.stringify(after[field]))continue;
  if(after[field]===undefined)remove.push(key);
  else Object.assign(set,{[key]:after[field]});
 }
 return {set,remove};
}
function appendEditorParameters(current:TemplateEvent|undefined,draft:TemplateEvent|undefined){
 if(!current||!draft)return draft;
 if(draft.parameters.some(parameter=>current.parameters.some(row=>row.key===parameter.key&&JSON.stringify(row)!==JSON.stringify(parameter))))
  throw new Error('事件参数已有新修改，请重新核对。草稿已保留。');
 return {...current,parameters:[...current.parameters,...draft.parameters.filter(row=>!current.parameters.some(parameter=>parameter.key===row.key))]};
}
function mergeEditorFields(base:TemplateGroup,current:TemplateGroup,draft:TemplateGroup){
 const fields=groupDiffKeys(base,draft),changed=new Set(groupDiffKeys(base,current)),remaining=new Set(groupDiffKeys(current,draft));
 if(fields.some(key=>changed.has(key)&&remaining.has(key)))throw new Error('同一字段已有新修改，请核对后重试。草稿已保留。');
 return applyTemplateGroupFields(current,draft,fields);
}
type ProposalControl={rows:TemplateProposalPreview[];active?:TemplateProposalPreview;original:boolean;temporary:boolean;onChange:(id:string|null)=>void;disabled:boolean;
 onApprove?:()=>void;onReject?:()=>void;onInspect?:()=>void;error?:string;submitting?:boolean;rejecting?:boolean;waiting?:boolean;
 onSaveUtterance?:(change:UtteranceChange,approve:boolean)=>Promise<void>;
};

export function TemplateGroupCard({group,event,catalog,utteranceBindings,entities:archivedEntities=[],scopeName,editable,onEdit,onSaveMetadata,metadataLocked=false,onCopy,onDelete,onExport,onFeedback,commentCounts,lastActivity,onRevisions,onReviewStatus,reviewPending,canFinalReview=false,onToggleIgnored,onToggleFixed,savingIgnore,warning,onConfirm,onSaveUtterances,utteranceDrafts,onUtteranceDraftsChanged,flagFeedback,conditionEditor,onSaveExpression,annotator=false,interactionLocked=false,fileMode=false,allowExport=true,workflow,proposal,proposalControl,originalGroup}:{group:TemplateGroup;event?:TemplateEvent;catalog?:ConditionCatalog;utteranceBindings?:UtteranceBindings;entities?:TemplateEntity[];scopeName:(id:string|null)=>string;editable:boolean;onEdit:()=>void;onSaveMetadata?:(field:'tags'|'batch',values:string[])=>Promise<void>;metadataLocked?:boolean;onCopy?:()=>void;onDelete?:()=>void;onExport?:()=>void;onFeedback?:(id?:string)=>void;commentCounts?:Record<string,number>;lastActivity?:Activity;onRevisions?:()=>void;onReviewStatus?:(status:TemplateReviewStatus|null)=>void;reviewPending?:PendingReview;canFinalReview?:boolean;onToggleIgnored?:(utteranceId?:string)=>void;onToggleFixed?:(utteranceId:string)=>void;savingIgnore?:{group:boolean;rows:string[]};warning?:TemplateWarning;onConfirm?:()=>void;onSaveUtterances?:(change:UtteranceChange)=>Promise<void>;utteranceDrafts?:UtteranceDraftStore;onUtteranceDraftsChanged?:()=>void;flagFeedback?:(id:string,field:EditFlag)=>UtteranceFlagFeedback|undefined;conditionEditor?:ReactNode;onSaveExpression?:(value:string)=>Promise<void>;annotator?:boolean;interactionLocked?:boolean;fileMode?:boolean;allowExport?:boolean;workflow?:ReactNode;proposal?:CardProposal;proposalControl?:ProposalControl;originalGroup?:TemplateGroup}){
 const cards=useCards(),entities=deriveTemplateEntities(group,event,cards,archivedEntities);
 const actionValues=fixedArguments(group);
 const explanations=templateExplanationFields.flatMap(([field,label])=>group[field]?.trim()?[{label,text:group[field]!}]:[]);
 const entries=explanations.length?explanations:group.explanation?.trim()?[{text:group.explanation}]:[];
 const {player_id:player,lineup_note_id:lineup}=group.scope;
 const playerName=player&&scopeName(player),lineupName=lineup&&scopeName(lineup);
 const expression=effectiveExpression(playerName,lineupName,group.expression??'');
 const expressionEdit=editable&&onSaveExpression&&(group.expression!==undefined||!group.conditions.length)?{
  value:group.expression??'',scope:effectiveExpression(playerName,lineupName,''),save:onSaveExpression,
 }:undefined;
 const originalExpression=originalGroup&&effectiveExpression(originalGroup.scope.player_id&&scopeName(originalGroup.scope.player_id),originalGroup.scope.lineup_note_id&&scopeName(originalGroup.scope.lineup_note_id),originalGroup.expression??'');
 const removedExpression=!!(proposal?.fields.has('rule')&&originalExpression&&!expression);
 const changed=(...fields:string[])=>proposal&&(proposal.newGroup||fields.some(field=>proposal.fields.has(field)))?true:undefined;
 const deletedLabel=(value:string)=><><s>{value}</s> <small>拟删除</small></>;
 const conditionEdit=editable?{label:'编辑模板'+group.name,disabled:interactionLocked,onClick:onEdit}:undefined;
 const status=reviewPending?reviewPending.status:effectiveReviewStatus(group.review_status),historyId=useId();
 const reviewDetails=group.reviewed_by?`复核 · ${group.reviewed_by}${group.reviewed_at?' · '+new Date(group.reviewed_at).toLocaleString():''}`:undefined;
 const Entity=fileMode?({label}:{label?:string;ids:string[];portrait?:boolean})=><span className="entity-chip">{label}</span>:EntityChip;
 return <article data-feedback-group={group.id} data-proposal-card={proposal?'preview':undefined} tabIndex={-1} className={'template-group '+(warning?'template-needs-check ':'')+(group.ignored?'template-group-ignored':'')} aria-label={group.name}>
  <header><div><h2 data-proposal-change={changed('name')||proposal?.deleted||undefined}>{proposal?.deleted?<s>{group.name}</s>:group.name}</h2><div className="template-title-controls">
   {entries.length>0&&<span data-proposal-change={changed('explanation',...templateExplanationFields.map(([field])=>field))}><GroupExplanation entries={entries}/></span>}
   {(workflow||proposal)&&<div className="template-review-statuses" role="group" aria-label={'审核状态 · '+group.name} aria-busy={!!reviewPending}>
    {(Object.entries(templateReviewLabels) as [TemplateReviewStatus,string][]).map(([value,label])=>{
     const selected=value===status;
     return <button type="button" key={value} aria-pressed={selected} title={selected?reviewDetails:undefined} data-review-pending={reviewPending?.button===value||undefined}
      data-proposal-change={selected?changed('review_status'):undefined}
      disabled={!onReviewStatus||value==='final_reviewed'&&!canFinalReview&&!selected}
      onClick={()=>onReviewStatus?.(selected?null:value)}>{label}</button>;
    })}{status===null&&changed('review_status')&&<span className="template-proposal-mark">{templateReviewLabel(null)}</span>}
   </div>}</div>
   <div className="template-scope"><span data-proposal-change={changed('event_id','event')}>{event?.name??group.event_id}</span>
    {(group.version||changed('version')&&originalGroup?.version)&&<span data-proposal-change={changed('version')}>{group.version||deletedLabel(originalGroup!.version!)}</span>}
    {(group.mode||changed('mode')&&originalGroup?.mode)&&<span data-proposal-change={changed('mode')}>{group.mode||deletedLabel(originalGroup!.mode!)}</span>}
    <TemplateInlineMetadata label="标签" values={group.tags??[]} proposalPrevious={changed('tags')?originalGroup?.tags??[]:undefined} disabled={metadataLocked} onSave={editable&&onSaveMetadata?values=>onSaveMetadata('tags',values):undefined}/>
    <TemplateInlineMetadata label="批次" values={group.batch??[]} proposalPrevious={changed('batch')?originalGroup?.batch??[]:undefined} disabled={metadataLocked} onSave={editable&&onSaveMetadata?values=>onSaveMetadata('batch',values):undefined}/>
    <span data-proposal-change={changed('priority')}>优先级 {group.priority??0}</span>
    {(group.ignored||changed('ignored'))&&<span className="template-ignored" data-proposal-change={changed('ignored')}>{group.ignored?'已忽略':'参与导出'}</span>}
    {group.last_modified_by&&<span>最后修改 · {group.last_modified_by.kind==='ai'?'AI':group.last_modified_by.username??'人工'}</span>}
   </div></div>
   <div className="template-card-actions">
    {onRevisions&&<div className="template-history-control"><button type="button" aria-describedby={historyId} disabled={interactionLocked} onClick={onRevisions}>版本记录</button>
     <span className="template-history-tooltip" id={historyId} role="tooltip">{lastActivity?`最近操作 · ${activityLabel(lastActivity)}`:'查看修订历史'}</span></div>}
    {onFeedback&&<button disabled={interactionLocked} onClick={()=>onFeedback()}>组批注与记录 <span className="template-comment-count">{commentCounts?.['']??0}</span></button>}
    {allowExport&&<button aria-label={'导出json：'+group.name} disabled={interactionLocked||group.ignored||group.utterances.every(row=>row.ignored)} onClick={onExport}>导出json</button>}
    {editable&&<>
     {onCopy&&<button type="button" aria-label={'复制模板组'+group.name} disabled={interactionLocked} onClick={onCopy}>复制</button>}
     {onToggleIgnored&&<button disabled={interactionLocked} onClick={()=>onToggleIgnored()}>{savingIgnore?.group?'保存中…':group.ignored?'取消忽略':'忽略'}</button>}
     {onDelete&&<button aria-label={'删除模板'+group.name} disabled={interactionLocked||group.utterances.some(row=>row.fixed)} title={group.utterances.some(row=>row.fixed)?'先取消固定再删除模板组':undefined} onClick={onDelete}>删除模板</button>}</>}
    {workflow}
   </div></header>
  {proposalControl&&<div className="template-card-proposal">
   {proposal?<><strong className="template-proposal-mark">{proposal.deleted?'提案 · 拟删除模板组':proposal.newGroup?'提案 · 新模板组':'提案预览'}</strong>
    {proposalControl.active&&<span>{proposalControl.active.author}</span>}</>:<span>{proposalControl.rows.length} 条待审核提案</span>}
   {proposal&&!proposalControl.temporary&&proposalControl.rows.length>1&&<label>预览提案
    <select value={proposalControl.active?.proposal_id} disabled={proposalControl.disabled} onChange={event=>proposalControl.onChange(event.currentTarget.value)}>
     {proposalControl.rows.map(row=><option key={row.proposal_id} value={row.proposal_id}>{row.author} · {new Date(row.created_at).toLocaleString()}</option>)}
    </select></label>}
   {proposalControl.onApprove&&<button type="button" className="primary" disabled={proposalControl.disabled||proposalControl.submitting||proposalControl.rejecting||proposalControl.waiting} onClick={proposalControl.onApprove}>
    {proposalControl.submitting?'采纳中…':proposalControl.waiting?'等待保存…':'采纳本组'}</button>}
   {proposalControl.onReject&&<button type="button" disabled={proposalControl.disabled||proposalControl.submitting||proposalControl.rejecting||proposalControl.waiting} onClick={proposalControl.onReject}>
    {proposalControl.rejecting?'驳回中…':'驳回本组'}</button>}
   {!proposalControl.temporary&&<button type="button" disabled={proposalControl.disabled} onClick={()=>proposalControl.onChange(proposalControl.original?(proposalControl.active??proposalControl.rows[0]).proposal_id:null)}>
    {proposalControl.original?'显示提案':'显示原数据'}</button>}
   {proposalControl.error&&<span className="template-proposal-action-error" role="alert">{proposalControl.error}</span>}
   {proposalControl.onInspect&&<button type="button" disabled={proposalControl.disabled} onClick={proposalControl.onInspect}>在提案浮窗核对</button>}
  </div>}
  {warning&&<div className="template-warning" role="status"><strong>关联资料已变化，待检查</strong><span>{warning.entities.map(e=>e.name).join('、')}</span>{editable&&!annotator&&onConfirm&&<button disabled={interactionLocked} onClick={onConfirm}>已检查，无需修改</button>}</div>}
  <div className="template-group-body"><section className="template-read-conditions" aria-label="卡牌与条件">
   <p className="template-action" data-proposal-change={changed('rule','event_id','event')}><strong>触发动作</strong> {templateAction(group,event,actionValues)}</p>
   {!!event?.parameters.length && <dl aria-label="动作参数" className="template-action-parameters" data-proposal-change={changed('rule','event_id','event')}>{event.parameters.map(p=>{
    const value=actionValues.get(p.key),ids=value?argumentCardIds(p,value,cards):[];
    return <div key={p.key}><dt><code>{p.key}</code></dt><dd>{parameterRole(event,p)} <small>（{parameterType(p)}）</small>
     {value&&(ids.length?<Entity ids={ids} label={value} portrait/>:<strong> · {value}</strong>)}</dd></div>;
   })}</dl>}
   <div className="template-condition-scopes" data-proposal-change={changed('scope')}><span>棋手：{scopeName(group.scope.player_id)}</span><span>阵容：{scopeName(group.scope.lineup_note_id)}</span></div>
   {entities.length>0&&<div className="template-chips" aria-label="关联卡牌" data-proposal-change={changed('related_entities')}>{entities.map(e=><Entity key={e.id} ids={[e.id]} label={e.name} portrait/>)}</div>}
   {group.expression===undefined&&group.conditions.length>0&&<><h3>同时满足</h3><dl>{group.conditions.map(c=>{const parameter=event?.parameters.find(p=>p.key===c.parameter_key);const entity=c.value as TemplateEntity;const removed=proposal?.removedConditions.includes(c.id);return <div key={c.id} data-proposal-change={changed('condition:'+c.id)}><dt>{parameter?.name??c.parameter_key}</dt><dd>{removed?deletedLabel(operators[c.operator]+' '+valueText(c.value)):<><span>{operators[c.operator]} </span>{parameter?.type==='entity'&&entity?.id?<Entity ids={deriveTemplateEntities({...group,scope:{player_id:null,lineup_note_id:null},conditions:[c]},event,cards).map(e=>e.id)} label={entity.name}/>:valueText(c.value)}</>}</dd></div>;})}</dl></>}{group.expression===undefined&&!expression&&!group.conditions.length&&<p className="muted">不限制条件</p>}
   {group.expression!==undefined||expression||removedExpression||expressionEdit?<div data-proposal-change={changed('rule','scope')}>
    <TemplateConditionPreview expression={removedExpression?originalExpression!:expression} edit={conditionEdit} expressionEdit={expressionEdit} allowCopy={!proposal} removed={removedExpression}/>
   </div>:conditionEdit&&
    <div className="template-condition-actions"><button type="button" aria-label={conditionEdit.label} disabled={conditionEdit.disabled} onClick={conditionEdit.onClick}>编辑模板组</button></div>}
   {conditionEditor}
  </section><TemplateUtterances commentCounts={commentCounts} onFeedback={onFeedback} utterances={group.utterances} bindings={utteranceBindings} parameters={event?.parameters} event={event} catalog={catalog} localFile={fileMode}
   editable={editable||!!proposalControl?.onSaveUtterance} annotator={annotator} disabled={false} savingIgnoreIds={savingIgnore?.rows}
   onToggleIgnored={onToggleIgnored} onToggleFixed={onToggleFixed}
   onSave={proposalControl?.onSaveUtterance?change=>proposalControl.onSaveUtterance!(change,false):onSaveUtterances}
   onSaveAndApprove={proposalControl?.onSaveUtterance&&proposalControl.onApprove?change=>proposalControl.onSaveUtterance!(change,true):undefined}
   proposalEditing={!!proposal} draftStore={utteranceDrafts} onDraftsChanged={onUtteranceDraftsChanged} flagFeedback={flagFeedback} proposal={proposal&&{fields:proposal.fields,removed:proposal.removedUtterances,all:proposal.newGroup}}/></div>
  {workflow&&<TemplateOfficialDescriptions group={group}/>}
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
type OpenFile={handle:LocalFileHandle;raw:string};
type View={filters:TemplateFilters;entityKey:string;byEntity:boolean;compact:boolean;selected:Set<string>};
export type TemplateWorkspaceState={opened?:OpenFile|null;views?:Record<string,View>;scroll?:Record<string,{top:number;visible:number}>;utteranceDrafts?:Map<string,UtteranceDraftStore>;cardEditors?:Map<string,CardEditor>;fileKeys?:WeakMap<LocalFileHandle,string>};
const emptyView:View={filters:emptyTemplateFilters,entityKey:'',byEntity:false,compact:false,selected:new Set()};
const templatePath=(season:Season,suffix='')=>'templates'+suffix+(suffix.includes('?')?'&':'?')+'season='+season;

export default function TemplateLibrary({notes,options,onDirty,onBusyChange,season='S1',source='database',gameMode,workspace}:{season?:Season;source?:'database'|'file';gameMode?:TemplateGameMode;notes:Note[];options:Options;onDirty?:(dirty:boolean)=>void;onBusyChange?:(busy:boolean)=>void;workspace?:TemplateWorkspaceState}){
 const [legacy,setLegacy]=useState<TemplateSnapshot|null>(null),[showLegacy,setShowLegacy]=useState(false);
 const {session}=useAuth(),fileMode=source==='file',legacyMode=!fileMode&&season==='S2'&&showLegacy&&!!legacy?.groups.length;
 const admin=session.role==='admin',annotator=session.role==='annotator',reviewer=!legacyMode&&(admin||session.role==='quality'),editable=reviewer||!legacyMode&&annotator;
 const canManage=editable&&(fileMode||admin||annotator);
 const cards=useCards();
 const [database,setDatabase]=useState<TemplateSnapshot|null>(null),[opened,setOpened]=useState<OpenFile|null>(()=>workspace?.opened??null);
 const openedFile=useRef(opened);
 const [official,setOfficial]=useState<OfficialTemplateCatalog>(),[officialError,setOfficialError]=useState('');
 const lookups=useMemo(()=>({entities:[...options.entities,...cards,...(official?.season===season?official.items:[])],lineups:notes.filter(n=>n.type==='lineup')}),[options.entities,cards,notes,official,season]);
 const parsedFile=useRef<{opened:OpenFile;lookups:typeof lookups;value:TemplateFile}|null>(null);
 function documentFor(opened:OpenFile){
  const cached=parsedFile.current;
  if(cached?.opened===opened&&cached.lookups===lookups)return cached.value;
  const value=parseTemplateFile(opened.raw,lookups);
  parsedFile.current={opened,lookups,value};
  return value;
 }
 const file=opened?documentFor(opened):null;
 const snapshot=fileMode?file?.snapshot??null:legacyMode?legacy:database;
 const [views,setViews]=useState<Record<string,View>>(()=>workspace?.views??{});
 useEffect(()=>{if(workspace)workspace.views=views;},[workspace,views]);
 function rememberFile(file:OpenFile){
  openedFile.current=file;
  if(workspace)workspace.opened=file;
  setOpened(file);
 }
 const viewKey=(legacyMode?'legacy':source)+':'+season,view=views[viewKey]??emptyView,{filters,entityKey,byEntity,compact,selected}=view;
 const changeView=(update:(current:View)=>View)=>setViews(current=>({...current,[viewKey]:update(current[viewKey]??emptyView)}));
 const setFilters=(update:TemplateFilters|((current:TemplateFilters)=>TemplateFilters))=>changeView(current=>({...current,filters:typeof update==='function'?update(current.filters):update}));
 const selectGroups=(ids:string[],checked:boolean)=>changeView(current=>{
  const next=new Set(current.selected);for(const id of ids)if(checked)next.add(id);else next.delete(id);
  return {...current,selected:next};
 });
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[editor,setEditor]=useState<TemplateGroup|null>(null),[settings,setSettings]=useState(false),[proposals,setProposals]=useState(false),[importOpen,setImportOpen]=useState(false),[importText,setImportText]=useState(''),[importSelection,setImportSelection]=useState<TemplateGroup[]|null>(null),[preview,setPreview]=useState<Preview|null>(null),[warnings,setWarnings]=useState<TemplateWarning[]>([]),[conflicted,setConflicted]=useState<string[]>([]);
 const [detailId,setDetailId]=useState<string|null>(null),[revisionGroup,setRevisionGroup]=useState<TemplateGroup|null>(null);
 const [locatedDetail,setLocatedDetail]=useState<{id:string;identity:string}|null>(null);
 const [proposalRefresh,setProposalRefresh]=useState(0);
 const [proposalPreviews,setProposalPreviews]=useState<{identity:string;items:TemplateProposalPreview[];error?:string}>();
 const [proposalChoices,setProposalChoices]=useState<Record<string,string|null|undefined>>({});
 const [proposalActionError,setProposalActionError]=useState<{id:string;groupId:string;message:string}>();
 const [approving,setApproving]=useState(new Set<string>());
 const [waitingApprovals,setWaitingApprovals]=useState(new Set<string>());
 const approvals=useRef(new Set<string>());
 const deletingGroups=useRef(new Set<string>());
 const [,redrawDelete]=useState(0);
 const proposalQueue=useRef(new Map<string,Promise<void>>());
 const proposalFailures=useRef(new Map<string,number>());
 const confirmedPreviews=useRef(new Map<string,TemplateProposalPreview[]|null>());
 const [utteranceDrafts]=useState(()=>workspace?.utteranceDrafts??new Map<string,UtteranceDraftStore>());
 const [cardEditors]=useState(()=>workspace?.cardEditors??new Map<string,CardEditor>());
 const [fileKeys]=useState(()=>workspace?.fileKeys??new WeakMap<LocalFileHandle,string>());
 const [,redrawEditors]=useState(0);
 const flags=useRef(new Map<string,FlagIntent>());
 const [,redrawFlags]=useState(0);
 useEffect(()=>{if(workspace){workspace.utteranceDrafts=utteranceDrafts;workspace.cardEditors=cardEditors;workspace.fileKeys=fileKeys;}},[workspace,utteranceDrafts,cardEditors,fileKeys]);
 const [inspectProposal,setInspectProposal]=useState<string>();
 const proposalIdentity=session.role+':'+(session.username??'');
 const identityRef=useRef(proposalIdentity);identityRef.current=proposalIdentity;
 const previewEpoch=useRef(0);
 const previewEnabled=!fileMode&&!legacyMode&&editable;
 const refreshProposals=()=>setProposalRefresh(value=>value+1);
 useEffect(()=>{
  if(!previewEnabled)return;
  let active=true,request=0;
  const fetchPreviews=async()=>{
   const latest=++request,generation=previewEpoch.current;
   try{
    const items=await api<TemplateProposalPreview[]>('templates/proposals?view=card-preview');
    if(active&&latest===request&&generation===previewEpoch.current){
     for(const id of confirmedPreviews.current.keys()){
      if(!proposalQueue.current.has(id))confirmedPreviews.current.delete(id);
     }
     setProposalPreviews({identity:proposalIdentity,items});
    }
   }catch(error){
    if(active&&latest===request)setProposalPreviews(current=>({
     identity:proposalIdentity,items:current?.identity===proposalIdentity?current.items:[],error:(error as Error).message,
    }));
   }
  };
  void fetchPreviews();
  const onFocus=()=>{if(!document.hidden)void fetchPreviews();};
  window.addEventListener('focus',onFocus);
  return ()=>{active=false;window.removeEventListener('focus',onFocus);};
 },[previewEnabled,proposalIdentity,proposalRefresh]);
 useEffect(()=>{setProposalChoices({});setProposalActionError(undefined);},[viewKey,gameMode,compact,byEntity,entityKey,filters,proposalIdentity]);
 const previewsByGroup=useMemo(()=>{
  const groups=new Map<string,TemplateProposalPreview[]>();
  if(previewEnabled&&proposalPreviews?.identity===proposalIdentity){
   for(const item of [...proposalPreviews.items].sort(newestProposalFirst)){
    const rows=groups.get(item.change.id)??[];
    rows.push(item);groups.set(item.change.id,rows);
   }
  }
  return groups;
 },[previewEnabled,proposalIdentity,proposalPreviews]);
 function chooseProposal(id:string,choice:string|null|undefined){
  setProposalChoices(current=>({...current,[id]:choice}));
  setProposalActionError(undefined);
 }
 const [batchMetadata,setBatchMetadata]=useState<TemplateMetadataField|null>(null);
 const [pendingReviews,setPendingReviews]=useState(new Map<string,PendingReview>());
 const reviewRequests=useRef(new Map<string,PendingReview>());
 const fileInlineQueue=useRef<Promise<void>>(Promise.resolve());
 const fileReviewWrite=useRef(false);
 const fileMetadataWrite=useRef(false);
 const reviewKey=(id:string)=>source+':'+season+':'+id;
 const [fileExport,setFileExport]=useState<{group?:TemplateGroup}>();
 const saveFileLock=useRef(false),pickerLock=useRef(false);
 const [pendingIgnores,setPendingIgnores]=useState<IgnoreChange[]>([]);
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
  if(fileMode||!editable)return;
  let active=true;
  async function read(){
   try{
    const {items}=await api<{items:{group_id:string;utterance_id:string|null;count:number}[]}>(templatePath(season,'/comments?counts=1'));
    const counts:Record<string,Record<string,number>>=Object.create(null);
    for(const row of items)(counts[row.group_id]??=Object.create(null))[row.utterance_id??'']=row.count;
    if(active)setCommentCounts(counts);
   }catch(e){if(active)setError('批注条数读取失败：'+(e as Error).message);}
  }
  void read();
  return ()=>{active=false;};
 },[fileMode,editable,season,feedbackRevision,snapshot?.read_generation]);
 const [lastActivity,setLastActivity]=useState<Record<string,Activity>>({});
 const [bypass,setBypass]=useState(false),[reason,setReason]=useState('');
 useEffect(()=>{
  if(fileMode||!editable||!snapshot?.revision)return;
  let active=true;api<{items:Activity[]}>(templatePath(season,'/history?latest=1')).then(data=>{if(active)setLastActivity(Object.fromEntries(data.items.map(a=>[a.group_id,a])));}).catch(e=>{if(active)setError('管理员操作记录读取失败：'+e.message);});return()=>{active=false;};
 },[fileMode,editable,season,snapshot?.revision,feedbackRevision]);
 const [jsonGroup,setJsonGroup]=useState<{id:string;name:string}|null>(null);
 const epoch=useRef(0);
 const projectionTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const load=useCallback(async(knownGeneration?:string,silent=false)=>{
  if(fileMode)return;
  const current=++epoch.current;
  if(!knownGeneration&&!silent){setLoading(true);setError('');}
  try{
   const data=await api<TemplateSnapshot|{unchanged:true}>(templatePath(season,knownGeneration?'?if_generation='+encodeURIComponent(knownGeneration):''));
   if(current!==epoch.current||'unchanged' in data)return;
   setDatabase(data);
   void loadTemplateWarnings().then(warning=>{if(current===epoch.current)setWarnings(warning.items);})
    .catch(e=>{if(current===epoch.current)setError('关联资料变化检查失败：'+e.message);});
  }catch(e){if(current===epoch.current)setError((e as Error).message);}
  finally{if(current===epoch.current)setLoading(false);}
 },[fileMode,season]);
 useEffect(()=>{
  if(fileMode||season!=='S2')return;
  let active=true;
  api<TemplateSnapshot>(templatePath(season,'?legacy=1')).then(result=>{if(active&&result.groups.length)setLegacy(result);}).catch(()=>{});
  return()=>{active=false;};
 },[fileMode,season]);
 useEffect(()=>{void load();return()=>{epoch.current++;clearTimeout(projectionTimer.current);};},[load]);
 useEffect(()=>{
  if(!fileMode)return;
  let active=true;
  setOfficialError('');
  api<OfficialTemplateCatalog>(templatePath(season,'/official')).then(result=>{if(active)setOfficial(result);})
   .catch(error=>{if(active)setOfficialError((error as Error).message);});
  return()=>{active=false;};
 },[fileMode,season]);
 useEffect(()=>{
  setError('');setNotice('');setDetailId(null);setLocatedDetail(null);setFocusTarget(null);setRevisionGroup(null);setEditor(null);setJsonGroup(null);setFeedback(null);
  setSettings(false);setProposals(false);setImportOpen(false);setImportSelection(null);setImportText('');setPreview(null);setFileExport(undefined);setBatchMetadata(null);
  onDirty?.(false);
 },[viewKey,gameMode]);
 const checkingAllowed=!fileMode&&!legacyMode&&!busy&&!queuedWrites&&!editor&&!approving.size&&!settings&&!proposals&&!importOpen;
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
 const players=useMemo(()=>{const map=new Map([...options.entities,...cards].filter(e=>['players','player'].includes(e.category??'')).map(e=>[e.id,{id:e.id,name:e.name}]));for(const n of notes)if(n.type==='player'&&n.player_id&&!map.has(n.player_id))map.set(n.player_id,{id:n.player_id,name:n.title});return Array.from(map.values());},[options.entities,cards,notes]);
 const lineups=lookups.lineups,scopeName=(id:string|null)=>id?(players.find(p=>p.id===id)?.name??notes.find(n=>n.id===id)?.title??snapshot?.scope_names?.[id]??id):'通用';
 const allGroups=useMemo(()=>snapshot?.groups.filter(group=>(legacyMode||templateGroupSeason(group)===season)&&(!gameMode||group.mode===gameMode))??[],[snapshot,season,legacyMode,gameMode]);
 const entityEntries=useMemo(()=>buildTemplateEntityIndex(allGroups,snapshot?.events??[],lookups.entities,snapshot?.condition_catalog),[allGroups,snapshot,lookups]);
 const allEntityIds=useMemo(()=>new Set(entityEntries.flatMap(row=>[...row.groupIds])),[entityEntries]);
 const entity=byEntity?entityEntries.find(row=>row.key===entityKey):undefined;
 const searchLabels={events:snapshot?.events,scopeName,links:snapshot?.entity_links,utteranceBindings:snapshot?.utterance_bindings};
 const countGroups=filterTemplateGroups(allGroups,{...filters,event:'',mode:gameMode===undefined?filters.mode:undefined},lookups.entities,searchLabels);
 const groups=byEntity?countGroups.filter(group=>(entity?.groupIds??allEntityIds).has(group.id)):filters.event?countGroups.filter(group=>group.event_id===filters.event):countGroups;
 const selectedGroups=allGroups.filter(group=>selected.has(group.id));
 const currentLocation=locatedDetail?.identity===proposalIdentity?locatedDetail:undefined;
 const locatedGroup=currentLocation&&snapshot?.groups.find(group=>group.id===currentLocation.id);
 const temporaryGroup=currentLocation&&!locatedGroup?(previewsByGroup.get(currentLocation.id)?.find(row=>
  !row.base&&row.proposal_id===proposalChoices[currentLocation.id])?.change.value as TemplateGroup|undefined):undefined;
 const detailGroup=allGroups.find(group=>group.id===detailId)??(previewEnabled?locatedGroup??temporaryGroup:undefined);
 useEffect(()=>{
  if(!focusTarget)return;
  const selector='[data-feedback-group="'+CSS.escape(focusTarget.group)+'"]';
  const card=document.querySelector<HTMLElement>('[role="dialog"] '+selector)??document.querySelector<HTMLElement>(selector);
  const node=focusTarget.utterance?card?.querySelector<HTMLElement>('[data-feedback-utterance="'+CSS.escape(focusTarget.utterance)+'"]'):card;
  if(node){node.focus({preventScroll:true});node.scrollIntoView({block:'center'});}
  setFocusTarget(null);
 },[focusTarget,detailGroup?.id]);
 function patch(value:Partial<TemplateFilters>){setFilters(f=>{const next={...f,...value};if(value.lineup&&value.lineup!=='common'){const n=lineups.find(n=>n.id===value.lineup);if(n)next.player=lineupPlayer(n)??next.player;}if(value.player!==undefined&&next.lineup&&next.lineup!=='common'){const n=lineups.find(n=>n.id===next.lineup);if(n&&lineupPlayer(n)!==value.player)next.lineup='';}return next;});}
 function enqueueWrite(run:(current:TemplateSnapshot,accept:(result:TemplateSnapshot)=>TemplateSnapshot)=>Promise<TemplateSnapshot|{proposal:unknown}>,notice:string|null,groupIds:string[],statusOnly=false){
  if(!snapshot)return Promise.reject(new Error('模板库尚未载入'));
  if(!statusOnly)clearTimeout(projectionTimer.current);
  if(!queueSize.current)queueSnapshot.current=snapshot;
  setQueuedWrites(++queueSize.current);
  const save=queue.current.then(async()=>{
   const current=queueSnapshot.current!;
   const accept=(result:TemplateSnapshot)=>{
    const previous=queueSnapshot.current!;
    const next=statusOnly?{...previous,revision:result.revision,groups:previous.groups.map(group=>{
     const updated=groupIds.includes(group.id)?result.groups.find(row=>row.id===group.id):undefined;
     return updated?{...group,review_status:updated.review_status,reviewed_by:updated.reviewed_by,reviewed_at:updated.reviewed_at}:group;
    })}:mergeTemplateWriteSnapshot(previous,result,groupIds);
    queueSnapshot.current=next;
    epoch.current++;
    setLoading(false);
    setDatabase(next);
    return next;
   };
   try{
    const result=await run(current,accept);
    if('proposal' in result){refreshProposals();if(notice!==null)setNotice('修改已提交，待审核。');return;}
    if(queueSnapshot.current!==result)accept(result);
    if(notice!==null)setNotice(notice);
    if(!statusOnly&&current.read_generation){
     clearTimeout(projectionTimer.current);
     const refresh=()=>{
      if(queueSize.current)projectionTimer.current=setTimeout(refresh,400);
      else void load(current.read_generation,true);
     };
     projectionTimer.current=setTimeout(refresh,400);
    }
   }catch(error){
    if((error as {status?:number}).status===409){
     // Use the server revision for the next queued operation. An editor's
     // draft and the record it started from remain independent of this read.
     const latest=await api<TemplateSnapshot>(templatePath(season));
     queueSnapshot.current=latest;
     epoch.current++;
     setLoading(false);
     setDatabase(latest);
    }
    throw error;
   }
  }).finally(()=>{setQueuedWrites(--queueSize.current);});
  queue.current=save.catch(()=>{});
  return save;
 }
 async function openFile(reuse=false){
  if(pickerLock.current||saveFileLock.current)return;
  pickerLock.current=true;onBusyChange?.(true);setBusy(true);setError('');
  try{
   const handle=reuse&&opened?opened.handle:await pickTemplateFile();
   const raw=await readTemplateFile(handle);
   parseTemplateFile(raw,lookups);
   if(!reuse){
    setViews(current=>Object.fromEntries(Object.entries(current).filter(([key])=>!key.startsWith('file:'))));
    setDetailId(null);
   }
   rememberFile({handle,raw});setNotice('');
  }catch(error){if((error as DOMException).name!=='AbortError')setError((error as Error).message);}
  finally{pickerLock.current=false;onBusyChange?.(false);setBusy(false);}
 }
 async function saveLocal(changes:TemplateChange[],action:'edit'|'status'='edit',destination=action==='status'?openedFile.current:opened,showNotice=true){
  const document=destination&&documentFor(destination);
  if(!destination||!document)throw new Error('请先打开模板文件。');
  if(saveFileLock.current||pickerLock.current)throw new Error('文件正在处理，请稍后再试。');
  saveFileLock.current=true;onBusyChange?.(true);setBusy(true);setError('');
  try{
   const at=new Date().toISOString(),user=session.username??'local';
   const marked=changes.flatMap(change=>{
    if(action==='status'||change.kind!=='group'||change.action!=='put')return [change];
    const group=change.value as TemplateGroup;
    const previous=document.snapshot.groups.find(row=>row.id===group.id);
    if(JSON.stringify(previous)===JSON.stringify(group))return [];
    const event=(changes.find(row=>row.kind==='event'&&row.id===group.event_id)?.value as TemplateEvent|undefined)??document.snapshot.events.find(row=>row.id===group.event_id);
    const references=deriveTemplateEntities(group,event,lookups.entities);
    const catalog=official?.season===templateGroupSeason(group)?official:undefined;
    const edited=reviewLocalGroup(group,user,'edit',at);
    const value=withLocalEntitySnapshot(edited,event,catalog,references,document.snapshot.condition_catalog,lookups.entities);
    return [{...change,value}];
   });
   if(!marked.length)return;
   const next=action==='status'?writeLocalReviewStatus(document,marked[0].value as TemplateGroup):writeTemplateDocument(document,marked,lookups);
   const parsed=parseTemplateFile(JSON.stringify(next),lookups);
   const raw=await saveTemplateFile(destination.handle,destination.raw,next);
   const updatedIds=new Map(marked.flatMap(change=>{
    if(change.kind!=='group')return [];
    if(change.action==='delete')return [[change.id,null] as const];
    const group=change.value as TemplateGroup;
    const event=parsed.snapshot.events.find(row=>row.name===(marked.find(row=>row.kind==='event'&&row.id===group.event_id)?.value?.name??document.snapshot.events.find(row=>row.id===group.event_id)?.name));
    const nextGroup=parsed.snapshot.groups.find(row=>row.id===group.id)??parsed.snapshot.groups.find(row=>row.name===group.name&&row.event_id===event?.id&&templateGroupVersion(row)===templateGroupVersion(group));
    return [[change.id,nextGroup?.id??null] as const];
   }));
   const savedFile={...destination,raw};
   parsedFile.current={opened:savedFile,lookups,value:parsed};
   rememberFile(savedFile);
   setDetailId(id=>id&&updatedIds.has(id)?updatedIds.get(id)??null:id);
   changeView(current=>({...current,selected:new Set([...current.selected].flatMap(id=>updatedIds.has(id)?updatedIds.get(id)??[]:id))}));
   if(action!=='status'&&showNotice)setNotice('已保存到原文件。');
  }finally{saveFileLock.current=false;onBusyChange?.(false);setBusy(false);}
 }
 function write(changes:TemplateChange[],original?:TemplateGroup){
  if(fileMode){
   const localChanges=original?changes.map(change=>{
    if(change.kind!=='group'||change.action!=='put'||change.id!==original.id)return change;
    const draft=change.value as TemplateGroup;
    const oldEvent=snapshot?.events.find(event=>event.id===original.event_id);
    const nextEvent=(changes.find(row=>row.kind==='event'&&row.id===draft.event_id)?.value as TemplateEvent|undefined)
     ??snapshot?.events.find(event=>event.id===draft.event_id);
    if(!fileTriggerChanged(original,draft,oldEvent,nextEvent))return change;
    const id=templateId('group');
    return {...change,id,value:{...draft,id,utterances:draft.utterances.map(({fixed,...row})=>row)}};
   }):changes;
   return saveLocal(localChanges);
  }
  return enqueueWrite(current=>{
   if(original&&JSON.stringify(current.groups.find(row=>row.id===original.id))!==JSON.stringify(original))
    throw new Error('该模板组已有修改，请核对最新内容后重新编辑。当前草稿已保留。');
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,changes});
  },'模板库已保存。',changes.filter(c=>c.kind==='group').map(c=>c.id));
 }
 async function remove(group:TemplateGroup){
  if(deletingGroups.current.has(group.id)||!confirm('确定删除模板组“'+group.name+'”及其中全部话术吗？'))return;
  const changes:TemplateChange[]=[{kind:'group',action:'delete',id:group.id}];
  deletingGroups.current.add(group.id);redrawDelete(value=>value+1);
  try{
   if(fileMode)await enqueueFileMetadataChanges(()=>changes);
   else await enqueueWrite(current=>api(templatePath(season,'/changes'),'POST',{revision:current.revision,changes}),null,[group.id]);
  }catch(error){setError((error as Error).message);}
  finally{deletingGroups.current.delete(group.id);redrawDelete(value=>value+1);}
 }
 function enqueueGroupChange(groupId:string,update:(group:TemplateGroup)=>TemplateGroup,notice:string|null='模板库已保存。'){
  if(fileMode)return enqueueFileMetadataChanges(groups=>{
   const group=groups.find(row=>row.id===groupId);
   if(!group)throw new Error('模板组已不存在，请重新读取文件。');
   return [{kind:'group',action:'put',id:groupId,value:update(group)}];
  });
  return enqueueWrite(current=>{
   const group=current.groups.find(row=>row.id===groupId);
   if(!group)throw new Error('模板组已不存在，请刷新后重试');
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,group_patches:[{id:groupId,fields:groupFields(group,update(group))}]});
  },notice,[groupId]);
 }
 function enqueueFileMetadataChanges(prepare:(groups:TemplateGroup[],events:TemplateEvent[])=>TemplateChange[],showNotice=false){
  const save=fileInlineQueue.current.then(async()=>{
   const destination=openedFile.current;
   if(!destination||destination.handle!==opened?.handle)throw new Error('模板文件已切换，请重新编辑。');
   const document=documentFor(destination);
   if(!document)throw new Error('请先打开模板文件。');
   const changes=prepare(document.snapshot.groups,document.snapshot.events);
   if(!changes.length)return;
   fileMetadataWrite.current=true;
   try{await saveLocal(changes,'edit',destination,showNotice);}
   finally{fileMetadataWrite.current=false;}
  });
  fileInlineQueue.current=save.catch(()=>{});
  return save;
 }
 function saveMetadata(groupId:string,field:TemplateMetadataField,values:string[]){
  const update=(group:TemplateGroup)=>({...group,[field]:values});
  if(!fileMode)return enqueueGroupChange(groupId,update,'');
  return enqueueFileMetadataChanges(groups=>{
   const current=groups.find(group=>group.id===groupId);
   if(!current)throw new Error('找不到要修改的模板组。');
   return [{kind:'group',action:'put',id:groupId,value:update(current)}];
  });
 }
 function saveBatchMetadata(field:TemplateMetadataField,values:string[]){
  const ids=new Set(selectedGroups.map(group=>group.id));
  const prepare=(current:TemplateGroup[])=>{
   const targets=current.filter(group=>ids.has(group.id));
   if(targets.length!==ids.size)throw new Error('部分所选模板组已不存在，请重新选择。');
   return appendTemplateMetadata(targets,field,values);
  };
  if(fileMode)return enqueueFileMetadataChanges(prepare,true);
  return enqueueWrite(async current=>{
   const changes=prepare(current.groups);
   if(!changes.length)return current;
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,changes});
  },'已批量添加'+templateMetadataLabels[field]+'。',[...ids]);
 }
 function saveUtterance(groupId:string,change:UtteranceChange){
  return enqueueGroupChange(groupId,group=>applyUtteranceChange(group,change));
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
 async function changeReviewStatus(group:TemplateGroup,status:TemplateReviewStatus|null){
  const key=reviewKey(group.id),queued=reviewRequests.current.get(key);
  const previous=queued?queued.status:effectiveReviewStatus(group.review_status),button=status??previous;
  if(!editable||!button||status==='final_reviewed'&&!reviewer||status===previous)return;
  reviewRequests.current.set(key,{button,status});
  setPendingReviews(new Map(reviewRequests.current));
  if(queued)return;
  setError('');
  try{
   if(fileMode){
    const save=fileInlineQueue.current.then(async()=>{
     fileReviewWrite.current=true;
     try{
      while(true){
       const desired=reviewRequests.current.get(key),destination=openedFile.current;
       if(!desired)return;
       if(!destination||destination.handle!==opened?.handle)throw new Error('模板文件已切换，请重新选择状态。');
       const current=parseTemplateFile(destination.raw,lookups).snapshot.groups.find(row=>row.id===group.id);
       if(!current)throw new Error('找不到要修改的模板组。');
       if(desired.status===effectiveReviewStatus(current.review_status))return;
       const {reviewed_by:_,reviewed_at:__,...base}=current;
       const value=desired.status==='final_reviewed'?reviewLocalGroup(current,session.username??'local','final'):{...base,review_status:desired.status};
       await saveLocal([{kind:'group',action:'put',id:group.id,value}],'status');
      }
     }finally{fileReviewWrite.current=false;}
    });
    fileInlineQueue.current=save.catch(()=>{});
    await save;
   }else await enqueueWrite(async(current,accept)=>{
    const route=templatePath(season,'/groups/'+encodeURIComponent(group.id)+'/review');
    while(true){
     const desired=reviewRequests.current.get(key);
     const saved=current.groups.find(row=>row.id===group.id);
     if(!desired||desired.status===effectiveReviewStatus(saved?.review_status))return current;
     const result=await api<TemplateSnapshot|{proposal:{id:string;proposal_revision:string}}>(route,'POST',{revision:current.revision,status:desired.status});
     if('proposal' in result){
      if(reviewRequests.current.get(key)?.status===desired.status)return result;
      const proposal=result.proposal;
      await api(templatePath(season,'/proposals/'+encodeURIComponent(proposal.id)+'/withdraw'),'POST',{proposal_revision:proposal.proposal_revision});
     }else current=accept(result);
    }
   },null,[group.id],true);
  }catch(error){setError((error as Error).message);}
  finally{
   reviewRequests.current.delete(key);
   setPendingReviews(new Map(reviewRequests.current));
  }
 }
 async function confirmWarning(warning:TemplateWarning){if(!confirm('已检查“'+warning.group_name+'”的关联资料，确认无需修改？'))return;setBusy(true);setError('');try{await api(templatePath(season,'/warnings/confirm'),'POST',{group_id:warning.group_id,revision:warning.revision});await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function exportSource(scope:FileExportScope,group?:TemplateGroup){
  const ids=group?[group.id]:scope==='all'?undefined:(scope==='selected'?selectedGroups:groups).map(row=>row.id);
  if(ids&&!ids.length)throw new Error('当前范围没有可导出的模板。');
  if(fileMode){
   if(!file)throw new Error('请先打开模板文件。');
   return fileExportDocument(file,ids);
  }
  const suffix='/export?authoring=1'+(ids?'&group_ids='+encodeURIComponent(ids.join(',')):'');
  return api<PortableTemplateLibrary>(templatePath(season,suffix));
 }
 async function exportAll(){setError('');try{downloadTemplates(await exportSource('all'),'话术模板库.json');}catch(e){setError((e as Error).message);}}
 function beginImport(selection:TemplateGroup[]|null=null){setError('');setBypass(false);setReason('');setPreview(null);setImportText('');setImportSelection(selection);setImportOpen(true);}
 function setImport(value:string){setImportText(value);setPreview(null);onDirty?.(!!value);}
 function finishImport(){setImportOpen(false);setImportText('');setImportSelection(null);setPreview(null);onDirty?.(false);}
 function closeImport(){if(busy||importText&&!confirm('关闭后将放弃本次导入内容，继续吗？'))return;finishImport();}
 async function previewImport(){
  if(fileMode)onBusyChange?.(true);
  setError('');setBusy(true);
  try{
   const document=fileMode&&file&&importSelection?fileImportDocument(file,importSelection.map(group=>group.id)):JSON.parse(importText);
   setPreview(await api<Preview>(templatePath(season,'/import/preview'),'POST',{document}));
  }catch(e){setError((e as Error).message);}finally{if(fileMode)onBusyChange?.(false);setBusy(false);}
 }
 async function commitImport(){
  if(!preview||preview.errors.length)return;
  if(fileMode)onBusyChange?.(true);
  setError('');setBusy(true);
  try{
   const result=await api<TemplateSnapshot|{proposal:unknown}>(templatePath(season,'/import/commit'),'POST',{revision:preview.revision,changes:preview.changes,source:fileMode?'file-import':'web-import',...(bypass?{bypass_review:true,reason}:{})});
   if('proposal' in result){refreshProposals();setNotice('导入已提交为私有提案，审核通过后生效。');}
   else{setDatabase(result);setNotice('所选模板已导入数据库。');}
   finishImport();
   if(!fileMode)await load();
  }catch(e){setError((e as Error).message);}finally{if(fileMode)onBusyChange?.(false);setBusy(false);}
 }
 function copy(group:TemplateGroup){
  if(!snapshot)return;
  editorBase.current=undefined;
  setEditor(copyTemplateGroup(group,snapshot.groups));
 }
 function create(){editorBase.current=undefined;if(!snapshot?.events.length){setNotice('请先在事件与参数设置中添加事件。');setSettings(true);return;}setEditor({id:templateId('group'),name:'',version:filters.version||season.toLowerCase(),mode:(gameMode??filters.mode)||'万象大赛',tags:filters.tags??[],event_id:snapshot.events.find(event=>event.id===filters.event)?.id??snapshot.events[0].id,scope:{player_id:filters.player&&filters.player!=='common'?filters.player:null,lineup_note_id:filters.lineup&&filters.lineup!=='common'?filters.lineup:null},priority:0,condition_tree:{kind:'all',children:[]},expression:'',editor_mode:'tree',conditions:[],utterances:[{id:templateId('utterance'),text:''}],related_entities:[]});}
 const scrollPositions=useRef(workspace?.scroll??{}),groupList=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(workspace)workspace.scroll=scrollPositions.current;},[workspace]);
 const pageSize=compact?80:20;
 const scrollKey=viewKey+':'+(gameMode??'')+':'+(compact?'board:':'cards:')+(byEntity?'entity:'+entityKey:'event:'+filters.event);
 const [paging,setPaging]=useState<{key:string;visible:number}>();
 const visibleCount=paging?.key===scrollKey?paging.visible:scrollPositions.current[scrollKey]?.visible??pageSize;
 const hasGroups=groups.length>0;
 useLayoutEffect(()=>{
  if(hasGroups&&groupList.current)groupList.current.scrollTop=scrollPositions.current[scrollKey]?.top??0;
 },[scrollKey,hasGroups]);
 function showMore(){
  const visible=Math.min(visibleCount+pageSize,groups.length);
  scrollPositions.current[scrollKey]={top:groupList.current?.scrollTop??0,visible};
  setPaging({key:scrollKey,visible});
 }
 const useProposalEditor=!fileMode&&annotator;
 const selectionLocked=busy&&!fileMetadataWrite.current&&!fileReviewWrite.current;
 const batchConflict=!fileMode&&selectedGroups.some(group=>conflicted.includes(group.id)||conflicted.includes(group.event_id));
 const showDetail=detailGroup&&(compact||!groups.slice(0,visibleCount).some(group=>group.id===detailGroup.id))&&
  !editor&&!settings&&!proposals&&!importOpen&&!jsonGroup&&!revisionGroup&&!feedback&&!help&&!batchMetadata&&!fileExport;
 function groupActions(group:TemplateGroup):ReactNode{
  return <>
   <button type="button" disabled={selectionLocked||group.ignored||group.utterances.every(row=>row.ignored)} onClick={()=>setFileExport({group})}>导出到文件</button>
   {fileMode&&editable&&<button type="button" disabled={selectionLocked} onClick={()=>beginImport([group])}>导入此组到数据库</button>}
  </>;
 }
 function locateProposal(proposal:TemplateProposal,id:string){
  const group=snapshot?.groups.find(group=>group.id===id);
  const preview=proposalCardPreview(proposal,id);
  if(!group&&(!preview||preview.base||!preview.change.value))return;
  if(preview){
   setProposalPreviews(current=>({identity:proposalIdentity,items:[
    ...((current?.identity===proposalIdentity?current.items:[]).filter(row=>row.proposal_id!==proposal.id||row.change.id!==id)),preview,
   ]}));
  }
  chooseProposal(id,preview?.proposal_id??null);
  const inList=!compact&&!!groupList.current?.querySelector('[data-feedback-group="'+CSS.escape(id)+'"]');
  setDetailId(null);
  setLocatedDetail(inList?null:{id,identity:proposalIdentity});
  setFocusTarget({group:id});
  setInspectProposal(undefined);
  setProposals(false);
 }
 function reconcileApproval(write:TemplateProposal['formal_write']){
  if(write&&!queueSize.current){
   epoch.current++;
   setDatabase(previous=>{
    if(!previous||previous.revision!==write.previous_revision)return previous;
    const groups=new Map(previous.groups.map(group=>[group.id,group]));
    const events=new Map(previous.events.map(event=>[event.id,event]));
    for(const change of write.changes){
     if(change.kind==='group'){
      if(change.action==='put')groups.set(change.id,change.value as TemplateGroup);
      else groups.delete(change.id);
     }else if(change.action==='put')events.set(change.id,change.value as TemplateEvent);
     else events.delete(change.id);
    }
    return mergeTemplateWriteSnapshot(previous,{...previous,revision:write.revision,groups:[...groups.values()],
     events:[...events.values()],utterance_bindings:undefined},write.changes.map(change=>change.id));
   });
  }
  void load(undefined,true);
 }
 function updateProposalPreview(result:TemplateProposal){
  const updated=result.status==='pending'?result.changes.flatMap(row=>{
   const preview=row.kind==='group'&&proposalCardPreview(result,row.id);
   return preview?[preview]:[];
  }):[];
  previewEpoch.current++;
  confirmedPreviews.current.set(result.id,updated);
  setProposalPreviews(current=>({identity:proposalIdentity,items:[
   ...(current?.identity===proposalIdentity?current.items.filter(row=>row.proposal_id!==result.id):[]),...updated,
  ]}));
 }
 const [rejecting,setRejecting]=useState<Set<string>>(new Set());
 function saveCardProposal(initial:TemplateProposalPreview,approve:boolean,prepare:(group:TemplateGroup)=>GroupEditorOperation=()=>({}),reject=false){
  const id=initial.proposal_id;
  const previous=proposalQueue.current.get(id)??Promise.resolve();
  const failures=proposalFailures.current.get(id)??0;
  if(approve||reject){
   if(approvals.current.has(id))return Promise.reject(new Error('本提案正在审核。'));
   approvals.current.add(id);
   if(reject)setRejecting(current=>new Set([...current,id]));
   else setWaitingApprovals(current=>new Set([...current,id]));
  }
  const run=previous.then(async()=>{
   if(identityRef.current!==proposalIdentity)throw new Error('登录身份已切换。草稿已保留。');
   if(approve&&(proposalFailures.current.get(id)??0)!==failures)
    throw new Error('采纳前有一项修改保存失败，请核对待审稿后重新采纳。');
   const known=confirmedPreviews.current.get(id);
   const target=known===undefined?initial:known?.find(row=>row.change.id===initial.change.id);
   if(!target)throw new Error('待审稿已处理，请重新选择保存目标。草稿已保留。');
   const {proposal_revision,change_index,change}=target;
   if(!proposal_revision||change_index===undefined)throw new Error('请刷新提案后重试。');
   const current=(change.value as TemplateGroup|undefined)??target.base!;
   const operation=prepare(current);
   const {group,...rest}=operation;
   const parameters=appendEditorParameters(target.event??snapshot?.events.find(event=>event.id===operation.event?.id),operation.event);
   const payload={...rest,event:parameters,...(group?{fields:groupFields(current,group)}:{})};
   setProposalActionError(current=>current?.id===id&&current.groupId===change.id?undefined:current);
   const path='templates/proposals/'+encodeURIComponent(id)+(reject?'/reject':approve?'/approve':'/edit');
   const request={proposal_revision,change_ids:[change_index],compact:true};
   let dependency_token:string|null=null;
   try{
    if(approve){
     setWaitingApprovals(current=>new Set([...current].filter(key=>key!==id)));
     setApproving(current=>new Set([...current,id]));
    }
    if(approve&&(operation.event||target.event)){
     const dependency=await api<{dependency_token:string|null;event:string;parameters:string[]}>(path,'POST',
      {...request,group_editor:{...payload,preview:true}});
     dependency_token=dependency.dependency_token;
     if(dependency_token&&!confirm('采纳本组时将同时发布「'+dependency.event+'」'+
      (dependency.parameters.length?'的参数 '+dependency.parameters.join('、'):'的事件定义')+'，是否继续？'))
      throw new Error('已取消采纳，草稿已保留。');
    }
    const result=await api<TemplateProposal>(path,'POST',reject?request:{...request,group_editor:{...payload,...(dependency_token?{dependency_token}:{})}});
    if(approve){reconcileApproval(result.formal_write);setFeedbackRevision(value=>value+1);}
    updateProposalPreview(result);
    const saved=result.reviews?.at(-1)?.changes?.find(row=>row.kind==='group');
    if(saved?.action==='put'&&saved.id!==change.id){
     chooseProposal(saved.id,approve?undefined:id);
     setDetailId(null);setLocatedDetail({id:saved.id,identity:proposalIdentity});
    }
   }catch(error){
    const message=(error as Error).message;
    if(!operation.ignore&&!operation.fixed)setProposalActionError({id,groupId:initial.change.id,message});
    if((error as {status?:number}).status===409){
     try{
      const items=await api<TemplateProposalPreview[]>('templates/proposals?view=card-preview&proposal_id='+encodeURIComponent(id));
      previewEpoch.current++;
      confirmedPreviews.current.set(id,items.filter(row=>row.proposal_id===id));
      setProposalPreviews(current=>({identity:proposalIdentity,items:[
       ...(current?.identity===proposalIdentity?current.items.filter(row=>row.proposal_id!==id):[]),
       ...items.filter(row=>row.proposal_id===id),
      ]}));
     }catch{confirmedPreviews.current.set(id,null);}
     if(message.startsWith('正式条件'))void load();
    }
    throw error;
   }
  }).catch(error=>{
   if(approve||reject)setProposalActionError({id,groupId:initial.change.id,message:(error as Error).message});
   else proposalFailures.current.set(id,(proposalFailures.current.get(id)??0)+1);
   throw error;
  }).finally(()=>{if(approve||reject){
   approvals.current.delete(id);
   setApproving(current=>new Set([...current].filter(key=>key!==id)));
   setWaitingApprovals(current=>new Set([...current].filter(key=>key!==id)));
   if(reject)setRejecting(current=>new Set([...current].filter(key=>key!==id)));
  }});
  const tail=run.catch(()=>{});
  proposalQueue.current.set(id,tail);
  void tail.then(()=>{if(proposalQueue.current.get(id)===tail)proposalQueue.current.delete(id);});
  return run;
 }
 function saveProposedUtterance(target:TemplateProposalPreview,change:UtteranceChange,approve:boolean){
  return saveCardProposal(target,approve,group=>({group:applyUtteranceChange(group,change)}));
 }
 function editKey(groupId:string,target?:TemplateProposalPreview){
  const handle=fileMode?opened?.handle:undefined;
  if(handle&&!fileKeys.has(handle))fileKeys.set(handle,templateId('file'));
  return JSON.stringify([proposalIdentity,viewKey,handle?fileKeys.get(handle):'',groupId,target?.proposal_id??'']);
 }
 function openGroupEditor(group:TemplateGroup,target?:TemplateProposalPreview){
  const key=editKey(group.id,target);
  if(!cardEditors.has(key))cardEditors.set(key,{base:group,proposal:target,scratch:{}});
  redrawEditors(value=>value+1);
 }
 function toggleFlag(key:string,confirmed:boolean,save:(value:boolean)=>Promise<void>,next?:boolean){
  const previous=flags.current.get(key);
  const value=next??!(previous&&!previous.error?previous.value:confirmed);
  const intent:FlagIntent={value,confirmed:previous?.confirmed??confirmed,retry:()=>toggleFlag(key,confirmed,save,value)};
  flags.current.set(key,intent);redrawFlags(count=>count+1);
  void save(value).then(()=>{
   if(flags.current.get(key)===intent)flags.current.delete(key);
  },error=>{
   if(flags.current.get(key)===intent)flags.current.set(key,{...intent,error:(error as Error).message});
  }).finally(()=>redrawFlags(count=>count+1));
 }
 function saveGroupEditor(base:TemplateGroup,draft:TemplateGroup,event?:TemplateEvent){
  function changes(groups:TemplateGroup[],events:TemplateEvent[]){
   const latest=groups.find(group=>group.id===base.id);
   if(!latest)throw new Error('模板组已不存在，草稿已保留。');
   const merged=mergeEditorFields(base,latest,draft);
   const nextEvent=appendEditorParameters(events.find(row=>row.id===event?.id),event);
   const result:TemplateChange[]=[];
   if(nextEvent)result.push({kind:'event',action:'put',id:nextEvent.id,value:nextEvent});
   let value=merged;
   if(fileMode&&fileTriggerChanged(latest,merged,events.find(row=>row.id===latest.event_id),nextEvent??events.find(row=>row.id===merged.event_id))){
    value={...merged,id:templateId('group'),utterances:merged.utterances.map(({fixed,...row})=>row)};
   }
   result.push({kind:'group',action:'put',id:value.id,value});
   return result;
  }
  if(fileMode)return enqueueFileMetadataChanges(changes);
  return enqueueWrite(current=>{
   const edits=changes(current.groups,current.events),group=edits.pop()!.value as TemplateGroup;
   const old=current.groups.find(row=>row.id===base.id)!;
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,changes:edits,group_patches:[{id:base.id,fields:groupFields(old,group)}]});
  },null,[base.id]);
 }
 function renderGroup(group:TemplateGroup){
  const pending=pendingIgnores.filter(change=>change.groupId===group.id);
  const original=pending.reduce(applyIgnore,group);
  const rows=previewsByGroup.get(group.id)??[];
  const choice=proposalChoices[group.id];
  const showOriginal=choice===null;
  const active=rows.find(row=>row.proposal_id===choice)??rows[0];
  const projected=active&&!showOriginal?projectProposalCard(original,active):undefined;
  if(projected&&active?.event)projected.fields.add('event');
  const content=projected?.group??original;
  const warning=(!projected&&!fileMode&&!legacyMode&&warnings.find(item=>item.group_id===group.id))||undefined;
  const canEditGroup=!projected&&editable&&(fileMode||!conflicted.includes(group.id)&&!conflicted.includes(group.event_id));
  const ruleChanged=projected&&(projected.newGroup||[...projected.fields].some(field=>['rule','scope','event','event_id'].includes(field)||field.startsWith('condition:')));
  const previewTarget=projected&&active?.proposal_revision?active:undefined;
  const canEditProposal=previewTarget&&
   (admin||previewTarget.author===session.username);
  const draftGroup=previewTarget&&((previewTarget.change.value as TemplateGroup|undefined)??previewTarget.base);
  const saveProposal=(operation:GroupEditorOperation)=>{if(previewTarget)void saveCardProposal(previewTarget,false,()=>operation).catch(()=>{});};
  const proposalEditable=!!canEditProposal&&!!draftGroup;
  const key=editKey(group.id,previewTarget);
  const oldDraftKey=(keys:Iterable<string>,hasDraft:(id:string)=>boolean)=>{
   if(previewTarget)return;
   const prefix=key.slice(0,-3);
   return [...keys].find(candidate=>candidate!==key&&candidate.startsWith(prefix)&&hasDraft(candidate)&&
    !rows.some(row=>editKey(group.id,row)===candidate));
  };
  const oldUtteranceKey=oldDraftKey(utteranceDrafts.keys(),id=>Object.keys(utteranceDrafts.get(id)!.drafts).length>0);
  const oldConditionKey=oldDraftKey(cardEditors.keys(),id=>!!cardEditors.get(id)?.scratch.draft);
  const recoveredDraftKey=oldUtteranceKey??oldConditionKey;
  function confirmDraftDestination(){
   if(!confirm(useProposalEditor?'原待审稿已处理。是否将这次修改提交为新的提案？':'原待审稿已处理。是否将这次修改保存到正式模板？'))
    throw new Error('已取消保存，草稿已保留。');
  }
  const flagKey=(id:string,field:EditFlag)=>JSON.stringify([key,id,field]);
  const feedback=(id:string,field:EditFlag)=>{
   const intent=flags.current.get(flagKey(id,field));
   return intent?{pending:!intent.error,confirmed:intent.confirmed,error:intent.error,retry:intent.retry}:undefined;
  };
  const displayed={...content,utterances:content.utterances.map(row=>{
   const ignored=flags.current.get(flagKey(row.id,'ignored')),fixed=flags.current.get(flagKey(row.id,'fixed'));
   return ignored&&!ignored.error||fixed&&!fixed.error?{...row,
    ignored:ignored&&!ignored.error?ignored.value:row.ignored,
    fixed:fixed&&!fixed.error?fixed.value:row.fixed}:row;
  })};
  const toggleRow=(id:string,field:EditFlag)=>{
   const row=(draftGroup??original).utterances.find(row=>row.id===id);
   if(!row)return;
   toggleFlag(flagKey(id,field),!!row[field],value=>{
    if(proposalEditable&&previewTarget)return saveCardProposal(previewTarget,false,latest=>{
     if(!latest.utterances.some(row=>row.id===id))throw new Error('话术已不存在，请重新核对。');
     return field==='ignored'?{ignore:{id,value}}:{fixed:{id,value}};
    });
    if(field==='fixed')return enqueueWrite(current=>api(templatePath(season,'/utterances/fixed'),'POST',{
     revision:current.revision,group_id:group.id,utterance_id:id,fixed:value,
    }),null,[group.id]);
    return enqueueGroupChange(group.id,latest=>{
     if(!latest.utterances.some(row=>row.id===id))throw new Error('话术已不存在，请重新核对。');
     return applyIgnore(latest,{groupId:group.id,utteranceId:id,ignored:value});
    },null);
   });
  };
  let drafts=utteranceDrafts.get(oldUtteranceKey??key);
  if(!drafts){drafts=createUtteranceDraftStore();utteranceDrafts.set(key,drafts);}
  const editorKey=oldConditionKey??key;
  const openedEditor=cardEditors.get(editorKey);
  const actionError=active&&proposalActionError?.id===active.proposal_id&&proposalActionError.groupId===group.id?proposalActionError.message:undefined;
  const editedEvent=openedEditor?.proposal?.event;
  const editorEvents=editedEvent?[...(snapshot?.events??[]).filter(event=>event.id!==editedEvent.id),editedEvent]:snapshot?.events??[];
  const groupEditor=openedEditor&&createPortal(<TemplateEditor scratch={openedEditor.scratch}
   review={!!openedEditor.proposal&&!oldConditionKey} group={openedEditor.base} events={editorEvents}
   players={players} lineups={lineups} scopeName={scopeName} catalog={snapshot?.condition_catalog} annotator={openedEditor.proposal?!admin:useProposalEditor}
   localFile={fileMode} allowEventParameters={canManage}
   formalConflict={admin&&actionError?.startsWith('正式条件')?snapshot?.groups.find(row=>row.id===group.id)?.expression??'':undefined}
   onClose={()=>{if(cardEditors.get(editorKey)===openedEditor){cardEditors.delete(editorKey);redrawEditors(value=>value+1);}}}
   onSave={async(draft,event,resolve)=>{
    if(oldConditionKey)confirmDraftDestination();
    if(openedEditor.proposal&&!oldConditionKey)return saveCardProposal(openedEditor.proposal,false,latest=>({
     group:mergeEditorFields(openedEditor.base,latest,draft),event,resolve_conditions:resolve?snapshot?.revision:undefined,
    }));
    return saveGroupEditor(openedEditor.base,draft,event);
   }}
   onSaveAndApprove={admin&&openedEditor.proposal&&!oldConditionKey?(draft,event,resolve)=>saveCardProposal(openedEditor.proposal!,true,latest=>({
    group:mergeEditorFields(openedEditor.base,latest,draft),event,resolve_conditions:resolve?snapshot?.revision:undefined,
   })):undefined}/>,document.body,editorKey);
  return <TemplateGroupCard key={group.id} group={displayed} catalog={snapshot?.condition_catalog} fileMode={fileMode} allowExport={!projected&&!legacyMode} utteranceBindings={ruleChanged?undefined:snapshot?.utterance_bindings?.[group.id]}
   originalGroup={projected?.newGroup?undefined:original} proposal={projected} proposalControl={rows.length?{
    rows,active,original:showOriginal,temporary:temporaryGroup?.id===group.id,
    disabled:selectionLocked,onChange:value=>chooseProposal(group.id,value),
    submitting:!!active&&approving.has(active.proposal_id),waiting:!!active&&waitingApprovals.has(active.proposal_id),error:actionError,
    rejecting:!!active&&rejecting.has(active.proposal_id),
    onApprove:admin&&previewTarget?()=>{void saveCardProposal(previewTarget,true).catch(()=>{});}:undefined,
    onReject:admin&&previewTarget?()=>{if(confirm('驳回当前模板组的待审修改？'))void saveCardProposal(previewTarget,false,undefined,true).catch(()=>{});}:undefined,
    onSaveUtterance:proposalEditable?(change,approve)=>saveProposedUtterance(previewTarget!,change,approve):undefined,
    onInspect:actionError?()=>{setInspectProposal(active.proposal_id);setProposals(true);}:undefined,
   }:undefined}
   commentCounts={fileMode||legacyMode?undefined:commentCounts[group.id]} lastActivity={fileMode||legacyMode?undefined:lastActivity[group.id]}
   onFeedback={!projected&&!fileMode&&editable?utteranceId=>setFeedback({group,utteranceId}):undefined}
   savingIgnore={{group:pending.some(change=>!change.utteranceId),rows:[]}}
   entities={ruleChanged||projected?.fields.has('related_entities')?undefined:snapshot?.entity_links?.[group.id]}
   event={(projected&&active?.event)||snapshot?.events.find(event=>event.id===displayed.event_id)} scopeName={scopeName}
   interactionLocked={selectionLocked} annotator={useProposalEditor}
   metadataLocked={selectionLocked}
   onSaveMetadata={proposalEditable?async(field,values)=>{await saveCardProposal(previewTarget!,false,latest=>({group:{...latest,[field]:values}}));}
    :(field,values)=>saveMetadata(group.id,field,values)}
   onSaveUtterances={async change=>{if(oldUtteranceKey&&change.kind!=='delete')confirmDraftDestination();await saveUtterance(group.id,change);}}
   utteranceDrafts={drafts} onUtteranceDraftsChanged={oldUtteranceKey?()=>redrawEditors(value=>value+1):undefined} flagFeedback={feedback} conditionEditor={<>
    {recoveredDraftKey&&<p className="muted" role="status">原待审稿已处理，未保存的草稿仍可继续编辑。</p>}{groupEditor}
   </>}
   editable={canEditGroup||proposalEditable}
   onReviewStatus={(canEditGroup||proposalEditable)&&!selectionLocked?
    status=>{if(proposalEditable)saveProposal({status});else void changeReviewStatus(group,status);}:undefined}
   reviewPending={projected?undefined:pendingReviews.get(reviewKey(group.id))} canFinalReview={reviewer}
   onRevisions={!projected&&!fileMode&&!legacyMode?()=>setRevisionGroup(group):undefined}
   onExport={()=>fileMode&&file?downloadTemplates(fileImportDocument(file,[group.id]),group.name+'.json'):setJsonGroup({id:group.id,name:group.name})}
   onSaveExpression={value=>{
    const base=proposalEditable?draftGroup!:group;
    const draft:TemplateGroup={...base,editor_mode:'text',expression:value,conditions:[]};
    return proposalEditable&&previewTarget
     ?saveCardProposal(previewTarget,false,latest=>({group:mergeEditorFields(base,latest,draft)}))
     :saveGroupEditor(base,draft);
   }}
   onEdit={()=>openGroupEditor(proposalEditable?draftGroup!:group,proposalEditable?previewTarget:undefined)}
   onCopy={canManage?()=>copy(draftGroup??group):undefined}
   onDelete={canManage&&!deletingGroups.current.has(group.id)?()=>{if(!proposalEditable){void remove(group);return;}
    if(confirm('确定将「'+displayed.name+'」及其中全部话术设为拟删除？'))saveProposal({delete:true});}:undefined}
   onToggleIgnored={fileMode?undefined:utteranceId=>{
    if(utteranceId){toggleRow(utteranceId,'ignored');return;}
    if(!proposalEditable){void toggleIgnored(group);return;}
    if(previewTarget)void saveCardProposal(previewTarget,false,latest=>({group:{...latest,ignored:!latest.ignored}})).catch(()=>{});
   }}
   onToggleFixed={!fileMode&&admin?utteranceId=>toggleRow(utteranceId,'fixed'):undefined}
   warning={warning} onConfirm={admin&&warning?()=>void confirmWarning(warning):undefined}
   workflow={projected||legacyMode?undefined:groupActions(group)}/>;
 }
 function renderCards(visible:TemplateGroup[]){
  if(!byEntity)return visible.map(renderGroup);
  const sections=new Map<string,TemplateGroup[]>();
  for(const group of visible){
   const section=sections.get(group.event_id);
   if(section)section.push(group);
   else sections.set(group.event_id,[group]);
  }
  return [...sections].map(([eventId,rows])=><section key={eventId} className="template-card-event">
   <h3>{snapshot?.events.find(event=>event.id===eventId)?.name??eventId}</h3>
   {rows.map(renderGroup)}
  </section>);
 }
 const resultsList=<div className="template-group-list" ref={groupList} onScroll={event=>{
  const list=event.currentTarget;
  scrollPositions.current[scrollKey]={top:list.scrollTop,visible:visibleCount};
  if(visibleCount<groups.length&&list.scrollHeight-list.scrollTop-list.clientHeight<200)showMore();
 }}>
  {!fileMode&&loading&&!snapshot?<p className="empty" role="status">正在载入模板库…</p>:!groups.length?<div className="empty"><p>{allGroups.length?'没有符合筛选的模板组。':'暂无 '+season+' 模板数据'}</p>{canManage&&snapshot&&!allGroups.length&&<button onClick={create}>新建模板组</button>}</div>:<>
   {compact?<TemplateBoard groups={groups.slice(0,visibleCount)} events={snapshot?.events??[]} selected={selected} onSelectionChange={selectGroups} onDetail={setDetailId} byEvent={byEntity} entity={entity} selectionDisabled={selectionLocked}/>
    :renderCards(groups.slice(0,visibleCount))}
   {visibleCount<groups.length&&<button type="button" onClick={showMore}>显示更多模板（{visibleCount} / {groups.length}）</button>}
  </>}
 </div>;
 return <main className="templates-page">
  <div className="template-page-heading"><div><h1>话术模板库</h1>{fileMode&&opened&&<p title={opened.handle.name}>{opened.handle.name}</p>}</div>
   {(!fileMode||opened)&&<div className="template-browse-toolbar">
    <div role="group" aria-label="模板分类方式"><button type="button" aria-pressed={!byEntity} disabled={selectionLocked} onClick={()=>changeView(current=>({...current,byEntity:false}))}>按事件</button>
     <button type="button" aria-pressed={byEntity} disabled={selectionLocked} onClick={()=>changeView(current=>({...current,byEntity:true}))}>按实体</button></div>
    <div role="group" aria-label="模板显示方式"><button type="button" aria-pressed={!compact} disabled={selectionLocked} onClick={()=>changeView(current=>({...current,compact:false}))}>卡片</button>
     <button type="button" aria-pressed={compact} disabled={selectionLocked} onClick={()=>changeView(current=>({...current,compact:true}))}>看板</button></div>
    <TemplateFilterBar filters={filters} patch={patch} groups={allGroups} players={players} lineups={lineups} disabled={selectionLocked} showMode={gameMode===undefined}/>
    {!legacyMode&&<button type="button" disabled={selectionLocked||(!fileMode&&loading)} onClick={()=>{if(fileMode)void openFile(true);else{refreshProposals();void load();}}} aria-label={fileMode?'重新读取模板文件':'刷新模板库'}>↻</button>}
   </div>}
   <fieldset className="template-toolbar" disabled={selectionLocked}>
    <button onClick={()=>setHelp(true)}>帮助</button>
    {!legacyMode&&snapshot&&<button type="button" onClick={()=>setFileExport({})}>导出到文件</button>}
    {fileMode?<><button onClick={()=>void openFile()}>{opened?'打开其他文件':'打开模板文件'}</button>
     {editable&&opened&&<button disabled={!selectedGroups.length} onClick={()=>beginImport(selectedGroups)}>导入所选到数据库{selectedGroups.length>0?'（'+selectedGroups.length+'）':''}</button>}
    </>:<>
     {season==='S2'&&!!legacy?.groups.length&&<button type="button" aria-pressed={legacyMode} onClick={()=>setShowLegacy(value=>!value)}>{legacyMode?'返回数据库模板':'查看 S2 旧模板（只读）'}</button>}
     {!legacyMode&&admin&&<TemplateConflicts events={snapshot?.events??[]} scopeName={scopeName} onResolved={()=>void load()} onConflicts={setConflicted}/>}
     {!legacyMode&&<button onClick={()=>void exportAll()}>导出全库</button>}
     {editable&&<><button onClick={()=>beginImport()}>导入 JSON</button><button onClick={()=>setFeedback({})}>全库批注与记录</button>
      <button onClick={()=>setProposals(true)}>{admin?'提案审核':'我的提案'}</button></>}
    </>}
    {canManage&&snapshot&&<><button onClick={()=>setSettings(true)}>事件与参数</button><button className="primary" onClick={create}>＋ 新建模板组</button></>}
   </fieldset>
  </div>
  {notice&&<div className="template-notice" role="status">{notice}<button aria-label="关闭提示" onClick={()=>setNotice('')}>×</button></div>}
  {error&&!importOpen&&<div role="alert" className="error template-error">{error}<button onClick={()=>fileMode?void openFile(!!opened):void load()}>重新载入</button></div>}
  {previewEnabled&&proposalPreviews?.identity===proposalIdentity&&proposalPreviews.error&&<div role="status" className="template-error">
   提案预览暂不可用：{proposalPreviews.error} <button type="button" onClick={refreshProposals}>重试</button>
  </div>}
  {fileMode&&officialError&&opened&&<p className="muted" role="status">官网卡牌资料读取失败：{officialError}</p>}
  {fileMode&&!opened?<div className="empty"><p>打开话术模板库 JSON 文件，查看和编辑其中的模板组。</p></div>:<div className="template-workspace">
   {byEntity?<TemplateEntityList entries={entityEntries} selected={entityKey} onSelect={key=>changeView(current=>({...current,entityKey:key}))} disabled={selectionLocked}/>
    :<TemplateEventList events={snapshot?.events??[]} groups={countGroups} selected={filters.event} onSelect={event=>patch({event})} disabled={selectionLocked}/>}
   <div className="template-results">
    <div className="template-result-heading">
     <div className="template-result-summary"><h2>{byEntity?(entity?.name??'全部实体'):snapshot?.events.find(event=>event.id===filters.event)?.name??'全部模板'}</h2>
      <span className="muted">{groups.length} 个模板组</span>
     </div>
     <div className="template-result-actions" role="group" aria-label="模板结果操作">
      {editable&&selectedGroups.length>0&&(['tags','batch'] as const).map(field=>
       <button key={field} type="button" disabled={selectionLocked||batchConflict}
        title={batchConflict?'选中的模板组包含同步冲突，请先解决冲突。':undefined}
        onClick={()=>setBatchMetadata(field)}>批量添加{templateMetadataLabels[field]}</button>)}
      {!fileMode&&!legacyMode&&<button type="button" disabled={selectionLocked||!groups.length} onClick={()=>setFileExport({})}>导出当前筛选</button>}
      {!!selectedGroups.length&&<button type="button" disabled={selectionLocked} onClick={()=>changeView(current=>({...current,selected:new Set()}))}>清除选择（{selectedGroups.length}）</button>}
     </div>
    </div>
    {!compact&&groups.length>0?<ReadingCards cardSearch>{resultsList}</ReadingCards>:resultsList}
   </div>
  </div>}
  {showDetail&&<section className="template-detail-panel" role="dialog" aria-modal="false" aria-label={detailGroup.name+(temporaryGroup?' · 临时提案卡':' · 模板详情')}>
   <header><strong>{detailGroup.name}</strong><button type="button" aria-label={'关闭'+detailGroup.name+'详情'} onClick={()=>{
    chooseProposal(detailGroup.id,undefined);setDetailId(null);setLocatedDetail(null);
   }}>关闭</button></header>
   <div className="template-form template-detail-body">
    {error&&<p className="error" role="alert">{error}</p>}
    <ReadingCards cardSearch><div className="template-card-stack">{renderGroup(detailGroup)}</div></ReadingCards>
   </div>
  </section>}
  {batchMetadata&&<TemplateBatchMetadata field={batchMetadata} groups={selectedGroups} proposal={useProposalEditor}
   onClose={()=>setBatchMetadata(null)} onSave={values=>saveBatchMetadata(batchMetadata,values)}/>}
  {feedback&&<TemplateFeedback groups={allGroups} revision={snapshot?.revision} onLocate={(group,utterance)=>{setFeedback(null);setLocatedDetail(null);setDetailId(group);setFocusTarget({group,utterance});}} target={feedback} admin={admin} onClose={()=>setFeedback(null)} onChanged={()=>setFeedbackRevision(n=>n+1)}/>}
  {help&&<TemplateHelp onClose={()=>setHelp(false)}/>}
  {jsonGroup&&<TemplateJsonExport key={jsonGroup.id} groupId={jsonGroup.id} groupName={jsonGroup.name} onClose={()=>setJsonGroup(null)}/>}
  {fileExport&&<TemplateFileExport groupName={fileExport.group?.name} counts={{selected:selectedGroups.length,filtered:groups.length}}
   opened={opened} loadSource={scope=>exportSource(scope,fileExport.group)} onClose={()=>setFileExport(undefined)}
   onBusy={value=>{onBusyChange?.(value);setBusy(value);}}
   onSaved={(handle,raw,sameAsOpened)=>{if(sameAsOpened)rememberFile({handle,raw});setFileExport(undefined);setNotice(`已导出到「${handle.name}」。`);}}/>}
  {revisionGroup&&snapshot&&<TemplateRevisions group={revisionGroup} revision={snapshot.revision} canRestore={editable} onClose={()=>setRevisionGroup(null)} onSaved={result=>{
   if('proposal' in result){refreshProposals();setNotice('回退已提交，待审核。');}else setDatabase(result);
   setRevisionGroup(null);void load();
  }}/>}
  {editor&&snapshot&&<TemplateEditor group={editor} creating={!editorBase.current} scopeName={scopeName} catalog={snapshot.condition_catalog} conditionLinks={snapshot.entity_condition_links?.[editor.id]} entities={snapshot.entity_links?.[editor.id]} events={snapshot.events} players={players} lineups={lineups} annotator={useProposalEditor} localFile={fileMode} allowEventParameters={canManage} onDirty={onDirty} onClose={()=>setEditor(null)} onSave={(group,event)=>write([...(event?[{kind:'event' as const,action:'put' as const,id:event.id,value:event}]:[]),{kind:'group',action:'put',id:group.id,value:group}],editorBase.current)}/>}
  {settings&&snapshot&&<TemplateSettings events={snapshot.events} annotator={useProposalEditor} onDirty={onDirty} onClose={()=>setSettings(false)} onSave={write}/>}
  {proposals&&snapshot&&<TemplateProposals snapshot={snapshot} scopeName={scopeName} admin={admin} initialProposal={inspectProposal}
   onEditGroup={(item,id)=>{const draft=proposalCardPreview(item,id);if(draft){locateProposal(item,id);const group=(draft.change.value as TemplateGroup|undefined)??draft.base;if(group)openGroupEditor(group,draft);}}}
   onClose={()=>{setProposals(false);setInspectProposal(undefined);}} onLocate={locateProposal} onChanged={(formalChanged,result)=>{
    updateProposalPreview(result);setFeedbackRevision(n=>n+1);if(formalChanged)reconcileApproval(result.formal_write);
   }}/>}
  {importOpen&&<TemplateDialog title={importSelection?'导入所选模板到数据库':'导入话术模板库'} onClose={closeImport} wide>
   <div className="template-form">
    {importSelection?<div><p>即将检查 {importSelection.length} 个模板组及其事件定义。</p><ul>{importSelection.map(group=><li key={group.id}>{group.name}</li>)}</ul></div>:<>
     <p>按事件名称及组名匹配现有模板。预览后提交审核，采纳后生效。</p>
     <label>选择 JSON 文件<input type="file" accept=".json,application/json" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(file)void file.text().then(setImport).catch(error=>setError(error.message));}}/></label>
     <label>或粘贴 JSON<textarea rows={10} value={importText} disabled={busy} onChange={event=>setImport(event.target.value)} spellCheck={false}/></label>
    </>}
    {error&&<p className="error" role="alert">{error}</p>}
    {preview&&<section><h3>导入预览</h3><p>新增 {(preview.summary as {created?:number}).created??0} 项，更新 {(preview.summary as {updated?:number}).updated??0} 项，无变化 {(preview.summary as {unchanged?:number}).unchanged??0} 项。</p>
     <p>共 {preview.changes.length} 项修改</p>
     {!!preview.preserved_fixed?.length&&<details><summary>保留 {preview.preserved_fixed.length} 条固定话术</summary>{preview.preserved_fixed.map(row=><p key={row.group_id+':'+row.utterance_id}>{row.group_name} · {row.text}</p>)}</details>}
     {preview.errors.length>0&&<div className="error" role="alert">{preview.errors.map((error,index)=><p key={index}>{typeof error==='string'?error:JSON.stringify(error)}</p>)}</div>}
     <details><summary>查看全部修改</summary>{preview.changes.map((change,index)=><p key={index}>{change.action==='delete'?'删除':'新增或更新'}{change.kind==='event'?'事件':'模板组'}：{change.value?.name??change.id}</p>)}</details>
    </section>}
    {admin&&<><label><input type="checkbox" checked={bypass} disabled={busy} onChange={event=>setBypass(event.target.checked)}/>跳过审核，直接导入</label>{bypass&&<label>直接导入原因<input required maxLength={4000} disabled={busy} value={reason} onChange={event=>setReason(event.target.value)}/></label>}</>}
    <footer><button disabled={busy} onClick={closeImport}>取消</button><button disabled={busy||!importSelection&&!importText.trim()} onClick={()=>void previewImport()}>检查并预览</button>
     <button className="primary" disabled={busy||!preview||!!preview.errors.length||!preview.changes.length||(bypass&&!reason.trim())} onClick={()=>void commitImport()}>{busy?'处理中…':bypass?'确认直接导入':'确认提交导入提案'}</button>
    </footer>
   </div>
  </TemplateDialog>}
 </main>;
}
