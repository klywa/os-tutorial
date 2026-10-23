import sys, unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from test_player_branches import fixture
import guide_layout as guide
import player_branches as branches
from lineup_layout import reading_document


class GuideV4Tests(unittest.TestCase):
    def test_reviewed_hero_roundtrip_preserves_evidence_and_manual_edit_is_scoped(self):
        n=self.note();n['reading_layout']['hero_fields_required']=True
        n['entity_names']['card:a']='英雄甲'
        c={'id':'reviewed-hero','section':'英雄','text':'**英雄甲：** 牺牲触发主C等级，增加输出。觉醒需求：普通卡已有牺牲；等级投入：保持低投入以尽早阵亡；购买策略：只在缺牺牲时取首张，重复不优先，不付费专找，拍卖出价上限未确认；上阵时机：主C在场再上；出售时机：替代牺牲已到且转移永久等级后可售；','condition':'','kind':'conditional_strategy','inference':True,'evidence':[{'source':'video:p1','start':10,'end':20}]}
        n['claims'].append(c);n['meta']['player_branches'][0]['claim_refs'].append(c['id'])
        original=deepcopy(n)
        text=guide.render(n,'one')
        parsed=guide.parse(text,n,'one')
        branches.apply_sections(n,'one',parsed['branch'])
        self.assertEqual(n,original)
        self.assertEqual(next(x for x in n['claims'] if x['id']==c['id'])['evidence'],c['evidence'])
        self.assertNotIn('英雄甲：',guide.render(n,'two'))
        parsed=guide.parse(text.replace('主C在场再上','主C和替代前排已在场再上'),n,'one')
        branches.apply_sections(n,'one',parsed['branch'])
        changed=next(x for x in n['claims'] if x['id']==c['id'])
        self.assertEqual(changed['origin'],'manual')
        # A semantic user edit is not automatically certified by prior evidence.
        self.assertEqual(changed['evidence'],[])
        self.assertTrue(n['reading_layout']['hero_fields_required'])
        self.assertIn('主C和替代前排已在场再上',guide.render(n,'one'))
        self.assertEqual(guide.render(n,'two'),guide.render(original,'two'))
        again=deepcopy(n);sections=guide.parse(guide.render(n,'one'),n,'one')
        branches.apply_sections(n,'one',sections['branch'])
        self.assertEqual(n,again)

    def test_hero_fields_are_opt_in_and_require_order_unique_nonempty_values(self):
        from guide_v4 import hero_field_errors
        good='**英雄甲：** 持续控制为输出争取时间。觉醒需求：普通卡可完成控制；等级投入：无需专门投入；购买策略：自然购买首张，不付费刷新，拍卖出价上限未确认；上阵时机：有空位即可补控制；出售时机：替换控制位时可售；'
        self.assertEqual(hero_field_errors(good),[])
        for bad in [good.replace('等级投入：无需专门投入；',''), good.replace('觉醒需求：普通卡可完成控制；','觉醒需求：；'), good.replace('出售时机：替换控制位时可售；','出售时机：替换控制位时可售。'), good+'觉醒需求：追觉醒；', good.replace('等级投入：无需专门投入；购买策略：','购买策略：无需专门投入；等级投入：'), good.replace('上阵时机：','\n上阵时机：')]:
            with self.subTest(text=bad):self.assertTrue(hero_field_errors(bad))
        n=self.note();n['meta']['player_branches'][0]['claim_refs']=[]
        n['entity_names']['card:a']='英雄甲'
        n['claims'].append({'id':'hero5','section':'英雄','text':good,'kind':'general_strategy','evidence':[]})
        n['meta']['common_claim_refs'].append('hero5')
        import guide_v4
        self.assertEqual(guide_v4.paragraph_errors(n,'one'),[])
        n['claims'][-1]['text']='英雄甲：控制。'
        self.assertEqual(guide_v4.paragraph_errors(n,'one'),[])
        n['reading_layout']['hero_fields_required']=True
        self.assertTrue(any('五字段' in e for e in guide_v4.paragraph_errors(n,'one')))

    def test_reviewed_stage_keeps_alternative_composition_outside_operation_paragraph(self):
        n=self.note();n['reading_layout']['entity_paragraphs']=True
        n['meta']['late_variants']=[{'id':'v','name':'备用组合','condition':'缺主力时','members':[{'hero':'pending:乙','necessity':'required','role':'承伤'}],'core_heroes':[],'required_factions':[],'ban_conditions':[],'ban_combinations':[],'claim_refs':[]}]
        n['meta']['player_branches'][0]['late_variant_ids']=['v']
        text=guide.render(n,'one')
        self.assertIn('## 后期组合\n',text)
        body=text.split('## 阵容组成与运营节奏\n',1)[1].split('\n## ',1)[0]
        self.assertNotIn('组合调整为备用组合',body)
        self.assertIn('组合调整为备用组合',text)
        self.assertIn('乙（必需）：承伤',text)
        self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))

    def test_skill_heading_alias_and_edit_preserve_original_section(self):
        n=self.note()
        n['claims'].append({'id':'skill','section':'棋手技能推荐','text':'技能甲：为核心提供成长。','kind':'general_strategy','evidence':[]})
        n['meta']['player_branches'][0]['claim_refs'].append('skill')
        text=guide.render(n,'one')
        self.assertIn('## 棋手技能选择\n',text)
        self.assertNotIn('## 棋手技能推荐\n',text)
        self.assertEqual(reading_document(n,'one')['section_aliases']['棋手技能推荐'],'棋手技能选择')
        parsed=guide.parse(text.replace('提供成长','提供持续成长'),n,'one')
        branches.apply_sections(n,'one',parsed['branch'])
        self.assertIn('技能甲：为核心提供持续成长。',guide.render(n,'one'))

    def test_reviewed_paragraph_contract_rejects_bad_entity_or_stage_blocks(self):
        from guide_v4 import paragraph_errors
        n=self.note()
        n['reading_layout']['entity_paragraphs']=True
        n['meta']['player_branches'][0]['claim_refs']=[]
        n['entity_names'].update({'card:a':'英雄甲','card:b':'装备乙'})
        for cid,section,text in [('hero','英雄','英雄甲：持续输出。'),('early','前期运营','【前期运营思路：】先保血，再升级。'),('middle','中期运营','【中期运营思路：】补齐组件。'),('late','后期运营','【后期运营思路：】提升质量。'),('improve','成型后提升思路','【后期提升思路：】按对手调整。')]:
            n['claims'].append({'id':cid,'section':section,'text':text,'kind':'general_strategy','evidence':[]})
            n['meta']['common_claim_refs'].append(cid)
        self.assertEqual(paragraph_errors(n,'one'),[])
        hero=next(c for c in n['claims'] if c['id']=='hero')
        hero['text']='有装备时，英雄甲承担输出。'
        self.assertTrue(paragraph_errors(n,'one'))
        hero['text']='英雄甲：输出。\n装备乙：承伤。'
        self.assertTrue(paragraph_errors(n,'one'))
        hero['text']='英雄甲：输出。装备乙：承伤。'
        self.assertTrue(paragraph_errors(n,'one'))
        hero['text']='英雄甲：持续输出。'
        early=next(c for c in n['claims'] if c['id']=='early')
        early['text']='先保血。'
        self.assertTrue(paragraph_errors(n,'one'))
        early['text']='【前期运营思路：】先保血。\n再升级。'
        self.assertTrue(paragraph_errors(n,'one'))
        n['reading_layout'].pop('entity_paragraphs')
        self.assertEqual(paragraph_errors(n,'one'),[])

    def test_operation_chapters_merge_before_positions_without_changing_ownership(self):
        n=self.note()
        for cid,section,scope in [('op-old','关键操作顺序','common'),('op-new','关键操作','one')]:
            n['claims'].append({'id':cid,'section':section,'text':cid,'kind':'general_strategy','evidence':[]})
            owner=n['meta'] if scope=='common' else n['meta']['player_branches'][0]
            owner.setdefault('common_claim_refs' if scope=='common' else 'claim_refs',[]).append(cid)
        baseline=deepcopy(n)
        text=guide.render(n,'one')
        self.assertEqual(text.count('## 关键操作\n'),1)
        self.assertNotIn('## 关键操作顺序\n',text)
        self.assertLess(text.index('## 关键操作\n'),text.index('## 站位技巧\n'))
        doc=reading_document(n,'one')
        self.assertEqual(doc['section_aliases']['关键操作顺序'],'关键操作')
        parsed=guide.parse(text.replace('op-old','edited operation'),n,'one')
        branches.apply_sections(n,'common',parsed['common'])
        self.assertEqual(next(c for c in n['claims'] if c['id']=='op-old')['section'],'关键操作顺序')
        self.assertEqual(next(c for c in n['claims'] if c['id']=='op-new'),baseline['claims'][-1])
        self.assertNotIn('op-new',guide.render(n,'two'))

    def test_legacy_operation_chapter_remains_in_original_layouts(self):
        for version in (2,3):
            n=self.note();n['reading_layout']['version']=version
            n['claims'].append({'id':'op','section':'关键操作顺序','text':'operation','kind':'general_strategy','evidence':[]})
            n['meta']['common_claim_refs'].append('op')
            text=guide.render(n,'one')
            self.assertIn('## 关键操作顺序\n',text)
            self.assertGreater(text.index('## 关键操作顺序\n'),text.index('## 站位技巧\n'))

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

    def test_canonical_equipment_heading_keeps_its_claim_and_roundtrips(self):
        n=self.note()
        n['claims'].append({'id':'equipment','section':'关键装备','text':'装备甲：保护输出。','kind':'conditional_strategy','evidence':[]})
        n['meta']['common_claim_refs'].append('equipment')
        text=guide.render(n,'one')
        self.assertIn('装备甲：保护输出。',text)
        self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))

    def test_equipment_heading_aliases_keep_both_owners_and_drop_empty_placeholder(self):
        n=self.note()
        for cid,section,text in [('old-equip','推荐装备','旧装备：保护前排。'),('new-equip','关键装备','新装备：保护输出。')]:
            n['claims'].append({'id':cid,'section':section,'text':text,'kind':'conditional_strategy','evidence':[]})
            n['meta']['common_claim_refs'].append(cid)
        text=guide.render(n,'one')
        body=text.split('## 关键装备\n',1)[1].split('\n## ',1)[0]
        self.assertIn('旧装备：保护前排。',body)
        self.assertIn('新装备：保护输出。',body)
        self.assertNotIn('暂无已确认',body)
        self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))

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

    def test_reviewed_purchase_list_precedes_late_operation_and_roundtrips(self):
        n=self.note()
        n['reading_layout']['purchase_lists_first']=True
        n['meta']['compositions']['late']=[{'hero':'card:a','necessity':'required','role':'先买关键牌。','replaces':'','replacement_note':''},{'hero':'card:b','necessity':'optional','role':'有位置再买工具。','replaces':'','replacement_note':''}]
        n['claims'].append({'id':'late-operation','section':'后期运营','text':'成型后再升级。','kind':'conditional_strategy','evidence':[]})
        n['meta']['common_claim_refs'].append('late-operation')
        text=guide.render(n,'one')
        self.assertLess(text.index('有位置再买工具。'),text.index('成型后再升级。'))
        self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))

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
