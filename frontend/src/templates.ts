import type {ConditionCatalog,ConditionNode} from './templateRules';
export type ParameterType='text'|'number'|'boolean'|'entity';
export function effectiveExpression(player:string|null,lineup:string|null,expression:string){
 const clauses:string[]=[];
 if(player!==null)clauses.push('玩家.使用棋手 is '+JSON.stringify(player));
 if(lineup!==null)clauses.push('玩家.使用阵容 is '+JSON.stringify(lineup));
 if(!clauses.length)return expression;
 if(expression.trim())clauses.push('('+expression+')');
 return clauses.join(' and ');
}

export type TemplateEntity={id:string;name:string};
export type TemplateParameter={id:string;key:string;name:string;type:ParameterType;dsl_type?:string;entity_categories?:string[];suggestions?:unknown[];min?:number;max?:number};
export type TemplateEvent={id:string;name:string;category?:string;parameters:TemplateParameter[]};
export type ConditionOperator='eq'|'ne'|'gt'|'gte'|'lt'|'lte'|'between';
export type TemplateCondition={id:string;parameter_key:string;operator:ConditionOperator;value:unknown};
export const templateExplanationLimit=300;
export type TemplateReviewStatus='ai_generated'|'initial_reviewed'|'final_reviewed';
export const templateGameModes=['万象大赛','万象速决'] as const;
export type TemplateGameMode=''|typeof templateGameModes[number];
export type TemplateModifier={kind:'ai'|'user';username?:string};
export type TemplateEntitySnapshot={season:string;version?:string;entities:Record<string,unknown>};
type TemplateGroupMetadata={version?:string;mode?:string;tags?:string[];batch?:string[];review_status?:TemplateReviewStatus|null;last_modified_by?:TemplateModifier;reviewed_by?:string;reviewed_at?:string;entity_snapshot?:TemplateEntitySnapshot;explanation?:string;explanation_before?:string;explanation_source?:string;explanation_after?:string};
export const templateReviewLabels:Record<TemplateReviewStatus,string>={ai_generated:'AI生成',initial_reviewed:'初核完成',final_reviewed:'复核完成'};
export const effectiveReviewStatus=(status:TemplateGroupMetadata['review_status'])=>status===undefined?'ai_generated':status;
export const templateReviewLabel=(status:TemplateGroupMetadata['review_status'])=>status===null?'未标记':templateReviewLabels[status??'ai_generated'];
export const groupSeason=(group:Pick<TemplateGroupMetadata,'version'>)=>(group.version||'S1').toUpperCase();
export const templateExplanationFields=[
 ['explanation_before','前置思考'],['explanation_source','来源'],['explanation_after','后置校验'],
] as const;
export const templateMetadataLabels={version:'版本',mode:'模式',tags:'标签',batch:'批次',explanation_before:'说明与依据-前置思考',explanation_source:'说明与依据-来源',explanation_after:'说明与依据-后置校验'};
export type TemplateGroup=TemplateGroupMetadata&{id:string;name:string;ignored?:boolean;event_id:string;expression?:string;priority?:number;condition_tree?:ConditionNode|null;editor_mode?:'tree'|'text';scope:{player_id:string|null;lineup_note_id:string|null};conditions:TemplateCondition[];utterances:{id:string;text:string;ignored?:boolean;fixed?:boolean}[];related_entities:TemplateEntity[]};
export type UtteranceBindings=Record<string,string[]>;
export type TemplateSnapshot={schema_version:number;condition_catalog?:ConditionCatalog;scope_names?:Record<string,string>;read_generation?:string;revision:string;events:TemplateEvent[];groups:TemplateGroup[];entity_links?:Record<string,TemplateEntity[]>;entity_condition_links?:Record<string,Record<string,TemplateEntity[]>>;utterance_bindings?:Record<string,UtteranceBindings>};
// Portable JSON is a separate contract from the canonical editor/proposal model.
export type PortableTemplateParameter=Omit<TemplateParameter,'id'|'suggestions'>&{id?:string;suggestions?:Array<string|number|boolean>};
export type PortableTemplateEvent=Omit<TemplateEvent,'id'|'parameters'>&{id?:string;parameters:PortableTemplateParameter[]};
export type PortableTemplateGroup=TemplateGroupMetadata&{id?:string;name:string;event_name:string;scope:{player:string|null;lineup:string|null};expression:string;effective_expression?:string;priority:number;editor_mode:'tree'|'text';condition_tree?:ConditionNode|null;utterances:string[]};
export type PortableTemplateLibrary={kind:'speech-template-library';schema_version:3;condition_catalog:ConditionCatalog;events:(PortableTemplateEvent&{signature:string})[];groups:PortableTemplateGroup[]};
type TemplateCatalogEntity=TemplateEntity&{category?:string;aliases?:string[]};
export function resolveTemplateEntities(name:string,catalog:TemplateCatalogEntity[],categories?:string[]):TemplateEntity[]{
 const value=name.trim(),allowed=catalog.filter(e=>!categories?.length||categories.includes(e.category??''));
 if(!value)return [];
 const exact=allowed.filter(e=>e.name.trim()===value),matched=exact.length?exact:allowed.filter(e=>e.aliases?.some(a=>a.trim()===value));
 if(!matched.length||(!categories?.length&&new Set(matched.map(e=>e.category)).size!==1))return [];
 return allowed.filter(e=>matched.some(m=>m.category===e.category&&m.name.trim()===e.name.trim())).map(({id,name})=>({id,name})).sort((a,b)=>a.id.localeCompare(b.id));
}
export function deriveTemplateEntities(group:TemplateGroup,event:TemplateEvent|undefined,catalog:TemplateCatalogEntity[],archive:TemplateEntity[]=[],savedGroup:TemplateGroup=group,conditionLinks:Record<string,TemplateEntity[]>={},savedEvent:TemplateEvent|undefined=event):TemplateEntity[]{
 const result=new Map<string,TemplateEntity>();
 const add=(ref:TemplateEntity,categories?:string[])=>{
  const existing=catalog.find(e=>e.id===ref.id&&(!categories?.length||categories.includes(e.category??'')));
  const matches=resolveTemplateEntities(ref.name,catalog,categories);
  for(const e of matches)result.set(e.id,{id:e.id,name:e.name});
  if(existing||!matches.length){const anchor=existing??ref;result.set(anchor.id,{id:anchor.id,name:anchor.name});}
  for(const e of archive)if(e.id===ref.id||e.name===ref.name){if(!catalog.some(c=>c.id===e.id))result.set(e.id,e);}
 };
 for(const c of group.conditions){const parameter=event?.parameters.find(p=>p.key===c.parameter_key),ref=c.value as TemplateEntity|null;if(parameter?.type==='entity'&&ref&&typeof ref==='object'&&!Array.isArray(ref)&&ref.id)add(ref,parameter.entity_categories);}
 if(group.expression!==undefined)for(const ref of group.related_entities){const anchor=catalog.find(c=>c.id===ref.id);add(ref,anchor?.category?[anchor.category]:undefined);}
 if(group.scope.player_id){const id=group.scope.player_id;add(catalog.find(e=>e.id===id)??archive.find(e=>e.id===id)??{id,name:id},['players']);}
 const remember=(ref:TemplateEntity)=>{const current=catalog.find(e=>e.id===ref.id);result.set(ref.id,{id:ref.id,name:current?.name??ref.name});};
 const categories=(definition:TemplateEvent|undefined,key:string)=>definition?.parameters.find(p=>p.key===key&&p.type==='entity')?.entity_categories;
 if(group.event_id===savedGroup.event_id)for(const c of group.conditions){
  const previous=savedGroup.conditions.find(p=>p.id===c.id);
  if(previous&&event?.parameters.some(p=>p.key===c.parameter_key&&p.type==='entity')&&savedEvent?.parameters.some(p=>p.key===previous.parameter_key&&p.type==='entity')&&previous.parameter_key===c.parameter_key&&JSON.stringify(previous.value)===JSON.stringify(c.value)&&JSON.stringify(categories(event,c.parameter_key))===JSON.stringify(categories(savedEvent,c.parameter_key)))for(const ref of conditionLinks[c.id]??[])remember(ref);
 }
 // Whole-group projections remain authoritative for saved cards. Per-condition
 // projections retain history independently while editing a subset of selectors.
 const selectors=(value:TemplateGroup,definition:TemplateEvent|undefined)=>value.conditions.filter(c=>definition?.parameters.some(p=>p.key===c.parameter_key&&p.type==='entity')).map(c=>({id:c.id,key:c.parameter_key,value:c.value,categories:categories(definition,c.parameter_key)})).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
 if(group.event_id===savedGroup.event_id&&group.scope.player_id===savedGroup.scope.player_id&&group.expression===savedGroup.expression&&JSON.stringify(group.related_entities)===JSON.stringify(savedGroup.related_entities)&&JSON.stringify(selectors(group,event))===JSON.stringify(selectors(savedGroup,savedEvent)))for(const ref of archive)remember(ref);
 return [...result.values()];
}
export type TemplateChange={kind:'event'|'group';action:'put'|'delete';id:string;value?:TemplateEvent|TemplateGroup;target_name?:string|null};
export type TemplateMetadataField='tags'|'batch';
export function appendTemplateMetadata(groups:TemplateGroup[],field:TemplateMetadataField,values:string[]):TemplateChange[]{
 const additions=[...new Set(values)];
 return groups.flatMap(group=>{
  const previous=group[field]??[];
  const missing=additions.filter(value=>!previous.includes(value));
  return missing.length?[{kind:'group',action:'put',id:group.id,value:{...group,[field]:[...previous,...missing]}}]:[];
 });
}
type TemplateVersions=Record<string,TemplateEvent|TemplateGroup|null>;
export type TemplateReview={action?:string;at:string;by:string;changes?:TemplateChange[];before?:TemplateVersions;after?:TemplateVersions};
export type TemplateProposal={history_targets?:TemplateChange[];has_history?:boolean;previously_approved?:boolean;formal_write?:{revision:string;previous_revision:string;changes:TemplateChange[]};group_review_overrides?:Record<string,TemplateReviewStatus|null>;discussion?:{id:string;by:string;at:string;body:string}[];source?:string;batch_id?:string;submission?:{before:TemplateVersions;changes:TemplateChange[]};reviews?:TemplateReview[];conflicts?:Record<string,{current:TemplateEvent|TemplateGroup|null;revision:string}>;id:string;author:string;status:string;created_at:string;revision:string;proposal_revision?:string;changes:TemplateChange[];base:{events:TemplateEvent[];groups:TemplateGroup[]}};
export type TemplateWarning={group_id:string;group_name:string;revision:string;entities:{id:string;name:string;before:unknown;after:unknown}[]};
export type WarningSnapshot={items:TemplateWarning[];unseen_items?:TemplateWarning[];notification_revision:string;unseen:boolean};
export function loginWarningItems(snapshot:WarningSnapshot){return snapshot.unseen_items??(snapshot.unseen?snapshot.items:[]);}
export type TemplateFilters={event:string;player:string;lineup:string;query:string;version?:string;mode?:string;tags?:string[];batch?:string[];review_status?:TemplateReviewStatus|''|'unmarked';actor?:string};
export const emptyTemplateFilters:TemplateFilters={event:'',player:'',lineup:'',query:'',version:'',mode:'',tags:[],batch:[],review_status:'',actor:''};
export const operators:Record<ConditionOperator,string>={eq:'等于',ne:'不等于',gt:'>',gte:'≥',lt:'<',lte:'≤',between:'介于'};
export const typeNames:Record<ParameterType,string>={text:'文本',number:'数字',boolean:'是/否',entity:'实体卡牌'};
export function templateId(prefix:string){return prefix+'_'+crypto.randomUUID();}
export function copyTemplateGroup(source:TemplateGroup,groups:TemplateGroup[]):TemplateGroup{
 const names=new Set(groups.filter(group=>group.event_id===source.event_id).map(group=>group.name.trim()));
 let number=1,name=source.name+'（副本）';
 while(names.has(name)){
  number++;
  name=source.name+'（副本 '+number+'）';
 }
 const draft=structuredClone(source);
 return {...draft,id:templateId('group'),name,
  conditions:draft.conditions.map(condition=>({...condition,id:templateId('conditions')})),
  utterances:draft.utterances.map(({fixed,...row})=>({...row,id:templateId('utterance')})),
 };
}
export function valueText(value:unknown):string{if(Array.isArray(value))return value.map(valueText).join(' 至 ');if(typeof value==='object'&&value)return String((value as TemplateEntity).name??(value as TemplateEntity).id??'');if(typeof value==='boolean')return value?'是 true':'否 false';return String(value??'');}
const utteranceTokens=/\{\{|\}\}|\{((?:[^{}"]|"(?:[^"\\]|\\.)*")+)\}/g;
export function renderUtterance(text:string,bindings?:UtteranceBindings):string{
 if(!bindings)return text;
 return text.replace(utteranceTokens,(token,path:string|undefined)=>{
  const candidates=path&&Object.hasOwn(bindings,path)?bindings[path]:undefined;
  return candidates?.length?candidates.join('/'):token;
 });
}
function templateSearchTerms(query:string):string[]{
 const terms:string[]=[],closing:string[]=[];
 const delimiters:Record<string,string>={'(':')','[':']','{':'}'};
 let start=0,inString=false;
 for(let i=0;i<query.length;i++){
  const char=query[i];
  if(inString&&char==='\\'){i++;continue;}
  if(char==='"'){inString=!inString;continue;}
  if(inString)continue;
  if(delimiters[char])closing.push(delimiters[char]);
  else if(char===closing.at(-1))closing.pop();
  else if(!closing.length&&(char===','||char==='，')){
   terms.push(query.slice(start,i));
   start=i+1;
  }
 }
 terms.push(query.slice(start));
 return terms.map(term=>term.trim().toLocaleLowerCase()).filter(Boolean);
}
export function filterTemplateGroups(groups:TemplateGroup[],filters:TemplateFilters,catalog:{id:string;name:string;aliases?:string[]}[]=[],labels:{events?:TemplateEvent[];scopeName?:(id:string|null)=>string;links?:Record<string,TemplateEntity[]>;utteranceBindings?:Record<string,UtteranceBindings>}={}){
 const compatible=(value:string|null,filter:string)=>!filter||(filter==='common'?value===null:value===null||value===filter);
 const terms=templateSearchTerms(filters.query);
 const actorMatches=(group:TemplateGroup)=>{
  const modifier=group.last_modified_by??{kind:'ai'};
  return !filters.actor||filters.actor===modifier.kind||(modifier.kind==='user'&&filters.actor==='user:'+modifier.username);
 };
 const scoped=groups.filter(group=>(!filters.event||group.event_id===filters.event)
  &&compatible(group.scope.player_id,filters.player)&&compatible(group.scope.lineup_note_id,filters.lineup)
  &&(!filters.version||filters.version.toUpperCase()===groupSeason(group))&&(!filters.mode||filters.mode===group.mode)
  &&(!filters.review_status||filters.review_status===(effectiveReviewStatus(group.review_status)??'unmarked'))&&actorMatches(group)
  &&(filters.batch??[]).every(batch=>group.batch?.includes(batch))
  &&(filters.tags??[]).every(tag=>group.tags?.includes(tag)));
 if(!terms.length)return scoped;
 const entities=new Map<string,{name:string;aliases:string[]}>();for(const e of catalog){const previous=entities.get(e.id);entities.set(e.id,{name:e.name,aliases:[...new Set([...(previous?.aliases??[]),...(e.aliases??[]),...(previous?.name&&previous.name!==e.name?[previous.name]:[])])]});}
 const searchValue=(value:unknown)=>{const ref=value as TemplateEntity|null;if(ref&&typeof ref==='object'&&!Array.isArray(ref)&&ref.id){const entity=entities.get(ref.id);return [ref.id,ref.name,entity?.name,...entity?.aliases??[]].filter(Boolean).join(' ').toLocaleLowerCase();}return valueText(value).toLocaleLowerCase();};
 return scoped.filter(group=>{
  const event=labels.events?.find(e=>e.id===group.event_id);
  const {player_id:player,lineup_note_id:lineup}=group.scope;
  const playerName=player&&(labels.scopeName?.(player)??player),lineupName=lineup&&(labels.scopeName?.(lineup)??lineup);
  const bindings=labels.utteranceBindings?.[group.id];
  const values=[group.name,effectiveExpression(playerName,lineupName,group.expression??''),
   ...group.utterances.flatMap(({text})=>bindings?[text,renderUtterance(text,bindings)]:[text]),
   event?.name,labels.scopeName?.(player),labels.scopeName?.(lineup),
   ...[...group.related_entities,...labels.links?.[group.id]??[]].map(searchValue),
   ...group.conditions.flatMap(c=>{
    const name=event?.parameters.find(p=>p.key===c.parameter_key)?.name??c.parameter_key;
    const displayed=[name,operators[c.operator],valueText(c.value)].join(' ');
    return [c.parameter_key,displayed,searchValue(c.value)];
   })].map(value=>value?.toLocaleLowerCase()??'');
  return terms.every(term=>values.some(value=>value.includes(term)));
 });
}
export function lineupPlayer(note:{player_id?:string;meta?:{players:string[]}}){return note.player_id??null;}
export function selectTemplateScope(scope:TemplateGroup['scope'],field:'player'|'lineup',value:string,notes:{id:string;player_id?:string;meta?:{players:string[]}}[]):TemplateGroup['scope']{
 if(field==='lineup'){if(!value)return {...scope,lineup_note_id:null};const note=notes.find(n=>n.id===value),player=note?lineupPlayer(note):null;if(!player)throw new Error('此阵容未关联明确棋手，请先完善阵容笔记');return {player_id:player,lineup_note_id:value};}
 const player=value||null,note=notes.find(n=>n.id===scope.lineup_note_id);return {player_id:player,lineup_note_id:note&&lineupPlayer(note)===player?scope.lineup_note_id:null};
}
export function parseConditionValue(type:ParameterType,operator:ConditionOperator,raw:string,extra=''):unknown{
 if(type==='number'){const number=(v:string)=>{if(!v.trim()||!Number.isFinite(Number(v)))throw new Error('请输入有效数字');return Number(v);};const lower=number(raw);if(operator==='between'){const upper=number(extra);if(lower>upper)throw new Error('下限不能大于上限');return [lower,upper];}return lower;}
 if(type==='boolean'){if(raw!=='true'&&raw!=='false')throw new Error('请选择是或否');return raw==='true';}
 if(type==='entity'){if(!raw||!extra)throw new Error('请选择有效实体');return {id:raw,name:extra};}
 if(!raw.trim())throw new Error('条件值不能为空');return raw;
}
export function utteranceReferences(text:string){
 return [...new Set(Array.from(text.matchAll(utteranceTokens),match=>match[1])
  .filter((path):path is string=>!!path))];
}
export function placeholderKeys(text:string){
 return utteranceReferences(text).filter(path=>/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(path));
}
export function groupDiffKeys(base:TemplateGroup,next:TemplateGroup){
 const keys:string[]=[];
 if((base.explanation??'')!==(next.explanation??''))keys.push('explanation');
 for(const key of Object.keys(templateMetadataLabels) as (keyof typeof templateMetadataLabels)[]){
  const empty=key==='tags'||key==='batch'?[]:'';
  if(JSON.stringify(base[key]??empty)!==JSON.stringify(next[key]??empty))keys.push(key);
 }
 if(['expression','condition_tree','editor_mode'].some(key=>JSON.stringify(base[key as keyof TemplateGroup])!==JSON.stringify(next[key as keyof TemplateGroup])))keys.push('rule');for(const key of ['name','event_id','scope','related_entities','priority','ignored'] as const)if(JSON.stringify(base[key])!==JSON.stringify(next[key]))keys.push(key);
 for(const [field,prefix] of [['conditions','condition'],['utterances','utterance']] as const){const ids=new Set([...base[field],...next[field]].map(v=>v.id));for(const id of ids)if(!(field==='conditions'&&keys.includes('rule'))&&JSON.stringify(base[field].find(v=>v.id===id))!==JSON.stringify(next[field].find(v=>v.id===id)))keys.push(prefix+':'+id);}
 return keys;
}
export function mergeTemplateWriteSnapshot(current:TemplateSnapshot,result:TemplateSnapshot,groupIds:string[]):TemplateSnapshot{
 // The read projection carries legacy editor rules needed for untouched groups.
 const previous=new Map(current.groups.map(group=>[group.id,group]));
 const changed=new Set(groupIds);
 const groups=result.groups.map(group=>changed.has(group.id)?group:previous.get(group.id)??group);
 const merged={...current,...result,groups};
 if(result.utterance_bindings||!current.utterance_bindings)return merged;
 // A write returns canonical groups. Wait for the fresh read projection on rule edits.
 const bindings=current.utterance_bindings;
 merged.utterance_bindings=Object.fromEntries(groups.flatMap(group=>{
  if(!Object.hasOwn(bindings,group.id))return [];
  const old=previous.get(group.id);
  if(old&&old!==group&&groupDiffKeys(old,group).some(key=>
   key==='rule'||key==='event_id'||key==='scope'||key.startsWith('condition:')))return [];
  return [[group.id,bindings[group.id]]];
 }));
 return merged;
}
export function selectedGroupChange(base:TemplateGroup,next:TemplateGroup,selected:string[],includeStatus=false):TemplateGroup{
 // The server compares the full accepted record with the proposal to close it.
 if(groupDiffKeys(base,next).every(key=>selected.includes(key))&&(!includeStatus||selected.includes('review_status')))return structuredClone(next);
 const result=applyTemplateGroupFields(base,next,selected);
 if(includeStatus&&selected.includes('review_status'))result.review_status=next.review_status;
 return result;
}
export function applyTemplateGroupFields(base:TemplateGroup,next:TemplateGroup,selected:string[]):TemplateGroup{
 const result=structuredClone(base);
 if(selected.includes('explanation')){
  if(Object.hasOwn(next,'explanation'))result.explanation=next.explanation;
  else delete result.explanation;
 }
 for(const key of Object.keys(templateMetadataLabels) as (keyof typeof templateMetadataLabels)[]){
  if(selected.includes(key)){
   if(Object.hasOwn(next,key))Object.assign(result,{[key]:next[key]});
   else delete result[key];
  }
 }
 if(selected.includes('rule'))Object.assign(result,{expression:next.expression,condition_tree:next.condition_tree,editor_mode:next.editor_mode,conditions:next.conditions});
for(const key of ['name','event_id','scope','related_entities','priority','ignored'] as const)if(selected.includes(key))Object.assign(result,{[key]:next[key]});
 for(const [field,prefix] of [['conditions','condition'],['utterances','utterance']] as const){const current=[...result[field]];for(const key of selected.filter(k=>k.startsWith(prefix+':'))){const id=key.slice(prefix.length+1),value=next[field].find(v=>v.id===id),at=current.findIndex(v=>v.id===id);if(at>=0)current.splice(at,1);if(value)current.splice(at<0?current.length:at,0,value as never);}Object.assign(result,{[field]:current});}
 return result;
}
export function downloadTemplates(document:unknown,name='话术模板库.json'){const href=URL.createObjectURL(new Blob([JSON.stringify(document,null,2)],{type:'application/json;charset=utf-8'})),a=window.document.createElement('a');a.href=href;a.download=name;a.click();URL.revokeObjectURL(href);}
const fieldNames:Record<string,string>={ignored:'忽略',name:'名称',effect:'效果',description:'说明',skills:'技能',stats:'属性',enhancements:'强化效果',level:'等级',value:'数值',text:'内容',health:'生命值',hp:'生命值',attack:'攻击',defense:'防御',speed:'速度',faction:'阵营',tier:'品阶',awakened:'觉醒',category:'类别',type:'类型',key:'参数引用',parameters:'参数',entity_categories:'实体类别',suggestions:'建议值',min:'建议下限',max:'建议上限'};
export function readableValue(value:unknown):string{if(value==null)return '无';if(Array.isArray(value))return value.map(readableValue).join('；');if(typeof value==='object'){const v=value as Record<string,unknown>;if(v.name&&Object.keys(v).every(k=>['id','name'].includes(k)))return String(v.name);return Object.entries(v).filter(([k])=>k!=='id'&&!/time|image|url|revision|source|updated|created|version/.test(k)).map(([k,v])=>(fieldNames[k]??'资料')+'：'+readableValue(v)).join('\n');}return typeof value==='boolean'?(value?'是':'否'):String(value);}
export function semanticChanges(before:unknown,after:unknown):{label:string;before:string;after:string}[]{
 if(JSON.stringify(before)===JSON.stringify(after))return [];
 if(before&&after&&typeof before==='object'&&typeof after==='object'&&!Array.isArray(before)&&!Array.isArray(after)){const a=before as Record<string,unknown>,b=after as Record<string,unknown>;return Array.from(new Set([...Object.keys(a),...Object.keys(b)])).filter(k=>k!=='id'&&!/time|image|url|revision|source|updated|created|version/.test(k)).flatMap(k=>JSON.stringify(a[k])===JSON.stringify(b[k])?[]:[{label:fieldNames[k]??'资料',before:readableValue(a[k]),after:readableValue(b[k])}]);}
 return [{label:'资料内容',before:readableValue(before),after:readableValue(after)}];
}
export function describeTemplateRecord(record:TemplateGroup|TemplateEvent|null|undefined,event?:TemplateEvent,scopeName:(id:string|null)=>string=id=>id??'通用'):string{
 if(!record)return '无记录';
 if('parameters' in record){
  const parameters=record.parameters.map(p=>{
   const fields=[p.name+' {'+p.key+'}',typeNames[p.type]];
   if(p.dsl_type)fields.push('条件数据类型：'+p.dsl_type);
   if(p.entity_categories?.length)fields.push('实体类别：'+p.entity_categories.join('、'));
   if(p.min!=null)fields.push('建议下限：'+p.min);
   if(p.max!=null)fields.push('建议上限：'+p.max);
   if(p.suggestions?.length)fields.push('建议值：'+p.suggestions.map(valueText).join('、'));
   return fields.join('，');
  });
  return [record.name,'分类：'+(record.category??'未分类'),...parameters].join('\n');
 }
 const metadata=(Object.keys(templateMetadataLabels) as (keyof typeof templateMetadataLabels)[]).flatMap(key=>{
  const value=record[key];
  return value?.length?[templateMetadataLabels[key]+'：'+(Array.isArray(value)?value.join('、'):value)]:[];
 });
 const details=metadata.length?'\n'+metadata.join('\n'):'';
 return record.name+details+'\n说明与依据：'+(record.explanation||'无')+'\n优先级：'+(record.priority??0)+'\n事件：'+(event?.name??record.event_id)+'\n棋手：'+scopeName(record.scope.player_id)+'\n阵容棋手组合：'+scopeName(record.scope.lineup_note_id)+'\n条件：\n'+(record.expression||record.conditions.map(c=>(event?.parameters.find(p=>p.key===c.parameter_key)?.name??c.parameter_key)+' '+operators[c.operator]+' '+valueText(c.value)).join('\n')||'不限制条件')+'\n全部话术：\n'+record.utterances.map(u=>u.text).join('\n')+'\n关联卡牌：'+record.conditions.flatMap(c=>{const p=event?.parameters.find(p=>p.key===c.parameter_key);return p?.type==='entity'?[valueText(c.value)]:[];}).join('、');
}
