import {useEffect,useRef,useState} from 'react';
import type {Annotation,Review} from './NoteReview';
import {api} from './model';

export default function ReviewComments({review}:{review:Review}){
 const dialog=useRef<HTMLDialogElement>(null),[text,setText]=useState(''),[editing,setEditing]=useState<Annotation|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{dialog.current?.showModal();},[]);
 const all=review.commentNode==='*';const rows=review.comments.filter(c=>all||c.node_id===review.commentNode);
 function cancel(){setText('');setEditing(null);review.setExtraDirty(false);}
 function close(){if(review.dirty){setError('修改未保存，请保存或取消');return;}review.closeComments();}
 async function action(row:Annotation,action:string){setBusy(true);setError('');try{await api('annotations/'+row.id,'PUT',{revision:row.revision,action});await review.reloadComments();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function save(){setBusy(true);setError('');try{await api(editing?'annotations/'+editing.id:'annotations',editing?'PUT':'POST',editing?{revision:editing.revision,text}:{note_id:review.note.id,node_id:review.commentNode,note_revision:review.note.revision,text});await review.reloadComments();cancel();}catch(e){setError((e as Error).message+'；草稿已保留。');}finally{setBusy(false);}}
 return <dialog className="review-dialog comment-dialog" ref={dialog} onCancel={e=>{e.preventDefault();close();}}>
 <div className="review-toolbar"><h2>{all?'本篇全部批注':'批注'}</h2><button disabled={busy} onClick={close}>关闭</button></div>
 <p className="muted">保存后可让 wanxiangqi-knowledge 处理批注；修改结果会记录在这里。</p>
 {error&&<p className="error" role="alert">{error}</p>}
 {!rows.length&&<p className="muted">暂无批注。</p>}
 {rows.map(row=><article className="annotation-row" key={row.id}><div><strong>{row.status==='open'?'待处理':'已处理'}</strong><time>{new Date(row.created_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}</time></div><p>{row.text}</p>
 {row.anchor_state!=='current'&&<p className="error">{row.anchor_state==='missing'?'原目标已删除':'目标内容已变化'}，请核对后重新批注。</p>}
 <details><summary>创建时的目标内容</summary><pre>{row.target.map(n=>n.type==='heading'?n.title:(n.show_key?n.key+'：':'')+n.value).join('\n\n')}</pre></details>
 {row.result&&<p className="annotation-result">处理记录：{row.result}{row.result_revision&&<small>版本 {row.result_revision}</small>}</p>}
 <div className="node-actions"><button disabled={busy||review.dirty} onClick={()=>{setEditing(row);setText(row.text);}}>编辑批注</button>{row.status==='resolved'&&<button disabled={busy||review.dirty} onClick={()=>void action(row,'reopen')}>重新打开</button>}<button disabled={busy||review.dirty} onClick={()=>{if(confirm('删除这条批注？处理历史仍会保留。'))void action(row,'delete');}}>删除</button></div></article>)}
 {(!all||editing)&&<section className="annotation-form" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null)&&review.dirty)setError('修改未保存，请保存或取消');}}><label>{editing?'编辑批注':'新增批注'}<textarea autoFocus rows={4} value={text} disabled={busy} onChange={e=>{setText(e.target.value);review.setExtraDirty(e.target.value!==(editing?.text??''));}}/></label><div className="node-actions"><button disabled={busy} onClick={cancel}>取消</button><button disabled={busy||!text.trim()} className="primary" onClick={()=>void save()}>保存批注</button></div></section>}
 </dialog>;
}
