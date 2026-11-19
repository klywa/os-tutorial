import {useEffect,useRef,useState,type ChangeEvent} from 'react';
import {createPortal} from 'react-dom';
import {api} from './model';
import {DiffText} from './ReviewFields';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import './sectionSync.css';

type Change={kind:'insert'|'update'|'delete';node_id:string;base_node:KnowledgeNode|null;proposed_node:KnowledgeNode|null;evidence_changes?:{evidence:unknown[];inference:boolean}[];blocked_reason?:string};
type Preview={revision:string;items:Change[]};
const labels={insert:'新增',update:'修改',delete:'删除'};
const text=(node:KnowledgeNode|null)=>node?.type==='entry'?(node.show_key?node.key+'：':'')+node.value:'';

export function NoteImport({note,document:body,disabled}:{note:Note;document:KnowledgeDocument;disabled:boolean}){
 const [open,setOpen]=useState(false),[notice,setNotice]=useState('');
 function download(){
  const url=URL.createObjectURL(new Blob([JSON.stringify({body,metadata:{id:note.id}},null,2)+'\n'],{type:'application/json;charset=utf-8'}));
  const link=window.document.createElement('a');
  link.href=url;link.download=note.title.replace(/[<>:"/\\|?*]/g,'_')+'-可导入.json';
  link.click();setTimeout(()=>URL.revokeObjectURL(url),0);
 }
 return <>
  <button disabled={disabled} onClick={download}>下载正文 JSON</button>
  <button disabled={disabled} onClick={()=>{setNotice('');setOpen(true);}}>导入 JSON</button>
  {notice&&<span role="status">{notice}</span>}
  {open&&createPortal(<ImportDialog note={note} onClose={()=>setOpen(false)} onSubmitted={count=>{
   setOpen(false);setNotice('已提交 '+count+' 条待审提案，可在账号区的「提案」查看。');
  }}/>,window.document.body)}
 </>;
}

function ImportDialog({note,onClose,onSubmitted}:{note:Note;onClose:()=>void;onSubmitted:(count:number)=>void}){
 const ref=useRef<HTMLDialogElement>(null);
 const [clientId]=useState(()=>crypto.randomUUID());
 const [upload,setUpload]=useState<{document:unknown;request_id:string}|null>(null);
 const [preview,setPreview]=useState<Preview|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  const dialog=ref.current;
  dialog?.showModal();
  return ()=>dialog?.close();
 },[]);

 async function select(event:ChangeEvent<HTMLInputElement>){
  const file=event.target.files?.[0];
  setUpload(null);setPreview(null);setError('');
  if(!file)return;
  setBusy(true);
  try{
   if(file.size>2_000_000)throw new Error('JSON 文件超过 2 MB');
   setUpload({document:JSON.parse((await file.text()).replace(/^\uFEFF/,'')),request_id:crypto.randomUUID()});
  }catch(err){setError((err as Error).message);}
  finally{setBusy(false);}
 }

 async function send(approve=false){
  if(!upload||busy)return;
  setBusy(true);setError('');
  const payload={note_id:note.id,client_id:clientId,...upload};
  try{
   if(approve&&preview){
    const result=await api<{ids:string[]}>('proposals/note-import/submit','POST',{...payload,revision:preview.revision});
    window.dispatchEvent(new Event('wxq:proposals-changed'));
    onSubmitted(result.ids.length);
   }else{
    setPreview(null);
    setPreview(await api<Preview>('proposals/note-import/preview','POST',payload));
   }
  }catch(err){
   if((err as {status?:number}).status===409)setPreview(null);
   setError((err as Error).message);
  }finally{setBusy(false);}
 }

 return <dialog ref={ref} className="section-sync-editor" aria-label="导入知识笔记 JSON" onCancel={event=>{
  event.preventDefault();if(!busy)onClose();
 }}>
  <header><h2>导入知识笔记 JSON</h2><p>{note.title}</p></header>
  <p>请选择这篇笔记的正文 JSON 或单篇知识提交包。文件中缺少的原段落会生成删除提案。</p>
  <label>选择 JSON 文件<input type="file" accept=".json,application/json" disabled={busy} onChange={event=>void select(event)}/></label>
  {error&&<p className="error" role="alert">{error}</p>}
  {preview&&<section aria-label="导入差异">
   <p role="status">{preview.items.length?preview.items.length+' 条段落变更待提交':'正文和证据均无变化'}</p>
   {preview.items.map(item=>{
    const before=text(item.base_node),after=text(item.proposed_node);
    const node=item.proposed_node??item.base_node;
    const label=node?.type==='entry'&&node.show_key?node.key:(after||before).slice(0,36);
    return <details key={item.node_id}>
     <summary>{before===after&&item.evidence_changes?'证据变更':labels[item.kind]} · {label}</summary>
     {item.blocked_reason&&<p className="error">{item.blocked_reason}</p>}
     {before!==after&&<DiffText before={before} after={after} delay={0}/>}
     {item.evidence_changes&&<pre>{JSON.stringify(item.evidence_changes,null,2)}</pre>}
    </details>;
   })}
  </section>}
  <footer>
   <button disabled={busy} onClick={onClose}>取消</button>
   <button disabled={!upload||busy} onClick={()=>void send()}>预览差异</button>
   <button className="primary" disabled={busy||!preview?.items.length} onClick={()=>void send(true)}>提交提案</button>
  </footer>
 </dialog>;
}
