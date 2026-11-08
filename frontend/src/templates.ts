export type ParameterType='text'|'number'|'boolean'|'entity';
export type TemplateEntity={id:string;name:string};
export type TemplateParameter={id:string;key:string;name:string;type:ParameterType;entity_categories?:string[];suggestions?:unknown[];min?:number;max?:number};
export type TemplateEvent={id:string;name:string;category?:string;parameters:TemplateParameter[]};
export type ConditionOperator='eq'|'ne'|'gt'|'gte'|'lt'|'lte'|'between';
export type TemplateCondition={id:string;parameter_key:string;operator:ConditionOperator;value:unknown};
export type TemplateGroup={id:string;name:string;event_id:string;scope:{player_id:string|null;lineup_note_id:string|null};conditions:TemplateCondition[];utterances:{id:string;text:string}[];related_entities:TemplateEntity[]};
export type TemplateSnapshot={schema_version:1;revision:string;events:TemplateEvent[];groups:TemplateGroup[];entity_links?:Record<string,TemplateEntity[]>;entity_condition_links?:Record<string,Record<string,TemplateEntity[]>>};
// Portable JSON is a separate contract from the canonical editor/proposal model.
export type PortableTemplateParameter=Omit<TemplateParameter,'id'|'suggestions'>&{id?:string;suggestions?:Array<string|number|boolean>};
export type PortableTemplateEvent=Omit<TemplateEvent,'id'|'parameters'>&{id?:string;parameters:PortableTemplateParameter[]};
export type PortableTemplateGroup={id?:string;name:string;event_id?:string;event_name?:string;scope:TemplateGroup['scope'];conditions:Array<Omit<TemplateCondition,'id'|'value'>&{value:string|number|boolean|[number,number]}>;utterances:string[]};
export type PortableTemplateLibrary={kind:'speech-template-library';schema_version:2;events:PortableTemplateEvent[];groups:PortableTemplateGroup[]};
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
 if(group.event_id===savedGroup.event_id&&group.scope.player_id===savedGroup.scope.player_id&&JSON.stringify(selectors(group,event))===JSON.stringify(selectors(savedGroup,savedEvent)))for(const ref of archive)remember(ref);
 return [...result.values()];
}
export type TemplateChange={kind:'event'|'group';action:'put'|'delete';id:string;value?:TemplateEvent|TemplateGroup};
export type TemplateProposal={id:string;author:string;status:string;created_at:string;revision:string;proposal_revision?:string;changes:TemplateChange[];base:{events:TemplateEvent[];groups:TemplateGroup[]}};
export type TemplateWarning={group_id:string;group_name:string;revision:string;entities:{id:string;name:string;before:unknown;after:unknown}[]};
export type WarningSnapshot={items:TemplateWarning[];unseen_items?:TemplateWarning[];notification_revision:string;unseen:boolean};
export function loginWarningItems(snapshot:WarningSnapshot){return snapshot.unseen_items??(snapshot.unseen?snapshot.items:[]);}
export type TemplateFilters={event:string;player:string;lineup:string;query:string};
export const operators:Record<ConditionOperator,string>={eq:'等于',ne:'不等于',gt:'>',gte:'≥',lt:'<',lte:'≤',between:'介于'};
export const typeNames:Record<ParameterType,string>={text:'文本',number:'数字',boolean:'是/否',entity:'实体卡牌'};
export function templateId(prefix:string){return prefix+'_'+crypto.randomUUID();}
export function valueText(value:unknown):string{if(Array.isArray(value))return value.map(valueText).join(' 至 ');if(typeof value==='object'&&value)return String((value as TemplateEntity).name??(value as TemplateEntity).id??'');if(typeof value==='boolean')return value?'是 true':'否 false';return String(value??'');}
export function filterTemplateGroups(groups:TemplateGroup[],filters:TemplateFilters,catalog:{id:string;name:string;aliases?:string[]}[]=[]){
 const compatible=(value:string|null,filter:string)=>!filter||(filter==='common'?value===null:value===null||value===filter);
 const terms=filters.query.toLocaleLowerCase().split(/[,，]/).map(v=>v.trim()).filter(Boolean);
 const entities=new Map<string,{name:string;aliases:string[]}>();for(const e of catalog){const previous=entities.get(e.id);entities.set(e.id,{name:e.name,aliases:[...new Set([...(previous?.aliases??[]),...(e.aliases??[]),...(previous?.name&&previous.name!==e.name?[previous.name]:[])])]});}
 const searchValue=(value:unknown)=>{const ref=value as TemplateEntity|null;if(ref&&typeof ref==='object'&&!Array.isArray(ref)&&ref.id){const entity=entities.get(ref.id);return [ref.id,ref.name,entity?.name,...entity?.aliases??[]].filter(Boolean).join(' ').toLocaleLowerCase();}return valueText(value).toLocaleLowerCase();};
 return groups.filter(group=>(!filters.event||group.event_id===filters.event)&&compatible(group.scope.player_id,filters.player)&&compatible(group.scope.lineup_note_id,filters.lineup)&&terms.every(term=>group.conditions.some(c=>searchValue(c.value).includes(term))));
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
export function placeholderKeys(text:string){return [...new Set(Array.from(text.replace(/\{\{[\s\S]*?\}\}/g,'' ).matchAll(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g),m=>m[1]))];}
export function groupDiffKeys(base:TemplateGroup,next:TemplateGroup){
 const keys:string[]=[];for(const key of ['name','event_id','scope','related_entities'] as const)if(JSON.stringify(base[key])!==JSON.stringify(next[key]))keys.push(key);
 for(const [field,prefix] of [['conditions','condition'],['utterances','utterance']] as const){const ids=new Set([...base[field],...next[field]].map(v=>v.id));for(const id of ids)if(JSON.stringify(base[field].find(v=>v.id===id))!==JSON.stringify(next[field].find(v=>v.id===id)))keys.push(prefix+':'+id);}
 return keys;
}
export function selectedGroupChange(base:TemplateGroup,next:TemplateGroup,selected:string[]):TemplateGroup{
 const result=structuredClone(base);for(const key of ['name','event_id','scope','related_entities'] as const)if(selected.includes(key))Object.assign(result,{[key]:next[key]});
 for(const [field,prefix] of [['conditions','condition'],['utterances','utterance']] as const){const current=[...result[field]];for(const key of selected.filter(k=>k.startsWith(prefix+':'))){const id=key.slice(prefix.length+1),value=next[field].find(v=>v.id===id),at=current.findIndex(v=>v.id===id);if(at>=0)current.splice(at,1);if(value)current.splice(at<0?current.length:at,0,value as never);}Object.assign(result,{[field]:current});}
 return result;
}
export function downloadTemplates(document:unknown,name='话术模板库.json'){const href=URL.createObjectURL(new Blob([JSON.stringify(document,null,2)],{type:'application/json;charset=utf-8'})),a=window.document.createElement('a');a.href=href;a.download=name;a.click();URL.revokeObjectURL(href);}
const fieldNames:Record<string,string>={name:'名称',effect:'效果',description:'说明',skills:'技能',stats:'属性',enhancements:'强化效果',level:'等级',value:'数值',text:'内容',health:'生命值',hp:'生命值',attack:'攻击',defense:'防御',speed:'速度',faction:'阵营',tier:'品阶',awakened:'觉醒',category:'类别',type:'类型',key:'参数引用',parameters:'参数',entity_categories:'实体类别',suggestions:'建议值',min:'建议下限',max:'建议上限'};
export function readableValue(value:unknown):string{if(value==null)return '无';if(Array.isArray(value))return value.map(readableValue).join('；');if(typeof value==='object'){const v=value as Record<string,unknown>;if(v.name&&Object.keys(v).every(k=>['id','name'].includes(k)))return String(v.name);return Object.entries(v).filter(([k])=>k!=='id'&&!/time|image|url|revision|source|updated|created|version/.test(k)).map(([k,v])=>(fieldNames[k]??'资料')+'：'+readableValue(v)).join('\n');}return typeof value==='boolean'?(value?'是':'否'):String(value);}
export function semanticChanges(before:unknown,after:unknown):{label:string;before:string;after:string}[]{
 if(JSON.stringify(before)===JSON.stringify(after))return [];
 if(before&&after&&typeof before==='object'&&typeof after==='object'&&!Array.isArray(before)&&!Array.isArray(after)){const a=before as Record<string,unknown>,b=after as Record<string,unknown>;return Array.from(new Set([...Object.keys(a),...Object.keys(b)])).filter(k=>k!=='id'&&!/time|image|url|revision|source|updated|created|version/.test(k)).flatMap(k=>JSON.stringify(a[k])===JSON.stringify(b[k])?[]:[{label:fieldNames[k]??'资料',before:readableValue(a[k]),after:readableValue(b[k])}]);}
 return [{label:'资料内容',before:readableValue(before),after:readableValue(after)}];
}
export function describeTemplateRecord(record:TemplateGroup|TemplateEvent|null|undefined,event?:TemplateEvent,scopeName:(id:string|null)=>string=id=>id??'通用'):string{
 if(!record)return '无记录';if('parameters' in record)return record.name+'\n分类：'+(record.category??'未分类')+'\n'+record.parameters.map(p=>p.name+' {'+p.key+'}，'+typeNames[p.type]+(p.entity_categories?.length?'，实体类别：'+p.entity_categories.join('、'):'')).join('\n');
 return record.name+'\n事件：'+(event?.name??record.event_id)+'\n棋手：'+scopeName(record.scope.player_id)+'\n阵容棋手组合：'+scopeName(record.scope.lineup_note_id)+'\n同时满足：\n'+(record.conditions.map(c=>(event?.parameters.find(p=>p.key===c.parameter_key)?.name??c.parameter_key)+' '+operators[c.operator]+' '+valueText(c.value)).join('\n')||'不限制条件')+'\n全部话术：\n'+record.utterances.map(u=>u.text).join('\n')+'\n关联卡牌：'+record.conditions.flatMap(c=>{const p=event?.parameters.find(p=>p.key===c.parameter_key);return p?.type==='entity'?[valueText(c.value)]:[];}).join('、');
}
