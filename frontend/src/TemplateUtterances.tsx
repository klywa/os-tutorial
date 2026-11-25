import {createContext,useContext,useRef,useState} from 'react';
import type {ClipboardEvent} from 'react';
import {EntityText} from './EntityCards';
import ConditionTextEditor from './ConditionTextEditor';
import {placeholderKeys,renderUtterance,templateId,visibleTemplateUtterances,type TemplateEvent,type TemplateGroup,type TemplateParameter,type UtteranceBindings,type UtteranceVisibility} from './templates';
import {slotToken,validateV04Template} from './templateV04';
import {invalidDirectPaths,TemplateUtteranceSlots} from './TemplateUtteranceSlots';
import type {ConditionCatalog} from './templateRules';

type Utterances=TemplateGroup['utterances'];
export const TemplateUtteranceVisibility=createContext<UtteranceVisibility>({hideIgnored:false});
export type UtteranceChange={kind:'add';row:Utterances[number]}
 |{kind:'edit';id:string;text:string;baseText?:string}|{kind:'delete';id:string;baseText?:string};

export function applyUtteranceChange(group:TemplateGroup,change:UtteranceChange):TemplateGroup{
 const rows=group.utterances;
 if(change.kind==='add')return {...group,utterances:[...rows,change.row]};
 const row=rows.find(row=>row.id===change.id);
 if(!row)throw new Error('话术已不存在，请重新核对。');
 if(change.baseText!==undefined&&row.text!==change.baseText)throw new Error('这条话术已有新修改。草稿已保留，请核对后重试。');
 if(change.kind==='delete'&&row.fixed)throw new Error('请先取消固定。');
 if(change.kind==='edit'&&row.text===change.text)return group;
 if(change.kind==='delete'&&rows.length<=1)throw new Error('每组至少保留一条话术');
 return {...group,utterances:change.kind==='delete'?rows.filter(row=>row.id!==change.id):
  rows.map(item=>item.id===change.id?{...item,text:change.text}:item)};
}

function copyUtteranceText(event:ClipboardEvent<HTMLUListElement>){
 const list=event.currentTarget;
 if(event.target instanceof HTMLTextAreaElement)return;
 const selection=list.ownerDocument.getSelection();
 if(!selection?.rangeCount||selection.isCollapsed)return;
 const selected=selection.getRangeAt(0);
 const parts:string[]=[];
 for(const utterance of list.querySelectorAll('.template-utterance-text')){
  if(!selected.intersectsNode(utterance))continue;
  const range=list.ownerDocument.createRange();
  range.selectNodeContents(utterance);
  if(utterance.contains(selected.startContainer))range.setStart(selected.startContainer,selected.startOffset);
  if(utterance.contains(selected.endContainer))range.setEnd(selected.endContainer,selected.endOffset);
  const text=range.toString().replace(/\r\n?|\n/g,'');
  if(text)parts.push(text);
 }
 if(!parts.length)return;
 event.clipboardData.setData('text/plain',parts.join(' '));
 event.preventDefault();
}
type Draft={id:string;text:string;creating:boolean;baseText?:string};
type UtteranceProposal={fields:Set<string>;removed:string[];all:boolean};
export type UtteranceDraftStore={drafts:Record<string,Draft>;saving:Set<string>;errors:Record<string,string>};
export const createUtteranceDraftStore=():UtteranceDraftStore=>({drafts:{},saving:new Set(),errors:{}});
export type UtteranceFlagFeedback={pending?:boolean;confirmed?:boolean;error?:string;retry?:()=>void};

export function UtteranceLength({text}:{text:string}){
 return <small className="template-utterance-length" title="按当前显示的文本计数，包含标点符号">{Array.from(text).length} 字</small>;
}

type Props={commentCounts?:Record<string,number>;onFeedback?:(id:string)=>void;utterances:Utterances;editable:boolean;event?:TemplateEvent;catalog?:ConditionCatalog;localFile?:boolean;v04?:boolean;
 annotator?:boolean;parameters?:TemplateParameter[];bindings?:UtteranceBindings;disabled?:boolean;savingIgnoreIds?:string[];
 onToggleIgnored?:(id:string)=>void;onToggleFixed?:(id:string)=>void;onSave?:(change:UtteranceChange)=>Promise<void>;
 proposal?:UtteranceProposal;onSaveAndApprove?:(change:UtteranceChange)=>Promise<void>;proposalEditing?:boolean;
 draftStore?:UtteranceDraftStore;onDraftsChanged?:()=>void;flagFeedback?:(id:string,field:'ignored'|'fixed')=>UtteranceFlagFeedback|undefined};
