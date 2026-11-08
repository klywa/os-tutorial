import {describe,it,expect} from 'vitest';
import {deriveTemplateEntities,resolveTemplateEntities,filterTemplateGroups,parseConditionValue,placeholderKeys,selectedGroupChange,semanticChanges,describeTemplateRecord,selectTemplateScope,loginWarningItems,type TemplateGroup,type TemplateWarning} from './templates';
const common:TemplateGroup={id:'common',name:'通用',event_id:'buy',scope:{player_id:null,lineup_note_id:null},conditions:[{id:'c',parameter_key:'hero',operator:'eq',value:{id:'hero:1',name:'虞姬'}}],utterances:[{id:'u',text:'标题不参与值搜索'}],related_entities:[]};
describe('template filtering and editing',()=>{
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
  expect(filterTemplateGroups([g],{event:'',player:'',lineup:'',query:'标题'})).toHaveLength(0);
 });
 it('matches entity IDs and aliases alongside another AND value',()=>{
  const group={...common,conditions:[...common.conditions,{id:'n',parameter_key:'round',operator:'eq' as const,value:4}]};
  const catalog=[{id:'hero:1',name:'虞姬',aliases:['虞美人']}];
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'hero:1,4'},catalog)).toHaveLength(1);
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'虞美人,4'},catalog)).toHaveLength(1);
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'虞美人,4'},[...catalog,{id:'hero:1',name:'虞姬',aliases:[]}])).toHaveLength(1);
  expect(filterTemplateGroups([group],{event:'',player:'',lineup:'',query:'虞美人,5'},catalog)).toHaveLength(0);
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
