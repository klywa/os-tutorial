import unittest,sys
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from test_player_branches import fixture
import guide_layout as guide,player_branches as branches

def sample():
 n=fixture();n['reading_layout']={'version':3,'claim_locations':{}}
 n['claims'][0].update(condition='已有保护时',text='执行共同机制。',evidence=[{'source':'old'}])
 return n

class BoundGuideTests(unittest.TestCase):
 def test_condition_and_action_share_editable_block(self):
  n=sample();text=guide.render(n,'one')
  self.assertIn('**已有保护时：** 执行共同机制。',text)
  self.assertNotIn('适用前提：',text)
  changed=guide.parse(text.replace('已有保护时','有额外位置时').replace('执行共同机制。','执行新操作。'),n,'one')
  branches.apply_sections(n,'common',{'核心机制':changed['common']['核心机制']})
  c=next(c for c in n['claims'] if c['id']=='common')
  self.assertEqual((c['condition'],c['text']),('有额外位置时','执行新操作。'))
  self.assertEqual(c['evidence'],[])
  new=guide.render(n,'two');self.assertIn('**有额外位置时：** 执行新操作。',new)
  self.assertEqual(new.count('有额外位置时'),1)
 def test_v3_roundtrip_and_unchanged_condition_preserved(self):
  n=sample();text=branches.documents(n)[branches.document_path(n,branches.branch(n,'one'))]
  self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))
  self.assertFalse(branches.apply_sections(n,'common',guide.parse(text,n,'one')['common']))
  self.assertEqual(n['claims'][0]['evidence'],[{'source':'old'}])
 def test_late_combination_does_not_repeat_stage_members(self):
  n=sample();m={'hero':'pending:核心','necessity':'required','role':'输出'}
  n['meta']['compositions']['late']=[deepcopy(m)]
  n['meta']['late_variants']=[{'id':'late','name':'基础组合','condition':'组件齐备','members':[deepcopy(m)],'core_heroes':[],'required_factions':[],'claim_refs':[]}]
  for b in n['meta']['player_branches']:b['late_variant_ids']=['late']
  text=guide.render(n,'one').split('### 后期英雄组成与运营')[1].split('### 后期提升思路')[0]
  self.assertEqual(text.count('核心（必需）'),1)
  self.assertNotIn('必须阵营',text)
 def test_legacy_layout_is_unchanged(self):
  n=sample();n['reading_layout']['version']=2
  self.assertIn('适用前提：已有保护时',guide.render(n,'one'))
 def test_late_member_edit_keeps_optional_and_updates_overview_source(self):
  n=sample();members=[{'hero':'pending:核心','necessity':'required','role':'输出'},{'hero':'pending:工具','necessity':'optional','role':'决赛时补控制','replaces':'pending:核心','replacement_note':'缺控制时'}]
  n['meta']['compositions']['late']=deepcopy(members)
  n['meta']['late_variants']=[{'id':'late','name':'基础','condition':'齐备','members':deepcopy(members),'core_heroes':[],'required_factions':[],'claim_refs':[]}]
  for b in n['meta']['player_branches']:b['late_variant_ids']=['late']
  # Pending names are accepted by the normal entity resolver.
  n['entity_names'].update({'pending:核心':'核心','pending:工具':'工具'})
  text=guide.render(n,'one');parsed=guide.parse(text.replace('决赛时补控制','决赛时补降级'),n,'one')
  for scope in ('common','branch'):branches.apply_sections(n,'common' if scope=='common' else 'one',parsed[scope])
  p=branches.project(n,'one')['meta']
  self.assertEqual(len(p['compositions']['late']),2)
  self.assertEqual(p['late_variants'][0]['members'][1]['role'],'决赛时补降级')
 def test_effect_card_edit_does_not_become_condition(self):
  n=sample();n['claims'][0].update(section='关键效果牌',text='- **唤醒：**补资源。',condition='')
  parsed=guide.parse(guide.render(n,'one').replace('补资源。','本轮兑现。'),n,'one')
  branches.apply_sections(n,'common',{'关键效果牌':parsed['common']['关键效果牌']})
  self.assertEqual(n['claims'][0]['condition'],'')
  self.assertEqual(n['claims'][0]['text'],'- **唤醒：** 本轮兑现。')
 def test_matching_variant_keeps_editable_condition(self):
  n=sample();m={'hero':'pending:甲','necessity':'required','role':'输出'}
  n['entity_names']['pending:甲']='甲'
  n['meta']['compositions']['late']=[deepcopy(m)]
  n['meta']['late_variants']=[{'id':'v','name':'基础','condition':'只有能稳血时','members':[deepcopy(m)],'core_heroes':[],'required_factions':[],'claim_refs':[]}]
  for b in n['meta']['player_branches']:b['late_variant_ids']=['v']
  text=guide.render(n,'one');self.assertIn('只有能稳血时',text)
  changes=guide.parse(text.replace('只有能稳血时','工具位充足时'),n,'one')
  for scope in ('common','branch'):branches.apply_sections(n,'common' if scope=='common' else 'one',changes[scope])
  self.assertEqual(n['meta']['late_variants'][0]['condition'],'工具位充足时')

if __name__=='__main__':unittest.main()
