import {useEffect,useRef,useState} from 'react';
import {EntityText} from './EntityCards';
import {placeholderKeys,templateId,type TemplateGroup,type TemplateParameter} from './templates';

type Utterances=TemplateGroup['utterances'];
type Draft={id:string;text:string;creating:boolean};

export default function TemplateUtterances({utterances,editable,annotator=false,parameters=[],disabled=false,onSave,onDirty}:{utterances:Utterances;editable:boolean;annotator?:boolean;parameters?:TemplateParameter[];disabled?:boolean;onSave?:(utterances:Utterances)=>Promise<void>;onDirty?:(dirty:boolean)=>void}){
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
   const value={id:draft.id,text:draft.text};
   setBusy(true);await onSave(draft.creating?[...utterances,value]:utterances.map(u=>u.id===draft.id?value:u));
   setDraft(null);onDirty?.(false);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function remove(id:string){
  if(!onSave||locked||draft||utterances.length<=1||!confirm('确定删除这条话术吗？'))return;
  setBusy(true);setError('');onDirty?.(true);
  try{await onSave(utterances.filter(u=>u.id!==id));}catch(e){setError((e as Error).message);}finally{setBusy(false);onDirty?.(false);}
 }
 function editor(){return draft&&<form className="template-inline-editor" onSubmit={e=>{e.preventDefault();void save();}}>
  <label>{draft.creating?'新增话术内容':'修改话术内容'}<textarea autoFocus rows={3} value={draft.text} disabled={busy} onChange={e=>setDraft({...draft,text:e.target.value})}/></label>
  {parameters.length>0&&<div className="template-inline-parameters" aria-label="插入话术参数">{parameters.map(p=><button key={p.id} type="button" disabled={busy} onClick={()=>setDraft({...draft,text:draft.text+'{'+p.key+'}'})}>{p.name}</button>)}</div>}
  <div className="template-inline-actions"><button type="button" disabled={busy} onClick={cancel}>取消</button><button className="primary" disabled={busy}>{busy?'保存中…':annotator?'提交话术提案':'保存话术'}</button></div>
 </form>;}
 return <section className="template-read-utterances" aria-label="模板话术"><div className="template-utterance-heading"><h3>全部话术 <small>每条等概率 · 共 {utterances.length} 条</small></h3>{editable&&onSave&&<button disabled={locked||!!draft} onClick={()=>start()}>＋ 新增话术</button>}</div>
  <ul>{utterances.map((u,i)=><li key={u.id}>{draft?.id===u.id&&!draft.creating?editor():<><div className="template-utterance-text"><EntityText>{u.text}</EntityText></div>{editable&&onSave&&<div className="template-row-actions"><button aria-label={'编辑话术'+(i+1)} disabled={locked||!!draft} onClick={()=>start(u)}>编辑</button><button aria-label={'删除话术'+(i+1)} disabled={locked||!!draft||utterances.length<=1} title={utterances.length<=1?'每组至少保留一条话术':undefined} onClick={()=>void remove(u.id)}>删除</button></div>}</>}</li>)}</ul>
  {draft?.creating&&editor()}{error&&<p className="template-inline-error" role="alert">{error}</p>}
 </section>;
}
