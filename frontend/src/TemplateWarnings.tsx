import {useEffect,useState} from 'react';
import {useAuth} from './auth';
import {api} from './model';
import {TemplateDialog} from './TemplateEditor';
import {EntityChip} from './EntityCards';
import {loginWarningItems,semanticChanges,type WarningSnapshot} from './templates';
export default function TemplateWarnings(){
 const {session}=useAuth(),editable=session.role==='admin'||session.role==='annotator';const [state,setState]=useState<WarningSnapshot|null>(null),[open,setOpen]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{if(!editable)return;let alive=true;void api<WarningSnapshot>('templates/warnings').then(data=>{if(alive){setState(data);setOpen(data.unseen&&loginWarningItems(data).length>0);}}).catch(()=>{});return()=>{alive=false;};},[editable,session.username,session.role]);
 async function close(){if(!state)return;setBusy(true);try{await api('templates/warnings/seen','POST',{notification_revision:state.notification_revision});setOpen(false);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 if(!open||!state)return null;
 return <TemplateDialog title="模板关联资料有变化" onClose={()=>{if(!busy)void close();}} wide><div className="template-form"><p>以下模板关联的卡牌资料已变化，请检查条件与话术是否仍适用。关闭汇总不会清除模板上的待检查标识。</p>{loginWarningItems(state).map(item=><section key={item.group_id}><h3>{item.group_name}</h3><div className="template-chips">{item.entities.map(e=><EntityChip key={e.id} ids={[e.id]} label={e.name}/>)}</div>{item.entities.map(e=><details key={e.id}><summary>{e.name}的资料变化</summary><div>{semanticChanges(e.before,e.after).map((change,index)=><dl className="template-warning-change" key={index}><dt>{change.label}</dt><dd>原来：{change.before}</dd><dd>现在：{change.after}</dd></dl>)}</div></details>)}</section>)}{error&&<p role="alert" className="error">{error}</p>}<footer><button className="primary" disabled={busy} onClick={()=>void close()}>{busy?'记录中…':'已知晓，稍后检查'}</button></footer></div></TemplateDialog>;
}
