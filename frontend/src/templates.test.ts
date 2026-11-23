import {describe,it,expect} from 'vitest';
import * as templates from './templates';
import {deriveTemplateEntities,resolveTemplateEntities,filterTemplateGroups,parseConditionValue,placeholderKeys,renderUtterance,groupDiffKeys,selectedGroupChange,semanticChanges,describeTemplateRecord,selectTemplateScope,loginWarningItems,type TemplateGroup,type TemplateWarning} from './templates';
const common:TemplateGroup={id:'common',name:'通用',event_id:'buy',scope:{player_id:null,lineup_note_id:null},conditions:[{id:'c',parameter_key:'hero',operator:'eq',value:{id:'hero:1',name:'虞姬'}}],utterances:[{id:'u',text:'标题参与话术搜索'}],related_entities:[]};
describe('template filtering and editing',()=>{
 it('copies a template into an independent editable draft and reserves a name in its event',()=>{
  const original:TemplateGroup={...common,ignored:true,version:'s1',mode:'万象大赛',tags:['技巧'],
   utterances:[{id:'u1',text:'第一句。',fixed:true},{id:'u2',text:'第二句。',ignored:true}],
   explanation_source:'正式卡牌库',condition_tree:{kind:'all',children:[]}};
  const draft=templates.copyTemplateGroup(original,[
   original,{...common,name:'通用（副本）'},{...common,event_id:'sell',name:'通用（副本 2）'},
  ]);
  expect(draft.name).toBe('通用（副本 2）');
  expect(draft.id).not.toBe(original.id);
  expect(draft.conditions[0].id).not.toBe(original.conditions[0].id);
  expect(draft.utterances.map(({id,...row})=>row)).toEqual([{text:'第一句。'},{text:'第二句。',ignored:true}]);
  expect(draft.utterances.map(row=>row.id)).not.toEqual(original.utterances.map(row=>row.id));
  expect(draft.ignored).toBe(true);
  expect(draft.explanation_source).toBe('正式卡牌库');
  draft.tags?.push('新增标签');
  draft.scope.player_id='p1';
  expect(original.tags).toEqual(['技巧']);
  expect(original.scope.player_id).toBeNull();
 });
 it('combines event, version, mode, every selected tag and fuzzy search',()=>{
  const group={...common,version:'s1',mode:'万象大赛',tags:['技巧','阵容']};
  const filters={event:'buy',player:'',lineup:'',query:'虞姬',version:'s1',mode:'万象大赛',tags:['阵容','技巧']};
  expect(filterTemplateGroups([group,{...group,id:'partial',tags:['技巧']},common],filters)).toEqual([group]);
  expect(filterTemplateGroups([group],{...filters,mode:'其他模式'})).toEqual([]);
  expect(groupDiffKeys(common,group)).toEqual(['version','mode','tags']);
  expect(selectedGroupChange(common,group,['tags'])).toEqual({...common,tags:group.tags});
 });
 it('distinguishes event parameter changes in review and history',()=>{
  const event={id:'custom',name:'自定义事件',parameters:[{id:'p',name:'参数',key:'arg1',type:'text' as const,dsl_type:'string'}]};
  const previous=describeTemplateRecord(event);
  expect(previous).toContain('条件数据类型：string');
  expect(describeTemplateRecord({...event,parameters:[{...event.parameters[0],dsl_type:'阵容'}]})).toContain('条件数据类型：阵容');
  const numeric=describeTemplateRecord({...event,parameters:[{id:'n',name:'等级',key:'level',type:'number',min:0,max:6,suggestions:[0,3]}]});
  for(const value of ['建议下限：0','建议上限：6','建议值：0、3'])expect(numeric).toContain(value);
 });
 it('reviews explanations independently and treats legacy missing text as empty',()=>{
  const next={...common,name:'改名',explanation:'第一行\n依据'};
  expect(groupDiffKeys(common,next)).toEqual(['explanation','name']);
  expect(groupDiffKeys(common,{...common,explanation:''})).toEqual([]);
  expect(selectedGroupChange(common,next,['explanation'])).toEqual({...common,explanation:next.explanation});
  expect(selectedGroupChange(next,common,['explanation'])).toStrictEqual({...common,name:next.name});
  expect(selectedGroupChange(common,next,['name']).explanation).toBeUndefined();
  expect(describeTemplateRecord(next)).toContain('说明与依据：第一行\n依据');
 });
 it('preserves the proposed JSON representation on full approval',()=>{
  const explicitEmpty={...common,explanation:''};
  expect(selectedGroupChange(common,explicitEmpty,[])).toStrictEqual(explicitEmpty);
  expect(selectedGroupChange(explicitEmpty,common,['record'])).toStrictEqual(common);
  const renamed={...common,name:'更新'};
  expect(selectedGroupChange(explicitEmpty,renamed,['name'])).toStrictEqual(renamed);
  expect(selectedGroupChange(renamed,explicitEmpty,['name'])).toStrictEqual(explicitEmpty);
  const moreChanges={...renamed,priority:2};
  expect(selectedGroupChange(explicitEmpty,moreChanges,['name'])).toStrictEqual({...explicitEmpty,name:renamed.name});
 });
 it('shows only unseen warning changes in the login popup while preserving the full badge list',()=>{
  const seen:TemplateWarning={group_id:'seen',group_name:'已知变化',revision:'a',entities:[]},unseen={...seen,group_id:'unseen',group_name:'新增变化'};
  const snapshot={items:[seen,unseen],unseen_items:[unseen],notification_revision:'both',unseen:true};
  expect(loginWarningItems(snapshot).map(w=>w.group_id)).toEqual(['unseen']);
  expect(snapshot.items.map(w=>w.group_id)).toEqual(['seen','unseen']);
  expect(loginWarningItems({...snapshot,unseen_items:[]})).toEqual([]);
 });
 it('binds a lineup to its player and clears incompatible lineups on player change',()=>{
  const notes=[{id:'n',player_id:'p1'},{id:'old',player_id:'p2'}];
  expect(selectTemplateScope({player_id:null,lineup_note_id:null},'lineup','n',notes)).toEqual({player_id:'p1',lineup_note_id:'n'});
  expect(selectTemplateScope({player_id:'p1',lineup_note_id:'n'},'player','p2',notes)).toEqual({player_id:'p2',lineup_note_id:null});
  expect(selectTemplateScope({player_id:'p1',lineup_note_id:'n'},'lineup','',notes)).toEqual({player_id:'p1',lineup_note_id:null});
 });
 it('presents changed semantic fields without raw metadata or JSON keys',()=>{
  expect(semanticChanges({effect:'旧效果',updated_at:'1',image_url:'a'},{effect:'新效果',updated_at:'2',image_url:'b'})).toEqual([{label:'效果',before:'旧效果',after:'新效果'}]);
  expect(describeTemplateRecord(common)).toContain('虞姬');
  expect(describeTemplateRecord(common)).not.toContain('parameter_key');
 });
 it('includes compatible common scopes but excludes another specific scope',()=>{
  const groups=[common,{...common,id:'specific',scope:{player_id:'p1',lineup_note_id:'n1'}},{...common,id:'other',scope:{player_id:'p2',lineup_note_id:'n1'}}];
  expect(filterTemplateGroups(groups,{event:'',player:'p1',lineup:'n1',query:''}).map(g=>g.id)).toEqual(['common','specific']);
  expect(filterTemplateGroups(groups,{event:'',player:'common',lineup:'',query:''}).map(g=>g.id)).toEqual(['common']);
 });
 it('ANDs comma separated condition values, including numeric endpoints and booleans',()=>{
  const g={...common,conditions:[...common.conditions,{id:'b',parameter_key:'round',operator:'between' as const,value:[3,7]},{id:'t',parameter_key:'ready',operator:'eq' as const,value:true}]};
  expect(filterTemplateGroups([g],{event:'buy',player:'',lineup:'',query:'虞姬，7,true'})).toHaveLength(1);
  expect(filterTemplateGroups([g],{event:'buy',player:'',lineup:'',query:'虞姬,9'})).toHaveLength(0);
  expect(filterTemplateGroups([g],{event:'',player:'',lineup:'',query:'标题'})).toHaveLength(1);
 });
 it('matches entity IDs and aliases alongside another AND value',()=>{
  const group={...common,conditions:[...common.conditions,{id:'n',parameter_key:'round',operator:'eq' as const,value:4}]};
  const catalog=[{id:'hero:1',name:'虞姬',aliases:['虞美人']}];
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'hero:1,4'},catalog)).toHaveLength(1);
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'虞美人,4'},catalog)).toHaveLength(1);
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'虞美人,4'},[...catalog,{id:'hero:1',name:'虞姬',aliases:[]}])).toHaveLength(1);
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'虞美人,5'},catalog)).toHaveLength(0);
 });
 it('finds spoken text and the displayed legacy condition in the same group',()=>{
  const group={...common,conditions:[{id:'n',parameter_key:'round',operator:'gte' as const,value:4}]};
  const events=[{id:'buy',name:'购买英雄',parameters:[{id:'round',key:'round',name:'当前回合',type:'number' as const}]}];
  const find=(query:string,event='buy')=>filterTemplateGroups([group],{event,player:'',lineup:'',query},[],{events});
  expect(find('参与话术')).toEqual([group]);
  expect(find('当前回合 ≥ 4，参与话术')).toEqual([group]);
  expect(find('当前回合 ≥ 5，参与话术')).toEqual([]);
  expect(find('当前回合','sell')).toEqual([]);
 });
 it('finds both rendered utterance text and the authored slot reference',()=>{
  const group={...common,conditions:[],utterances:[{id:'u',text:'先留{arg1.名称}，下轮再换'}]};
  const labels={utteranceBindings:{common:{'arg1.名称':['虞姬','李白']}}};
  const find=(query:string)=>filterTemplateGroups([group],{query,event:'',player:'',lineup:''},[],labels);
  expect(find('先留虞姬/李白')).toEqual([group]);
  expect(find('先留{arg1.名称}')).toEqual([group]);
  expect(find('先留赵云')).toEqual([]);
 });
 it('keeps condition bindings through text edits and clears them when the rule changes',()=>{
  const group={...common,expression:'arg1.名称 in ["虞姬","李白"]'};
  const bindings={common:{'arg1.名称':['虞姬','李白']}};
  const current={schema_version:3,revision:'original',events:[],groups:[group],utterance_bindings:bindings};
  const result={schema_version:3,revision:'changed',events:[],groups:[{...group,utterances:[{id:'u',text:'保留{arg1.名称}'}]}]};
  expect(templates.mergeTemplateWriteSnapshot(current,result,['common']).utterance_bindings).toEqual(bindings);
  result.groups[0]={...group,expression:'arg1.名称 in ["亚瑟"]'};
  expect(templates.mergeTemplateWriteSnapshot(current,result,['common']).utterance_bindings?.common).toBeUndefined();
 });
 it('keeps commas inside copied conditions and splits only top-level search terms',()=>{
  const target=JSON.stringify({类型:'单位',名称:'甲"，乙'});
  const expression='玩家.战场.计数(标签, "登场") >= 2 and arg1 in ["电磁弹簧","等离子屏障"] and arg2 is '+target;
  const group={...common,conditions:[],expression,scope:{player_id:'p1',lineup_note_id:'n1'}};
  const filters={event:'buy',player:'p1',lineup:'n1'};
  const labels={scopeName:(id:string|null)=>id==='p1'?'班叔':id==='n1'?'机关队':''};
  const find=(query:string)=>filterTemplateGroups([group],{...filters,query},[],labels);
  expect(find('玩家.使用棋手 is "班叔" and 玩家.使用阵容 is "机关队" and ('+expression+')')).toEqual([group]);
  expect(find('计数(标签, "登场") >= 2，参与话术')).toEqual([group]);
  expect(find('arg1 in ["电磁弹簧","等离子屏障"]')).toEqual([group]);
  expect(find('arg2 is '+target+',参与话术')).toEqual([group]);
  expect(find('计数(标签, "整备") >= 2，参与话术')).toEqual([]);
  const splitOnly={...group,expression:'玩家.战场.计数(标签, "整备") >= 2 and 玩家.战场.计数(阵营, "登场") >= 2'};
  expect(filterTemplateGroups([splitOnly],{...filters,query:'计数(标签, "登场") >= 2'},[],labels)).toEqual([]);
 });
 it('rejects invalid typed numbers and preserves explicit false and entity ids',()=>{
  expect(parseConditionValue('number','between','2','5')).toEqual([2,5]);
  expect(()=>parseConditionValue('number','between','9','2')).toThrow();
  expect(()=>parseConditionValue('number','eq','')).toThrow();
  expect(parseConditionValue('boolean','eq','false')).toBe(false);
  expect(parseConditionValue('entity','eq','hero:1','虞姬')).toEqual({id:'hero:1',name:'虞姬'});
 });
 it('ignores double brace literals while finding parameter references',()=>{
  expect(placeholderKeys('花费{cost}，{{不是参数}}，{hero}，{cost}')).toEqual(['cost','hero']);
 });
 it('preserves numeric references and only expands named candidates in the preview',()=>{
  const number='{玩家.战场.计数(阵营, "{hero}")}';
  const text='给{hero}装备，目前在场有'+number+'名。';
  expect(placeholderKeys(text)).toEqual(['hero']);
  expect(placeholderKeys(number)).toEqual([]);
  expect(renderUtterance(text,{hero:['蒙恬','刘禅']})).toBe('给蒙恬/刘禅装备，目前在场有'+number+'名。');
 });
 it('keeps unapproved condition and utterance changes at their base values',()=>{
  const next={...common,name:'新组名',conditions:[{...common.conditions[0],value:{id:'hero:2',name:'李白'}}],utterances:[{id:'u',text:'新话术'},{id:'u2',text:'增加'}]};
  expect(selectedGroupChange(common,next,['utterance:u2'])).toEqual({...common,utterances:[...common.utterances,{id:'u2',text:'增加'}]});
 });
});


