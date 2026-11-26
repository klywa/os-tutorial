import {useState,type ReactNode} from 'react';
import {TemplateDialog} from './TemplateEditor';
import {detailFileName,loadTemplateTrace,type LoadedTrace,type TraceNode} from './templateTrace';
import type {TemplateGroup} from './templates';

const stages:Record<string,string>={identify:'知识点识别',split:'分流',enrich:'知识补充',events:'事件框架生成',conditions:'条件生成',phrases:'话术生成',assemble:'汇总'};

function Fold({label,children}:{label:string;children:ReactNode}){
 const [open,setOpen]=useState(false);
 return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>{label}</summary>{open&&children}</details>;
}
function Value({value}:{value:unknown}){
 return <pre>{typeof value==='string'?value:JSON.stringify(value,null,2)??'无'}</pre>;
}
function NodeDetail({id,node,version}:{id:string;node:TraceNode;version:string}){
 const adopted=version===node.selected_version?node:[...node.attempts,...node.revisions].find(item=>item.id===version)!;
 const input=adopted.input;
 return <Fold label={stages[node.stage]??node.stage}>
  <p>{id} · 实际采用版本 {version}</p>
  {input&&typeof input==='object'&&'versions' in input?<Fold label="采用的上游版本"><Value value={input.versions}/></Fold>:null}
  <Fold label="实际输入"><Value value={input}/></Fold>
  <Fold label="采用的输出"><Value value={adopted.output}/></Fold>
  {node.attempts.map(call=><Fold key={call.id} label={'调用 '+call.id+(call.id===version?' · 已采用':'')}>
   <p>{[call.provider,call.model].filter(Boolean).join(' · ')}</p>
   {call.upstream_versions!=null&&<Fold label="调用采用的上游版本"><Value value={call.upstream_versions}/></Fold>}
   <Fold label="本次调用输入"><Value value={call.input}/></Fold>
   {call.prompt!=null&&<Fold label="实际发送的 prompt"><Value value={call.prompt}/></Fold>}
   {call.raw!=null&&<Fold label="原始回复"><Value value={call.raw}/></Fold>}
   {call.parsed!=null&&<Fold label="模型回复解析结果"><Value value={call.parsed}/></Fold>}
   <Fold label="本次调用输出"><Value value={call.output}/></Fold>
   {call.error!=null&&<Fold label="调用错误"><Value value={call.error}/></Fold>}
  </Fold>)}
  {node.revisions.map(revision=><Fold key={revision.id} label={'人工修订 '+revision.id+(revision.id===version?' · 已采用':'')}><Value value={revision}/></Fold>)}
 </Fold>;
}

export default function TemplateTraceDialog({group,loaded,library,onLoad,onClose}:{group:TemplateGroup;loaded?:LoadedTrace;library?:{name:string;raw:string};onLoad:(value:LoadedTrace)=>void;onClose:()=>void}){
 const [id,setId]=useState(group.utterances[0]?.id??''),[error,setError]=useState('');
 const entries=loaded&&Object.hasOwn(loaded.trace.groups,group.id)?loaded.trace.groups[group.id].sentences:undefined;
 const sentence=entries&&Object.hasOwn(entries,id)?entries[id]:undefined,current=group.utterances.find(row=>row.id===id);
 async function attach(file:File){
  try{
   const result=await loadTemplateTrace({name:file.name,getFile:async()=>file},library);
   if(!Object.hasOwn(result.trace.groups,group.id))throw new Error('这个溯源文件没有当前模板组的记录。');
   onLoad(result);setError('');
  }catch(e){setError((e as Error).message);}
 }
 return <TemplateDialog title="话术溯源" wide onClose={onClose}><div className="template-form template-trace">
  <strong>{group.name}</strong>
  <label>选择话术<select value={id} onChange={e=>setId(e.target.value)}>
   {group.utterances.map((row,index)=><option key={row.id} value={row.id}>{index+1}. {row.text}</option>)}
  </select></label>
  {!sentence&&<p>无生成记录</p>}
  {loaded&&<p>{loaded.name} · 运行 {loaded.trace.run_id}</p>}
  {loaded?.modified&&<p>当前主库与生成时的文件内容有差异，以下按组和句 ID 展示生成记录。</p>}
  {sentence&&loaded&&<section key={id} aria-label="句级溯源">
   {sentence.text!==current?.text&&<p>生成时的话术 · {sentence.text}</p>}
   <dl>{Object.entries({'句 ID':id,'知识点':sentence.point_id,'事件':sentence.event_id,'条件':sentence.condition_id,...(sentence.candidate_id?{'候选句':sentence.candidate_id}:{})}).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
   {sentence.node_ids.map(nodeId=><NodeDetail key={nodeId} id={nodeId} node={loaded.trace.nodes[nodeId]} version={sentence.node_versions?.[nodeId]??loaded.trace.nodes[nodeId].selected_version}/>)}
  </section>}
  <label>载入溯源文件{library?' · '+detailFileName(library.name):''}<input type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void attach(file);}}/></label>
  {error&&<p className="error" role="alert">{error}</p>}
 </div></TemplateDialog>;
}
