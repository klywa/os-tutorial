import {useEffect,useRef,useState} from 'react';
import TemplateSettings from './TemplateSettings';

import {api} from './model';
import {TemplateDialog} from './TemplateEditor';
import {newestProposalFirst,proposalCardPreview,proposalLocationChanges} from './templateProposalPreview';
import {describeTemplateRecord,groupDiffKeys,templateMetadataLabels,templateReviewLabel,operators,readableValue,selectedGroupChange,valueText,type TemplateChange,type TemplateEvent,type TemplateGroup,type TemplateProposal,type TemplateSnapshot} from './templates';
const statuses:Record<string,string>={pending:'待审核',approved:'已采纳',partially_approved:'部分采纳',rejected:'已拒绝',withdrawn:'已撤回'};
function changeFields(proposal:TemplateProposal,change:TemplateChange){
 if(proposal.source==='review-status'&&change.kind==='group')return ['review_status'];
 if(change.kind==='group'&&change.action==='put'){
  const base=proposal.base.groups.find(g=>g.id===change.id);
  if(base){
   const fields=groupDiffKeys(base,change.value as TemplateGroup);
   if(Object.hasOwn(proposal.group_review_overrides??{},change.id))fields.push('review_status');
   if(fields.length)return fields;
  }
 }
 return ['record'];
}
function describeValue(value:unknown):string{return readableValue(value);}
function FieldDiff({proposal,change,field,scopeName}:{proposal:TemplateProposal;change:TemplateChange;field:string;scopeName:(id:string|null)=>string}){
 const base=(change.kind==='group'?proposal.base.groups:proposal.base.events).find(v=>v.id===change.id) as unknown as Record<string,unknown>|undefined,next=change.value as unknown as Record<string,unknown>|undefined;
 const [kind,id]=field.split(':');const get=(record:Record<string,unknown>|undefined)=>id?((record?.[kind==='condition'?'conditions':'utterances']??[]) as {id:string}[]).find(v=>v.id===id):field==='record'?record:record?.[field];
 const event=proposal.base.events.find(e=>e.id===next?.event_id||e.id===base?.event_id);
 const describe=(record:Record<string,unknown>|undefined)=>{const value=get(record);if(field==='explanation')return String(value||'无');if(field==='rule')return String(record?.expression||'不限制条件');if(field==='record')return describeTemplateRecord(record as never,event,scopeName);if(kind==='condition'&&value){const c=value as {parameter_key:string;operator:keyof typeof operators;value:unknown};return (event?.parameters.find(p=>p.key===c.parameter_key)?.name??c.parameter_key)+' '+operators[c.operator]+' '+valueText(c.value);}if(kind==='utterance'){const row=value as TemplateGroup['utterances'][number]|undefined;return row?(row.ignored?'已忽略 · ':'')+row.text:'无';}if(field==='ignored')return value?'已忽略':'参与导出';if(field==='scope'){const v=value as {player_id:string|null;lineup_note_id:string|null}|undefined;return '棋手：'+scopeName(v?.player_id??null)+'\n阵容棋手组合：'+scopeName(v?.lineup_note_id??null);}return describeValue(value);};
 const label:Record<string,string>={...templateMetadataLabels,review_status:'审核状态',ignored:'忽略状态',explanation:'说明与依据',rule:'条件表达式及树稿',priority:'优先级',name:'名称',event_id:'事件',scope:'适用范围',related_entities:'关联实体',condition:'条件',utterance:'话术',record:'完整记录'};
 const show=(record:Record<string,unknown>|undefined)=>field==='review_status'?templateReviewLabel(record?.review_status as TemplateGroup['review_status']):describe(record);
 return <details className="template-diff" open><summary>{label[kind]??field}{id?' · '+id:''}</summary><div><section><strong>修改前</strong><pre>{show(base)}</pre></section><section><strong>修改后</strong><pre>{change.action==='delete'?'删除此记录':show(next)}</pre></section></div></details>;
}
type ReviewProps={
 admin:boolean;snapshot:TemplateSnapshot;
 onClose:()=>void;onChanged:(formalChanged:boolean,result:TemplateProposal)=>void;onLocate:(proposal:TemplateProposal,groupId:string)=>void;
 onEditGroup:(proposal:TemplateProposal,groupId:string)=>void;scopeName:(id:string|null)=>string;initialProposal?:string;
};
function rowKey(proposal:TemplateProposal,change:TemplateChange){
 return [proposal.id,proposal.proposal_revision,change.kind,change.id].join(':');
}
function ReviewHistory({proposal,scopeName,expanded}:{proposal:TemplateProposal;scopeName:ReviewProps['scopeName'];expanded:boolean}){
 const recordText=(record:TemplateEvent|TemplateGroup|null|undefined)=>describeTemplateRecord(record,
  record&&'event_id' in record?proposal.base.events.find(event=>event.id===record.event_id):undefined,scopeName);
 return <>{proposal.submission&&<details open={expanded||undefined}><summary>原始提案</summary>{proposal.submission.changes.map(change=><div key={change.kind+change.id}>
  <strong>{change.value?.name??change.id}</strong><p>提交前</p><pre>{recordText(proposal.submission!.before[change.kind+':'+change.id])}</pre>
  <p>编辑员提交稿</p><pre>{change.action==='delete'?'删除此记录':recordText(change.value)}</pre></div>)}</details>}
  {proposal.reviews?.map((review,index)=><details key={index}><summary>{{approve:'确认记录',edit:'修改提案',reject:'拒绝记录',withdraw:'撤回记录'}[review.action??'approve']} · {review.by} · {review.at}</summary>
   {review.changes?.map(change=><section key={change.kind+change.id}><strong>{change.value?.name??change.id}</strong>
    <pre>{change.action==='delete'?'删除此记录':recordText(change.value)}</pre></section>)}</details>)}</>;
}
export default function TemplateProposals({admin,snapshot,onClose,onChanged,onLocate,onEditGroup,scopeName,initialProposal}:ReviewProps){
 const [rows,setRows]=useState<TemplateProposal[]>([]),[error,setError]=useState(''),[pending,setPending]=useState<Record<string,string>>({}),[loaded,setLoaded]=useState(false);
 const active=useRef(new Set<string>());
 const [expanded,setExpanded]=useState<Record<string,boolean>>({});
 const proposalPath=(id:string)=>'templates/proposals/'+encodeURIComponent(id);
 const replace=(item:TemplateProposal)=>setRows(rows=>rows.map(row=>row.id===item.id?item:row));
 async function perform(proposal:TemplateProposal,action:string,run:()=>Promise<void>){
  if(active.current.has(proposal.id))return;
  active.current.add(proposal.id);setPending(values=>({...values,[proposal.id]:action}));setError('');
  try{await run();}
  catch(e){setError((e as Error).message);if((e as {status?:number}).status===409)void detail(proposal,false);}
  finally{active.current.delete(proposal.id);setPending(values=>{const next={...values};delete next[proposal.id];return next;});}
 }
 const [messages,setMessages]=useState<Record<string,string>>({});
 async function discuss(proposal:TemplateProposal){
  await perform(proposal,'discuss',async()=>{
   const item=await api<TemplateProposal>(proposalPath(proposal.id)+'/comments','POST',{proposal_revision:proposal.proposal_revision,body:messages[proposal.id]});
   setMessages(m=>({...m,[proposal.id]:''}));replace({...item,conflicts:proposal.conflicts});onChanged(false,item);
  });
 }
 const [selections,setSelections]=useState<Record<string,string[]>>({});
 const [editing,setEditing]=useState<{proposal:TemplateProposal;index:number}|null>(null);
 async function load(){
  try{const data=await api<TemplateProposal[]>('templates/proposals?view=summary');setRows(data);setLoaded(true);}
  catch(e){setError((e as Error).message);}
 }
 async function detail(proposal:TemplateProposal,open=true){
  try{
   const [item]=await api<TemplateProposal[]>('templates/proposals?proposal_id='+encodeURIComponent(proposal.id)+(open?'':'&view=summary'));
   if(item)setRows(rows=>rows.map(row=>row.id===item.id&&row.proposal_revision===proposal.proposal_revision?item:row));
   if(open)setExpanded(values=>({...values,[proposal.id]:true}));
  }catch(e){setError((e as Error).message);}
 }
 useEffect(()=>{void load();},[]);
 useEffect(()=>{
  if(!loaded||!initialProposal)return;
  const target=document.querySelector<HTMLElement>('[data-template-proposal-id="'+CSS.escape(initialProposal)+'"]');
  if(target){target.focus({preventScroll:true});target.scrollIntoView({block:'start'});}
 },[loaded,initialProposal]);
 function selection(proposal:TemplateProposal,change:TemplateChange){return selections[rowKey(proposal,change)]??changeFields(proposal,change);}
 async function revise(proposal:TemplateProposal,index:number,change:TemplateChange){
  const key=change.kind+':'+change.id,conflict=proposal.conflicts?.[key];
  const item=await api<TemplateProposal>(proposalPath(proposal.id)+'/edit','POST',{
   proposal_revision:proposal.proposal_revision,change_ids:[index],changes:[change],
   ...(conflict?{rebase:{[key]:conflict.revision}}:{})
  });
  setError('');replace(item);onChanged(false,item);
 }
 async function rebase(proposal:TemplateProposal,index:number,change:TemplateChange){
  if(!confirm('将当前正式版本作为审批依据，并保留此提案内容？'))return;
  await perform(proposal,'edit',()=>revise(proposal,index,change));
 }
 async function act(proposal:TemplateProposal,action:string){
  if(action!=='approve'&&!confirm('确定'+(action==='withdraw'?'撤回':'驳回')+'此提案的全部待审修改吗？'))return;
  await perform(proposal,action,async()=>{
   let payload:unknown={proposal_revision:proposal.proposal_revision,summary:true};
   if(action==='approve'&&proposal.inline_trigger){
    payload={proposal_revision:proposal.proposal_revision,return_write:true,summary:true};
   }else if(action==='approve'){
    const ids:number[]=[],changes:TemplateChange[]=[];
    for(const [i,change] of proposal.changes.entries()){
     const selected=selection(proposal,change);if(!selected.length)continue;
     if(proposal.conflicts?.[change.kind+':'+change.id]&&
      (change.kind!=='group'||change.action!=='put'||proposal.source==='review-status'||selected.length!==changeFields(proposal,change).length))
       throw new Error('请先核对已变化的正式版本');
     ids.push(i);
     const base=change.kind==='group'?proposal.base.groups.find(g=>g.id===change.id):undefined;
     changes.push(base&&change.action==='put'?{...change,value:selectedGroupChange(base,change.value as TemplateGroup,selected,
      Object.hasOwn(proposal.group_review_overrides??{},change.id))}:change);
    }
    if(!ids.length)throw new Error('请先选择需要采纳的修改');
    payload={proposal_revision:proposal.proposal_revision,change_ids:ids,changes,return_write:true,summary:true};
   }
   const item=await api<TemplateProposal>(proposalPath(proposal.id)+'/'+action,'POST',payload);
   replace(item);onChanged(action==='approve',item);
   if(item.status==='pending')void detail(item,false);
  });
 }
 if(editing){
  const {proposal,index}=editing,change=proposal.changes[index],close=()=>setEditing(null);
  return <TemplateSettings review annotator={!admin} events={[change.value as TemplateEvent]}
   onClose={close} onSave={async changes=>{if(changes[0])await revise(proposal,index,changes[0]);}}/>;
 }
 function target(proposal:TemplateProposal,change:TemplateChange){
  const group=change.kind==='group'?snapshot.groups.find(group=>group.id===change.id):undefined;
  const base=(change.kind==='group'?proposal.base.groups:proposal.base.events).find(record=>record.id===change.id);
  const original=proposal.submission?.before[change.kind+':'+change.id];
  const name=change.value?.name??group?.name??base?.name??original?.name??change.target_name??change.id;
  const preview=change.kind==='group'?proposalCardPreview(proposal,change.id):undefined;
  const temporary=preview&&!preview.base&&preview.change.action==='put';
  return <div className="template-proposal-target">
   <h3>{change.action==='delete'?'删除':'修改'}{change.kind==='event'?'事件':'模板组'}：{name}</h3>
   {group||temporary?<button type="button" aria-label={'定位'+name} onClick={()=>onLocate(proposal,change.id)}>定位</button>:
    <span className="template-proposal-location">{change.kind==='event'?'事件变更无对应模板卡片':'正式卡片不存在'}</span>}
  </div>;
 }
 function renderProposal(proposal:TemplateProposal){
  const action=pending[proposal.id],busy=!!action;
  const historyTargets=proposalLocationChanges(proposal).filter(change=>!proposal.changes.some(row=>row.kind===change.kind&&row.id===change.id));
  return <article key={proposal.id} className="template-proposal" data-template-proposal-id={proposal.id} tabIndex={-1}><header><strong>{proposal.author}</strong><time dateTime={proposal.created_at}>{proposal.created_at}</time>
   <span className="badge">{proposal.status==='pending'&&(proposal.previously_approved||proposal.reviews?.some(r=>(r.action??'approve')==='approve'))?'部分已采纳 · 待继续审核':statuses[proposal.status]??proposal.status}</span></header>
   <p>来源 {proposal.source??'proposal'} · 批次 {proposal.batch_id??proposal.id}</p>
   <details><summary>提案讨论（{proposal.discussion?.length??0}）</summary>{proposal.discussion?.map(m=><p key={m.id}><strong>{m.by}</strong> <time>{new Date(m.at).toLocaleString()}</time> {m.body}</p>)}<label>讨论内容<textarea maxLength={4000} value={messages[proposal.id]??''} onChange={e=>setMessages({...messages,[proposal.id]:e.target.value})}/></label><button disabled={busy||!messages[proposal.id]?.trim()} onClick={()=>void discuss(proposal)}>发表讨论</button></details>
   {proposal.has_history&&!proposal.submission&&!proposal.reviews?<button type="button" onClick={()=>void detail(proposal)}>原始提案</button>:
    <ReviewHistory proposal={proposal} scopeName={scopeName} expanded={!!expanded[proposal.id]}/>}
   {proposal.changes.map((change,i)=>{
    const key=rowKey(proposal,change),fields=changeFields(proposal,change),selected=selection(proposal,change);
    const conflict=proposal.conflicts?.[change.kind+':'+change.id],canReview=admin&&proposal.status==='pending';
    const editableTarget=change.kind==='group'?snapshot.groups.some(group=>group.id===change.id)||
     change.action==='put'&&!proposal.base.groups.some(group=>group.id===change.id):
     change.action==='put'&&(!conflict||admin);
    return <section key={key}>{target(proposal,change)}
     {conflict&&<div className="template-diff"><strong>正式版本已变化</strong><pre>{describeTemplateRecord(conflict.current,undefined,scopeName)}</pre>
      {!proposal.inline_trigger&&(change.kind==='group'?<p>打开模板组编辑器核对正式内容。</p>:canReview?<button disabled={busy} onClick={()=>void rebase(proposal,i,change)}>已核对当前版本，保留提案内容</button>:<p>等待管理员核对正式版本。</p>)}</div>}
     {fields.map(field=><div key={field}>{canReview&&!proposal.inline_trigger&&<label className="template-approve-choice"><input type="checkbox" checked={selected.includes(field)}
      onChange={e=>setSelections(s=>({...s,[key]:e.target.checked?[...selected,field]:selected.filter(v=>v!==field)}))}/>采纳此项{field.startsWith('condition:')?'条件修改':field.startsWith('utterance:')?'话术修改':''}</label>}
      <FieldDiff proposal={proposal} change={change} field={field} scopeName={scopeName}/></div>)}
     {proposal.status==='pending'&&!proposal.inline_trigger&&editableTarget&&<button disabled={busy}
      onClick={()=>change.kind==='group'?onEditGroup(proposal,change.id):setEditing({proposal,index:i})}>{conflict?'核对并修改提案':admin?'修改审核稿':'修改我的提案'}</button>}
    </section>;
   })}
   {historyTargets.map(change=><section key={change.kind+':'+change.id}>{target(proposal,change)}</section>)}
   {proposal.status==='pending'&&<footer>{admin?<><button disabled={busy} onClick={()=>void act(proposal,'reject')}>{action==='reject'?'驳回中…':'驳回整份提案'}</button>
    <button disabled={busy} className="primary" onClick={()=>void act(proposal,'approve')}>{action==='approve'?'采纳中…':proposal.inline_trigger?'采纳整份提案':'采纳勾选修改'}</button></>:<button disabled={busy} onClick={()=>void act(proposal,'withdraw')}>撤回提案</button>}</footer>}
  </article>;
 }
 const sorted=[...rows].sort(newestProposalFirst),withdrawn=sorted.filter(proposal=>proposal.status==='withdrawn');
 return <TemplateDialog title={admin?'模板提案审核':'我的模板提案'} onClose={onClose} wide><div className="template-proposals">
  {error&&<p className="error" role="alert">{error} <button onClick={()=>void load()}>刷新提案</button></p>}
  {!loaded&&!error&&<p role="status">正在载入提案…</p>}{loaded&&!rows.length&&<p className="empty">暂无模板提案。</p>}
  {sorted.filter(proposal=>proposal.status!=='withdrawn').map(renderProposal)}
  {!!withdrawn.length&&<details className="template-withdrawn-proposals"><summary>已撤回（{withdrawn.length}）</summary>{withdrawn.map(renderProposal)}</details>}
 </div></TemplateDialog>;
}
