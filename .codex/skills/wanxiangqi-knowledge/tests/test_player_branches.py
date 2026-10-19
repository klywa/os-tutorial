import unittest
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import player_branches as branches


def fixture():
    return {'id':'test','type':'lineup','title':'测试打法','path':'knowledge/lineups/测试打法.md',
            'claims':[{'id':i,'section':'核心机制' if i=='common' else '前期运营','text':t,'kind':'general_strategy','evidence':[]} for i,t in [('common','共同机制'),('one','甲棋手独立开局'),('two','乙棋手独立开局')]],
            'entities':[],'core':[],'related':[],'entity_names':{'player:1':'甲','player:2':'乙'},
            'meta':{'players':['player:1','player:2'],'required_factions':[],'core_heroes':[],
                    'compositions':{'early':[],'middle':[],'late':[]},'ban_conditions':[],'matchups':[],
                    'common_claim_refs':['common'],'player_branches':[
                        {'id':'one','player':'player:1','claim_refs':['one'],'condition_refs':[],
                         'operation_route_ids':[],'late_variant_ids':[],'major_variant_ids':[],
                         'overrides':{'compositions':{'early':[{'hero':'pending:甲','necessity':'optional','role':'过渡'}]}},'assessment':[]},
                        {'id':'two','player':'player:2','claim_refs':['two'],'condition_refs':[],
                         'operation_route_ids':[],'late_variant_ids':[],'major_variant_ids':[],'overrides':{},'assessment':[]}],
                    'assessment':[]}}


class BranchTests(unittest.TestCase):
    def test_shared_claim_edit_forks_only_current_player(self):
        n=fixture();n['meta']['player_branches'][1]['claim_refs'].append('one')
        branches.apply_sections(n,'one',{'前期运营':'只属于甲的新开局'})
        branches.validate(n)
        self.assertEqual([c['text'] for c in branches.project(n,'two')['claims'] if c['id']=='one'],['甲棋手独立开局'])
        self.assertIn('只属于甲的新开局',[c['text'] for c in branches.project(n,'one')['claims']])
        self.assertNotIn('只属于甲的新开局',[c['text'] for c in branches.project(n,'two')['claims']])

    def test_manual_selection_survives_schema5_snapshot_import(self):
        import workspace
        n=fixture();n['meta']['player_branches'][0]['selection']={'adopt':'旧采用','avoid':'旧转向','signals':{}}
        prior=deepcopy(n)
        text=branches.selection_markdown(n['meta']['player_branches'][0]['selection']).replace('旧采用','人工采用')
        branches.apply_sections(n,'one',{'采用与转向信号':text})
        result=workspace.merge_note(n,prior)
        self.assertEqual(result['meta']['player_branches'][0]['selection']['adopt'],'人工采用')
        self.assertTrue(result['conflicts'])
    def test_projection_isolated_and_stage_replaces_instead_of_appending(self):
        n=fixture();before=deepcopy(n)
        p=branches.project(n,'player:1')
        self.assertEqual([c['id'] for c in p['claims']],['common','one'])
        self.assertEqual(p['meta']['players'],['player:1'])
        self.assertEqual(p['meta']['compositions']['early'][0]['hero'],'pending:甲')
        self.assertEqual(n,before)
        with self.assertRaises(ValueError):branches.project(n,'player:9')

    def test_markdown_roundtrip_common_exact_and_complete_player_text(self):
        n=fixture();files=branches.documents(n)
        self.assertEqual(len(files),2)
        a=files['knowledge/lineups/测试打法-甲.md'];b=files['knowledge/lineups/测试打法-乙.md']
        parsed_a=branches.parse_document(a,n,'one');parsed_b=branches.parse_document(b,n,'two')
        self.assertEqual(parsed_a['common'],parsed_b['common'])
        self.assertIn('共同机制',a);self.assertIn('甲棋手独立开局',a)
        self.assertNotIn('乙棋手独立开局',a)
        self.assertEqual(parsed_a['branch']['前期运营'],'甲棋手独立开局')
        self.assertIn('测试打法-甲.md',branches.entry_markdown(n))

    def test_ownership_requires_every_claim_and_no_common_branch_overlap(self):
        n=fixture();branches.validate(n)
        for change in ['missing','overlap','dangling']:
            bad=deepcopy(n)
            if change=='missing':bad['meta']['player_branches'][1]['claim_refs']=[]
            if change=='overlap':bad['meta']['player_branches'][0]['claim_refs'].append('common')
            if change=='dangling':bad['meta']['player_branches'][0]['condition_refs']=['absent']
            with self.assertRaises(ValueError):branches.validate(bad)

    def test_statistics_need_scope_sample_time_and_source(self):
        n=fixture();n['meta']['assessment']=[{'dimension':'win_rate','text':'','claim_refs':[], 'statistic':{'value':.2}}]
        with self.assertRaises(ValueError):branches.validate(n)
        n['meta']['assessment'][0]['statistic'].update(sample_size=100,scope='测试分段',period='2026-10',source='公开统计')
        branches.validate(n)

    def test_parser_rejects_duplicate_scope_wrong_title_and_unknown_sections(self):
        n=fixture();text=next(iter(branches.documents(n).values()))
        for broken in [text+'\n## 通用打法\n',text.replace('# 测试打法-甲','# 测试打法-未知'),text+'\n## 其他顶层\n']:
            with self.assertRaises(ValueError):branches.parse_document(broken,n,'one')

    def test_legacy_is_unchanged(self):
        n=fixture();n['meta'].pop('player_branches');n['meta'].pop('common_claim_refs')
        self.assertEqual(branches.project(n),n)
        self.assertEqual(branches.documents(n),{})


if __name__=='__main__':unittest.main()
