import sys, unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from test_player_branches import fixture
import guide_layout as guide
import player_branches as branches
from lineup_layout import reading_document


class GuideV4Tests(unittest.TestCase):
    def test_principle_first_for_different_win_conditions_and_roundtrip(self):
        for text in ('甲承担输出，资源优先提升甲的等级，以持续伤害建立优势。',
                     '甲乙共同输出，靠经济技能更快补齐阵容，保留工具牌反复触发收益。'):
            n=self.note()
            n['claims'].append({'id':'principle','section':'核心原理','text':text,'inference':True,'kind':'general_strategy','evidence':[]})
            n['meta']['common_claim_refs'].append('principle')
            rendered=guide.render(n,'one')
            self.assertEqual(rendered.split('## ')[1].splitlines()[0],'核心原理')
            self.assertEqual(rendered.count(text),1)
            self.assertEqual(guide.parse(rendered,n,'one'),guide.initial_sections(n,'one'))

    def test_principle_validation_is_generic_and_checks_visible_branch(self):
        from guide_v4 import validate_principles
        n=self.note()
        n['claims'].append({'id':'p','section':'核心原理','text':'甲乙共同输出。','kind':'general_strategy','evidence':[]})
        n['meta']['common_claim_refs'].append('p')
        validate_principles(n)
        for invalid in ('字'*501,'甲输出。\n\n乙成长。'):
            n['claims'][-1]['text']=invalid
            with self.assertRaises(ValueError):validate_principles(n)
        n['claims'][-1]['text']='甲输出。'
        n['claims'].append({**n['claims'][-1],'id':'p2'})
        n['meta']['player_branches'][0]['claim_refs'].append('p2')
        with self.assertRaises(ValueError):validate_principles(n)
        n['reading_layout']['requires_principle']=True
        n['claims']=[c for c in n['claims'] if c['section']!='核心原理']
        n['meta']['common_claim_refs'].remove('p')
        n['meta']['player_branches'][0]['claim_refs'].remove('p2')
        with self.assertRaises(ValueError):validate_principles(n)

    def test_unreviewed_route_conditions_are_not_silently_hidden(self):
        n=self.note()
        n['meta']['operation_routes']=[{'id':'r','name':'路线甲','condition':'独有条件','advantages':'收益','risks':'风险','transition':'独有转向','phases':{'early':[],'middle':[],'late':[]}}]
        n['meta']['player_branches'][0]['operation_route_ids']=['r']
        text=guide.render(n,'one')
        self.assertIn('独有条件',text);self.assertIn('独有转向',text)

    def note(self):
        n = fixture()
        n['reading_layout'] = {'version': 4, 'claim_locations': {}, 'supporting_claim_refs': {}}
        n['claims'][0].update(inference=True, condition='有位置时')
        return n

    def test_layout_and_aliases_share_reading_projection(self):
        n = self.note()
        text = guide.render(n, 'one')
        self.assertIn('## 英雄\n', text)
        self.assertIn('## 拍卖\n', text)
        self.assertNotIn('\n## 第一轮拍卖\n', text)
        doc = reading_document(n, 'one')
        self.assertEqual(doc['layout_version'], 4)
        self.assertEqual(doc['section_aliases']['第一轮拍卖'], '拍卖')
        self.assertEqual(doc['section_aliases']['推荐装备'], '关键装备')
        self.assertIn('优先拿阵容英雄', text)

    def test_untouched_inference_survives_unrelated_edit(self):
        n = self.note(); original = deepcopy(n['claims'][0])
        text = guide.render(n, 'one')
        self.assertNotIn('推测：', text)
        parsed = guide.parse(text.replace('甲棋手独立开局', '甲的新开局'), n, 'one')
        branches.apply_sections(n, 'one', parsed['branch'])
        self.assertEqual(n['claims'][0], original)
        self.assertEqual(guide.parse(guide.render(n, 'one'), n, 'one'), guide.initial_sections(n, 'one'))

    def test_supporting_claim_is_retained_but_not_printed_twice(self):
        n = self.note()
        n['claims'].append({'id':'summary', 'section':'前期运营', 'text':'精简后的操作', 'kind':'general_strategy', 'evidence':[], 'inference':True})
        n['meta']['player_branches'][0]['claim_refs'].append('summary')
        n['reading_layout']['supporting_claim_refs']['one'] = 'summary'
        text = guide.render(n, 'one')
        self.assertIn('精简后的操作', text)
        self.assertNotIn('甲棋手独立开局', text)
        self.assertEqual(len(n['claims']), 4)
        self.assertEqual(guide.parse(text, n, 'one'), guide.initial_sections(n, 'one'))

    def test_original_versions_still_show_inference(self):
        n = self.note(); n['reading_layout']['version'] = 3
        self.assertIn('推测：', guide.render(n, 'one'))

    def test_other_player_summary_cannot_hide_this_players_source(self):
        n=self.note()
        n['reading_layout']['supporting_claim_refs']={'one':['two']}
        self.assertIn('甲棋手独立开局',guide.render(n,'one'))

    def test_editing_one_claim_keeps_untouched_inference_in_the_same_section(self):
        n=self.note()
        n['claims'].append({'id':'extra','section':'核心机制','text':'保留预算','inference':False,'condition':'','kind':'general_strategy','evidence':[]})
        n['meta']['common_claim_refs'].append('extra')
        original=deepcopy(n['claims'][0])
        parsed=guide.parse(guide.render(n,'one').replace('保留预算','先保留购买预算'),n,'one')
        branches.apply_sections(n,'common',parsed['common'])
        self.assertEqual(n['claims'][0],original)
        self.assertIn('先保留购买预算',guide.render(n,'two'))

    def test_legacy_migration_never_downgrades_a_new_layout(self):
        from migrate_bound_guides import migrate
        n=self.note();n['id']='heluo-huamulan'
        items,audit=migrate([n],[])
        self.assertEqual(items,[n]);self.assertEqual(audit,{})


if __name__ == '__main__': unittest.main()
