import {useState} from 'react';
import type {KnowledgeDocument,KnowledgeNode,Note} from './types';
import {api} from './model';
import JsonReading from './JsonReading';
import KnowledgeFactsEditor from './KnowledgeFactsEditor';
import {moveNode,removeNode} from './jsonDocument';

type Props={note:Note;onSaved:(note:Note)=>void;onCancel:()=>void;onDirty:(dirty:boolean)=>void};
export default function StructuredEditor({note,onSaved,onCancel,onDirty}:Props){
 const [body,setBody]=useState<KnowledgeDocument>(()=>structuredClone(note.document!));
 const [preview,setPreview]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 function change(nodes:KnowledgeNode[]){setBody({...body,nodes});onDirty(true);}
 function update(index:number,patch:Partial<KnowledgeNode>){change(body.nodes.map((n,i)=>i===index?{...n,...patch} as KnowledgeNode:n));}
 function move(index:number,offset:number){change(moveNode(body.nodes,index,offset));}
 function add(type:'heading'|'entry',after=body.nodes.length-1){
  const node:KnowledgeNode=type==='heading'?{id:crypto.randomUUID(),type,level:2,title:'新章节',separator:'\n\n'}:{id:crypto.randomUUID(),type,key:'正文',show_key:false,value:'',separator:'\n\n'};
  const nodes=[...body.nodes];nodes.splice(after+1,0,node);change(nodes);
 }
 async function save(){setBusy(true);setError('');try{onSaved(await api<Note>('notes/'+encodeURIComponent(note.id),'PUT',{revision:note.revision,document:body}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <div className="structured-editor"><div className="edit-toolbar"><strong>编辑知识条目</strong><button disabled={busy} onClick={()=>setPreview(!preview)}>{preview?'继续编辑':'预览'}</button><button disabled={busy} onClick={onCancel}>取消</button><button disabled={busy} className="primary" onClick={()=>void save()}>{busy?'保存中…':'保存修改'}</button></div>
  {error&&<div className="error" role="alert">{error}<p>草稿仍保留在编辑器中。</p></div>}
  {preview?<JsonReading body={body} nodes={body.nodes} note={note} onNote={()=>{}}/>:<fieldset disabled={busy} className="node-fields">{body.nodes.map((n,i)=><div key={n.id} className="node-editor">
   {n.type==='heading'?<><label>标题层级<select aria-label="标题层级" disabled={n.level===1} value={n.level} onChange={e=>update(i,{level:Number(e.target.value)})}>{[1,2,3,4,5,6].map(level=><option key={level} value={level}>{level}级标题</option>)}</select></label><label>章节标题<input aria-label="章节标题" readOnly={n.level===1} value={n.title} onChange={e=>update(i,{title:e.target.value})}/></label></>:<><label>key<input aria-label="条目key" readOnly={!n.show_key} value={n.key} onChange={e=>update(i,{key:e.target.value})}/></label><label className="inline"><input type="checkbox" checked={n.show_key} onChange={e=>update(i,{show_key:e.target.checked,key:e.target.checked?n.key:'正文'})}/>显示key</label><label>内容<textarea aria-label="条目内容" rows={Math.max(3,Math.min(12,Math.ceil(n.value.length/65)))} value={n.value} onChange={e=>update(i,{value:e.target.value})}/></label></>}
   {!(n.type==='heading'&&n.level===1)&&<div className="node-actions"><button type="button" disabled={moveNode(body.nodes,i,-1)===body.nodes} onClick={()=>move(i,-1)}>上移</button><button type="button" disabled={moveNode(body.nodes,i,1)===body.nodes} onClick={()=>move(i,1)}>下移</button><button type="button" onClick={()=>change(removeNode(body.nodes,i))}>{n.type==='heading'?'删除章节及内容':'删除条目'}</button><button type="button" onClick={()=>add('entry',i)}>后插条目</button><button type="button" onClick={()=>add('heading',i)}>后插章节</button></div>}
  </div>)}<div className="action-line"><button type="button" onClick={()=>add('heading')}>添加章节</button><button type="button" onClick={()=>add('entry')}>添加条目</button></div>
  {body.semantics&&Object.keys(body.semantics).length>0&&<KnowledgeFactsEditor name="阵容结构与适用条件" value={body.semantics} onChange={value=>{setBody({...body,semantics:value as Record<string,unknown>});onDirty(true);}}/>}</fieldset>}
 </div>;
}
