import {describe,expect,it} from 'vitest';
import {addLineupRosters,buildLineupTabs,lineupBoardRows,lineupRosterNames,unscopedLineup} from './TemplateLineupBoard';
import {buildTemplateEntityIndex} from './templateEntityIndex';
import type {TemplateEvent,TemplateGroup} from './templates';

const makeGroup=(id:string,event_id:string,scope:Partial<TemplateGroup['scope']>={},expression='',extra_key=''):TemplateGroup=>({
 id,event_id,name:id,scope:{player_id:null,lineup_note_id:null,...scope},syntax_version:'0.4',expression,extra_key,
 conditions:[],related_entities:[],utterances:[{id:id+'-line',text:'补充战力。'}],
});

describe('阵容看板',()=>{
 it('groups unbound hero events once in the hero column and keeps other events separate',()=>{
  const events:TemplateEvent[]=[
   {id:'deploy',name:'解释为何上阵英雄',parameters:[]},
   {id:'auction',name:'解释为何竞拍目标英雄（第2次拍卖）',parameters:[]},
   {id:'ready',name:'解释为何准备战斗',parameters:[]},
  ];
  const groups=[makeGroup('deploy-all','deploy',{},'','*'),makeGroup('auction-all','auction',{},'','*'),
   makeGroup('named','deploy',{},'','吕布'),makeGroup('battle','ready')];
  const entries=buildTemplateEntityIndex(groups,events,[{id:'lu',name:'吕布',category:'heroes'}],undefined,undefined,true);
  const rows=lineupBoardRows(groups,entries,new Set(),[],events);
  expect(rows.generalHeroEvents).toEqual(new Map([['deploy',new Set(['deploy-all'])],['auction',new Set(['auction-all'])]]));
  expect(rows.columnIds.get('heroes')).toEqual(new Set(['named','deploy-all','auction-all']));
  expect(rows.other).toEqual(new Map([['ready',new Set(['battle'])]]));
 });
 it('uses notes to enrich an open file without creating absent lineups or player tabs',()=>{
  const tabs=buildLineupTabs([
   makeGroup('file-group','deploy',{lineup_note_id:'三分登场',player_id:'白歌'}),
   makeGroup('generic','deploy'),
  ],id=>id,true);
  const rosters=addLineupRosters(tabs,[
   {title:'三分登场-白歌',lineup_name:'三分登场',player_id:'白歌',lineup_heroes:['小乔','孙尚香']},
   {title:'三分登场-镜',lineup_name:'三分登场',player_id:'镜',lineup_heroes:['吕布']},
   {title:'常小娥灵活4人组',lineup_heroes:['刘禅']},
  ],id=>id,false);
  expect([...tabs.keys()]).toEqual(['三分登场',unscopedLineup]);
  expect([...tabs.get('三分登场')!.keys()]).toEqual(['白歌']);
  expect([...lineupRosterNames(rosters,'三分登场','白歌')]).toEqual(['小乔','孙尚香']);
  expect([...lineupRosterNames(rosters,'三分登场','')]).toEqual(['小乔','孙尚香']);
 });
 it('includes roster heroes with no templates, inherits fallbacks by hero and deduplicates a column drill',()=>{
  const events:TemplateEvent[]=[{id:'deploy',name:'解释为何上阵英雄',parameters:[]},{id:'ready',name:'解释为何准备战斗',parameters:[]}];
  const groups=[makeGroup('shared','ready',{lineup_note_id:'三分登场'}),makeGroup('child','deploy',{lineup_note_id:'三分登场',player_id:'白歌'},'','小乔')];
  const fallbacks=[makeGroup('dynamic','deploy',{},'动作.英雄.名称 in 我方.阵容英雄名列表','*'),
   makeGroup('named','deploy',{},'','小乔'),makeGroup('other','deploy',{},'','吕布'),makeGroup('excluded','deploy',{},'我方.阵容名称 != "三分登场"','小乔')];
  const tabs=buildLineupTabs([...groups,...fallbacks],id=>id,true);
  const rosters=addLineupRosters(tabs,[{title:'三分登场-白歌',lineup_name:'三分登场',player_id:'白歌',lineup_heroes:['小乔','孙尚香']},
   {title:'三分登场-镜',lineup_name:'三分登场',player_id:'镜',lineup_heroes:['吕布']}],id=>id);
  const heroes=lineupRosterNames(rosters,'三分登场','白歌');
  expect([...heroes]).toEqual(['小乔','孙尚香']);
  expect(tabs.get('三分登场')?.get('镜')?.size).toBe(0);
  expect(tabs.get(unscopedLineup)?.get('')).not.toContain('excluded');
  const entities=['小乔','孙尚香','吕布'].map(name=>({id:name,name,category:'heroes'}));
  const entries=buildTemplateEntityIndex([...groups,...fallbacks],events,entities,undefined,undefined,true,new Set(['小乔']));
  const rows=lineupBoardRows(groups,entries,heroes,fallbacks.filter(group=>group.id!=='excluded'));
  expect(rows.cards.find(card=>card.entity.name==='孙尚香')?.ids.size).toBe(0);
  expect(rows.cards.some(card=>card.entity.name==='吕布')).toBe(false);
  expect(rows.columnIds.get('heroes')).toEqual(new Set(['child','dynamic','named']));
  expect(rows.columnIds.get('other')).toEqual(new Set(['shared']));
  const dynamic=buildTemplateEntityIndex(fallbacks,events,entities,undefined,undefined,true,heroes);
  expect(dynamic.filter(entry=>entry.groupIds.has('dynamic')).map(entry=>entry.name).sort()).toEqual([...heroes].sort());
 });
 it('按明确归属归并阵容别名并保留不同棋手分支',()=>{
  const groups=[
   makeGroup('global','buy'),
   makeGroup('common','buy',{lineup_note_id:'三分倒转'}),
   makeGroup('baige','buy',{lineup_note_id:'三分倒转-白歌',player_id:'白歌'}),
   makeGroup('branches','buy',{},'(我方.阵容名称 == "三分倒转" and 我方.棋手名称 == "镜") or (我方.阵容名称 == "三分射" and 我方.棋手名称 == "白歌")'),
   makeGroup('condition','buy',{},'我方.阵容名称 == "三分射"'),
   makeGroup('optional-lineup','buy',{},'我方.阵容名称 == "三分射" or 我方.棋手名称 == "白歌"'),
  ];
  const tabs=buildLineupTabs(groups,id=>id);
  expect(tabs).toEqual(new Map([
   ['三分倒转',new Map([['',new Set(['common'])],['白歌',new Set(['baige'])],['镜',new Set(['branches'])]])],
   ['三分射',new Map([['白歌',new Set(['branches'])],['',new Set(['condition'])]])],
  ]));
 });

 it('将文件里的未限定阵容组留在独立入口，不计入有名阵容',()=>{
  const groups=[
   makeGroup('equipment','equip',{},'','孙尚香-影牙'),
   makeGroup('lineup','buy',{lineup_note_id:'三分登场'}),
   makeGroup('player','buy',{lineup_note_id:'三分登场-白歌',player_id:'白歌'}),
  ];
  const tabs=buildLineupTabs(groups,id=>id,true);
  expect(tabs.get(unscopedLineup)?.get('')).toEqual(new Set(['equipment']));
  expect(tabs.get('三分登场')?.get('')).toEqual(new Set(['lineup']));
  expect(tabs.get('三分登场')?.get('白歌')).toEqual(new Set(['player']));
  expect(buildLineupTabs(groups,id=>id).has(unscopedLineup)).toBe(false);
 });

 it('索引键和命名的动作对象，并将无对象事件归入其他',()=>{
  const events:TemplateEvent[]=[
   {id:'equip',name:'解释为何穿戴装备',parameters:[]},
   {id:'buy',name:'解释为何购买英雄',parameters:[]},
   {id:'ready',name:'解释为何准备战斗',parameters:[]},
  ];
  const entities=[
   {id:'sun',name:'孙尚香',category:'heroes'},
   {id:'cai',name:'蔡文姬',category:'heroes'},
   {id:'wind',name:'铸梦·逐风',category:'equipment'},
  ];
  const groups=[
   makeGroup('equip','equip',{},'any(我方.场上英雄列表, .名称 == "蔡文姬")','孙尚香-铸梦·逐风'),
   makeGroup('buy','buy',{},'动作.选中.名称 in ["孙尚香", "孙尚香"]','*'),
   makeGroup('ready','ready'),
  ];
  const entries=buildTemplateEntityIndex(groups,events,entities,undefined,undefined,true);
  expect(entries.find(entry=>entry.id==='cai')?.groupIds.size).toBe(0);
  const rows=lineupBoardRows(groups,entries);
  expect(rows.cards.map(({entity,events})=>[entity.id,[...events]])).toEqual([
   ['sun',[['equip',new Set(['equip'])],['buy',new Set(['buy'])]]],
   ['wind',[['equip',new Set(['equip'])]]],
  ]);
  expect(rows.other).toEqual(new Map([['ready',new Set(['ready'])]]));
 });
});
