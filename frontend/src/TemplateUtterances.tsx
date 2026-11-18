import {useEffect,useRef,useState} from 'react';
import type {ClipboardEvent} from 'react';
import {EntityText} from './EntityCards';
import {placeholderKeys,templateId,type TemplateGroup,type TemplateParameter} from './templates';

type Utterances=TemplateGroup['utterances'];
export type UtteranceChange={kind:'add';row:Utterances[number]}
 |{kind:'edit';id:string;text:string}|{kind:'delete';id:string};

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
type Draft={id:string;text:string;creating:boolean};

export default function TemplateUtterances({utterances,editable,annotator=false,parameters=[],disabled=false,savingIgnoreIds,onSave,onToggleIgnored,onDirty}:{utterances:Utterances;editable:boolean;annotator?:boolean;parameters?:TemplateParameter[];disabled?:boolean;savingIgnoreIds?:string[];onToggleIgnored?:(id:string)=>void;onSave?:(change:UtteranceChange)=>Promise<void>;onDirty?:(dirty:boolean)=>void}){
 const [draft,setDraft]=useState<Draft|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const dirtyRef=useRef(onDirty);dirtyRef.current=onDirty;
 useEffect(()=>()=>dirtyRef.current?.(false),[]);
 const locked=busy||disabled;
 function start(value?:Utterances[number]){setError('');setDraft(value?{...value,creating:false}:{id:templateId('utterance'),text:'',creating:true});onDirty?.(true);}
 function cancel(){setDraft(null);setError('');onDirty?.(false);}
 async function save(){
  if(!draft||!onSave||locked)return;setError('');
  try{
   if(!draft.text.trim())throw new Error('请填写话术内容');
   const unknown=placeholderKeys(draft.text).filter(key=>!parameters.some(p=>p.key===key));
   if(unknown.length)throw new Error('话术引用未知参数：'+unknown.join('、'));
   setBusy(true);await onSave(draft.creating?{kind:'add',row:{id:draft.id,text:draft.text}}:
    {kind:'edit',id:draft.id,text:draft.text});
   setDraft(null);onDirty?.(false);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function remove(id:string){
  if(!onSave||locked||draft||utterances.length<=1||!confirm('确定删除这条话术吗？'))return;
  setBusy(true);setError('');onDirty?.(true);
  try{await onSave({kind:'delete',id});}catch(e){setError((e as Error).message);}finally{setBusy(false);onDirty?.(false);}
 }
 function editor(){return draft&&<form className="template-inline-editor" onSubmit={e=>{e.preventDefault();void save();}}>
  <label>{draft.creating?'新增话术内容':'修改话术内容'}<textarea autoFocus rows={3} value={draft.text} disabled={busy} onChange={e=>setDraft({...draft,text:e.target.value})}/></label>
  {parameters.length>0&&<div className="template-inline-parameters" aria-label="插入话术参数">{parameters.map(p=><button key={p.id} type="button" disabled={busy} onClick={()=>setDraft({...draft,text:draft.text+'{'+p.key+'}'})}>{p.name}</button>)}</div>}
  <div className="template-inline-actions"><button type="button" disabled={busy} onClick={cancel}>取消</button><button className="primary" disabled={busy}>{busy?'保存中…':annotator?'提交话术提案':'保存话术'}</button></div>
 </form>;}
 return <section className="template-read-utterances" aria-label="模板话术"><div className="template-utterance-heading"><h3>全部话术 <small>每条等概率 · 共 {utterances.length} 条</small></h3>{editable&&onSave&&<button disabled={locked||!!draft} onClick={()=>start()}>＋ 新增话术</button>}</div>
  <ul onCopy={copyUtteranceText}>{[...utterances.filter(u=>!u.ignored),...utterances.filter(u=>u.ignored)].map((u,i)=><li key={u.id} className={u.ignored?"template-utterance-ignored":undefined}>{draft?.id===u.id&&!draft.creating?editor():<><div className="template-utterance-text"><EntityText inline>{u.text}</EntityText></div>{u.ignored&&<span className="template-ignored">已忽略</span>}{editable&&onSave&&<div className="template-row-actions"><button aria-label={'编辑话术'+(i+1)} disabled={locked||!!draft||savingIgnoreIds?.includes(u.id)} onClick={()=>start(u)}>编辑</button>{onToggleIgnored&&<button aria-label={(u.ignored?"取消忽略话术":"忽略话术")+(i+1)} disabled={locked||!!draft||savingIgnoreIds?.includes(u.id)} onClick={()=>onToggleIgnored(u.id)}>{savingIgnoreIds?.includes(u.id)?"保存中…":u.ignored?"取消忽略":"忽略"}</button>}<button aria-label={'删除话术'+(i+1)} disabled={locked||!!draft||savingIgnoreIds?.includes(u.id)||utterances.length<=1} title={utterances.length<=1?'每组至少保留一条话术':undefined} onClick={()=>void remove(u.id)}>删除</button></div>}</>}</li>)}</ul>
  {draft?.creating&&editor()}{error&&<p className="template-inline-error" role="alert">{error}</p>}
 </section>;
}
