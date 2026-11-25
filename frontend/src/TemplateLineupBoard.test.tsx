import {describe,expect,it} from 'vitest';
import {buildLineupTabs,lineupBoardRows,unscopedLineup} from './TemplateLineupBoard';
import {buildTemplateEntityIndex} from './templateEntityIndex';
import type {TemplateEvent,TemplateGroup} from './templates';

const makeGroup=(id:string,event_id:string,scope:Partial<TemplateGroup['scope']>={},expression='',extra_key=''):TemplateGroup=>({
 id,event_id,name:id,scope:{player_id:null,lineup_note_id:null,...scope},syntax_version:'0.4',expression,extra_key,
 conditions:[],related_entities:[],utterances:[{id:id+'-line',text:'补充战力。'}],
});

describe('阵容看板',()=>{
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
