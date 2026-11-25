import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import rawCatalog from '../../src/condition/catalog.json?raw';
import TemplateRuleEditor from './TemplateRuleEditor';
import type {ConditionCatalog} from './templateRules';
import type {TemplateGroup} from './templates';

it('shows editable filter inputs for a saved count on either side of a comparison',()=>{
 const catalog:ConditionCatalog={...JSON.parse(rawCatalog),card_tags:{hero:{type:'英雄',tags:['登场']}}};
 const tree={kind:'leaf' as const,left:'玩家.战场.计数(标签,"登场")',operator:'>=',right:'对局.当前对手.战场.计数(阵营, "三分之地")'};
 const draft:TemplateGroup={id:'count',name:'比较双方英雄数量',event_id:'battle',scope:{player_id:null,lineup_note_id:null},condition_tree:tree,conditions:[],utterances:[],related_entities:[]};
 const html=renderToStaticMarkup(<TemplateRuleEditor draft={draft} catalog={catalog} patch={()=>{}} preview=""/>);
 expect(html).toContain('>统计标签<input');
 expect(html).toContain('value="登场"');
 expect(html).toContain('>比较阵营<input');
 expect(html).toContain('value="三分之地"');
});

it('keeps the saved names and awakening restrictions in the hero count editor',()=>{
 const catalog:ConditionCatalog=JSON.parse(rawCatalog);
 const tree={kind:'leaf' as const,left:'玩家.战场.计数(英雄, ["小乔",{"类型":"英雄","名称":"弈星","已觉醒":true}])',operator:'>=',right:'2'};
 const draft:TemplateGroup={id:'count',name:'按英雄名单计数',event_id:'battle',scope:{player_id:null,lineup_note_id:null},condition_tree:tree,conditions:[],utterances:[],related_entities:[]};
 const html=renderToStaticMarkup(<TemplateRuleEditor draft={draft} catalog={catalog} patch={()=>{}} preview=""/>);
 expect(html).toContain('>统计英雄名单');
 expect(html).toContain('value="[&quot;小乔&quot;,{&quot;类型&quot;:&quot;英雄&quot;,&quot;名称&quot;:&quot;弈星&quot;,&quot;已觉醒&quot;:true}]"');
});