export default function TemplateUtterances({commentCounts,onFeedback,utterances,editable,annotator,parameters=[],bindings,disabled,event,catalog,localFile,v04=false,
 savingIgnoreIds,onSave,onToggleIgnored,onToggleFixed,proposal,onSaveAndApprove,proposalEditing,draftStore,onDraftsChanged,flagFeedback}:Props){
 const [local]=useState(createUtteranceDraftStore),[,redraw]=useState(0);
 const [copyFeedback,setCopyFeedback]=useState<{id:string;failed:boolean}>();
 const inputs=useRef(new Map<string,HTMLTextAreaElement>());
 const state=draftStore??local;
 const update=()=>redraw(value=>value+1);
 const liveCount=utterances.filter(row=>!proposal?.removed.includes(row.id)).length;
 const shown=visibleTemplateUtterances(utterances,useContext(TemplateUtteranceVisibility));
 const shownCount=shown.filter(row=>!proposal?.removed.includes(row.id)).length;
 function displayRank(row:Utterances[number]){
  if(row.fixed)return 0;
  const ignore=flagFeedback?.(row.id,'ignored');
  return (ignore?.pending?ignore.confirmed:row.ignored)?2:1;
 }
 function start(value?:Utterances[number]){
  const id=value?.id??templateId('utterance');
  delete state.errors[id];
  state.drafts[id]=value?{...value,creating:false,baseText:value.text}:{id,text:'',creating:true};
  update();
 }
 function cancel(id:string){delete state.drafts[id];delete state.errors[id];update();onDraftsChanged?.();}
 async function commit(id:string,change:UtteranceChange,approve=false){
  if(!onSave||disabled||state.saving.has(id))return;
  state.saving.add(id);delete state.errors[id];update();
  try{
   if(change.kind!=='delete'){
    const text=change.kind==='add'?change.row.text:change.text;
    if(!text.trim())throw new Error('请填写话术内容');
    if(v04&&event)validateV04Template(event.name,text);
    const unknown=(v04?[]:placeholderKeys(text)).filter(key=>!parameters.some(p=>p.key===key));
    if(unknown.length)throw new Error('话术引用未知参数：'+unknown.join('、'));
    if(localFile&&!v04){
     const invalid=invalidDirectPaths(text,event,catalog);
     if(invalid.length)throw new Error('话术引用需要可用的单值路径：'+invalid.join('、'));
    }
   }
   await (approve&&onSaveAndApprove?onSaveAndApprove:onSave)(change);
   cancel(id);
  }catch(error){state.errors[id]=(error as Error).message;}finally{state.saving.delete(id);update();}
 }
 function remove(id:string){
  if(liveCount>1&&confirm('确定删除这条话术吗？'))void commit(id,{kind:'delete',id,baseText:utterances.find(row=>row.id===id)?.text});
 }
 async function copy(id:string,text:string){
  try{
   await navigator.clipboard.writeText(text);
   setCopyFeedback({id,failed:false});
  }catch{
   setCopyFeedback({id,failed:true});
  }
 }
 function editor(draft:Draft){
  const {id,text,creating}=draft,busy=state.saving.has(id);
  function setText(text:string){state.drafts[id]={...draft,text};update();}
  function insert(path:string){
   const input=inputs.current.get(id),token=slotToken(path,v04);
   const start=input?.selectionStart??text.length,end=input?.selectionEnd??start;
   setText(text.slice(0,start)+token+text.slice(end));
   requestAnimationFrame(()=>{input?.focus();input?.setSelectionRange(start+token.length,start+token.length);});
  }
  return <form key={id} className="template-inline-editor" data-template-dirty={text!==(draft.baseText??'')||busy?true:undefined} onSubmit={e=>{
   e.preventDefault();void commit(id,creating?{kind:'add',row:{id,text}}:{kind:'edit',id,text,baseText:draft.baseText},
    (e.nativeEvent as SubmitEvent).submitter?.getAttribute('value')==='approve');
  }}>
   {draft.baseText!==undefined&&<p className="template-utterance-original">
    <span>原话术</span><span>{draft.baseText}</span>
   </p>}
   <div><span>{creating?'新增话术内容':'修改话术内容'}</span><ConditionTextEditor slots label={creating?'新增话术内容':'修改话术内容'}
    config={{event,catalog,v04}} textareaRef={node=>{if(node)inputs.current.set(id,node);else inputs.current.delete(id);}}
    autoFocus rows={3} value={text} disabled={busy} onChange={setText}/></div>
   <UtteranceLength text={text}/>
   <div className="template-inline-parameters" aria-label="插入话术参数">
    {!v04&&parameters.map(p=><button key={p.id} type="button" disabled={busy} onClick={()=>insert(p.key)}>{p.name}</button>)}
    <TemplateUtteranceSlots event={event} catalog={catalog} v04={v04} disabled={busy} onInsert={insert}/>
   </div>
   <div className="template-inline-actions"><button type="button" disabled={busy} onClick={()=>cancel(id)}>取消</button><button className="primary" disabled={busy}>{busy?'保存中…':proposalEditing?'保存提案':annotator?'提交话术提案':'保存话术'}</button>{onSaveAndApprove&&<button type="submit" value="approve" className="primary" disabled={busy}>保存并采纳本组</button>}</div>
   {state.errors[id]&&<small role="alert" className="template-inline-error">{state.errors[id]}</small>}
  </form>;
 }
 return <section className="template-read-utterances" aria-label="模板话术">
  <div className="template-utterance-heading"><h3>{shownCount===liveCount?'全部话术':'筛选后话术'} <small>{shownCount===liveCount?'每条等概率 · 共 '+liveCount+' 条':'显示 '+shownCount+' / '+liveCount+' 条'}</small></h3>{editable&&onSave&&<button disabled={disabled} onClick={()=>start()}>＋ 新增话术</button>}</div>
  {!shown.length&&<p className="muted">没有符合筛选的话术。</p>}
  <ul onCopy={copyUtteranceText}>{shown.sort((a,b)=>displayRank(a)-displayRank(b)).map((row,index)=>{
   const {id,ignored,fixed}=row,text=renderUtterance(row.text,bindings);
   const removed=proposal?.removed.includes(id),changed=proposal?.all||proposal?.fields.has('utterance:'+id);
   const content=<EntityText inline>{text}</EntityText>,draft=state.drafts[id],busy=state.saving.has(id);
   const ignore=flagFeedback?.(id,'ignored'),pin=flagFeedback?.(id,'fixed');
   const rowClass=[fixed&&'template-utterance-fixed',ignored&&'template-utterance-ignored'].filter(Boolean).join(' ');
   return <li key={id} tabIndex={-1} data-feedback-utterance={id} data-proposal-change={changed||undefined} className={rowClass||undefined}>
    {draft?editor(draft):<>
     <div className="template-utterance-text">{removed?<s>{content}</s>:content}</div>{removed&&<span className="template-proposal-mark">拟删除</span>}
     <UtteranceLength text={text}/>{ignored&&<span className="template-ignored">已忽略</span>}{fixed&&<span className="template-fixed">已固定</span>}
     {editable&&onSave&&!removed&&<div className="template-row-actions">
      {onFeedback&&<button aria-label={'批注话术'+(index+1)} disabled={disabled} onClick={()=>onFeedback(id)}>批注 <span className="template-comment-count">{commentCounts?.[id]??0}</span></button>}
      <button aria-label={'编辑话术'+(index+1)} disabled={disabled||busy} onClick={()=>start(row)}>编辑</button>
      {onToggleFixed&&<button type="button" aria-label={(fixed?'取消固定话术':'固定话术')+(index+1)} aria-pressed={!!fixed} disabled={disabled||busy||(!fixed&&!!ignored)||!!ignore?.pending} title={!fixed&&ignored?'请先取消忽略':undefined} aria-busy={pin?.pending||undefined} onClick={()=>onToggleFixed(id)}>{fixed?'取消固定':'固定'}{pin?.pending&&'…'}</button>}
      <button type="button" aria-label={'复制话术'+(index+1)} onClick={()=>void copy(id,text)}>复制</button>
      {onToggleIgnored&&<button type="button" className="template-utterance-ignore" aria-label={(ignored?'取消忽略话术':'忽略话术')+(index+1)} disabled={disabled||busy||(!ignored&&!!fixed)||!!pin?.pending} title={!ignored&&fixed?'请先取消固定':undefined} aria-busy={ignore?.pending||undefined} onClick={()=>onToggleIgnored(id)}>{ignored?'取消忽略':'忽略'}{(ignore?.pending||savingIgnoreIds?.includes(id))&&'…'}</button>}
      <button aria-label={'删除话术'+(index+1)} disabled={disabled||busy||!!fixed||liveCount<=1} title={fixed?'先取消固定再删除':liveCount<=1?'每组至少保留一条话术':undefined} onClick={()=>remove(id)}>{busy?'删除中…':'删除'}</button>
     </div>}
     {copyFeedback?.id===id&&<small role="status" className={copyFeedback.failed?'template-inline-error':undefined}>
      {copyFeedback.failed?'复制失败，请检查剪贴板权限':'已复制'}
     </small>}
     {state.errors[id]&&<small className="template-inline-error" role="alert">{state.errors[id]}</small>}
     {[ignore,pin].map((feedback,i)=>feedback?.error&&<small key={i} className="template-inline-error" role="alert">{feedback.error} <button type="button" onClick={feedback.retry}>重试</button></small>)}
    </>}
   </li>;
  })}</ul>
  {Object.values(state.drafts).filter(draft=>!utterances.some(row=>row.id===draft.id)).map(editor)}
 </section>;
}
