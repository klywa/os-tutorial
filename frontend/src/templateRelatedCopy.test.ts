import {describe,expect,it} from 'vitest';
import {relatedCopy,relatedDisplayRows,relatedEventDefinition,relatedTargets} from './templateRelatedCopy';
import type {TemplateGroup} from './templates';

const makeGroup=(event:string,extra_key:string,expression:string,text:string):TemplateGroup=>({
 id:'source',name:'原组',event_id:event,syntax_version:'0.4',extra_key,expression,conditions:[],
 scope:{player_id:null,lineup_note_id:null},related_entities:[],review_status:'final_reviewed',
 wording_brief:'旧构思',explanation_source:'来源',utterances:[{id:'line',text,fixed:true}],
});

describe('举一反三',()=>{
 it('maps equipment conditions while retaining every utterance in order and its flags',()=>{
  const wear='解释为何穿戴装备',forge='解释为何铸造装备';
  const source=makeGroup(wear,'吕布-冥王','"动作.装备" in 动作.装备.标签','穿戴冥王能增强承伤能力。');
  source.utterances.push({id:'line2',text:'{{动作.目标英雄.名称}}更耐打。',ignored:true},
   {id:'line3',text:'穿戴冥王能增强承伤能力。',fixed:true});
  const copy=relatedCopy(source,wear,relatedEventDefinition(forge),[]);
  expect(copy).toMatchObject({kind:'new',group:{extra_key:'吕布-*-冥王',
   name:'解释为何将吕布的旧装备铸造成冥王',
   expression:'"动作.装备" in 动作.目标装备.标签',syntax_version:'0.5',
   review_status:null,explanation_source:'来源'}});
  expect(copy.group.utterances.map(({id,...row})=>row)).toEqual(source.utterances.map(({id,...row})=>row));
  expect(copy.group.utterances.every(row=>!source.utterances.some(original=>original.id===row.id))).toBe(true);
  expect(copy.group.wording_brief).toBeUndefined();
  expect(relatedCopy(copy.group,forge,relatedEventDefinition(wear),[])).toMatchObject({group:{extra_key:'吕布-冥王'}});
  const unsupported=makeGroup(wear,'吕布-冥王','','{{动作.装备.名称}}增强承伤能力。');
  expect(()=>relatedCopy(unsupported,wear,relatedEventDefinition(forge),[])).toThrow('话术槽位');
 });
 it('preserves source prose even when it names the source action',()=>{
  const a='解释为何竞拍目标英雄（第1次拍卖）',b='解释为何竞拍目标英雄（第2次拍卖）',buy='解释为何购买英雄';
  const source=makeGroup(a,'吕布','动作.出价 < 5','吕布可补充终局战力。');
  expect(relatedTargets(a)).toContain(b);
  expect(relatedCopy(source,a,relatedEventDefinition(b),[])).toMatchObject({kind:'new',group:{expression:'动作.出价 < 5'}});
  expect(()=>relatedCopy(source,a,relatedEventDefinition(buy),[])).toThrow('出价');
  const effect='解释为何购买效果牌',choice='解释为何选择效果牌';
  expect(relatedCopy(makeGroup(effect,'唤醒','','买下唤醒后能触发登场。'),effect,relatedEventDefinition(choice),[]))
   .toMatchObject({group:{utterances:[{text:'买下唤醒后能触发登场。',fixed:true}]}});
  const transfer='解释为何转移装备',wear='解释为何穿戴装备';
  expect(()=>relatedCopy(makeGroup(transfer,'吕布-曹操-冥王','','冥王增加承伤能力。'),transfer,relatedEventDefinition(wear),[]))
   .toThrow('原英雄');
 });
 it('locates a target with equivalent formatting and retains existing metadata',()=>{
  const buy='解释为何购买效果牌',choose='解释为何选择效果牌',event=relatedEventDefinition(choose);
  const source=makeGroup(buy,'唤醒','我方.等级 >= 4','唤醒可触发登场。');
  const existing={...source,id:'already',event_id:event.id,expression:'(我方.等级>=4)'};
  expect(relatedCopy(source,buy,event,[existing])).toEqual({kind:'existing',group:existing});
  expect(relatedCopy(source,buy,event,[{...existing,name:'另一个组名'}]).kind).toBe('existing');
  expect(relatedCopy(source,buy,event,[{...existing,expression:'我方.等级 >= 5'}]).kind).toBe('new');
  for(const utterances of [[{...existing.utterances[0],ignored:true}],[{...existing.utterances[0],fixed:false}],
   [{...existing.utterances[0],text:'另一句话。'}]]){
   const result=relatedCopy(source,buy,event,[{...existing,utterances}]);
   expect(result.kind).toBe('new');
   expect(result.group.name).toBe(existing.name);
  }
 });
 it('reconciles stale related-copy titles with the existing equivalent target without altering other conditions',()=>{
  const wear='解释为何穿戴装备',forge=relatedEventDefinition('解释为何铸造装备');
  const rule='none(动作.目标英雄.装备列表, .名称 == "无尽巨剑")';
  const source={...makeGroup(wear,'吕布-无尽巨剑',rule,'穿戴无尽巨剑可提升暴击。'),name:'解释为何给吕布穿戴无尽巨剑'};
  const first={...makeGroup(forge.id,'吕布-*-无尽巨剑',rule,'铸造无尽巨剑可提升暴击。'),id:'target',name:'解释为何将吕布的旧装备铸造成无尽巨剑'};
  const stale={...first,id:'stale',name:source.name,utterances:source.utterances};
  const other={...stale,id:'other',expression:'我方.等级 >= 5'};
  const prepared=relatedCopy(source,wear,forge,[first,other]);
  expect(prepared).toMatchObject({kind:'new',group:{name:first.name}});
  expect(prepared.renamePeers).toBeUndefined();
  expect(relatedCopy(source,wear,forge,[first,stale,other])).toEqual({kind:'existing',group:stale,
   renamePeers:[{...stale,name:first.name}]});
 });
 it('places a related result behind its source without duplicating an already visible row',()=>{
  const parent=makeGroup('购买','吕布','','吕布提供终局输出。');
  const child={...parent,id:'target',event_id:'选择'};
  const another={...parent,id:'another'};
  const groups=new Map([parent,child,another].map(group=>[group.id,group]));
  const links=new Map([[child.id,parent.id]]);
  expect(relatedDisplayRows([child,parent,another],groups,links).rows.map(group=>group.id))
   .toEqual([parent.id,child.id,another.id]);
  expect(relatedDisplayRows([parent],groups,links).roots.get(child.id)).toBe(parent);
  expect(relatedDisplayRows([child],groups,links).rows).toEqual([child]);
 });
});
