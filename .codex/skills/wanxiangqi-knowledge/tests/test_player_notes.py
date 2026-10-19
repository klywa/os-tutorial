import unittest,re
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import wxq,player_branches as branches
from lineup_layout import reading_document
from tactics import remap_claims
from test_player_branches import fixture


class PlayerNoteTests(unittest.TestCase):
    def sample(self):
        n=fixture();b=n['meta']['player_branches'][0]
        b['selection']={'adopt':'旧采用','avoid':'旧转向','signals':{},'stage_strength':{
            'early':{'text':'依靠过渡英雄，核心未到有空窗。','claim_refs':['one'],'inference':True},
            'middle':{'text':'取得组件后补质量。','claim_refs':['common'],'inference':True}}}
        p={'id':'player-test','type':'player','title':'甲棋手','entities':['player:1'],'claims':[
            {'id':'skill','section':'技能','text':'技能原文','kind':'mechanic','evidence':[]},
            {'id':'tip','section':'使用技巧','text':'操作技巧原文','kind':'general_strategy','evidence':[]},
            {'id':'fit','section':'适配阵容','text':'尚未完整整理的其他方向','kind':'conditional_strategy','evidence':[]}],
            'related':[],'revision':'r1'}
        return n,p

    def test_player_chapter_order_legacy_labels_and_stage_projection(self):
        n,p=self.sample();branches.update_player_adaptations([n,p]);text=wxq.render_note(p,{})
        self.assertEqual(re.findall(r'^## (.+)$',text,re.M),['技能','前期思路','适用打法与选择','适用技巧','关联知识'])
        self.assertIn('尚未完整整理的其他方向',text)
        self.assertIn('#### 阶段强度',text);self.assertIn('依靠过渡英雄',text)
        self.assertIn('后期',text);self.assertIn('待补充',text)
        doc=reading_document(p)
        self.assertEqual([s['title'] for s in doc['sections']],['技能','前期思路','适用打法与选择','适用技巧','关联知识'])
        self.assertEqual(doc['section_aliases']['使用技巧'],'适用技巧')
        self.assertEqual(doc['section_aliases']['适配阵容'],'适用打法与选择')
        self.assertEqual(p['lineup_adaptations'][0]['selection']['stage_strength'],n['meta']['player_branches'][0]['selection']['stage_strength'])

    def test_unlinked_player_still_has_ordered_reading_document(self):
        _,p=self.sample()
        self.assertEqual(len(reading_document(p)['sections']),5)

    def test_old_selection_edit_retains_stage_strength_and_new_edit_is_local(self):
        n,_=self.sample();before=deepcopy(n['meta']['player_branches'][0]['selection']['stage_strength'])
        legacy='| 判断 | 内容 |\n|---|---|\n| 采用 | 新采用 |\n| 转向 | 旧转向 |'
        branches.apply_sections(n,'one',{'采用与转向信号':legacy})
        self.assertEqual(n['meta']['player_branches'][0]['selection']['stage_strength'],before)
        table=branches.selection_markdown(n['meta']['player_branches'][0]['selection'])
        table=table.replace('依靠过渡英雄，核心未到有空窗。','人工前期判断')
        branches.apply_sections(n,'one',{'采用与转向信号':table})
        stage=n['meta']['player_branches'][0]['selection']['stage_strength']
        self.assertEqual(stage['early']['text'],'人工前期判断');self.assertEqual(stage['early']['claim_refs'],[])
        self.assertEqual(stage['middle'],before['middle'])
        self.assertNotIn('stage_strength',n['meta']['player_branches'][1].get('selection',{}))

    def test_stage_refs_validate_ownership_and_remap_with_claims(self):
        n,_=self.sample();branches.validate(n)
        bad=deepcopy(n);bad['meta']['player_branches'][0]['selection']['stage_strength']['early']['claim_refs']=['two']
        with self.assertRaises(ValueError):branches.validate(bad)
        remap_claims(n['meta'],{'one'},'renamed')
        self.assertEqual(n['meta']['player_branches'][0]['selection']['stage_strength']['early']['claim_refs'],['renamed'])

    def test_projection_rebuilds_from_branch_and_does_not_duplicate(self):
        n,p=self.sample();branches.update_player_adaptations([n,p]);before=wxq.render_note(p,{})
        branches.update_player_adaptations([n,p]);self.assertEqual(wxq.render_note(p,{}),before)
        n['meta']['player_branches'][0]['selection']['stage_strength']['early']['text']='阵容分支更新'
        branches.update_player_adaptations([n,p]);self.assertIn('阵容分支更新',wxq.render_note(p,{}))

    def test_stage_fields_survive_v3_markdown_roundtrip_and_noop_save(self):
        from test_bound_guide import sample
        import guide_layout
        n=sample();n['meta']['player_branches'][0]['selection']=self.sample()[0]['meta']['player_branches'][0]['selection']
        text=guide_layout.render(n,'one');parsed=guide_layout.parse(text,n,'one')
        before=deepcopy(n)
        self.assertFalse(branches.apply_sections(n,'one',parsed['branch']))
        self.assertEqual(n,before)

    def test_old_player_editor_section_name_updates_canonical_section(self):
        import tempfile,workspace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wxq.init_store(root)
            workspace.persist(root,[{'id':'p','type':'player','title':'棋手','entities':[],'core':[],
                'claims':[{'id':'tip','section':'适用技巧','text':'旧操作','kind':'general_strategy','evidence':[]}]}])
            n=workspace.notes(root)[0]
            result=workspace.edit(root,'p',{'revision':n['revision'],'sections':{'使用技巧':'新操作'}})
            text=wxq.render_note(result,{})
            self.assertIn('新操作',text);self.assertNotIn('旧操作',text)
            self.assertEqual([c['section'] for c in result['claims']],['适用技巧'])


if __name__=='__main__':unittest.main()
