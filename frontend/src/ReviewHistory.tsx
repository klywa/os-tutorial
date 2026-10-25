import {useEffect,useRef,useState} from 'react';
import type {KnowledgeDocument,Note} from './types';
import {api} from './model';
import {applyReviewField,displayValue,hasReviewChanges,reviewFields,type ReviewField} from './noteReviewModel';
import {DiffText,ValueEditor} from './ReviewFields';

type Version={id:string;at:string;origin:string;body_sha256:string};
function valueAt(body:KnowledgeDocument,field:ReviewField):unknown{
 if(field.collection){const nodes=body[field.collection]??[];if(field.key==='$order')return nodes.map(n=>n.id);const node=nodes.find(n=>n.id===field.nodeId);return field.key==='$node'?node:(node as unknown as Record<string,unknown>|undefined)?.[field.key];}
 return field.path.reduce<unknown>((v,k)=>(v as Record<string,unknown>|undefined)?.[k],body);
}
export default function ReviewHistory({note,onDirty,onSaved,onClose}:{note:Note;onDirty:(v:boolean)=>void;onSaved:(n:Note)=>void;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),[base]=useState(()=>structuredClone(note));
 const [versions,setVersions]=useState<Version[]>([]),[selected,setSelected]=useState(''),[old,setOld]=useState<KnowledgeDocument|null>(null),[draft,setDraft]=useState(()=>structuredClone(base.document!));
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[epochs,setEpochs]=useState<Record<string,number>>({}),[invalid,setInvalid]=useState<Record<string,boolean>>({});
 const dirty=hasReviewChanges(draft,base.document!,invalid);
 useEffect(()=>{onDirty(dirty);},[dirty]);
 useEffect(()=>{dialog.current?.showModal();void api<Version[]>('notes/'+encodeURIComponent(base.id)+'/versions').then(setVersions).catch(e=>setError(e.message));},[]);
 const fields=old?reviewFields(old,base.document!):[];
 function update(next:KnowledgeDocument){setDraft(next);}
 async function select(id:string){if(dirty||Object.values(invalid).some(Boolean)){setError('修改未保存，请保存或取消');return;}setSelected(id);setOld(null);setError('');setBusy(true);try{const row=await api<{record:{body:KnowledgeDocument}}>('notes/'+encodeURIComponent(base.id)+'/versions/'+id);setOld(row.record.body);setDraft(structuredClone(base.document!));setEpochs({});setInvalid({});}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 function choose(field:ReviewField,value:unknown,reference:KnowledgeDocument){update(applyReviewField(draft,field,value,reference));setEpochs({...epochs,[field.id]:(epochs[field.id]??0)+1});setInvalid({...invalid,[field.id]:false});}
 async function save(){setBusy(true);setError('');try{onSaved(await api<Note>('notes/'+encodeURIComponent(base.id),'PUT',{revision:base.revision,document:draft,restore_version:selected}));}catch(e){setError((e as Error).message+'；合并草稿已保留。');}finally{setBusy(false);}}
 function close(){if(dirty||Object.values(invalid).some(Boolean)){setError('修改未保存，请保存或取消');return;}onClose();}
 return <dialog className="review-dialog history-dialog" ref={dialog} onCancel={e=>{e.preventDefault();close();}}>
 <div className="review-toolbar"><h2>历史版本对比</h2><button disabled={busy} onClick={close}>关闭</button></div>
 <label>选择历史版本<select aria-label="选择历史版本" value={selected} disabled={busy} onChange={e=>void select(e.target.value)}><option value="" disabled>请选择</option>{versions.map(v=><option key={v.id} value={v.id}>{new Date(v.at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})} · {({manual:'人工编辑',import:'技能提交',review:'批注修改',baseline:'历史基线',history_merge:'历史合并',save:'保存'} as Record<string,string>)[v.origin]??v.origin} · {v.id.slice(0,6)}</option>)}</select></label>
 {!versions.length&&!error&&<p className="muted">暂无历史版本；下次正文保存时会自动保存当前基线及新版本。</p>}
 {error&&<p className="error" role="alert">{error}</p>}
 {old&&<><p className="muted">左侧为历史内容，右侧为当前合并结果。默认使用当前版本，保存后生成新版本。</p>
 {!fields.length&&<p>该版本与当前正文一致。</p>}
 <div className="history-fields">{fields.map(field=>{const value=valueAt(draft,field);return <section className="history-field" key={field.id}><h3>{field.label}</h3><div className="history-columns"><div><strong>旧版本</strong><pre>{displayValue(field.oldValue)}</pre><button disabled={busy} onClick={()=>choose(field,field.oldValue,old)}>使用旧的</button></div><div><strong>合并结果</strong><div className="node-actions"><button disabled={busy} onClick={()=>choose(field,field.newValue,base.document!)}>使用新的</button></div>{value!==undefined?<ValueEditor disabled={busy} key={field.id+(epochs[field.id]??0)} label={field.label+'：合并结果'} value={value} onValidity={valid=>{setInvalid(prev=>({...prev,[field.id]:!valid}));}} onChange={v=>update(applyReviewField(draft,field,v,old))}/>:<p className="muted">此字段或节点将被删除。</p>}<DiffText before={displayValue(field.oldValue)} after={displayValue(value)}/></div></div></section>;})}</div></>}
 <div className="review-toolbar history-footer"><span>{dirty?'有未保存修改':'当前正文尚未修改'}</span><button disabled={busy} onClick={()=>{setDraft(structuredClone(base.document!));onDirty(false);onClose();}}>取消</button><button className="primary" disabled={busy||!dirty||Object.values(invalid).some(Boolean)} onClick={()=>void save()}>{busy?'保存中…':'保存合并结果'}</button></div>
 </dialog>;
}
