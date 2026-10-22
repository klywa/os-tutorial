import {useState} from 'react';
import {api} from './model';
import NoteTitleField from './NoteTitleField';
import type {Note,ReadingDocument} from './types';
export default function BranchEditor({note,document,onSaved,onCancel,onDirty}:{note:Note;document:ReadingDocument;onSaved:(n:Note)=>void;onCancel:()=>void;onDirty:(v:boolean)=>void}){
 const [scope,setScope]=useState<'common'|'branch'>('branch'),[drafts,setDrafts]=useState(document.scope_sections!),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [dirtyScopes,setDirtyScopes]=useState<string[]>([]);
 const [title,setTitle]=useState(note.title);
 const titleChanged=title.trim()!==note.title;
 async function save(){if(!title.trim()){setError('请填写笔记标题');return;}setBusy(true);setError('');try{onSaved(await api<Note>('notes/'+note.id,'PUT',{revision:note.revision,title:title.trim(),scopes:dirtyScopes.map(group=>({scope:group==='common'?'common':document.branch,sections:drafts[group as 'common'|'branch']}))}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <div className="editor"><div className="edit-toolbar"><strong>编辑{document.player_options?.find(p=>p.id===document.player)?.name}打法</strong><button onClick={onCancel}>取消</button><button className="primary" disabled={busy||(!dirtyScopes.length&&!titleChanged)} onClick={()=>void save()}>{busy?'保存中…':'保存修改'}</button></div><NoteTitleField value={title} shared disabled={busy} onChange={value=>{setTitle(value);onDirty(true);}}/><label>编辑范围<select value={scope} onChange={e=>setScope(e.target.value as typeof scope)}><option value="branch">当前棋手专属</option><option value="common">通用打法（影响全部棋手）</option></select></label><p role="status">{scope==='common'?'本范围的修改将同步到所有棋手文件。':'本范围的修改只更新当前棋手分支。'} 成员配置表中用“（空）”表示该阶段不设置成员。</p>{error&&<p className="error">{error}；草稿保留。</p>}{Object.entries(drafts[scope]).map(([name,text])=><section key={name} className="section-edit"><h3>{name}</h3><textarea aria-label={scope+'：'+name} rows={Math.min(18,Math.max(4,text.split('\n').length+1))} value={text} onChange={e=>{setDrafts({...drafts,[scope]:{...drafts[scope],[name]:e.target.value}});setDirtyScopes([...new Set([...dirtyScopes,scope])]);onDirty(true);}}/></section>)}</div>;
}