describe('derived template entity links',()=>{
 const event={id:'buy',name:'购买',parameters:[{id:'p',key:'hero',name:'英雄',type:'entity' as const,entity_categories:['heroes']}]};
 const cards=[{id:'h1',name:'虞姬',category:'heroes',aliases:['虞美人']},{id:'h2',name:'虞姬',category:'heroes',aliases:[]},{id:'e1',name:'虞姬',category:'equipment',aliases:[]},{id:'p1',name:'棋手甲',category:'players',aliases:[]}];
 it('uses trimmed exact names before aliases, category restrictions and every version',()=>{
  expect(resolveTemplateEntities(' 虞姬 ',cards,['heroes']).map(e=>e.id)).toEqual(['h1','h2']);
  expect(resolveTemplateEntities('虞美人',cards,['heroes']).map(e=>e.id)).toEqual(['h1','h2']);
  expect(resolveTemplateEntities('虞姬',cards)).toEqual([]);
  expect(resolveTemplateEntities('虞姬',cards,['heroes','equipment']).map(e=>e.id)).toEqual(['e1','h1','h2']);
  expect(resolveTemplateEntities('虞',cards,['heroes'])).toEqual([]);
  expect(resolveTemplateEntities('虞姬',[...cards,{id:'h3',name:'虞美人',category:'heroes',aliases:['虞姬']}],['heroes']).map(e=>e.id)).toEqual(['h1','h2']);
 });
 it('retains authoritative live and retired versions across renames until selectors change',()=>{
  const group={...common,conditions:[{...common.conditions[0],value:{id:'h1',name:'虞姬'}}]};
  const old=[{id:'h1',name:'虞姬'},{id:'h2',name:'虞姬'}];
  const anchorRenamed=cards.map(c=>c.id==='h1'?{...c,name:'新名字',aliases:[]}:c);
  expect(deriveTemplateEntities(group,event,anchorRenamed,old).map(e=>e.id).sort()).toEqual(['h1','h2']);
  const nonAnchorRenamed=cards.map(c=>c.id==='h2'?{...c,name:'新版名字',aliases:[]}:c);
  expect(deriveTemplateEntities(group,event,nonAnchorRenamed,[{id:'h1',name:'虞姬'},{id:'h2',name:'新版名字'}]).map(e=>e.id).sort()).toEqual(['h1','h2']);
  const noConditions={...group,conditions:[]};
  expect(deriveTemplateEntities(noConditions,event,anchorRenamed,old,group)).toEqual([]);
  const changed={...group,conditions:[{...group.conditions[0],value:{id:'h3',name:'李白'}}]};
  const updated=[...nonAnchorRenamed,{id:'h3',name:'李白',category:'heroes',aliases:[]}];
  expect(deriveTemplateEntities(changed,event,updated,old,group)).toEqual([{id:'h3',name:'李白'}]);
 });
 it('keeps each unchanged condition history when a different selector is removed or changed',()=>{
  const original={...common,conditions:[{id:'c',parameter_key:'hero',operator:'eq' as const,value:{id:'h1',name:'虞姬'}},{id:'other',parameter_key:'hero',operator:'eq' as const,value:{id:'q1',name:'李白'}}]};
  const catalog=[...cards,{id:'q1',name:'李白',category:'heroes',aliases:[]},{id:'q2',name:'旧版李白',category:'heroes',aliases:[]}].map(c=>c.id==='h2'?{...c,name:'新版虞姬'}:c);
  const links={c:[{id:'h1',name:'虞姬'},{id:'h2',name:'新版虞姬'}],other:[{id:'q1',name:'李白'},{id:'q2',name:'旧版李白'}]};
  const archive=Object.values(links).flat();
  const removed={...original,conditions:[original.conditions[0]]};
  expect(deriveTemplateEntities(removed,event,catalog,archive,original,links).map(e=>e.id).sort()).toEqual(['h1','h2']);
  const replaced={...original,conditions:[{...original.conditions[0],value:{id:'q1',name:'李白'}},original.conditions[1]]};
  expect(deriveTemplateEntities(replaced,event,catalog,archive,original,links).map(e=>e.id).sort()).toEqual(['q1','q2']);
  const switchedType={...event,parameters:[{...event.parameters[0],entity_categories:['equipment']}]};
  expect(deriveTemplateEntities(removed,switchedType,catalog,archive,original,links,event).map(e=>e.id)).not.toContain('h2');
 });
 it('derives only actual entity conditions and scope, retaining retired archives',()=>{
  const group={...common,scope:{player_id:'p1',lineup_note_id:null},related_entities:[{id:'manual',name:'手动旧记录'}],utterances:[{id:'u',text:'手动旧记录'}]};
  expect(deriveTemplateEntities(group,event,cards).map(e=>e.id)).toEqual(['h1','h2','p1']);
  const retired={...common,conditions:[{...common.conditions[0],value:{id:'retired',name:'旧名字'}}]};
  expect(deriveTemplateEntities(retired,event,cards,[{id:'retired',name:'旧名字'}])).toEqual([{id:'retired',name:'旧名字'}]);
  const renamed=[{id:'hero:1',name:'新名字',category:'heroes',aliases:[]}];
  expect(deriveTemplateEntities(common,event,renamed)).toEqual([{id:'hero:1',name:'新名字'}]);
  expect(deriveTemplateEntities({...group,conditions:[],scope:{player_id:null,lineup_note_id:null}},event,cards,[{id:'hero:1',name:'虞姬'}],group)).toEqual([]);
 });
});
