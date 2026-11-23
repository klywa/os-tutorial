import {UtteranceLength} from './TemplateUtterances';
import {effectiveExpression,templateExplanationFields} from './templates';
import TemplateRuleEditor from './TemplateRuleEditor';
import {completeTree,emptyTree,listPaths,newLeaf,renderRule,treeEntities,type ConditionCatalog,type ConditionNode} from './templateRules';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {categoryNames,EntityChip,useCards} from './EntityCards';
import NewTemplateParameter from './NewTemplateParameter';
import type {Entity,Note} from './types';
import {deriveTemplateEntities,lineupPlayer,parseConditionValue,selectTemplateScope,placeholderKeys,templateExplanationLimit,templateId,valueText,type TemplateCondition,type TemplateEvent,type TemplateGroup,type TemplateParameter} from './templates';

export function TemplateDialog({title,onClose,children,wide=false}:{title:string;onClose:()=>void;children:ReactNode;wide?:boolean}){
 const panel=useRef<HTMLElement>(null),closeRef=useRef(onClose);closeRef.current=onClose;
 useEffect(()=>{const previous=document.activeElement as HTMLElement;const node=panel.current;node?.querySelector<HTMLElement>('input,button,textarea,select')?.focus();function key(e:KeyboardEvent){if(e.key==='Escape'){e.preventDefault();closeRef.current();}if(e.key==='Tab'&&node){const focusable=Array.from(node.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]'));const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}}document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus();};},[]);
 return <div className="template-overlay"><section ref={panel} className={'template-dialog '+(wide?'template-dialog-wide':'')} role="dialog" aria-modal="true" aria-label={title}><header><h2>{title}</h2><button type="button" aria-label={'关闭'+title} onClick={onClose}>×</button></header>{children}</section></div>;
}
export function ConditionInput({condition,parameter,onChange}:{condition:TemplateCondition;parameter?:TemplateParameter;onChange:(value:unknown)=>void}){
 const cards=useCards();if(!parameter)return <span className="error">请选择参数</span>;
 if(parameter.type==='entity'){const value=condition.value as {id:string;name:string}|null;return <select aria-label="实体条件值" value={value?.id??''} onChange={e=>{const card=cards.find(c=>c.id===e.target.value);onChange(card?{id:card.id,name:card.name}:null);}}><option value="">选择实体卡牌</option>{value?.id&&!cards.some(c=>c.id===value.id)&&<option value={value.id} disabled>{value.name||value.id}（资料暂缺/已下架）</option>}{cards.filter(c=>!parameter.entity_categories?.length||parameter.entity_categories.includes(c.category)).map(c=><option key={c.id} value={c.id}>{c.name}{c.awakened?'（觉醒）':''}</option>)}</select>;}
 if(parameter.type==='boolean')return <select aria-label="是或否" value={String(condition.value??'')} onChange={e=>onChange(e.target.value==='true')}><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select>;
 const values=Array.isArray(condition.value)?condition.value:[condition.value,''];return <><input aria-label={condition.operator==='between'?'条件下限':'条件值'} type={parameter.type==='number'?'number':'text'} step="any" value={String(condition.operator==='between'?values[0]??'':condition.value??'')} onChange={e=>onChange(condition.operator==='between'?[e.target.value,values[1]]:e.target.value)} list={'suggest-'+condition.id}/>{condition.operator==='between'&&<><span>至</span><input aria-label="条件上限" type="number" step="any" value={String(values[1]??'')} onChange={e=>onChange([values[0],e.target.value])}/></>}<datalist id={'suggest-'+condition.id}>{(parameter.suggestions??[]).map((s,i)=><option key={i} value={valueText(s)}/>)}</datalist></>;
}
function TemplateTagInput({tags,onChange}:{tags:string[];onChange:(next:string[])=>void}){
 const [value,setValue]=useState('');
 function add(){
  const tag=value.trim();
  if(tag&&!tags.includes(tag))onChange([...tags,tag]);
  setValue('');
 }
 return <div>
  <label>标签<input value={value} maxLength={40} onChange={e=>setValue(e.target.value)}
   onBlur={add} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();add();}}}/></label>
  <div className="template-chips">{tags.map(tag=><button type="button" key={tag} onClick={()=>onChange(tags.filter(item=>item!==tag))} aria-label={'移除标签 '+tag}>{tag} ×</button>)}</div>
 </div>;
}

export default function TemplateEditor({group,review=false,creating=false,scopeName,entities:archivedEntities=[],conditionLinks={},catalog,events,players,lineups,annotator,onSave,onClose,onDirty}:{group:TemplateGroup;review?:boolean;creating?:boolean;scopeName?:(id:string|null)=>string;catalog?:ConditionCatalog;entities?:{id:string;name:string}[];conditionLinks?:Record<string,{id:string;name:string}[]>;events:TemplateEvent[];players:Entity[];lineups:Note[];annotator:boolean;onSave:(group:TemplateGroup,event?:TemplateEvent)=>Promise<void>;onClose:()=>void;onDirty?:(dirty:boolean)=>void}){
 const [draft,setDraft]=useState(()=>structuredClone(group)),[busy,setBusy]=useState(false),[error,setError]=useState('');const cards=useCards(),lastText=useRef<HTMLTextAreaElement|null>(null);
 const [addedParameters,setAddedParameters]=useState<TemplateParameter[]>([]),[parameterAdding,setParameterAdding]=useState(false);
 const baseEvent=events.find(e=>e.id===draft.event_id),event=baseEvent?{...baseEvent,parameters:[...baseEvent.parameters,...addedParameters]}:undefined,dirty=JSON.stringify(draft)!==JSON.stringify(group)||addedParameters.length>0||parameterAdding;
 useEffect(()=>{onDirty?.(dirty);return()=>onDirty?.(false);},[dirty,onDirty]);
 function close(){if(!dirty||confirm('有未保存的模板修改，确定放弃吗？'))onClose();}
 function patch(value:Partial<TemplateGroup>){
  if(value.editor_mode==='tree'&&value.condition_tree)value.related_entities=treeEntities(value.condition_tree,listPaths(event,catalog),cards,catalog?.unit_types);
  setDraft(d=>({...d,...value}));}
 function addParameter(parameter:TemplateParameter){
  setAddedParameters(p=>[...p,parameter]);
  const existing=draft.condition_tree??emptyTree();
  if(draft.editor_mode!=='text'){
   const paths=listPaths(event?{...event,parameters:[...event.parameters,parameter]}:undefined,catalog);
   const leaf=newLeaf(paths.filter(p=>p.path===parameter.key||p.path.startsWith(parameter.key+'.')));
   const tree:ConditionNode={kind:'all',children:[...(existing.kind==='all'?existing.children:[existing]),leaf]};
   patch({condition_tree:tree,expression:renderRule(tree),conditions:[],editor_mode:'tree'});
  }
  setParameterAdding(false);
 }
 const boundName=(id:string|null)=>id?(players.find(row=>row.id===id)?.name??lineups.find(row=>row.id===id)?.title??archivedEntities.find(row=>row.id===id)?.name??scopeName?.(id)??id):null;
 const preview=effectiveExpression(boundName(draft.scope.player_id),boundName(draft.scope.lineup_note_id),draft.expression??renderRule(draft.condition_tree??emptyTree()));
 const explanationLength=Array.from(draft.explanation??'').length;
 async function save(){setError('');try{
  if(explanationLength>templateExplanationLimit)throw new Error('说明与依据最多可填写 300 字');
  if(parameterAdding)throw new Error('请先添加事件参数，或取消新增参数');
  if(!draft.name.trim())throw new Error('请填写模板组名称');if(!event)throw new Error('请选择事件');if(!draft.utterances.length||draft.utterances.some(u=>!u.text.trim()))throw new Error('至少填写一条完整话术');
  if(draft.editor_mode!=='text'&&draft.condition_tree&&!completeTree(draft.condition_tree))throw new Error('请填写完整的条件，并为每个子组添加条件');
  if(!Number.isSafeInteger(draft.priority??0))throw new Error('优先级必须是整数');
  const conditions=draft.conditions.map(c=>{const p=event.parameters.find(p=>p.key===c.parameter_key);if(!p)throw new Error('条件引用了不存在的参数');const v=c.value,range=Array.isArray(v)?v:[];return {...c,value:parseConditionValue(p.type,c.operator,p.type==='entity'?String((v as {id?:string})?.id??''):String(c.operator==='between'?range[0]??'':v??''),p.type==='entity'?String((v as {name?:string})?.name??''):String(range[1]??''))};});
  for(const u of draft.utterances){const unknown=placeholderKeys(u.text).filter(k=>!event.parameters.some(p=>p.key===k));if(unknown.length)throw new Error('话术引用未知参数：'+unknown.join('、'));}
  setBusy(true);await onSave({...draft,name:draft.name.trim(),version:draft.version?.trim(),mode:draft.mode?.trim(),conditions},addedParameters.length?event:undefined);onDirty?.(false);onClose();
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const entities=deriveTemplateEntities(draft,event,cards,archivedEntities,group,conditionLinks,events.find(e=>e.id===group.event_id));
 return <TemplateDialog title={review?'修改模板提案':creating?'新建模板组':annotator?'提议修改模板':'编辑模板'} onClose={close} wide><form className="template-form" onSubmit={e=>{e.preventDefault();void save();}}><fieldset disabled={busy}><div className="template-form-grid"><label>模板组名称<input value={draft.name} onChange={e=>patch({name:e.target.value})} required/></label><label>触发事件<select value={draft.event_id} onChange={e=>{if((draft.expression||draft.condition_tree?.kind==='leaf'||draft.conditions.length||addedParameters.length||parameterAdding)&&!confirm('切换事件会清空现有条件和本次新增参数，继续吗？'))return;setAddedParameters([]);setParameterAdding(false);patch({event_id:e.target.value,conditions:[],condition_tree:emptyTree(),expression:'',editor_mode:'tree'});}}><option value="">选择事件</option>{events.map(e=><option key={e.id} value={e.id}>{e.name}</option>)}</select></label><label>适用棋手<select value={draft.scope.player_id??''} onChange={e=>patch({scope:selectTemplateScope(draft.scope,'player',e.target.value,lineups)})}><option value="">通用棋手</option>{draft.scope.player_id&&!players.some(p=>p.id===draft.scope.player_id)&&<option value={draft.scope.player_id} disabled>{archivedEntities.find(e=>e.id===draft.scope.player_id)?.name??draft.scope.player_id}（资料暂缺/已下架）</option>}{players.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label>阵容棋手组合<select value={draft.scope.lineup_note_id??''} onChange={e=>patch({scope:selectTemplateScope(draft.scope,'lineup',e.target.value,lineups)})}><option value="">通用组合</option>{lineups.filter(n=>lineupPlayer(n)&&(!draft.scope.player_id||lineupPlayer(n)===draft.scope.player_id)).map(n=><option key={n.id} value={n.id}>{n.title}</option>)}</select></label></div>
 <div className="template-form-grid">
  <label>版本<input value={draft.version??''} maxLength={80} onChange={e=>patch({version:e.target.value})}/></label>
  <label>模式<input value={draft.mode??''} maxLength={80} onChange={e=>patch({mode:e.target.value})}/></label>
  <TemplateTagInput tags={draft.tags??[]} onChange={tags=>patch({tags})}/>
 </div>
 {templateExplanationFields.map(([field,label])=><label key={field}>说明与依据-{label}<textarea rows={3} value={draft[field]??''} onChange={e=>patch({[field]:e.target.value})}/></label>)}
 {!!group.explanation&&<label className="template-explanation-field">旧版说明与依据<textarea aria-describedby="template-explanation-count" aria-invalid={explanationLength>templateExplanationLimit} rows={2} value={draft.explanation??''} onChange={e=>patch({explanation:e.target.value})}/>
 <small id="template-explanation-count" className={explanationLength>templateExplanationLimit?'error':''}>{explanationLength} / {templateExplanationLimit} 字</small></label>}
 <label>优先级<input type="number" step="1" value={draft.priority??0} onChange={e=>patch({priority:Number(e.target.value)})}/><small>先选最高优先级。同级优先采用条件更严格的组，剩余候选组等概率抽取。</small></label>
 <TemplateRuleEditor key={draft.event_id} preview={preview} draft={draft} event={event} catalog={catalog} patch={patch}/>
 {!review&&<button type="button" disabled={!event||parameterAdding} onClick={()=>setParameterAdding(true)}>＋ 新增事件参数</button>}
 {parameterAdding&&event&&<NewTemplateParameter event={event} onAdd={addParameter} onCancel={()=>setParameterAdding(false)}/>}
 {addedParameters.length>0&&<p role="status">将随模板保存新增参数：{addedParameters.map(p=>p.name).join('、')}</p>}
 <section><h3>全部话术 <small className="muted">每条等概率</small></h3><p className="muted">点击参数插入 {'{key}'}。可引用 <code>in</code> 限定的名称（如 <code>{'{玩家.主C}'}</code>），也可引用必选数值比较中的实际数字。双花括号 {'{{文字}}'} 表示原样文字。</p><div className="template-parameter-tools">{event?.parameters.map(p=><button type="button" key={p.id} onClick={()=>{const text=lastText.current,token='{'+p.key+'}';if(text&&!text.readOnly){const id=text.dataset.id,start=text.selectionStart,end=text.selectionEnd;patch({utterances:draft.utterances.map(u=>u.id===id?{...u,text:u.text.slice(0,start)+token+u.text.slice(end)}:u)});requestAnimationFrame(()=>{text.focus();text.setSelectionRange(start+token.length,start+token.length);});}}}>{p.name} <code>{'{'+p.key+'}'}</code></button>)}</div>{draft.utterances.map((u,i)=><div className="template-utterance-edit" key={u.id}><div className="template-utterance-draft"><label>话术 {i+1}{u.fixed&&<small className="template-fixed">已固定</small>}<textarea readOnly={!!u.fixed} data-id={u.id} value={u.text} rows={3} onFocus={e=>{lastText.current=e.currentTarget;}} onChange={e=>patch({utterances:draft.utterances.map(x=>x.id===u.id?{...x,text:e.target.value}:x)})}/></label><UtteranceLength text={u.text}/></div><button type="button" aria-label={'删除话术'+(i+1)} disabled={!!u.fixed} onClick={()=>patch({utterances:draft.utterances.filter(x=>x.id!==u.id)})}>删除</button></div>)}<button type="button" onClick={()=>patch({utterances:[...draft.utterances,{id:templateId('utterance'),text:''}]})}>＋ 添加话术</button></section>
 <section><h3>关联卡牌</h3>
 {draft.editor_mode==='text'?<><label>按名称添加关联卡牌<select value="" onChange={e=>{const selected=cards.find(c=>c.id===e.target.value);if(selected){const next=cards.filter(c=>c.name===selected.name&&c.category===selected.category&&!draft.related_entities.some(r=>r.id===c.id)).map(({id,name})=>({id,name}));patch({related_entities:[...draft.related_entities,...next]});}}}><option value="">选择卡牌</option>{cards.filter((c,i)=>cards.findIndex(x=>x.category===c.category&&x.name===c.name)===i).map(c=><option key={c.id} value={c.id}>{c.name} · {categoryNames[c.category]??c.category}</option>)}</select></label>
 <div className="template-chips">{draft.related_entities.map(ref=><button type="button" key={ref.id} onClick={()=>patch({related_entities:draft.related_entities.filter(r=>r.id!==ref.id)})}>移除 {ref.name}</button>)}</div></>:<p className="muted">实体名称条件和适用棋手将关联同类同名卡牌。</p>}
 <div className="template-chips">{entities.map(e=><EntityChip key={e.id} ids={[e.id]} label={e.name}/>)}</div></section>
 {error&&<p role="alert" className="error">{error}</p>}<footer><button type="button" onClick={close}>取消</button><button className="primary" disabled={busy}>{busy?'保存中…':review?(annotator?'保存提案修改':'保存审核稿'):annotator?'提交修改提案':'保存模板'}</button></footer></fieldset></form></TemplateDialog>;
}
