import {useEffect,useRef,useState} from 'react';
import {api} from './model';
import {lineupLabel} from './lineupNames';
import {buildSourcePrompt,copyOrFallback,DEFAULT_SOURCE_PROMPT_TEMPLATE,newerBasket,StagingWriteGate} from './sourceTools';
import type {PromptItem} from './sourceTools';
import type {Source,TopicCatalog} from './types';

type Basket={ids:string[];items:{id:string;title:string}[];revision:number;project_key:string};
type Paths={paths:string[];skipped:number;details:{id:string;title:string;reason:string}[];fingerprint:string;revision:number};
type PromptSnapshot={items:PromptItem[];revision:number;fingerprint:string};
type Draft={name:string;text:string;edited:boolean;fingerprint:string;template:string};
type Activity='mutation'|'paths'|'prompt';
const empty:Draft={name:'',text:'',edited:false,fingerprint:'',template:DEFAULT_SOURCE_PROMPT_TEMPLATE};
export default function SourceStaging({selected,sources,catalog,onAdded,onProject}:{selected:string[];sources:Source[];catalog:TopicCatalog;onAdded:(ids:string[])=>void;onProject:(key:string)=>void}){
 const [basket,setBasket]=useState<Basket>({ids:[],items:[],revision:0,project_key:''});
 const [expanded,setExpanded]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[clear,setClear]=useState(false),[prompt,setPrompt]=useState(false),[draft,setDraft]=useState<Draft>(empty),[manualCopy,setManualCopy]=useState('');
 const [template,setTemplate]=useState(DEFAULT_SOURCE_PROMPT_TEMPLATE),[templateDraft,setTemplateDraft]=useState(''),[editingTemplate,setEditingTemplate]=useState(false);
 const [activity,setActivity]=useState({mutation:false,paths:false,prompt:false});
 const [pollError,setPollError]=useState('');
 const active=useRef({...activity}),writes=useRef(new StagingWriteGate());
 const [promptData,setPromptData]=useState<PromptSnapshot|null>(null);
 const snapshotSources=useRef(new Map<string,string>());
 const sourceSignature=(source:Source)=>JSON.stringify([source.title??'',source.transcript_path||source.url,source.notes??'']);
 const sourcesRef=useRef(sources),draftRef=useRef(draft),templateRef=useRef(template);
 sourcesRef.current=sources;draftRef.current=draft;templateRef.current=template;
 const project=useRef('');
 function accept(data:Basket){
  setBasket(old=>newerBasket(old,data));
  if(project.current!==data.project_key){
   project.current=data.project_key;onProject(data.project_key);
   try{setDraft({...empty,...JSON.parse(sessionStorage.getItem('wxq.prompt.'+data.project_key)||'{}')});}catch{setDraft(empty);}
   try{setTemplate(localStorage.getItem('wxq.prompt-template.'+data.project_key)??DEFAULT_SOURCE_PROMPT_TEMPLATE);}catch{setTemplate(DEFAULT_SOURCE_PROMPT_TEMPLATE);}
  }
 }
 useEffect(()=>{
  let alive=true,pending=false;
  const load=()=>{if(pending)return;pending=true;void api<Basket>('sources/staging').then(data=>{if(alive){accept(data);setPollError('');}}).catch(e=>{if(alive)setPollError(e.message);}).finally(()=>{pending=false;});};
  load();const timer=setInterval(load,2000);return()=>{alive=false;clearInterval(timer);};
 },[]);
 useEffect(()=>{if(project.current)try{sessionStorage.setItem('wxq.prompt.'+project.current,JSON.stringify(draft));}catch{setError('浏览器无法保留本次草稿，请及时复制。');}},[draft]);
 async function action(kind:Activity,work:()=>Promise<void>){
  if(active.current[kind])return;
  active.current[kind]=true;setActivity({...active.current});setError('');setMessage('');
  try{await work();}catch(e){setError((e as Error).message);}finally{active.current[kind]=false;setActivity({...active.current});}
 }
 async function mutate(work:()=>Promise<void>){await action('mutation',()=>writes.current.run(work));}
 async function add(){
  const submitted=[...selected];
  await mutate(async()=>{accept(await api<Basket>('sources/staging','POST',{ids:submitted}));onAdded(submitted);setMessage('已追加至暂存，已清除本次提交的勾选。');});
 }
 async function promptSnapshot(){
  const result=await writes.current.read(()=>api<PromptSnapshot>('sources/staging/prompt','POST',{}));
  snapshotSources.current=new Map(sourcesRef.current.map(source=>[source.id,sourceSignature(source)]));setPromptData(result);return result;
 }
 async function copyText(value:string){const fallback=await copyOrFallback(value,text=>navigator.clipboard.writeText(text));if(fallback){setManualCopy(fallback);throw Error('剪贴板不可用，文本已保留，可手动选中复制。');}}
 async function copyPaths(){await action('paths',async()=>{
  const data=await writes.current.read(()=>api<Paths>('sources/staging/paths','POST',{}));
  if(!data.paths.length){setMessage(`暂无可用文字稿，等待或跳过 ${data.skipped} 条。`);return;}
  await copyText(data.paths.join('\n'));setMessage(`已复制 ${data.paths.length} 个文字稿路径，等待或跳过 ${data.skipped} 条。`);
 });}
 async function openPrompt(){
  setPrompt(true);setEditingTemplate(false);
  await action('prompt',async()=>{
   const data=await promptSnapshot();
   setDraft(old=>old.text?old:{...old,text:buildSourcePrompt(old.name,data.items,templateRef.current),template:templateRef.current,fingerprint:data.fingerprint,edited:false});
  });
 }
 async function regenerate(){await action('prompt',async()=>{
  const data=await promptSnapshot();
  setDraft(old=>({...old,text:buildSourcePrompt(old.name,data.items,templateRef.current),template:templateRef.current,fingerprint:data.fingerprint,edited:false}));
  setMessage(`已填入 ${data.items.length} 条内容，无文字稿时使用网页链接。`);
 });}
 function saveTemplate(){
  try{localStorage.setItem('wxq.prompt-template.'+project.current,templateDraft);setTemplate(templateDraft);setEditingTemplate(false);setError('');setMessage('模板已保存，本次草稿保留；重新生成时使用新模板。');}
  catch{setError('模板保存失败，请检查浏览器存储后重试；编辑内容已保留。');}
 }
 const stagedChange=!!promptData&&(basket.revision>promptData.revision||promptData.fingerprint!==draft.fingerprint||promptData.items.some(item=>{const source=sources.find(s=>s.id===item.id);if(!source)return false;const current=sourceSignature(source);return snapshotSources.current.get(item.id)!==current&&JSON.stringify([item.title,item.location,item.notes])!==current;}));
 const available=!!basket.ids.length||activity.mutation;
 return <><div className="staging-toolbar"><strong>暂存 {basket.ids.length}</strong><button disabled={activity.mutation||!selected.length} onClick={()=>void add()}>{activity.mutation?'正在更新暂存…':`加入暂存（${selected.length}）`}</button><button aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'收起暂存':'查看暂存'}</button><button className="primary" disabled={activity.paths||!available} onClick={()=>void copyPaths()}>{activity.paths?'正在准备复制…':'复制文字稿路径'}</button><button disabled={!available} onClick={()=>void openPrompt()}>编辑prompt</button>{!available&&!!selected.length&&<small>先加入暂存，再复制路径或生成prompt</small>}</div>
 {message&&<p className="notice" role="status">{message}</p>}{error&&<p className="error" role="alert">{error}</p>}{pollError&&<p className="error" role="alert">暂存同步失败：{pollError}，正在自动重试。</p>}
 {expanded&&<section className="staging-basket" aria-label="暂存内容"><div className="section-heading"><h2>暂存内容 · {basket.ids.length}</h2><button disabled={activity.mutation||!basket.ids.length} onClick={()=>setClear(true)}>清空暂存</button></div>{clear&&<div className="notice">确认清空全部暂存？文件与外部内容保留。<button onClick={()=>setClear(false)}>取消清空</button><button disabled={activity.mutation} onClick={()=>void mutate(async()=>{accept(await api<Basket>('sources/staging/clear','POST',{revision:basket.revision}));setClear(false);})}>确认清空</button></div>}{basket.items.map(item=><div className="staging-item" key={item.id}><div><strong>{item.title||item.id}</strong><small>{sources.find(s=>s.id===item.id)?.transcript_path?'文字稿可用':'等待文字稿'}</small></div><button aria-label={'移出暂存 '+(item.title||item.id)} disabled={activity.mutation} onClick={()=>void mutate(async()=>accept(await api<Basket>('sources/staging/'+encodeURIComponent(item.id),'DELETE',{})))}>移除</button></div>)}{!basket.ids.length&&<p className="muted">勾选外部内容后加入暂存，可跨多次筛选累加。</p>}</section>}
 {prompt&&<PromptDialog onClose={()=>setPrompt(false)}>
  <div className="section-heading"><h2>{editingTemplate?'编辑通用模板':'编辑prompt'}</h2><button onClick={()=>{if(editingTemplate)setEditingTemplate(false);else{setTemplateDraft(template);setEditingTemplate(true);}}}>{editingTemplate?'返回本次 Prompt':'编辑模板'}</button></div>
  {activity.prompt&&<p className="notice" role="status">{activity.mutation?'正在等待暂存更新，将包含本次加入的内容；可先编辑模板。':'正在核对暂存资料，可先编辑模板。'}</p>}
  {editingTemplate?<>
   <label>通用模板<textarea aria-label="通用模板" rows={14} value={templateDraft} onChange={e=>setTemplateDraft(e.target.value)}/></label>
   <p className="muted">{'{阵容名} 与 {内容列表} 在生成时自动填入。模板按项目保存在当前浏览器，保存后本次草稿保留。'}</p>
   <div className="action-line"><button className="primary" disabled={!templateDraft.trim()||!basket.project_key} onClick={saveTemplate}>保存模板</button><button onClick={()=>setEditingTemplate(false)}>取消</button></div>
  </>:<>
   <label>阵容名<input aria-label="Prompt阵容名" list="prompt-lineups" value={draft.name} onChange={e=>{const name=e.target.value;setDraft(old=>({...old,name,...(!old.edited&&old.text&&promptData&&promptData.fingerprint===old.fingerprint?{text:buildSourcePrompt(name,promptData.items,old.template)}:{})}));}}/></label>
   <datalist id="prompt-lineups">{catalog.topic_lineups.map(r=><option key={r.id} value={lineupLabel(r)}/>)}</datalist>
   {stagedChange&&<p className="notice">暂存、标题、备注或文件状态已变化，已保留编辑内容；请按当前暂存重新生成。</p>}
   <label>完整prompt<textarea aria-label="完整prompt" rows={14} readOnly={activity.prompt} value={draft.text} onChange={e=>setDraft({...draft,text:e.target.value,edited:true})}/></label>
   <p className="muted">本次草稿会保留；仅复制文本，不自动执行知识整理。{promptData?` 共 ${promptData.items.length} 条内容；无文字稿时使用网页链接。`:''}</p>
   {draft.template!==template&&<p className="notice">模板已更新；按当前暂存重新生成后应用。</p>}
   <div className="action-line"><button disabled={activity.prompt} onClick={()=>void regenerate()}>按当前暂存重新生成</button><button className="primary" disabled={activity.prompt||!draft.text.trim()} onClick={()=>void action('prompt',async()=>{const data=await promptSnapshot();const current=draftRef.current;if(data.fingerprint!==current.fingerprint)throw Error('暂存内容或文件状态已变化，请重新生成后复制。');await copyText(current.text);setMessage('prompt已复制。');})}>复制</button><button onClick={()=>setPrompt(false)}>关闭</button></div>
  </>}
  {message&&<p className="notice" role="status">{message}</p>}{error&&<p className="error" role="alert">{error}</p>}
 </PromptDialog>}
 {manualCopy&&<PromptDialog onClose={()=>setManualCopy('')}><h2>手动复制</h2><textarea aria-label="手动复制文本" rows={14} readOnly value={manualCopy}/><button onClick={()=>setManualCopy('')}>关闭</button></PromptDialog>}</>;
}
function PromptDialog({children,onClose}:{children:React.ReactNode;onClose:()=>void}){const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{ref.current?.showModal();},[]);return <dialog ref={ref} className="creator-dialog prompt-dialog" aria-label="编辑整理prompt" onCancel={e=>{e.preventDefault();onClose();}}>{children}</dialog>;}
