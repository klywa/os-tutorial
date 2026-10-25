import {memo,useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {KnowledgeDocument,Note} from './types';
import {api} from './model';
import {createHistoryDraft,displayValue,reviewFields,type ReviewField} from './noteReviewModel';
import {DiffText,ValueEditor} from './ReviewFields';

type Version={id:string;at:string;origin:string;body_sha256:string};
const HistoryFieldEditor=memo(function HistoryFieldEditor({field,busy,onChange,onValidity}:{field:ReviewField;busy:boolean;onChange:(field:ReviewField,value:unknown)=>void;onValidity:(id:string,valid:boolean)=>void}){
 const [value,setValue]=useState(field.newValue),[epoch,setEpoch]=useState(0),[composing,setComposing]=useState(false);
 function update(value:unknown){setValue(value);onChange(field,value);}
 function choose(value:unknown){update(value);setEpoch(e=>e+1);onValidity(field.id,true);}
 return <section className="history-field"><h3>{field.label}</h3><div className="history-columns"><div><strong>旧版本</strong><pre>{displayValue(field.oldValue)}</pre><button disabled={busy} onClick={()=>choose(field.oldValue)}>使用旧的</button></div><div><strong>合并结果</strong><div className="node-actions"><button disabled={busy} onClick={()=>choose(field.newValue)}>使用新的</button></div>
 {value!==undefined?<ValueEditor key={epoch} disabled={busy} onComposing={setComposing} label={field.label+'：合并结果'} value={value} onValidity={valid=>onValidity(field.id,valid)} onChange={update}/>:<p className="muted">此字段或节点将被删除。</p>}
 <DiffText composing={composing} before={displayValue(field.oldValue)} after={displayValue(value)}/></div></div></section>;
});
export default function ReviewHistory({note,onDirty,onSaved,onClose}:{note:Note;onDirty:(v:boolean)=>void;onSaved:(n:Note)=>void;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),[base]=useState(()=>note);
 const [versions,setVersions]=useState<Version[]>([]),[selected,setSelected]=useState(''),[old,setOld]=useState<KnowledgeDocument|null>(null);
 const [changed,setChanged]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[invalid,setInvalid]=useState<Record<string,boolean>>({});
 const dirty=changed||Object.values(invalid).some(Boolean);
 const draft=useMemo(()=>old?createHistoryDraft(base.document!,old):null,[old,base]);
 const update=useCallback((field:ReviewField,value:unknown)=>{draft?.set(field,value);setChanged(draft?.changed??false);},[draft]);
 const validity=useCallback((id:string,valid:boolean)=>setInvalid(prev=>(prev[id]??false)===!valid?prev:{...prev,[id]:!valid}),[]);
 useEffect(()=>{onDirty(dirty);},[dirty]);
 useEffect(()=>{dialog.current?.showModal();void api<Version[]>('notes/'+encodeURIComponent(base.id)+'/versions').then(setVersions).catch(e=>setError(e.message));},[]);
 const fields=useMemo(()=>old?reviewFields(old,base.document!):[],[old,base]);
 async function select(id:string){if(dirty){setError('修改未保存，请保存或取消');return;}setSelected(id);setOld(null);setError('');setBusy(true);try{const row=await api<{record:{body:KnowledgeDocument}}>('notes/'+encodeURIComponent(base.id)+'/versions/'+id);setOld(row.record.body);setChanged(false);setInvalid({});}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function save(){if(!draft)return;setBusy(true);setError('');try{const document=draft.build();onSaved(await api<Note>('notes/'+encodeURIComponent(base.id),'PUT',{revision:base.revision,document,restore_version:selected}));}catch(e){setError((e as Error).message+'；合并草稿已保留。');}finally{setBusy(false);}}
 function close(){if(dirty||Object.values(invalid).some(Boolean)){setError('修改未保存，请保存或取消');return;}onClose();}
 return <dialog className="review-dialog history-dialog" ref={dialog} onCancel={e=>{e.preventDefault();close();}}>
 <div className="review-toolbar"><h2>历史版本对比</h2><button disabled={busy} onClick={close}>关闭</button></div>
 <label>选择历史版本<select aria-label="选择历史版本" value={selected} disabled={busy} onChange={e=>void select(e.target.value)}><option value="" disabled>请选择</option>{versions.map(v=><option key={v.id} value={v.id}>{new Date(v.at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})} · {({manual:'人工编辑',import:'技能提交',review:'批注修改',baseline:'历史基线',history_merge:'历史合并',save:'保存'} as Record<string,string>)[v.origin]??v.origin} · {v.id.slice(0,6)}</option>)}</select></label>
 {!versions.length&&!error&&<p className="muted">暂无历史版本；下次正文保存时会自动保存当前基线及新版本。</p>}
 {error&&<p className="error" role="alert">{error}</p>}
 {old&&<><p className="muted">左侧为历史内容，右侧为当前合并结果。默认使用当前版本，保存后生成新版本。</p>
 {!fields.length&&<p>该版本与当前正文一致。</p>}
 <div className="history-fields">{fields.map(field=><HistoryFieldEditor key={selected+field.id} field={field} busy={busy} onChange={update} onValidity={validity}/>)}</div></>}
 <div className="review-toolbar history-footer"><span>{dirty?'有未保存修改':'当前正文尚未修改'}</span><button disabled={busy} onClick={()=>{onDirty(false);onClose();}}>取消</button><button className="primary" disabled={busy||!changed||Object.values(invalid).some(Boolean)} onClick={()=>void save()}>{busy?'保存中…':'保存合并结果'}</button></div>
 </dialog>;
}
