import TemplateRelatedCopy,{type RelatedCopyChoice} from './TemplateRelatedCopyMenu';
import {relatedCopy,relatedDisplayRows,relatedEventDefinition,relatedTargets} from './templateRelatedCopy';
import {templateConditionLength,templateDisplayExpression,templateDisplaySections,templateRelatedSection} from './templateDisplayGroups';
import {catalogV04,currentTemplateSyntax,keyedTemplateSyntax,registeredEvent,validateKeyedCondition,validateV04Template,wildcardKey} from './templateV04';
import TemplateInlineChoice from './TemplateInlineChoice';
import {canEditTemplateArgument,canonicalTemplateName,changeTemplateArgument,copyConditionExpression,moveTemplateEvent,sameCopyCondition,startTemplateEventCopy,templateCardGroups,templateTriggerParameters} from './templateInlineTrigger';
import {createPortal} from 'react-dom';
import {TemplateConditionPreview} from './TemplateConditionPreview';
import TemplateGroupName from './TemplateGroupName';
import type {TemplateScopeOptions} from './TemplateScopeFields';
import {resolveConditionEdit} from './templateConditionText';
import TemplateInlineMetadata from './TemplateInlineMetadata';
import {TemplateMetadataChoices} from './MetadataSuggestions';
import TemplateBatchMetadata from './TemplateBatchMetadata';
import {loadTemplateWarnings} from './TemplateWarnings';
import {parameterType} from './templateRules';
import {argumentCardIds,fileTriggerChanged,fixedArguments,parameterRole,templateAction} from './templateAction';
import {Fragment,useCallback,useEffect,useId,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {useAuth} from './auth';
import {api} from './model';
import {EntityChip,ReadingCards,useCards} from './EntityCards';
import TemplateFilterBar,{TemplateEventList,TemplateLineupEventFilter} from './TemplateFilters';
import TemplateEditor,{TemplateDialog,type TemplateEditorScratch} from './TemplateEditor';
import type {ConditionCatalog} from './templateRules';
import TemplateSettings from './TemplateSettings';
import TemplateProposals from './TemplateProposals';
import {newestProposalFirst,projectProposalCard,proposalCardPreview,type TemplateProposalPreview} from './templateProposalPreview';
import TemplateConflicts from './TemplateConflicts';
import TemplateUtterances,{applyUtteranceChange,createUtteranceDraftStore,TemplateUtteranceVisibility,type UtteranceChange,type UtteranceDraftStore,type UtteranceFlagFeedback} from './TemplateUtterances';
import TemplateJsonExport from './TemplateJsonExport';
import TemplateFileExport,{type FileExportScope} from './TemplateFileExport';
import TemplateHelp from './TemplateHelp';
import TemplateFeedback,{LocalTemplateFeedback,activityLabel,type Activity,type FeedbackTarget} from './TemplateFeedback';
import TemplateBoard,{TemplateEntityList,buildTemplateEntityIndex} from './TemplateBoard';
import TemplateLineupBoard,{addLineupRosters,buildLineupTabs,generalHeroLabel,lineupBoardRows,lineupRosterName,lineupRosterNames,lineupTemplateCounts,TemplateLineupSidebar,unscopedLineup} from './TemplateLineupBoard';
import FloatingDocumentNote from './FloatingDocumentNote';
import {TemplateLineupName} from './ConditionTextEditor';
import TemplateTraceDialog from './TemplateTraceDialog';
import {detailFileName,loadTemplateTrace,type LoadedTrace} from './templateTrace';
import TemplateBrowsePopup from './TemplateBrowsePopup';
import TemplateRevisions,{TemplateOfficialDescriptions} from './TemplateRevisions';
import {assertNoNewGroupErrors,fileDeliveryDocument,fileImportDocument,fixEditedLocalUtterances,parseTemplateFile,pickTemplateDirectory,readTemplateFile,reviewLocalGroup,saveTemplateFile,templateFilesInDirectory,templateGroupSeasons,withLocalEntitySnapshot,writeLocalComment,writeLocalReviewStatus,writeTemplateDocument,type LocalDirectoryHandle,type LocalFileHandle,type OfficialTemplateCatalog,type TemplateFile} from './templateFile';
import {recentTemplateFiles,rememberRecentTemplateFile,sameTemplateFile,type RecentTemplateFile} from './templateRecentFiles';
import {actionArgumentFields,applyTemplateGroupFields,groupDiffKeys,appendTemplateMetadata,copyTemplateGroup,deriveTemplateEntities,downloadTemplates,effectiveReviewStatus,emptyTemplateFilters,filterTemplateGroups,templateGroupVisible,lineupPlayer,templateExplanationFields,templateMetadataLabels,templateRangeKey,templateRangeText,templateRangeValues,templateVersionValues,templateReviewLabels,templateReviewLabel,mergeTemplateWriteSnapshot,orderTemplateEvents,operators,templateId,valueText,type TemplateChange,type TemplateEntity,type TemplateEvent,type TemplateFilters,type TemplateGameMode,type TemplateGroup,type TemplateMetadataField,type TemplateParameter,type TemplateProposal,type TemplateReviewStatus,type TemplateSnapshot,type PortableTemplateLibrary,type TemplateWarning,type UtteranceBindings} from './templates';
import type {Note,Options} from './types';
import './templates.css';

function GroupExplanation({entries,title='说明与依据'}:{entries:{label?:string;text:string}[];title?:string}){
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
   onClick={()=>setState(current=>current==='pinned'?'closed':'pinned')}>{title}</button>
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

type InlineTriggerEditing={events:string[];saveEvent:(name:string)=>Promise<void>;saveArgument:(parameter:TemplateParameter,value:string|null,entityId?:string)=>Promise<void>};
type CopyKind='event'|'condition';
type CopyDraft={kind:CopyKind;source:TemplateGroup;group:TemplateGroup;view:string;popupKey?:string;target?:TemplateEvent;error?:string;busy?:boolean};

export function TemplateGroupCard({group,event,catalog,utteranceBindings,entities:archivedEntities=[],scopeName,editable,onEdit,onSaveName,onSaveMetadata,metadataLocked=false,onCopy,relatedCopyOptions,onRelatedCopy,onDelete,onExport,onTrace,onFeedback,commentCounts,lastActivity,onRevisions,onReviewStatus,reviewPending,canFinalReview=false,onToggleIgnored,onToggleFixed,savingIgnore,warning,onConfirm,onSaveUtterances,utteranceDrafts,onUtteranceDraftsChanged,flagFeedback,conditionEditor,onSaveExpression,scopeOptions,annotator=false,interactionLocked=false,fileMode=false,allowExport=true,workflow,proposal,proposalControl,originalGroup,inlineTrigger,conditionVariant=false}:{group:TemplateGroup;event?:TemplateEvent;catalog?:ConditionCatalog;utteranceBindings?:UtteranceBindings;entities?:TemplateEntity[];scopeName:(id:string|null)=>string;editable:boolean;onEdit:()=>void;onSaveName?:(name:string)=>Promise<void>;onSaveMetadata?:(field:'tags'|'batch',values:string[])=>Promise<void>;metadataLocked?:boolean;onCopy?:(kind:CopyKind)=>void;relatedCopyOptions?:()=>RelatedCopyChoice[];onRelatedCopy?:(event:string)=>void;onDelete?:()=>void;onExport?:()=>void;onTrace?:()=>void;onFeedback?:(id?:string)=>void;commentCounts?:Record<string,number>;lastActivity?:Activity;onRevisions?:()=>void;onReviewStatus?:(status:TemplateReviewStatus|null)=>void;reviewPending?:PendingReview;canFinalReview?:boolean;onToggleIgnored?:(utteranceId?:string)=>void;onToggleFixed?:(utteranceId:string)=>void;savingIgnore?:{group:boolean;rows:string[]};warning?:TemplateWarning;onConfirm?:()=>void;onSaveUtterances?:(change:UtteranceChange)=>Promise<void>;utteranceDrafts?:UtteranceDraftStore;onUtteranceDraftsChanged?:()=>void;flagFeedback?:(id:string,field:EditFlag)=>UtteranceFlagFeedback|undefined;conditionEditor?:ReactNode;onSaveExpression?:(value:string,scope:TemplateGroup['scope'])=>Promise<void>;scopeOptions?:TemplateScopeOptions;annotator?:boolean;interactionLocked?:boolean;fileMode?:boolean;allowExport?:boolean;workflow?:ReactNode;proposal?:CardProposal;proposalControl?:ProposalControl;originalGroup?:TemplateGroup;inlineTrigger?:InlineTriggerEditing;conditionVariant?:boolean}){
 const cards=useCards(),entities=deriveTemplateEntities(group,event,cards,archivedEntities);
 const actionValues=fixedArguments(group,event);
 const parameters=event?templateTriggerParameters(group,event):[];
 const actionPaths=event&&keyedTemplateSyntax(group.syntax_version)?actionArgumentFields(event).map(field=>'动作.'+field):[];
 const explanations=templateExplanationFields.flatMap(([field,label])=>group[field]?.trim()?[{label,text:group[field]!}]:[]);
 const entries=explanations.length?explanations:group.explanation?.trim()?[{text:group.explanation}]:[];
 const expression=templateDisplayExpression(group,scopeName);
 const expressionEdit=editable&&onSaveExpression&&(group.expression!==undefined||!group.conditions.length)?{
  value:expression,
  save:(value:string)=>{
   if(keyedTemplateSyntax(group.syntax_version)&&event)
    validateKeyedCondition(event.name,group.extra_key??'',value,group.syntax_version);
   const next=resolveConditionEdit(value,group,scopeName,{...scopeOptions,fileMode});
   return onSaveExpression(next.expression,next.scope);
  },
 }:undefined;
 const originalExpression=originalGroup&&templateDisplayExpression(originalGroup,scopeName);
 const removedExpression=!!(proposal?.fields.has('rule')&&originalExpression&&!expression);
 const changed=(...fields:string[])=>proposal&&(proposal.newGroup||fields.some(field=>proposal.fields.has(field)))?true:undefined;
 const deletedLabel=(value:string)=><><s>{value}</s> <small>拟删除</small></>;
 const conditionEdit=editable?{label:'编辑模板'+group.name,disabled:interactionLocked,onClick:onEdit}:undefined;
 const status=reviewPending?reviewPending.status:effectiveReviewStatus(group.review_status),historyId=useId();
 const reviewDetails=group.reviewed_by?`复核 · ${group.reviewed_by}${group.reviewed_at?' · '+new Date(group.reviewed_at).toLocaleString():''}`:undefined;
 const Entity=fileMode?({label}:{label?:string;ids:string[];portrait?:boolean})=><span className="entity-chip">{label}</span>:EntityChip;
 const badge=event?.name.replace(/^解释为何\s*/,'');
 const eventField=(label:string,value:string,className?:string)=>inlineTrigger&&!conditionVariant?
  <TemplateInlineChoice label={label} value={value} className={className} choices={inlineTrigger.events} disabled={interactionLocked} onSave={inlineTrigger.saveEvent}/>:
  <span className={className}>{value}</span>;
 return <article data-feedback-group={group.id} data-proposal-card={proposal?'preview':undefined} tabIndex={-1} className={'template-group '+(warning?'template-needs-check ':'')+(group.ignored?'template-group-ignored':'')+(conditionVariant?' template-condition-variant':'')} aria-label={conditionVariant?'触发条件与话术':group.name}>
  <header><div>{!conditionVariant&&<div className="template-card-title">
   {badge&&eventField('编辑动作徽标',badge,'template-action-badge')}
   <h2 data-proposal-change={changed('name')||proposal?.deleted||undefined}>{proposal?.deleted?<s>{group.name}</s>:editable&&onSaveName?
   <TemplateGroupName name={group.name} disabled={interactionLocked} onSave={onSaveName}/>:group.name}</h2>
   </div>}<div className="template-title-controls">
   {entries.length>0&&<span data-proposal-change={changed('explanation',...templateExplanationFields.map(([field])=>field))}><GroupExplanation entries={entries}/></span>}
   {group.wording_brief?.trim()&&<span data-proposal-change={changed('wording_brief')}><GroupExplanation title="话术构思" entries={[{text:group.wording_brief}]}/></span>}
   {(workflow||proposal)&&<div className="template-review-statuses" role="group" aria-label={'审核状态 · '+group.name} aria-busy={!!reviewPending}>
    {(Object.entries(templateReviewLabels) as [TemplateReviewStatus,string][]).map(([value,label])=>{
     const selected=value===status;
     return <button type="button" key={value} aria-pressed={selected} title={selected?reviewDetails:undefined} data-review-pending={reviewPending?.button===value||undefined}
      data-proposal-change={selected?changed('review_status'):undefined}
      disabled={!onReviewStatus||value==='final_reviewed'&&!canFinalReview&&!selected}
      onClick={()=>onReviewStatus?.(selected?null:value)}>{label}</button>;
    })}{status===null&&changed('review_status')&&<span className="template-proposal-mark">{templateReviewLabel(null)}</span>}
   </div>}</div>
   <div className="template-scope">{!conditionVariant&&<span data-proposal-change={changed('event_id','event')}>{eventField('编辑事件名称',event?.name??group.event_id)}</span>}
    {(['version','mode'] as const).map(field=>{
     const value=templateRangeText(group[field]),original=templateRangeText(originalGroup?.[field]);
     return (value||changed(field)&&original)&&<span key={field} data-proposal-change={changed(field)}>{value||deletedLabel(original)}</span>;
    })}
    <TemplateInlineMetadata label="标签" values={group.tags??[]} proposalPrevious={changed('tags')?originalGroup?.tags??[]:undefined} disabled={metadataLocked} onSave={editable&&onSaveMetadata?values=>onSaveMetadata('tags',values):undefined}/>
    <TemplateInlineMetadata label="批次" values={group.batch??[]} proposalPrevious={changed('batch')?originalGroup?.batch??[]:undefined} disabled={metadataLocked} onSave={editable&&onSaveMetadata?values=>onSaveMetadata('batch',values):undefined}/>
    {keyedTemplateSyntax(group.syntax_version)&&<span>额外信息键 {group.extra_key||'（空）'}</span>}
    {group.publication_hold&&<span title={group.publication_hold}>暂停发布 · {group.publication_hold}</span>}
    <span data-proposal-change={changed('priority')}>优先级 {group.priority??0}</span>
    {(group.ignored||changed('ignored'))&&<span className="template-ignored" data-proposal-change={changed('ignored')}>{group.ignored?'已忽略':'参与导出'}</span>}
    {group.last_modified_by&&<span>最后修改 · {group.last_modified_by.kind==='ai'?'AI':group.last_modified_by.username??'人工'}</span>}
   </div></div>
   <div className="template-card-actions">
    {onTrace&&<button type="button" onClick={onTrace}>溯源</button>}
    {onRevisions&&<div className="template-history-control"><button type="button" aria-describedby={historyId} disabled={interactionLocked} onClick={onRevisions}>版本记录</button>
     <span className="template-history-tooltip" id={historyId} role="tooltip">{lastActivity?`最近操作 · ${activityLabel(lastActivity)}`:'查看修订历史'}</span></div>}
    {onFeedback&&<button disabled={interactionLocked} onClick={()=>onFeedback()}>{fileMode?'组批注':'组批注与记录'} <span className="template-comment-count">{commentCounts?.['']??0}</span></button>}
    {allowExport&&<button aria-label={'导出json：'+group.name} disabled={interactionLocked||group.ignored||group.utterances.every(row=>row.ignored)} onClick={onExport}>导出json</button>}
    {editable&&<>
     {onCopy&&<TemplateRelatedCopy label="复制" buttonLabel={'复制模板组'+group.name} choicesLabel="复制模板组方式"
      disabled={interactionLocked} options={()=>[{event:'新事件'},{event:'新条件'}]} onChoose={choice=>onCopy(choice==='新事件'?'event':'condition')}/>}
     {relatedCopyOptions&&onRelatedCopy&&<TemplateRelatedCopy disabled={interactionLocked} options={relatedCopyOptions} onChoose={onRelatedCopy}/>}
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
   {!!event&&!!parameters.length && <dl aria-label="动作参数" className="template-action-parameters" data-proposal-change={changed('rule','event_id','event')}>{parameters.map(p=>{
    const position=/^arg([1-9]\d*)$/.exec(p.key);
    const label=(position&&actionPaths[Number(position[1])-1])||p.key;
    const value=actionValues.get(p.key),ids=value?argumentCardIds(p,value,cards):[];
    const candidates=p.type==='entity'?cards.filter(card=>!p.entity_categories?.length||p.entity_categories.includes(card.category)):[];
    const argument=inlineTrigger&&canEditTemplateArgument(group,event,p)?<TemplateInlineChoice label={'编辑参数 '+label}
     value={value??'未固定'} className="template-inline-argument" disabled={interactionLocked} previewIds={ids} firstChoice="未固定"
     choices={p.type==='entity'?candidates.map(card=>card.name):(p.suggestions??[]).map(valueText)} allowText
     onSave={next=>inlineTrigger.saveArgument(p,next==='未固定'?null:next,candidates.find(card=>card.name===next)?.id)}/>:
     value&&(ids.length?<EntityChip ids={ids} label={value} portrait={!fileMode}/>:<strong> · {value}</strong>);
    return <div key={p.key}><dt><code>{label}</code></dt><dd>{parameterRole(event,p)} <small>（{parameterType(p)}）</small>{argument}</dd></div>;
   })}</dl>}
   <div className="template-condition-scopes" data-proposal-change={changed('scope')}><span>棋手：{scopeName(group.scope.player_id)}</span><span>阵容：{scopeName(group.scope.lineup_note_id)}</span></div>
   {entities.length>0&&<div className="template-chips" aria-label="关联卡牌" data-proposal-change={changed('related_entities')}>{entities.map(e=><Entity key={e.id} ids={[e.id]} label={e.name} portrait/>)}</div>}
   {group.expression===undefined&&group.conditions.length>0&&<><h3>同时满足</h3><dl>{group.conditions.map(c=>{const parameter=event?.parameters.find(p=>p.key===c.parameter_key);const entity=c.value as TemplateEntity;const removed=proposal?.removedConditions.includes(c.id);return <div key={c.id} data-proposal-change={changed('condition:'+c.id)}><dt>{parameter?.name??c.parameter_key}</dt><dd>{removed?deletedLabel(operators[c.operator]+' '+valueText(c.value)):<><span>{operators[c.operator]} </span>{parameter?.type==='entity'&&entity?.id?<Entity ids={deriveTemplateEntities({...group,scope:{player_id:null,lineup_note_id:null},conditions:[c]},event,cards).map(e=>e.id)} label={entity.name}/>:valueText(c.value)}</>}</dd></div>;})}</dl></>}{group.expression===undefined&&!expression&&!group.conditions.length&&<p className="muted">不限制条件</p>}
   {group.expression!==undefined||expression||removedExpression||expressionEdit?<div data-proposal-change={changed('rule','scope')}>
    <TemplateConditionPreview expression={removedExpression?originalExpression!:expression} edit={conditionEdit} expressionEdit={expressionEdit} allowCopy={!proposal} removed={removedExpression}
     config={{event,catalog,v04:keyedTemplateSyntax(group.syntax_version)}}/>
   </div>:conditionEdit&&
    <div className="template-condition-actions"><button type="button" aria-label={conditionEdit.label} disabled={conditionEdit.disabled} onClick={conditionEdit.onClick}>编辑模板组</button></div>}
   {conditionEditor}
  </section><TemplateUtterances commentCounts={commentCounts} onFeedback={onFeedback} utterances={group.utterances} v04={keyedTemplateSyntax(group.syntax_version)} syntaxVersion={group.syntax_version} bindings={utteranceBindings} parameters={event?.parameters} event={event} catalog={catalog} localFile={fileMode}
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
function canDeliver(group:TemplateGroup){
 return !group.ignored&&group.utterances.some(row=>!row.ignored);
}
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
type OpenFile={handle:LocalFileHandle;raw:string;directory:LocalDirectoryHandle};
type FileChoice={directory:LocalDirectoryHandle;files:LocalFileHandle[];selected:string};
type LineupView={active:boolean;lineup:string;player:string;query:string;eventIds?:string[];filters:Pick<TemplateFilters,'review_status'|'onlyFixed'|'hideIgnored'>};
type BrowsePopup={key:string;title:string;ids:string[];parents:Map<string,string>;visibility:Pick<TemplateFilters,'onlyFixed'|'hideIgnored'>};
type View={filters:TemplateFilters;entityKey:string;byEntity:boolean;compact:boolean;selected:Set<string>;lineupView?:LineupView};
export type TemplateWorkspaceState={opened?:OpenFile|null;views?:Record<string,View>;details?:Record<string,string|null>;scroll?:Record<string,{top:number;visible:number}>;utteranceDrafts?:Map<string,UtteranceDraftStore>;cardEditors?:Map<string,CardEditor>;fileKeys?:WeakMap<LocalFileHandle,string>;traces?:WeakMap<LocalFileHandle,{raw:string;result:Promise<LoadedTrace>}>};
const emptyView:View={filters:emptyTemplateFilters,entityKey:'',byEntity:false,compact:false,selected:new Set()};
const emptyLineupView:LineupView={active:false,lineup:'',player:'',query:'',filters:{hideIgnored:true}};
const templatePath=(season:Season,suffix='')=>'templates'+suffix+(suffix.includes('?')?'&':'?')+'season='+season;

export default function TemplateLibrary({notes,options,onDirty,onDocumentNoteDirty,onBusyChange,season='S1',source='database',gameMode,workspace}:{season?:Season;source?:'database'|'file';gameMode?:TemplateGameMode;notes:Note[];options:Options;onDirty?:(dirty:boolean)=>void;onDocumentNoteDirty?:(dirty:boolean)=>void;onBusyChange?:(busy:boolean)=>void;workspace?:TemplateWorkspaceState}){
 const [legacy,setLegacy]=useState<TemplateSnapshot|null>(null),[showLegacy,setShowLegacy]=useState(false);
 const {session}=useAuth(),fileMode=source==='file',legacyMode=!fileMode&&season==='S2'&&showLegacy&&!!legacy?.groups.length;
 const admin=session.role==='admin',annotator=session.role==='annotator',reviewer=!legacyMode&&(admin||session.role==='quality'),editable=reviewer||!legacyMode&&annotator;
 const canManage=editable&&(fileMode||admin||annotator);
 const cards=useCards();
 const [database,setDatabase]=useState<TemplateSnapshot|null>(null),[opened,setOpened]=useState<OpenFile|null>(()=>workspace?.opened??null);
 const [traceGroup,setTraceGroup]=useState<TemplateGroup|null>(null);
 const [fileChoice,setFileChoice]=useState<FileChoice>();
 const [traceCache]=useState<NonNullable<TemplateWorkspaceState['traces']>>(()=>workspace?.traces??new WeakMap());
 useEffect(()=>{if(workspace)workspace.traces=traceCache;},[workspace,traceCache]);
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
 const readTrace=useCallback((retry:boolean)=>{
  if(!opened)return Promise.reject(new Error('请先打开模板文件。'));
  const {handle,raw,directory}=opened,cached=traceCache.get(handle);
  if(!retry&&cached?.raw===raw)return cached.result;
  const document=parsedFile.current;
  const groups=document?.opened===opened?document.value.snapshot.groups:undefined;
  const name=detailFileName(handle.name);
  const result=(async()=>{
   try{
    if(retry&&directory.requestPermission&&await directory.requestPermission({mode:'read'})!=='granted'){
     throw new DOMException('未授权','NotAllowedError');
    }
    return await loadTemplateTrace(await directory.getFileHandle(name),{name:handle.name,raw,groups});
   }catch(error){
    if((error as Error).name==='NotFoundError')throw new Error('模板目录中找不到 '+name+'。放入生成记录后重试。');
    if(['NotAllowedError','SecurityError'].includes((error as Error).name))throw new Error('读取模板目录的权限已取消。请重试并授权读取。');
    throw error;
   }
  })();
  traceCache.set(handle,{raw,result});
  void result.catch(()=>{if(traceCache.get(handle)?.result===result)traceCache.delete(handle);});
  return result;
 },[opened,traceCache]);
 const snapshot=fileMode?file?.snapshot??null:legacyMode?legacy:database;
 function localCommentCounts(groupId:string){
  const counts:Record<string,number>=Object.create(null);
  for(const comment of file?.comments.get(groupId)??[]){
   const id=comment.utterance_id??'';
   counts[id]=(counts[id]??0)+1;
  }
  return counts;
 }
 const [views,setViews]=useState<Record<string,View>>(()=>workspace?.views??{});
 useEffect(()=>{if(workspace)workspace.views=views;},[workspace,views]);
 function rememberFile(file:OpenFile|null){
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
 const [details,setDetails]=useState<Record<string,string|null>>(()=>workspace?.details??{});
 const detailKey=viewKey+':'+(gameMode??''),detailId=details[detailKey]??null;
 const [revisionGroup,setRevisionGroup]=useState<TemplateGroup|null>(null);
 function setDetailId(update:string|null|((previous:string|null)=>string|null)){
  setDetails(current=>({...current,[detailKey]:typeof update==='function'?update(current[detailKey]??null):update}));
 }
 useEffect(()=>{if(workspace)workspace.details=details;},[workspace,details]);
 const [recentFiles,setRecentFiles]=useState<RecentTemplateFile[]>([]);
 useEffect(()=>{
  if(!fileMode)return;
  let active=true;
  void recentTemplateFiles().then(items=>{if(active)setRecentFiles(items);});
  return ()=>{active=false;};
 },[fileMode]);
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
 if(opened&&!fileKeys.has(opened.handle))fileKeys.set(opened.handle,templateId('file'));
 const lineupViewKey=JSON.stringify(['lineup',viewKey,gameMode,fileMode&&opened?fileKeys.get(opened.handle):null]);
 const lineupView=views[lineupViewKey]?.lineupView??emptyLineupView;
 const byLineup=lineupView.active;
 const [browsePopup,setBrowsePopup]=useState<BrowsePopup>();
 const [copyDraft,setCopyDraft]=useState<CopyDraft>();
 function openBrowsePopup(title:string,ids:string[],visibility:BrowsePopup['visibility']){
  if(!ids.length)return;
  setError('');
  setBrowsePopup({key:templateId('browse'),title,ids,visibility,parents:new Map()});
 }
 const changeLineupView=(patch:Partial<LineupView>,browse?:Partial<View>)=>setViews(current=>({
  ...current,
  ...(browse?{[viewKey]:{...(current[viewKey]??emptyView),...browse}}:{}),
  [lineupViewKey]:{...emptyView,lineupView:{...(current[lineupViewKey]?.lineupView??emptyLineupView),...patch}},
 }));
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
 const [fileExport,setFileExport]=useState<{group?:TemplateGroup;scope?:FileExportScope}>();
 const saveFileLock=useRef(false),pickerLock=useRef(false);
 const documentNoteDirty=useRef(false);
 function changeDocumentNoteDirty(dirty:boolean){documentNoteDirty.current=dirty;onDocumentNoteDirty?.(dirty);}
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
  setTraceGroup(null);setFileChoice(undefined);
  setError('');setNotice('');setLocatedDetail(null);setFocusTarget(null);setRevisionGroup(null);setEditor(null);setJsonGroup(null);setFeedback(null);
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
 const lineups=lookups.lineups;
 const scopeNames=useMemo(()=>new Map([...notes.map(note=>[note.id,note.title] as const),...players.map(player=>[player.id,player.name] as const)]),[notes,players]);
 const scopeName=useCallback((id:string|null)=>id?(scopeNames.get(id)??snapshot?.scope_names?.[id]??id):'通用',
  [scopeNames,snapshot?.scope_names]);
 const allGroups=useMemo(()=>snapshot?.groups.filter(group=>(legacyMode||templateGroupSeasons(group).includes(season))&&(!gameMode||templateRangeValues(group.mode).includes(gameMode)))??[],[snapshot,season,legacyMode,gameMode]);
 const lineupEventOptions=useMemo(()=>{
  if(!byLineup)return [];
  const used=new Set(allGroups.map(group=>group.event_id));
  return orderTemplateEvents((snapshot?.events??[]).filter(event=>used.has(event.id)));
 },[byLineup,allGroups,snapshot?.events]);
 const selectedLineupEvents=useMemo(()=>{
  const selected=new Set(lineupView.eventIds);
  return new Set(lineupEventOptions.filter(event=>selected.has(event.id)).map(event=>event.id));
 },[lineupEventOptions,lineupView.eventIds]);
 const lineupEventGroups=useMemo(()=>selectedLineupEvents.size
  ?allGroups.filter(group=>selectedLineupEvents.has(group.event_id)):allGroups,[allGroups,selectedLineupEvents]);
 const cardEvents=useMemo(()=>new Map(snapshot?.events.map(event=>[event.id,event])),[snapshot?.events]);
 const displayNames=useMemo(()=>new Map(allGroups.map(group=>[group.id,canonicalTemplateName(group,cardEvents.get(group.event_id))??group.name])),[allGroups,cardEvents]);
 const metadataChoices=useMemo(()=>({tags:[...new Set(allGroups.flatMap(group=>group.tags??[]))],batch:[...new Set(allGroups.flatMap(group=>group.batch??[]))]}),[allGroups]);
 const entityEntries=useMemo(()=>buildTemplateEntityIndex(allGroups,snapshot?.events??[],lookups.entities,snapshot?.condition_catalog)
  .filter(row=>!fileMode||row.groupIds.size>0),[allGroups,snapshot,lookups,fileMode]);
 const {lineupTabs,rosters}=useMemo(()=>{
  const noteLineups=new Map(lineups.map(note=>[note.id,lineupRosterName(note,scopeName)]));
  const tabs=buildLineupTabs(allGroups,id=>noteLineups.get(id)??scopeName(id),true);
  const rosters=addLineupRosters(tabs,lineups.filter(note=>(note.seasons??['S1']).includes(season)),scopeName,!fileMode);
  return {lineupTabs:tabs,rosters};
 },[allGroups,lineups,season,scopeName,fileMode]);
 const lineupNames=[...lineupTabs.keys()].filter(name=>name!==unscopedLineup).sort((a,b)=>a.localeCompare(b,'zh-CN'));
 const selectedLineup=lineupTabs.has(lineupView.lineup)?lineupView.lineup:lineupNames[0]??(lineupTabs.has(unscopedLineup)?unscopedLineup:'');
 const selectedLineupTabs=lineupTabs.get(selectedLineup);
 const lineupPlayerTab=selectedLineupTabs?.has(lineupView.player)?lineupView.player:'';
 const lineupRoster=useMemo(()=>{
  const names=new Map<string,string>();
  for(const entity of byLineup?lookups.entities:[])if(entity.category==='heroes'){
   names.set(entity.id,entity.name);
   names.set(entity.name,entity.name);
   for(const alias of entity.aliases??[])if(!names.has(alias))names.set(alias,entity.name);
  }
  const rosterFor=(name:string,player:string)=>new Set([...lineupRosterNames(rosters,name,player)].flatMap(ref=>{
   const name=names.get(ref)??(ref.startsWith('pending:')?names.get(ref.slice(8))??ref.slice(8):undefined);
   return name?[name]:[];
  }));
  const known=new Set(names.values());
  const extras=(heroes:ReadonlySet<string>)=>[...heroes].filter(name=>!known.has(name)).map(name=>({id:'pending:'+name,name,category:'heroes'}));
  return {rosterFor,extras};
 },[byLineup,rosters,lookups.entities]);
 const lineupSelection=useMemo(()=>{
  if(!byLineup)return {groups:[],inherited:[],entries:[],heroes:new Set<string>()};
  const heroes=lineupRoster.rosterFor(selectedLineup,lineupPlayerTab);
  const shared=selectedLineupTabs?.get(''),local=selectedLineupTabs?.get(lineupPlayerTab);
  const fallback=lineupTabs.get(unscopedLineup);
  const groups=lineupEventGroups.filter(group=>shared?.has(group.id)||local?.has(group.id));
  const inherited=selectedLineup===unscopedLineup?[]:lineupEventGroups.filter(group=>
   fallback?.get('')?.has(group.id)||!!lineupPlayerTab&&fallback?.get(lineupPlayerTab)?.has(group.id));
  const entries=buildTemplateEntityIndex([...groups,...inherited],snapshot?.events??[],
   [...lookups.entities,...lineupRoster.extras(heroes)],snapshot?.condition_catalog,undefined,true,heroes);
  return {groups,inherited,entries,heroes};
 },[byLineup,lineupRoster,selectedLineup,lineupPlayerTab,lookups.entities,selectedLineupTabs,lineupTabs,lineupEventGroups,snapshot]);
 const countGroups=useMemo(()=>filterTemplateGroups(byLineup?[]:allGroups,
  {...filters,event:'',mode:gameMode===undefined?filters.mode:undefined},lookups.entities,
  {events:snapshot?.events,scopeName,links:snapshot?.entity_links,utteranceBindings:snapshot?.utterance_bindings,displayNames}),
 [byLineup,allGroups,filters,gameMode,lookups.entities,scopeName,snapshot?.events,snapshot?.entity_links,snapshot?.utterance_bindings,displayNames]);
 const boardFilters={...emptyTemplateFilters,...lineupView.filters};
 const lineupSidebarCounts=useMemo(()=>{
  const reviews=new Map((byLineup?filterTemplateGroups(lineupEventGroups,{...emptyTemplateFilters,...lineupView.filters}):[])
   .map(group=>[group.id,group.review_status]));
  const fallback=lineupTabs.get(unscopedLineup);
  const fallbackIds=new Set([...(fallback?.values()??[])].flatMap(ids=>[...ids]));
  const fallbackGroups=byLineup?lineupEventGroups.filter(group=>fallbackIds.has(group.id)&&reviews.has(group.id)):[];
  const heroNames=new Set<string>();
  if(fallbackGroups.length)for(const [name,branches] of lineupTabs){
   if(name===unscopedLineup)continue;
   for(const player of ['',...branches.keys()])for(const hero of lineupRoster.rosterFor(name,player))heroNames.add(hero);
  }
  const byHero=new Map((heroNames.size?buildTemplateEntityIndex(fallbackGroups,snapshot?.events??[],
   [...lookups.entities,...lineupRoster.extras(heroNames)],snapshot?.condition_catalog,undefined,true,heroNames):[])
   .filter(entity=>entity.category==='heroes').map(entity=>[entity.name,entity.groupIds]));
  return (name:string,player:string)=>{
   const branches=lineupTabs.get(name);
   const ids=new Set([...(branches?.get('')??[]),...(branches?.get(player)??[])].filter(id=>reviews.has(id)));
   if(name!==unscopedLineup)for(const hero of lineupRoster.rosterFor(name,player)){
    for(const id of byHero.get(hero)??[]){
     if(fallback?.get('')?.has(id)||player&&fallback?.get(player)?.has(id))ids.add(id);
    }
   }
   return lineupTemplateCounts(ids,reviews);
  };
 },[lineupEventGroups,byLineup,lineupView.filters,lineupTabs,lineupRoster,snapshot?.events,snapshot?.condition_catalog,lookups.entities]);
 const boardRows=lineupBoardRows(byLineup?filterTemplateGroups(lineupSelection.groups,boardFilters):[],lineupSelection.entries,
  lineupSelection.heroes,byLineup?filterTemplateGroups(lineupSelection.inherited,boardFilters):[],byLineup?snapshot?.events:undefined);
 const allEntityIds=useMemo(()=>new Set(entityEntries.flatMap(row=>[...row.groupIds])),[entityEntries]);
 const entity=byEntity?entityEntries.find(row=>row.key===entityKey):undefined;
 const groups=useMemo(()=>{
  const visible=byEntity?countGroups.filter(group=>(entity?.groupIds??allEntityIds).has(group.id)):
   filters.event?countGroups.filter(group=>group.event_id===filters.event):countGroups;
  return templateDisplaySections(visible,snapshot?.events??[],scopeName).flatMap(section=>section.events.flatMap(event=>event.rows));
 },[byEntity,countGroups,entity,allEntityIds,filters.event,snapshot?.events,scopeName]);
 const lineupEvents=new Map(snapshot?.events.map(event=>[event.id,event.name]));
 const selectedGroups=allGroups.filter(group=>selected.has(group.id));
 const importableSelection=fileMode?selectedGroups.filter(canDeliver):[];
 const currentLocation=locatedDetail?.identity===proposalIdentity?locatedDetail:undefined;
 const locatedGroup=currentLocation&&snapshot?.groups.find(group=>group.id===currentLocation.id);
 const temporaryGroup=currentLocation&&!locatedGroup?(previewsByGroup.get(currentLocation.id)?.find(row=>
  !row.base&&row.proposal_id===proposalChoices[currentLocation.id])?.change.value as TemplateGroup|undefined):undefined;
 const detailCandidate=allGroups.find(group=>group.id===detailId)??(previewEnabled?locatedGroup??temporaryGroup:undefined);
 const detailGroup=detailCandidate&&templateGroupVisible(detailCandidate,filters)?detailCandidate:undefined;
 useEffect(()=>{
  if(!focusTarget)return;
  const selector='[data-feedback-group="'+CSS.escape(focusTarget.group)+'"]';
  const card=document.querySelector<HTMLElement>('[role="dialog"] '+selector)??document.querySelector<HTMLElement>(selector);
  const node=focusTarget.utterance?card?.querySelector<HTMLElement>('[data-feedback-utterance="'+CSS.escape(focusTarget.utterance)+'"]'):card;
  if(node){node.focus({preventScroll:true});node.scrollIntoView({block:'center'});}
  setFocusTarget(null);
 },[focusTarget,detailGroup?.id]);
 function patch(value:Partial<TemplateFilters>){setFilters(f=>{const next={...f,...value};if(value.lineup&&value.lineup!=='common'){const n=lineups.find(n=>n.id===value.lineup);if(n)next.player=lineupPlayer(n)??next.player;}if(value.player!==undefined&&next.lineup&&next.lineup!=='common'){const n=lineups.find(n=>n.id===next.lineup);if(n&&lineupPlayer(n)!==value.player)next.lineup='';}return next;});}
 function retargetGroups(ids:ReadonlyMap<string,string|null>,groups:TemplateGroup[]){
  if(!ids.size)return;
  const target=(id:string)=>ids.has(id)?ids.get(id)??null:id;
  const targets=(previous:Iterable<string>)=>[...new Set([...previous].flatMap(id=>target(id)??[]))];
  const parents=(previous:ReadonlyMap<string,string>)=>{
   const next=new Map<string,string>();
   for(const [child,parent] of previous){
    const from=target(child),to=target(parent);
    if(!from||!to||next.has(from))continue;
    let ancestor:string|undefined=to;
    while(ancestor&&ancestor!==from)ancestor=next.get(ancestor);
    if(!ancestor)next.set(from,to);
   }
   return next;
  };
  setDetailId(id=>id?target(id):id);
  setLocatedDetail(previous=>{
   const id=previous&&target(previous.id);
   return previous&&id?{...previous,id}:null;
  });
  changeView(current=>({...current,selected:new Set(targets(current.selected))}));
  setBrowsePopup(previous=>{
   if(!previous)return previous;
   const next=targets(previous.ids);
   if(!next.length)return undefined;
   const renamed=previous.ids.length===1&&next[0]!==previous.ids[0]&&previous.title.endsWith(' · 模板详情')
    ?groups.find(group=>group.id===next[0])?.name:undefined;
   return {...previous,ids:next,parents:parents(previous.parents),title:renamed?renamed+' · 模板详情':previous.title};
  });
  setRelatedPlacement(previous=>previous&&({...previous,parents:parents(previous.parents)}));
 }
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
    if(result.merged_groups)retargetGroups(new Map(Object.entries(result.merged_groups)),next.groups);
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
 function fileDraftKey(key:string){
  const [,mode,handle]=JSON.parse(key);
  const active=openedFile.current;
  return !!active&&mode.startsWith('file:')&&handle===fileKeys.get(active.handle);
 }
 function allowReplaceFile(){
  if(!openedFile.current)return true;
  const editedUtterance=[...utteranceDrafts].some(([key,store])=>fileDraftKey(key)&&
   Object.values(store.drafts).some(draft=>draft.text!==(draft.baseText??'')));
  const editedGroup=[...cardEditors].some(([key,{base,scratch}])=>fileDraftKey(key)&&
   (scratch.addedParameters?.length||scratch.parameterAdding||scratch.draft&&JSON.stringify(scratch.draft)!==JSON.stringify(base)));
  return !(editedUtterance||editedGroup||documentNoteDirty.current)||confirm('当前文件有未保存的修改。确定放弃这些修改吗？');
 }
 function resetFileView(){
  setTraceGroup(null);
  if(openedFile.current){
   for(const key of utteranceDrafts.keys())if(fileDraftKey(key))utteranceDrafts.delete(key);
   for(const key of cardEditors.keys())if(fileDraftKey(key))cardEditors.delete(key);
  }
  setViews(current=>Object.fromEntries(Object.entries(current).filter(([key])=>!key.startsWith('file:'))));
  setDetails(current=>Object.fromEntries(Object.entries(current).filter(([key])=>!key.startsWith('file:'))));
  for(const key of Object.keys(scrollPositions.current))if(key.startsWith('file:'))delete scrollPositions.current[key];
  setPaging(undefined);
  if(groupList.current)groupList.current.scrollTop=0;
  setEditor(null);setFeedback(null);setJsonGroup(null);setFileExport(undefined);setBatchMetadata(null);
  setSettings(false);setImportOpen(false);setImportSelection(null);setPreview(null);
  onDirty?.(false);
 }
 function closeFile(){
  if(!openedFile.current||busy||pickerLock.current||saveFileLock.current||!allowReplaceFile())return;
  resetFileView();
  parsedFile.current=null;
  rememberFile(null);
  setError('');setNotice('');
 }
 async function chooseDirectory(options:{directory?:LocalDirectoryHandle;startIn?:LocalDirectoryHandle|LocalFileHandle}={}){
  if(busy||pickerLock.current||saveFileLock.current)return;
  pickerLock.current=true;onBusyChange?.(true);setBusy(true);setError('');
  try{
   const directory=options.directory??await pickTemplateDirectory(options.startIn);
   if(options.directory&&directory.requestPermission&&await directory.requestPermission({mode:'read'})!=='granted'){
    throw new Error('未获得模板目录的读取权限，请重新授权。');
   }
   const files=await templateFilesInDirectory(directory);
   setFileChoice({directory,files,selected:files.find(handle=>handle.name===opened?.handle.name)?.name??files[0]?.name??''});
  }catch(error){
   if((error as Error).name!=='AbortError')setError((error as Error).message);
  }
  finally{pickerLock.current=false;onBusyChange?.(false);setBusy(false);}
 }
 async function openFile(reuse=false,reportInDialog=false,options:{recent?:RecentTemplateFile;selection?:{handle:LocalFileHandle;directory:LocalDirectoryHandle}}={}){
  if(busy||pickerLock.current||saveFileLock.current||!reuse&&!allowReplaceFile())return;
  const target=options.recent??options.selection??(reuse?openedFile.current:null);
  if(!target)return;
  if(!target.directory){void chooseDirectory({startIn:target.handle});return;}
  pickerLock.current=true;onBusyChange?.(true);setBusy(true);setError('');
  try{
   const {handle,directory}=target;
   if(options.recent&&directory.requestPermission&&await directory.requestPermission({mode:'read'})!=='granted'){
    throw new Error('未获得模板目录的读取权限，请重新授权。');
   }
   const raw=await readTemplateFile(handle);
   parseTemplateFile(raw,lookups);
   const current=openedFile.current;
   const same=current&&await sameTemplateFile(current.handle,handle);
   if(!same)resetFileView();
   const known=same||options.recent?undefined:(await Promise.all(recentFiles.map(async entry=>await sameTemplateFile(entry.handle,handle)?entry:undefined))).find(entry=>entry);
   const activeHandle=same?current.handle:known?.handle??handle;
   if(reuse)traceCache.delete(activeHandle);
   rememberFile({handle:activeHandle,raw,directory});setNotice('');setFileChoice(undefined);
   void rememberRecentTemplateFile({id:options.recent?.id??templateId('recent'),handle:activeHandle,directory,openedAt:Date.now()}).then(setRecentFiles);
  }catch(error){
   if(reportInDialog)throw error;
   const {name,message}=error as Error;
   if(name!=='AbortError')setError(name==='NotFoundError'?'找不到模板文件，可能已移动或删除。请重新选择文件。':message);
  }
  finally{pickerLock.current=false;onBusyChange?.(false);setBusy(false);}
 }
 function saveFileComment(group:TemplateGroup,utteranceId:string|undefined,body:string){
  const save=fileInlineQueue.current.then(async()=>{
   const destination=openedFile.current;
   if(!destination||destination.handle!==opened?.handle)throw new Error('模板文件已切换，请重新打开批注。');
   if(saveFileLock.current||pickerLock.current)throw new Error('文件正在处理，请稍后再试。');
   const target=utteranceId?group.utterances.find(row=>row.id===utteranceId):undefined;
   if(utteranceId&&!target)throw new Error('话术已不存在，请重新打开批注。');
   const next=writeLocalComment(documentFor(destination),group.id,target,{
    id:templateId('comment'),by:session.username??'local',at:new Date().toISOString(),body,
   });
   saveFileLock.current=true;onBusyChange?.(true);setBusy(true);
   try{
    const raw=await saveTemplateFile(destination.handle,destination.raw,next);
    rememberFile({...destination,raw});
   }finally{saveFileLock.current=false;onBusyChange?.(false);setBusy(false);}
  });
  fileInlineQueue.current=save.catch(()=>{});
  return save;
 }
 async function saveDocumentNote(text:string){
  const destination=openedFile.current;
  if(!destination||destination.handle!==opened?.handle)throw new Error('模板文件已切换，请重新打开笔记。');
  if(saveFileLock.current||pickerLock.current)throw new Error('文件正在处理，请稍后再试。');
  saveFileLock.current=true;onBusyChange?.(true);setBusy(true);
  try{
   const raw=await saveTemplateFile(destination.handle,destination.raw,{...documentFor(destination).document,note:text});
   rememberFile({...destination,raw});
  }finally{saveFileLock.current=false;onBusyChange?.(false);setBusy(false);}
 }
 async function saveLocal(changes:TemplateChange[],action:'edit'|'status'|'fixed'='edit',destination=action==='status'?openedFile.current:opened,showNotice=true,merge?:{origin?:string}){
  const document=destination&&documentFor(destination);
  if(!destination||!document)throw new Error('请先打开模板文件。');
  if(saveFileLock.current||pickerLock.current)throw new Error('文件正在处理，请稍后再试。');
  saveFileLock.current=true;onBusyChange?.(true);setBusy(true);setError('');
  try{
   const at=new Date().toISOString(),user=session.username??'local';
   const previousGroups=new Map(document.snapshot.groups.map(group=>[group.id,group]));
   const events=new Map(document.snapshot.events.map(event=>[event.id,event]));
   for(const change of changes)if(change.kind==='event'&&change.action==='put')events.set(change.id,change.value as TemplateEvent);
   const marked=changes.flatMap(change=>{
    if(action!=='edit'||change.kind!=='group'||change.action!=='put')return [change];
    const supplied=change.value as TemplateGroup;
    const previous=previousGroups.get(supplied.id);
    const group=previous?fixEditedLocalUtterances(previous,supplied):supplied;
    if(JSON.stringify(previous)===JSON.stringify(group))return [];
    const event=events.get(group.event_id);
    const references=deriveTemplateEntities(group,event,lookups.entities);
    const edited=reviewLocalGroup(group,user,'edit',at);
    const value=withLocalEntitySnapshot(edited,event,official,references,document.snapshot.condition_catalog,lookups.entities,season);
    return [{...change,value}];
   });
   const mergedIds=new Map<string,string>();
   if(!marked.length)return mergedIds;
   const next=action==='status'?writeLocalReviewStatus(document,marked[0].value as TemplateGroup):
    writeTemplateDocument(document,marked,lookups,merge?mergedIds:undefined);
   const parsed=parseTemplateFile(JSON.stringify(next),lookups);
   assertNoNewGroupErrors(document,next,parsed);
   const raw=await saveTemplateFile(destination.handle,destination.raw,next);
   const updatedIds=new Map<string,string|null>(mergedIds);
   for(const change of marked){
    if(change.kind!=='group')continue;
    if(change.action==='delete')updatedIds.set(change.id,null);
    if(merge?.origin&&change.id!==merge.origin&&mergedIds.has(change.id))updatedIds.set(merge.origin,mergedIds.get(change.id)!);
   }
   const savedFile={...destination,raw};
   parsedFile.current={opened:savedFile,lookups,value:parsed};
   rememberFile(savedFile);
   retargetGroups(updatedIds,parsed.snapshot.groups);
   if(action!=='status'&&showNotice)setNotice('已保存到原文件。');
   return mergedIds;
  }finally{saveFileLock.current=false;onBusyChange?.(false);setBusy(false);}
 }
 async function write(changes:TemplateChange[],original?:TemplateGroup){
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
   await saveLocal(localChanges,'edit',undefined,true,{origin:original?.id});
   return;
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
 function enqueueGroupChange(groupId:string,update:(group:TemplateGroup)=>TemplateGroup,notice:string|null='模板库已保存。',mergeGroups=false){
  if(fileMode)return enqueueFileMetadataChanges(groups=>{
   const group=groups.find(row=>row.id===groupId);
   if(!group)throw new Error('模板组已不存在，请重新读取文件。');
   return [{kind:'group',action:'put',id:groupId,value:update(group)}];
  },false,'edit',mergeGroups?{}:undefined);
  return enqueueWrite(current=>{
   const group=current.groups.find(row=>row.id===groupId);
   if(!group)throw new Error('模板组已不存在，请刷新后重试');
   const fields=groupFields(group,update(group));
   if(!Object.keys(fields.set).length&&!fields.remove.length)return Promise.resolve(current);
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,group_patches:[{id:groupId,fields}]});
  },notice,[groupId]);
 }
 function enqueueFileMetadataChanges(prepare:(groups:TemplateGroup[],events:TemplateEvent[])=>TemplateChange[],showNotice=false,action:'edit'|'fixed'='edit',merge?:{origin?:string}){
  const save=fileInlineQueue.current.then(async()=>{
   const destination=openedFile.current;
   if(!destination||destination.handle!==opened?.handle)throw new Error('模板文件已切换，请重新编辑。');
   const document=documentFor(destination);
   if(!document)throw new Error('请先打开模板文件。');
   const changes=prepare(document.snapshot.groups,document.snapshot.events);
   if(!changes.length)return;
   fileMetadataWrite.current=true;
   try{await saveLocal(changes,action,destination,showNotice,merge);}
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
  return enqueueGroupChange(groupId,group=>applyUtteranceChange(group,change),'模板库已保存。',true);
 }
 async function changeSelectedGroups(action:'ignore'|'delete'){
  if(!selectedGroups.length||busy||batchConflict)return;
  if(action==='delete'&&(!canManage||selectedGroups.some(group=>group.utterances.some(row=>row.fixed))||
   !confirm('确定删除所选 '+selectedGroups.length+' 个模板组及其全部话术吗？')))return;
  const ids=new Set(selectedGroups.map(group=>group.id));
  const prepare=(current:TemplateGroup[]):TemplateChange[]=>{
   const targets=current.filter(group=>ids.has(group.id));
   if(targets.length!==ids.size)throw new Error('部分所选模板组已不存在，请重新选择。');
   if(action==='delete'){
    if(targets.some(group=>group.utterances.some(row=>row.fixed)))throw new Error('请先取消所选模板组中的固定话术。');
    return targets.map(group=>({kind:'group',action:'delete',id:group.id}));
   }
   return targets.filter(group=>!group.ignored).map(group=>({
    kind:'group',action:'put',id:group.id,value:applyIgnore(group,{groupId:group.id,ignored:true})
   }));
  };
  const notice=action==='delete'?'已批量删除模板组。':'已批量忽略模板组。';
  setError('');
  try{
   if(fileMode){
    await enqueueFileMetadataChanges(prepare);
    setNotice(notice);
   }else{
    await enqueueWrite(async current=>{
     const changes=prepare(current.groups);
     return changes.length?api(templatePath(season,'/changes'),'POST',{revision:current.revision,changes}):current;
    },notice,[...ids]);
   }
   changeView(current=>({...current,selected:new Set([...current.selected].filter(id=>!ids.has(id)))}));
  }catch(error){setError((error as Error).message);}
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
 async function exportSource(scope:FileExportScope,group?:TemplateGroup,sameAsOpened=false){
  const ids=group?[group.id]:scope==='all'?undefined:(scope==='selected'?selectedGroups:groups).map(row=>row.id);
  if(ids&&!ids.length)throw new Error('当前范围没有可导出的模板。');
  if(fileMode){
   if(!file)throw new Error('请先打开模板文件。');
   if(sameAsOpened)throw new Error('请选择另一个文件作为导出目标。当前模板文件可直接保存。');
   return fileDeliveryDocument(file,ids);
  }
  const suffix='/export?authoring=1'+(ids?'&group_ids='+encodeURIComponent(ids.join(',')):'');
  return api<PortableTemplateLibrary>(templatePath(season,suffix));
 }
 async function exportAll(){setError('');try{downloadTemplates(await exportSource('all'),'话术模板库.json');}catch(e){setError((e as Error).message);}}
 function beginImport(selection:TemplateGroup[]|null=null){setError('');setBypass(false);setReason('');setPreview(null);setImportText('');setImportSelection(selection?.filter(canDeliver)??null);setImportOpen(true);}
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
 function create(){
  editorBase.current=undefined;
  const v04=keyedTemplateSyntax(snapshot?.syntax_version)||!!snapshot?.groups.some(group=>keyedTemplateSyntax(group.syntax_version));
  const events=orderTemplateEvents(snapshot?.events??[]).filter(event=>!v04||registeredEvent(event.name));
  if(!events.length){setNotice('请先在事件与参数设置中添加事件。');setSettings(true);return;}
  const event=events.find(row=>row.id===filters.event)??events[0];
  const version=filters.version||season;
  setEditor({id:templateId('group'),name:'',version:/^S[12]$/i.test(version)?[version.toUpperCase()]:version,mode:[(gameMode??filters.mode)||'万象大赛'],
   tags:filters.tags??[],event_id:event.id,scope:{player_id:filters.player&&filters.player!=='common'?filters.player:null,
   lineup_note_id:filters.lineup&&filters.lineup!=='common'?filters.lineup:null},priority:0,
   ...(v04?{syntax_version:currentTemplateSyntax,extra_key:wildcardKey(event.name)}:{condition_tree:{kind:'all' as const,children:[]}}),
   expression:'',editor_mode:v04?'text':'tree',conditions:[],utterances:[{id:templateId('utterance'),text:''}],related_entities:[]});
 }
 const scrollPositions=useRef(workspace?.scroll??{}),groupList=useRef<HTMLDivElement>(null);
 const lineupScroll=useRef<HTMLDivElement>(null);
 const lineupScrollKey=JSON.stringify([lineupViewKey,selectedLineup,lineupPlayerTab]);
 useLayoutEffect(()=>{
  if(byLineup){
   for(const pane of lineupScroll.current?.querySelectorAll<HTMLElement>('[data-lineup-scroll]')??[]){
    const saved=scrollPositions.current[lineupScrollKey+':'+pane.dataset.lineupScroll];
    pane.scrollTop=saved?.top??0;pane.scrollLeft=saved?.visible??0;
   }
  }
 },[byLineup,lineupScrollKey]);
 useEffect(()=>{if(workspace)workspace.scroll=scrollPositions.current;},[workspace]);
 const pageSize=compact?80:20;
 const scrollKey=viewKey+':'+(gameMode??'')+':'+(compact?'board:':'cards:')+(byEntity?'entity:'+entityKey:'event:'+filters.event);
 const [relatedPlacement,setRelatedPlacement]=useState<{key:string;parents:Map<string,string>}>();
 const relatedWriting=useRef(false);
 const relatedParents=relatedPlacement?.key===scrollKey?relatedPlacement.parents:new Map<string,string>();
 useEffect(()=>{setRelatedPlacement(undefined);},[scrollKey]);
 const relatedAvailable=new Map(allGroups.map(group=>[group.id,group]));
 for(const [id,rows] of previewsByGroup){
  if(relatedAvailable.has(id))continue;
  const pending=rows.find(row=>!row.base&&row.proposal_id===proposalChoices[id])?.change.value as TemplateGroup|undefined;
  if(pending)relatedAvailable.set(id,pending);
 }
 const relatedDisplayRoots=relatedDisplayRows(groups,relatedAvailable,relatedParents).roots;
 const rootRows=relatedParents.size?groups.filter(group=>
  relatedDisplayRoots.get(group.id)?.id===group.id):groups;
 const wholeCards=templateCardGroups(allGroups,cardEvents);
 const cardMembers=new Map(wholeCards.flatMap(rows=>rows.map(group=>[group.id,rows] as const)));
 const normalRows=compact?rootRows.map(group=>[group]):templateCardGroups(rootRows,cardEvents);
 const [paging,setPaging]=useState<{key:string;visible:number}>();
 const visibleCount=paging?.key===scrollKey?paging.visible:scrollPositions.current[scrollKey]?.visible??pageSize;
 const hasGroups=groups.length>0;
 useLayoutEffect(()=>{
  if(hasGroups&&groupList.current)groupList.current.scrollTop=scrollPositions.current[scrollKey]?.top??0;
 },[scrollKey,hasGroups]);
 function showMore(){
  const visible=Math.min(visibleCount+pageSize,normalRows.length);
  scrollPositions.current[scrollKey]={top:groupList.current?.scrollTop??0,visible};
  setPaging({key:scrollKey,visible});
 }
 const useProposalEditor=!fileMode&&annotator;
 const selectionLocked=busy&&!fileMetadataWrite.current&&!fileReviewWrite.current;
 const batchConflict=!fileMode&&selectedGroups.some(group=>conflicted.includes(group.id)||conflicted.includes(group.event_id));
 const batchFixed=selectedGroups.some(group=>group.utterances.some(row=>row.fixed));
 const relatedPage=relatedDisplayRows(normalRows.slice(0,visibleCount).flat(),relatedAvailable,relatedParents);
 const showDetail=!byLineup&&detailGroup&&(compact||!relatedPage.rows.some(group=>group.id===detailGroup.id))&&
  !editor&&!settings&&!proposals&&!importOpen&&!jsonGroup&&!revisionGroup&&!feedback&&!help&&!batchMetadata&&!fileExport;
 function placeRelated(source:string,target:string,first=false,popupKey?:string){
  function attach(previous?:Map<string,string>){
   const parents=new Map(previous);
   for(let ancestor:string|undefined=source;ancestor;ancestor=parents.get(ancestor)){
    if(ancestor===target)return parents;
   }
   if(!first)return parents.set(target,source);
   parents.delete(target);
   return new Map([[target,source],...parents]);
  }
  if(popupKey){
   setBrowsePopup(previous=>previous?.key===popupKey?{...previous,ids:previous.ids.includes(target)?previous.ids:[...previous.ids,target],
    parents:attach(previous.parents)}:previous);
  }else setRelatedPlacement(previous=>({key:scrollKey,parents:attach(previous?.key===scrollKey?previous.parents:undefined)}));
 }
 function prepareRelated(current:TemplateSnapshot,sourceId:string,name:string,newId?:string){
  const source=current.groups.find(group=>group.id===sourceId);
  const origin=current.events.find(event=>event.id===source?.event_id);
  if(!source||!origin)throw new Error('来源模板组已有修改，请重新打开后再试。');
  const pending=fileMode?[]:[...previewsByGroup.values()].flat().filter(row=>
   !row.base&&row.change.value&&(!annotator||row.author===session.username));
  const savedEvent=current.events.find(event=>event.name===name);
  const event=savedEvent??pending.find(row=>row.event?.name===name)?.event??relatedEventDefinition(name);
  const copy=relatedCopy(source,origin.name,event,[...current.groups,...pending.map(row=>row.change.value as TemplateGroup)],newId);
  return {event,savedEvent,copy,proposal:pending.find(row=>row.change.id===copy.group.id)};
 }
 function relatedCopyOptions(group:TemplateGroup,event:TemplateEvent){
  return relatedTargets(event.name).map(name=>{
   try{prepareRelated(snapshot!,group.id,name);return {event:name};}
   catch(error){return {event:name,reason:(error as Error).message};}
  });
 }
 function inlineEventNames(group:TemplateGroup){
  const names=[...cardEvents.values()].map(event=>event.name);
  return keyedTemplateSyntax(group.syntax_version)?[...new Set(names.filter(registeredEvent).concat(fileMode?Object.keys(catalogV04.events):[]))]:names;
 }
 function startCopy(source:TemplateGroup,kind:CopyKind,popupKey?:string){
  const name=canonicalTemplateName(source,cardEvents.get(source.event_id))??source.name;
  setCopyDraft({kind,source,group:{...copyTemplateGroup(source),name},view:lineupViewKey,popupKey});
 }
 function closeCopy(draft:CopyDraft){setCopyDraft(current=>current?.group.id===draft.group.id?undefined:current);}
 function renderCopyDraft(draft:CopyDraft){
  const {group,source,kind,popupKey,target}=draft;
  const origin=cardEvents.get(source.event_id);
  if(!origin)return null;
  const event=target??origin;
  const v04=keyedTemplateSyntax(group.syntax_version);
  const baseline={...group,expression:copyConditionExpression(group,event)};
  const expression=templateDisplayExpression(baseline,scopeName);
  function patchDraft(update:(current:CopyDraft)=>CopyDraft){
   setCopyDraft(current=>current?.group.id===group.id?update(current):current);
  }
  async function chooseEvent(name:string){
   if(name===origin!.name){closeCopy(draft);return;}
   if(name===target?.name)return;
   const next=[...cardEvents.values()].find(row=>row.name===name)??(fileMode?relatedEventDefinition(name):undefined);
   if(!next)throw new Error('目标事件已不存在，请重新选择。');
   const created=startTemplateEventCopy({...copyTemplateGroup(source),id:group.id,utterances:group.utterances},origin!,next);
   patchDraft(current=>({...current,target:next,group:created,error:undefined}));
  }
  async function saveEvent(){
   if(!target||draft.busy)return;
   patchDraft(current=>({...current,busy:true,error:undefined}));
   try{
    if(keyedTemplateSyntax(group.syntax_version)){
     validateKeyedCondition(target.name,group.extra_key??'',expression,group.syntax_version);
     group.utterances.forEach(row=>validateV04Template(target.name,row.text,group.syntax_version));
    }
    await createCopy(source,undefined,source.id,popupKey,{id:group.id,prepare:current=>{
     const existing=current.events.find(row=>row.name===target.name);
     if(!existing&&!fileMode)throw new Error('目标事件已不存在，请重新选择。');
     return {group:{...group,event_id:existing?.id??target.id},event:existing?undefined:target};
    }});
    closeCopy(draft);
   }catch(error){patchDraft(current=>({...current,busy:false,error:(error as Error).message}));}
  }
  async function saveCondition(value:string){
   if(sameCopyCondition(value,expression,v04))return;
   if(keyedTemplateSyntax(group.syntax_version))
    validateKeyedCondition(event.name,group.extra_key??'',value,group.syntax_version);
   const condition=resolveConditionEdit(value,baseline,scopeName,{fileMode,players,lineups});
   const updated:TemplateGroup={...group,...condition,conditions:[],editor_mode:'text',condition_tree:null};
   if(target){patchDraft(current=>({...current,group:updated,error:undefined}));return;}
   await createCopy(source,undefined,source.id,popupKey,{id:group.id,prepare:()=>{
    return {group:{...updated,name:canonicalTemplateName(updated,event)??group.name}};
   }});
  }
  const eventDraft=kind==='event';
  const parameters=target?templateTriggerParameters(group,target).filter(parameter=>canEditTemplateArgument(group,target,parameter)):[];
  const values=fixedArguments(group,event);
  return <article key={group.id} aria-label={eventDraft?'新事件草稿':'新条件草稿'}
   className={'template-group template-copy-draft '+(eventDraft?'':'template-condition-variant')}>
   <header><div>{eventDraft?<div className="template-card-title">
    <TemplateInlineChoice key={target?.id??'source'} label="选择新事件" value={event.name} choices={inlineEventNames(group)} autoStart={!target}
     disabled={draft.busy} onSave={chooseEvent} onCancel={target?undefined:()=>closeCopy(draft)}/><h2>{group.name}</h2>
   </div>:<strong>新条件</strong>}</div></header>
   <div className="template-group-body"><section className="template-read-conditions" aria-label="卡牌与条件">
    {!!parameters.length&&<dl aria-label="新事件参数" className="template-action-parameters">{parameters.map(parameter=>{
     const candidates=parameter.type==='entity'?cards.filter(card=>!parameter.entity_categories?.length||parameter.entity_categories.includes(card.category)):[];
     const choices=parameter.type==='entity'?candidates.map(card=>card.name):(parameter.suggestions??[]).map(valueText);
     return <div key={parameter.key}><dt>{parameterRole(event,parameter)||parameter.key}</dt><dd>
      <TemplateInlineChoice label={'指定参数 '+parameter.key} value={values.get(parameter.key)??'未固定'} choices={choices} firstChoice="未固定"
       disabled={draft.busy} allowText className="template-inline-argument" onSave={async value=>{
        const selected=value==='未固定'?null:value;
        const update=changeTemplateArgument(v04?{...group,expression:undefined}:group,event,parameter,selected,candidates.find(card=>card.name===value)?.id);
        patchDraft(current=>({...current,group:v04?{...update,expression:group.expression}:update,error:undefined}));
       }}/></dd></div>;
    })}</dl>}
    <TemplateConditionPreview expression={expression} allowCopy={false} autoStart={!eventDraft}
     onExit={eventDraft?undefined:()=>closeCopy(draft)} config={{event,catalog:snapshot?.condition_catalog,v04}}
     expressionEdit={eventDraft&&!target||draft.busy?undefined:{value:expression,save:saveCondition}}/>
   </section>{target?<TemplateUtterances utterances={group.utterances} event={event} parameters={event.parameters} v04={v04}
    catalog={snapshot?.condition_catalog} localFile={fileMode} editable disabled={!!draft.busy}
    onSave={async change=>patchDraft(current=>({...current,group:applyUtteranceChange(current.group,change),error:undefined}))}/>:
   <section className="template-read-utterances"><h3>全部话术</h3><ul>
    {group.utterances.map(row=><li key={row.id}>{row.text}</li>)}
   </ul></section>}</div>
   {target&&<footer className="template-copy-actions" data-template-dirty={true}>
    {draft.error&&<span role="alert" className="error">{draft.error}</span>}
    <button type="button" disabled={draft.busy} onClick={()=>closeCopy(draft)}>取消</button>
    <button type="button" className="primary" disabled={draft.busy} onClick={()=>void saveEvent()}>{draft.busy?'保存中…':'保存新事件模板组'}</button>
   </footer>}
  </article>;
 }
 async function createCopy(source:TemplateGroup,name:string|undefined,anchor=source.id,popupKey?:string,
   edit?:{id:string;prepare:(current:TemplateSnapshot)=>{group:TemplateGroup;event?:TemplateEvent}}){
  if(!snapshot||relatedWriting.current){if(edit)throw new Error('模板库正在处理，请稍后重试。');return;}
  relatedWriting.current=true;
  setError('');
  const newId=edit?.id??templateId('group');
  function changesFor(current:TemplateSnapshot){
   if(name===undefined){
    if(!edit||!current.groups.some(group=>group.id===source.id))throw new Error('来源模板组已不存在。');
    const {group,event}=edit.prepare(current);
    const definition=event??current.events.find(row=>row.id===group.event_id);
    const equivalent=definition&&current.groups.find(peer=>peer.event_id===group.event_id&&
     (canonicalTemplateName(peer,definition)??peer.name)===group.name&&peer.syntax_version===group.syntax_version&&
     peer.extra_key===group.extra_key&&templateRangeKey(templateVersionValues(peer.version))===templateRangeKey(templateVersionValues(group.version))&&
     templateRangeKey(templateRangeValues(peer.mode))===templateRangeKey(templateRangeValues(group.mode))&&
     Boolean(peer.ignored)===Boolean(group.ignored)&&peer.publication_hold===group.publication_hold&&
     sameCopyCondition(templateDisplayExpression({...peer,expression:copyConditionExpression(peer,definition)},scopeName),
      templateDisplayExpression({...group,expression:copyConditionExpression(group,definition)},scopeName),keyedTemplateSyntax(group.syntax_version)));
    const value=equivalent?{...group,name:equivalent.name}:group;
    const changes:TemplateChange[]=[...(event?[{kind:'event' as const,action:'put' as const,id:event.id,value:event}]:[]),
     {kind:'group',action:'put',id:newId,value}];
    return {copy:{kind:'new' as const,group:value},changes,proposal:undefined};
   }
   const {event,savedEvent,copy,proposal}=prepareRelated(current,source.id,name,newId);
   const ids=new Set(current.groups.map(group=>group.id));
   const reconcile:TemplateChange[]=proposal?[]:(copy.renamePeers??[]).filter(group=>ids.has(group.id)).map(value=>
    ({kind:'group',action:'put',id:value.id,value}));
   const changes:TemplateChange[]=copy.kind==='existing'?reconcile:[...reconcile,
    ...(savedEvent?[]:[{kind:'event' as const,action:'put' as const,id:event.id,value:event}]),
    {kind:'group',action:'put',id:copy.group.id,value:copy.group,related_copy_source:source.id},
   ];
   return {copy,changes,proposal};
  }
  let targetId=newId;
  let message=name===undefined?'已复制模板组。':'已创建关联模板组。';
  try{
   if(fileMode){
    const destination=openedFile.current;
    const current=destination?.handle===opened?.handle&&destination?documentFor(destination)?.snapshot:undefined;
    if(!current)throw new Error('请先打开模板文件。');
    const {copy,changes}=changesFor(current);
    targetId=copy.group.id;
    if(changes.length){
     const merged=await saveLocal(changes,'edit',destination,true,{});
     const retained=merged.get(targetId);
     if(retained||merged.size){targetId=retained??targetId;message='已合并至事件和条件一致的模板组。';}
    }
    else message='已定位条件和话术一致的模板组。';
   }else{
    await enqueueWrite(async current=>{
     const {copy,changes,proposal}=changesFor(current);
     targetId=copy.group.id;
     if(!changes.length){
      if(proposal)chooseProposal(targetId,proposal.proposal_id);
      message='已定位条件和话术一致的模板组。';
      return current;
     }
     const result=await api<TemplateSnapshot|{proposal:TemplateProposal}>(templatePath(season,'/changes'),'POST',
      {revision:current.revision,changes});
     if('proposal' in result){
      updateProposalPreview(result.proposal);
      chooseProposal(targetId,result.proposal.id);
      message=name===undefined?'模板组副本已提交，待审核。':'关联模板组已提交，待审核。';
     }else{
      const retained=result.merged_groups?.[targetId];
      if(retained||Object.keys(result.merged_groups??{}).length){targetId=retained??targetId;message='已合并至事件和条件一致的模板组。';}
     }
     return result;
    },null,[newId]);
   }
   if(popupKey||!groups.some(group=>group.id===targetId))placeRelated(anchor,targetId,name===undefined,popupKey);
   else if(relatedPage.rows.some(group=>group.id===targetId))setFocusTarget({group:targetId});
   else setDetailId(targetId);
   setNotice(message);
  }catch(error){if(edit)throw error;setError((error as Error).message);}
  finally{relatedWriting.current=false;}
 }
 function groupActions(group:TemplateGroup):ReactNode{
  return <>
   <button type="button" disabled={selectionLocked||!canDeliver(group)} onClick={()=>setFileExport({group})}>导出到文件</button>
   {fileMode&&editable&&<button type="button" disabled={selectionLocked||!canDeliver(group)} onClick={()=>beginImport([group])}>导入此组到数据库</button>}
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
  if(write?.merged_groups)retargetGroups(new Map(Object.entries(write.merged_groups)),
   write.changes.flatMap(change=>change.kind==='group'&&change.action==='put'?[change.value as TemplateGroup]:[]));
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
    const result=await api<TemplateProposal>(path,'POST',target.inline_trigger?{proposal_revision,compact:true,return_write:true}:
     reject?request:{...request,group_editor:{...payload,...(dependency_token?{dependency_token}:{})}});
    if(approve){reconcileApproval(result.formal_write);setFeedbackRevision(value=>value+1);}
    updateProposalPreview(result);
    const saved=result.reviews?.at(-1)?.changes?.find(row=>row.kind==='group');
    const retained=result.formal_write?.merged_groups?.[change.id]??(saved?.action==='put'?saved.id:undefined);
    if(retained&&retained!==change.id){
     chooseProposal(retained,approve?undefined:id);
     setLocatedDetail({id:retained,identity:proposalIdentity});
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
  if(fileMode)return enqueueFileMetadataChanges(changes,false,'edit',{origin:base.id});
  return enqueueWrite(current=>{
   const edits=changes(current.groups,current.events),group=edits.pop()!.value as TemplateGroup;
   const old=current.groups.find(row=>row.id===base.id)!;
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,changes:edits,group_patches:[{id:base.id,fields:groupFields(old,group)}]});
  },null,[base.id]);
 }
 function saveInlineTrigger(bases:TemplateGroup[],update:(group:TemplateGroup,events:TemplateEvent[])=>TemplateGroup,newEvent?:TemplateEvent){
  function patches(groups:TemplateGroup[],events:TemplateEvent[]){
   return bases.map(base=>{
    const latest=groups.find(row=>row.id===base.id);
    if(!latest||['event_id','extra_key','expression','conditions'].some(key=>
     JSON.stringify(latest[key as keyof TemplateGroup])!==JSON.stringify(base[key as keyof TemplateGroup])))
     throw new Error('触发条件已变化，请核对后重试。');
    return update(latest,events);
   });
  }
  const addition:TemplateChange[]=newEvent?[{kind:'event',action:'put',id:newEvent.id,value:newEvent}]:[];
  if(fileMode)return enqueueFileMetadataChanges((groups,events)=>[
   ...addition,...patches(groups,[...events,...(newEvent?[newEvent]:[])]).map(value=>({kind:'group' as const,action:'put' as const,id:value.id,value})),
  ],false,'edit',{});
  return enqueueWrite(current=>{
   const edits=patches(current.groups,current.events).map(value=>({id:value.id,fields:groupFields(current.groups.find(row=>row.id===value.id)!,value)}))
    .filter(({fields})=>Object.keys(fields.set).length||fields.remove.length);
   if(!edits.length)return Promise.resolve(current);
   return api(templatePath(season,'/changes'),'POST',{revision:current.revision,inline_trigger:true,group_patches:edits});
  },useProposalEditor?'触发动作已保存。':null,bases.map(row=>row.id));
 }

 function renderGroup(group:TemplateGroup,popupKey?:string,conditionVariant=false){
  const sourceEvent=snapshot?.events.find(event=>event.id===group.event_id);
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
  const canEditProposal=previewTarget&&!previewTarget.inline_trigger&&
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
  const event=(projected&&active?.event)||cardEvents.get(content.event_id);
  const canonical=projected?undefined:canonicalTemplateName(content,event);
  const displayed={...content,name:canonical??content.name,utterances:content.utterances.map(row=>{
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
    if(fileMode)return enqueueFileMetadataChanges(groups=>{
     const latest=groups.find(candidate=>candidate.id===group.id);
     const current=latest?.utterances.find(utterance=>utterance.id===id);
     if(!latest||!current||!keyedTemplateSyntax(latest.syntax_version)&&current.text!==row.text)
      throw new Error('话术已修改或删除，请重新核对。');
     const updated={...current};
     if(value)updated[field]=true;else delete updated[field];
     return [{kind:'group',action:'put',id:group.id,value:{
      ...latest,utterances:latest.utterances.map(utterance=>utterance.id===id?updated:utterance),
     }}];
    },false,field==='fixed'?'fixed':'edit');
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
  const embeddedEditor=!openedEditor?.proposal;
  const editorForm=openedEditor&&<TemplateEditor key={editorKey} embedded={embeddedEditor} scratch={openedEditor.scratch}
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
   })):undefined}/>;
  const groupEditor=editorForm&&!embeddedEditor?createPortal(editorForm,document.body,editorKey):editorForm;
  return <TemplateGroupCard key={group.id} group={displayed} catalog={snapshot?.condition_catalog} fileMode={fileMode} allowExport={!projected&&!legacyMode} utteranceBindings={ruleChanged?undefined:snapshot?.utterance_bindings?.[group.id]}
   onTrace={fileMode?()=>setTraceGroup(displayed):undefined}
   originalGroup={projected?.newGroup?undefined:original} proposal={projected} proposalControl={rows.length?{
    rows,active,original:showOriginal,temporary:temporaryGroup?.id===group.id,
    disabled:selectionLocked,onChange:value=>chooseProposal(group.id,value),
    submitting:!!active&&approving.has(active.proposal_id),waiting:!!active&&waitingApprovals.has(active.proposal_id),error:actionError,
    rejecting:!!active&&rejecting.has(active.proposal_id),
    onApprove:admin&&previewTarget?()=>{void saveCardProposal(previewTarget,true).catch(()=>{});}:undefined,
    onReject:admin&&previewTarget?()=>{if(confirm(previewTarget.inline_trigger?'驳回整个大组的待审修改？':'驳回当前模板组的待审修改？'))void saveCardProposal(previewTarget,false,undefined,true).catch(()=>{});}:undefined,
    onSaveUtterance:proposalEditable?(change,approve)=>saveProposedUtterance(previewTarget!,change,approve):undefined,
    onInspect:actionError?()=>{setInspectProposal(active.proposal_id);setProposals(true);}:undefined,
   }:undefined}
   commentCounts={fileMode?localCommentCounts(group.id):legacyMode?undefined:commentCounts[group.id]} lastActivity={fileMode||legacyMode?undefined:lastActivity[group.id]}
   onFeedback={!projected&&editable?utteranceId=>setFeedback({group,utteranceId}):undefined}
   savingIgnore={{group:pending.some(change=>!change.utteranceId),rows:[]}}
   entities={ruleChanged||projected?.fields.has('related_entities')?undefined:snapshot?.entity_links?.[group.id]}
   event={event} scopeName={scopeName} conditionVariant={conditionVariant}
   inlineTrigger={canEditGroup&&event?{
    events:inlineEventNames(group),
    saveEvent:async name=>{
     if(name===event.name)return;
     const target=[...cardEvents.values()].find(row=>row.name===name);
     const newEvent=!target&&fileMode?relatedEventDefinition(name):undefined;
     const nextEvent=target??newEvent;
     if(!nextEvent)throw new Error('请选择有效事件');
     const members=cardMembers.get(group.id)??[group];
     await saveInlineTrigger(members,(current,events)=>{
      const before=events.find(row=>row.id===current.event_id);
      if(!before)throw new Error('原事件已不存在');
      return moveTemplateEvent(current,before,nextEvent);
     },newEvent);
    },
    saveArgument:(parameter,value,entityId)=>saveInlineTrigger([group],current=>changeTemplateArgument(current,event,parameter,value,entityId)),
   }:undefined}
   interactionLocked={selectionLocked} annotator={useProposalEditor}
   metadataLocked={selectionLocked}
   onSaveName={canonical?undefined:async name=>{
    const base=proposalEditable?draftGroup!:group;
    if(proposalEditable&&previewTarget){await saveCardProposal(previewTarget,false,latest=>({group:{...latest,name}}));return;}
    await saveGroupEditor(base,{...base,name});
   }}
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
   onExport={()=>setJsonGroup({id:group.id,name:group.name})}
   scopeOptions={{players,lineups,scopeName,localFile:fileMode}}
   onSaveExpression={(value,scope)=>{
    const base=proposalEditable?draftGroup!:group;
    const draft:TemplateGroup=value===(base.expression??'')?{...base,scope}:{...base,scope,editor_mode:'text',expression:value,conditions:[]};
    return proposalEditable&&previewTarget
     ?saveCardProposal(previewTarget,false,latest=>({group:mergeEditorFields(base,latest,draft)}))
     :saveGroupEditor(base,draft);
   }}
   onEdit={()=>openGroupEditor(proposalEditable?draftGroup!:group,proposalEditable?previewTarget:undefined)}
    onCopy={canManage&&canEditGroup?kind=>startCopy(group,kind,popupKey):undefined}
   {...(!projected&&canManage&&canEditGroup&&keyedTemplateSyntax(group.syntax_version)&&sourceEvent&&relatedTargets(sourceEvent.name).length?{
     relatedCopyOptions:()=>relatedCopyOptions(group,sourceEvent),onRelatedCopy:(name:string)=>{void createCopy(group,name,group.id,popupKey);},
   }:{})}
   onDelete={canManage&&!deletingGroups.current.has(group.id)?()=>{if(!proposalEditable){void remove(group);return;}
    if(confirm('确定将「'+displayed.name+'」及其中全部话术设为拟删除？'))saveProposal({delete:true});}:undefined}
   onToggleIgnored={utteranceId=>{
    if(utteranceId){toggleRow(utteranceId,'ignored');return;}
    if(!proposalEditable){void toggleIgnored(group);return;}
    if(previewTarget)void saveCardProposal(previewTarget,false,latest=>({group:{...latest,ignored:!latest.ignored}})).catch(()=>{});
   }}
   onToggleFixed={(fileMode?editable:admin)?utteranceId=>toggleRow(utteranceId,'fixed'):undefined}
   warning={warning} onConfirm={admin&&warning?()=>void confirmWarning(warning):undefined}
   workflow={projected||legacyMode?undefined:groupActions(group)}/>;
 }
 function groupIsIgnored(group:TemplateGroup){
  return pendingIgnores.find(change=>change.groupId===group.id&&!change.utteranceId)?.ignored??!!group.ignored;
 }
 function visibleCardRows(rows:TemplateGroup[],hideIgnored=filters.hideIgnored){
  return (hideIgnored??true)?rows.filter(group=>!groupIsIgnored(group)):rows;
 }
 function renderGroupList(rows:TemplateGroup[],popupKey?:string){
  const families=new Map<string,{title?:string;eventIds:Set<string>;cards:React.ReactNode[]}>();
  for(const members of templateCardGroups(rows,cardEvents)){
   const ordered=[...members].sort((a,b)=>Number(groupIsIgnored(a))-Number(groupIsIgnored(b))||
    templateConditionLength(a,cardEvents.get(a.event_id),scopeName)-
    templateConditionLength(b,cardEvents.get(b.event_id),scopeName));
   const draft=copyDraft?.view===lineupViewKey&&copyDraft.popupKey===popupKey&&members.some(group=>group.id===copyDraft.source.id)?copyDraft:undefined;
   const cards=ordered.map((group,index)=>renderGroup(group,popupKey,index>0));
   const conditionDraft=draft?.kind==='condition'?renderCopyDraft(draft):null;
   if(conditionDraft)cards.push(conditionDraft);
   const card=cards.length===1?cards[0]:<div className="template-card-merged">{cards}</div>;
   const first=members[0];
   const related=popupKey?templateRelatedSection(first,cardEvents.get(first.event_id)):undefined;
   const key=related?.key??first.id;
   const family=families.get(key)??{title:related?.title,eventIds:new Set<string>(),cards:[]};
   family.eventIds.add(first.event_id);
   family.cards.push(<Fragment key={first.id}>{card}{draft?.kind==='event'&&renderCopyDraft(draft)}</Fragment>);
   families.set(key,family);
  }
  return [...families].map(([key,{title,eventIds,cards}])=>eventIds.size>1
   ?<section key={key} className="template-card-related-family" aria-label={title+'关联事件'}>{cards}</section>
   :<Fragment key={key}>{cards}</Fragment>);
 }
 function renderBrowsePopupRows(popup:BrowsePopup){
  const roots=popup.ids.flatMap(id=>{
   const group=relatedAvailable.get(id);
   return group?[group]:[];
  });
  const rows=visibleCardRows(relatedDisplayRows(roots,relatedAvailable,popup.parents).rows,popup.visibility.hideIgnored??true);
  return rows.length?renderGroupList(rows,popup.key):<p className="empty">没有符合筛选的模板组。</p>;
 }
 function renderCards(visible:TemplateGroup[]){
  const clusters=templateCardGroups(visibleCardRows(visible),cardEvents);
  const grouped=new Map(clusters.map(members=>[members[0].id,members]));
  return templateDisplaySections(clusters.map(members=>members[0]),snapshot?.events??[],scopeName).map(({key,title,events})=><section key={key} className="template-card-event" aria-label={title}>
   <h3>{title}</h3>
   {events.map(event=><div key={event.key} className="template-display-event" aria-label={event.title} role="group">
    <h4>{event.title}</h4>
    {renderGroupList(event.rows.flatMap(group=>grouped.get(group.id)??[group]))}
   </div>)}
  </section>);
 }
 const resultsList=<div className="template-group-list" ref={groupList} onScroll={event=>{
  const list=event.currentTarget;
  scrollPositions.current[scrollKey]={top:list.scrollTop,visible:visibleCount};
  if(visibleCount<normalRows.length&&list.scrollHeight-list.scrollTop-list.clientHeight<200)showMore();
 }}>
  {!fileMode&&loading&&!snapshot?<p className="empty" role="status">正在载入模板库…</p>:!groups.length?<div className="empty"><p>{allGroups.length?'没有符合筛选的模板组。':'暂无 '+season+' 模板数据'}</p>{canManage&&snapshot&&!allGroups.length&&<button onClick={create}>新建模板组</button>}</div>:<>
   {compact?<TemplateBoard groups={relatedPage.rows} events={snapshot?.events??[]} selected={selected} onSelectionChange={selectGroups}
    onDetail={id=>{const group=relatedAvailable.get(id);if(group)openBrowsePopup(group.name+' · 模板详情',[id],filters);}}
    byEvent entity={entity} selectionDisabled={selectionLocked} visibility={filters} scopeName={scopeName}/>
    :renderCards(relatedPage.rows)}
   {visibleCount<normalRows.length&&<button type="button" onClick={showMore}>显示更多模板（{visibleCount} / {normalRows.length}）</button>}
  </>}
 </div>;
 return <TemplateLineupName.Provider value={byLineup&&selectedLineup!==unscopedLineup?selectedLineup:undefined}><TemplateMetadataChoices.Provider value={metadataChoices}><TemplateUtteranceVisibility.Provider value={filters}><main className="templates-page">
  {fileMode&&opened&&file&&<FloatingDocumentNote key={fileKeys.get(opened.handle)} title={opened.handle.name}
   value={typeof file.document.note==='string'?file.document.note:''} editable={editable} disabled={busy}
   onDirty={changeDocumentNoteDirty} onSave={saveDocumentNote}/>}
  <div className="template-page-heading"><div><h1>话术模板库</h1>{fileMode&&opened&&<p title={opened.handle.name}>{opened.handle.name}</p>}</div>
   {(!fileMode||opened)&&<div className="template-browse-toolbar">
    <div role="group" aria-label="模板分类方式"><button type="button" aria-pressed={!byLineup&&!byEntity} disabled={selectionLocked} onClick={()=>changeLineupView({active:false},{byEntity:false})}>按事件</button>
     <button type="button" aria-pressed={!byLineup&&byEntity} disabled={selectionLocked} onClick={()=>changeLineupView({active:false},{byEntity:true})}>按实体</button>
     <button type="button" aria-pressed={byLineup} disabled={selectionLocked} onClick={()=>{setDetailId(null);changeLineupView({active:true});}}>按阵容</button></div>
    {!byLineup&&<><div role="group" aria-label="模板显示方式"><button type="button" aria-pressed={!compact} disabled={selectionLocked} onClick={()=>changeView(current=>({...current,compact:false}))}>卡片</button>
     <button type="button" aria-pressed={compact} disabled={selectionLocked} onClick={()=>changeView(current=>({...current,compact:true}))}>看板</button></div>
    <TemplateFilterBar filters={filters} patch={patch} groups={allGroups} players={players} lineups={lineups} disabled={selectionLocked} showMode={gameMode===undefined}/></>}
    {!legacyMode&&<button type="button" disabled={selectionLocked||(!fileMode&&loading)} onClick={()=>{setRelatedPlacement(undefined);if(fileMode)void openFile(true);else{refreshProposals();void load();}}} aria-label={fileMode?'重新读取模板文件':'刷新模板库'}>↻</button>}
    {byLineup&&<TemplateLineupEventFilter events={lineupEventOptions} selected={selectedLineupEvents}
     disabled={selectionLocked} onChange={eventIds=>changeLineupView({eventIds})}/>}
   </div>}
   <fieldset className="template-toolbar" disabled={selectionLocked}>
    <button onClick={()=>setHelp(true)}>帮助</button>
    {!legacyMode&&snapshot&&<button type="button" onClick={()=>setFileExport({})}>导出到文件</button>}
    {fileMode?<>{opened&&<><button onClick={()=>void exportAll()}>导出全库</button><button type="button" disabled={busy} onClick={closeFile}>关闭文件</button><button type="button" disabled={busy} onClick={()=>void chooseDirectory({startIn:opened.directory})}>更换模板文件夹</button></>}<button type="button" disabled={busy} onClick={()=>void chooseDirectory({directory:opened?.directory})}>{opened?'选择其他主库':'选择模板文件夹'}</button>
     {editable&&opened&&<button disabled={!importableSelection.length} onClick={()=>beginImport(importableSelection)}>导入所选到数据库{importableSelection.length>0?'（'+importableSelection.length+'）':''}</button>}
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
  {error&&!importOpen&&!fileChoice&&<div role="alert" className="error template-error">{error}<button onClick={()=>fileMode?opened?void openFile(true):void chooseDirectory():void load()}>重新载入</button></div>}
  {fileMode&&!!file?.groupErrors.length&&<div role="alert" className="error template-error">
   <details open={file.groupErrors.length===1}><summary>有 {file.groupErrors.length} 个模板组未载入</summary>
    <ul>{file.groupErrors.map(({index,message})=><li key={index}>{message}</li>)}</ul>
   </details>
  </div>}
  {previewEnabled&&proposalPreviews?.identity===proposalIdentity&&proposalPreviews.error&&<div role="status" className="template-error">
   提案预览暂不可用：{proposalPreviews.error} <button type="button" onClick={refreshProposals}>重试</button>
  </div>}
  {fileMode&&officialError&&opened&&<p className="muted" role="status">官网卡牌资料读取失败：{officialError}</p>}
  {fileMode&&!opened?<div className="empty"><p>系统窗口只显示文件夹。进入模板文件夹后，点击「选择文件夹」，再从网页列表选主库 JSON。</p>{recentFiles.length>0&&
   <section aria-label="最近载入的模板文件" className="template-recent-files">
    <h2>最近载入</h2><ul>{recentFiles.map(entry=><li key={entry.id}>
     <button type="button" disabled={busy} title={entry.directory?.name} onClick={()=>void openFile(false,false,{recent:entry})}>{entry.handle.name}</button>
     <button type="button" disabled={busy} aria-label={'从 '+entry.handle.name+' 所在文件夹选文件'} onClick={()=>void chooseDirectory({directory:entry.directory,startIn:entry.handle})}>从所在文件夹选文件</button>
    </li>)}</ul>
   </section>}</div>:byLineup?<div className="template-workspace">
   <TemplateLineupSidebar names={lineupNames} tabs={lineupTabs} query={lineupView.query} selected={selectedLineup} player={lineupPlayerTab} counts={lineupSidebarCounts}
    onQuery={query=>changeLineupView({query})} onSelect={(lineup,player)=>changeLineupView({lineup,player})}/>
   <div className="template-lineup-results" ref={lineupScroll} onScrollCapture={event=>{
    const pane=event.target;
    if(pane instanceof HTMLElement&&pane.dataset.lineupScroll){
     scrollPositions.current[lineupScrollKey+':'+pane.dataset.lineupScroll]={top:pane.scrollTop,visible:pane.scrollLeft};
    }
   }}>
    <TemplateLineupBoard name={selectedLineup} players={[...(selectedLineupTabs?.keys()??[])].filter(Boolean).sort((a,b)=>a.localeCompare(b,'zh-CN'))}
     player={lineupPlayerTab} rows={boardRows} filters={lineupView.filters} eventNames={lineupEvents}
     onPlayer={player=>changeLineupView({player})}
     onFilter={update=>changeLineupView({filters:{...lineupView.filters,...update}})}
     onDrill={({kind,key,event})=>{
      const card=kind==='entity'?boardRows.cards.find(row=>row.entity.key===key):undefined;
      const eventName=lineupEvents.get(event??key);
      const ids=kind==='column'?boardRows.columnIds.get(key):kind==='generalHero'?(event?boardRows.generalHeroEvents.get(event):boardRows.generalHeroIds):
       card?(event?card.events.get(event):card.ids):boardRows.other.get(key);
      const columnLabel=({heroes:'英雄',talents:'天赋',equipment:'装备','effect-cards':'效果牌',other:'其他'} as Record<string,string>)[key];
      if(ids?.size)openBrowsePopup((kind==='column'?[selectedLineup,columnLabel]:[kind==='generalHero'?generalHeroLabel:card?.entity.name,eventName]).filter(Boolean).join(' · '),[...ids],lineupView.filters);
     }}/>
   </div>
  </div>:<div className="template-workspace">
   {byEntity?<TemplateEntityList entries={entityEntries} selected={entityKey}
    onSelect={key=>changeView(current=>({...current,entityKey:key}))} disabled={selectionLocked}/>
    :<TemplateEventList events={snapshot?.events??[]} groups={countGroups} selected={filters.event}
     onSelect={event=>patch({event})} disabled={selectionLocked}/>}
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
      {compact&&editable&&selectedGroups.length>0&&<>
       <button type="button" disabled={busy||batchConflict||selectedGroups.every(group=>group.ignored)}
        onClick={()=>void changeSelectedGroups('ignore')}>批量忽略</button>
       {canManage&&<button type="button" className="danger" disabled={busy||batchConflict||batchFixed}
        title={batchFixed?'请先取消所选模板组中的固定话术。':undefined}
        onClick={()=>void changeSelectedGroups('delete')}>批量删除</button>}
      </>}
      {!legacyMode&&<button type="button" disabled={selectionLocked||!groups.length} onClick={()=>setFileExport({scope:'filtered'})}>导出当前筛选</button>}
      {!!selectedGroups.length&&<button type="button" disabled={selectionLocked} onClick={()=>changeView(current=>({...current,selected:new Set()}))}>清除选择（{selectedGroups.length}）</button>}
     </div>
    </div>
    {!compact&&groups.length>0?<ReadingCards cardSearch>{resultsList}</ReadingCards>:resultsList}
   </div>
  </div>}
  {browsePopup&&<TemplateBrowsePopup key={browsePopup.key} title={browsePopup.title} error={error||undefined}
   busy={!!(selectionLocked||revisionGroup||feedback||jsonGroup||fileExport||importOpen||proposals)}
   onClose={()=>setBrowsePopup(undefined)}>
   <TemplateUtteranceVisibility.Provider value={browsePopup.visibility}>
    {renderBrowsePopupRows(browsePopup)}
   </TemplateUtteranceVisibility.Provider>
  </TemplateBrowsePopup>}
  {showDetail&&<section className="template-detail-panel" role="dialog" aria-modal="false" aria-label={detailGroup.name+(temporaryGroup?' · 临时提案卡':' · 模板详情')}>
   <header><strong>{detailGroup.name}</strong><button type="button" aria-label={'关闭'+detailGroup.name+'详情'} onClick={()=>{
    chooseProposal(detailGroup.id,undefined);setDetailId(null);setLocatedDetail(null);
   }}>关闭</button></header>
   <div className="template-form template-detail-body">
    {error&&<p className="error" role="alert">{error}</p>}
    <ReadingCards cardSearch><div className="template-card-stack">{renderGroupList(visibleCardRows(relatedDisplayRows(cardMembers.get(detailGroup.id)??[detailGroup],relatedAvailable,relatedParents).rows))}</div></ReadingCards>
   </div>
  </section>}
  {fileMode&&fileChoice&&<TemplateDialog title="选择模板文件" onClose={()=>{if(!busy){setFileChoice(undefined);setError('');}}}>
   <form className="template-form" onSubmit={event=>{
    event.preventDefault();
    const handle=fileChoice.files.find(item=>item.name===fileChoice.selected);
    if(handle)void openFile(false,false,{selection:{handle,directory:fileChoice.directory}});
   }}>
    <p>模板目录 · {fileChoice.directory.name}</p>
    {fileChoice.files.length?<label>主库文件<select value={fileChoice.selected} disabled={busy}
     onChange={event=>setFileChoice({...fileChoice,selected:event.target.value})}>
     {fileChoice.files.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}
    </select></label>:<p role="status">这个目录没有可选的主库 JSON。请选择生成主库所在的目录。</p>}
    {error&&<p className="error" role="alert">{error}</p>}
    <footer>
     <button type="button" disabled={busy} onClick={()=>void chooseDirectory({startIn:fileChoice.directory})}>更换目录</button>
     <button type="submit" className="primary" disabled={busy||!fileChoice.selected}>打开主库</button>
    </footer>
   </form>
  </TemplateDialog>}
  {fileMode&&opened&&traceGroup&&<TemplateTraceDialog key={traceGroup.id} group={traceGroup} load={readTrace} onClose={()=>setTraceGroup(null)}/>}
  {batchMetadata&&<TemplateBatchMetadata field={batchMetadata} groups={selectedGroups} proposal={useProposalEditor}
   onClose={()=>setBatchMetadata(null)} onSave={values=>saveBatchMetadata(batchMetadata,values)}/>}
  {feedback&&(fileMode?feedback.group&&<LocalTemplateFeedback group={feedback.group} utteranceId={feedback.utteranceId}
   comments={(file?.comments.get(feedback.group.id)??[]).filter(comment=>comment.utterance_id===feedback.utteranceId)}
   onSave={body=>saveFileComment(feedback.group!,feedback.utteranceId,body)} onReload={()=>openFile(true,true)} onClose={()=>setFeedback(null)}/>
   :<TemplateFeedback groups={allGroups} revision={snapshot?.revision} onLocate={(group,utterance)=>{setFeedback(null);setLocatedDetail(null);setDetailId(group);setFocusTarget({group,utterance});}} target={feedback} admin={admin} onClose={()=>setFeedback(null)} onChanged={()=>setFeedbackRevision(n=>n+1)}/>)}
  {help&&<TemplateHelp onClose={()=>setHelp(false)}/>}
  {jsonGroup&&<TemplateJsonExport key={jsonGroup.id} groupId={jsonGroup.id} groupName={jsonGroup.name} file={fileMode?file:undefined} onClose={()=>setJsonGroup(null)}/>}
  {fileExport&&<TemplateFileExport groupName={fileExport.group?.name} counts={{selected:selectedGroups.length,filtered:groups.length}}
   initialScope={fileExport.scope} opened={opened} loadSource={(scope,sameAsOpened)=>exportSource(scope,fileExport.group,sameAsOpened)} onClose={()=>setFileExport(undefined)}
   onBusy={value=>{onBusyChange?.(value);setBusy(value);}}
   onSaved={(handle,raw,sameAsOpened)=>{if(sameAsOpened&&opened)rememberFile({...opened,raw});setFileExport(undefined);setNotice(`已导出到「${handle.name}」。`);}}/>}
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
 </main></TemplateUtteranceVisibility.Provider></TemplateMetadataChoices.Provider></TemplateLineupName.Provider>;
}
