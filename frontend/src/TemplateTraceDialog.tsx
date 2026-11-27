import {useEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {TemplateDialog} from './TemplateEditor';
import type {LoadedTrace,TemplateTrace,TraceStage} from './templateTrace';
import type {TemplateGroup} from './templates';

type Point=TemplateTrace['points'][string];
type TraceGroup=TemplateTrace['groups'][string];

function Fields({entries}:{entries:[string,string][]}){
 return <dl>{entries.map(([label,text])=><div key={label}><dt>{label}</dt><dd>{text||'无'}</dd></div>)}</dl>;
}

function Writing({value}:{value:TraceGroup['writing']}){
 return <Fields entries={[
  ['限制',value.limited],['不限制',value.not_limited],['预期',value.expected],['话术写法',value.wording],
 ]}/>;
}

function Events({point,entry,withConditions=false}:{point:Point;entry:TraceGroup;withConditions?:boolean}){
 return <ol className="template-trace-items" aria-label="事件列表">{point.events.map(event=>{
  const conditions=withConditions?point.conditions.filter(condition=>condition.event_id===event.id):[];
  const rejected=withConditions?point.rejected?.filter(item=>item.event_id===event.id):undefined;
  return <li key={event.id} aria-current={event.id===entry.event_id||undefined}>
   <strong>{event.event}</strong>{event.id===entry.event_id&&<span className="muted"> · 当前事件</span>}
   <Fields entries={[["预期",event.expected]]}/>
   {conditions.length>0&&<ol aria-label="条件列表">{conditions.map(condition=><li key={condition.id} aria-current={condition.id===entry.condition_id||undefined}>
    <strong>{condition.expression||'恒真'}</strong>{condition.id===entry.condition_id&&<span className="muted"> · 当前条件</span>}
    {condition.extra_key!==undefined&&<Fields entries={[["额外信息键",condition.extra_key||'空键']]}/>}
    <Fields entries={[["理由",condition.reason]]}/>
    <Writing value={condition}/>
   </li>)}</ol>}
   {rejected?.map((item,index)=><p key={index}>未生成条件 · {item.reason}</p>)}
  </li>;
 })}</ol>;
}

function Stage({title,stage,trace,entry,children}:{title:string;stage:TraceStage;trace:TemplateTrace;entry:TraceGroup;children:ReactNode}){
 const promptId=entry.prompt_ids[stage];
 return <details data-trace-stage={stage} name="template-trace-stage">
  <summary>{title}</summary>
  <div className="template-trace-stage-body">
   {promptId?<details><summary>原始输入提示词</summary><pre>{trace.prompts[promptId]}</pre></details>:
    <p className="muted">此阶段无输入提示词记录。</p>}
   {children}
  </div>
 </details>;
}

function SentenceTrace({loaded,entry,id}:{loaded:LoadedTrace;entry:TraceGroup;id:string}){
 const trace=loaded.trace,point=trace.points[entry.point_id],knowledge=trace.knowledge_lists[entry.knowledge_list_id];
 const props={trace,entry};
 const enriched=<>{point.type&&<Fields entries={[["知识类型",point.type]]}/>}<p>{point.knowledge}</p></>;
 return <section aria-label="句级溯源" className="template-trace-stages">
  <Stage title="知识点列表" stage="identify" {...props}>
   <ol className="template-trace-items">{knowledge.map((item,index)=><li key={index}><Fields entries={[
    ['知识点原句',item.original],['类型',item.type],['前提',item.prerequisite],['相关知识',item.related_knowledge],
   ]}/></li>)}</ol>
  </Stage>
  <Stage title="补充知识" stage="enrich" {...props}>{enriched}</Stage>
  <Stage title="事件框架" stage="events" {...props}>
   {enriched}<Events point={point} entry={entry}/>
  </Stage>
  <Stage title="条件" stage="conditions" {...props}>
   {enriched}<Events point={point} entry={entry} withConditions/>
  </Stage>
  <Stage title="话术生成" stage="phrases" {...props}>
   {enriched}<Events point={point} entry={entry} withConditions/>
   <h4>话术编写要求</h4>
   <Writing value={entry.writing}/>
   <ol className="template-trace-items" aria-label="生成的话术">{Object.entries(entry.sentences).map(([sentenceId,text])=><li key={sentenceId} aria-current={sentenceId===id||undefined}>
    {text}{sentenceId===id&&<span className="muted"> · 当前话术</span>}
   </li>)}</ol>
  </Stage>
 </section>;
}

type TraceLoader=(retry:boolean)=>Promise<LoadedTrace>;
type TraceResult={load:TraceLoader;loaded?:LoadedTrace;error?:string};

export default function TemplateTraceDialog({group,load,onClose}:{group:TemplateGroup;load:TraceLoader;onClose:()=>void}){
 const [id,setId]=useState(group.utterances[0]?.id??'');
 const [result,setResult]=useState<TraceResult>();
 const request=useRef(0);
 function read(retry:boolean){
  const number=++request.current;
  if(retry)setResult(undefined);
  void load(retry).then(loaded=>{
   if(request.current===number)setResult({load,loaded});
  },(error:Error)=>{
   if(request.current===number)setResult({load,error:error.message});
  });
 }
 useEffect(()=>{
  read(false);
  return ()=>{++request.current;};
 },[load]);
 const current=result?.load===load?result:undefined,loaded=current?.loaded;
 const entry=loaded&&Object.hasOwn(loaded.trace.groups,group.id)?loaded.trace.groups[group.id]:undefined;
 const sentence=entry&&Object.hasOwn(entry.sentences,id)?entry.sentences[id]:undefined;
 return createPortal(<TemplateDialog title="话术溯源" wide className="template-trace-dialog" onClose={onClose}><div className="template-form template-trace">
  <strong>{group.name}</strong>
  <label>选择话术<select value={id} onChange={event=>setId(event.target.value)}>
   {group.utterances.map((row,index)=><option key={row.id} value={row.id}>{index+1}. {row.text}</option>)}
  </select></label>
  {!current&&<p role="status">正在读取生成记录…</p>}
  {current?.error&&<div role="alert" className="error"><p>{current.error}</p><button type="button" onClick={()=>read(true)}>重试读取</button></div>}
  {loaded&&<p className="muted">{loaded.name}</p>}
  {loaded?.modified&&<p role="status">当前主库在生成后有修改。以下显示对应话术的原始生成记录。</p>}
  {loaded&&sentence===undefined&&<p>这条话术没有生成记录。</p>}
  {loaded&&entry&&sentence!==undefined&&<SentenceTrace key={id} loaded={loaded} entry={entry} id={id}/>}
 </div></TemplateDialog>,document.body);
}
