import sys,re,unittest,tempfile
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from test_player_branches import fixture
import player_branches as branches
import guide_layout as guide
import workspace,wxq,markdown_sync

def note_fixture():
    n=fixture();n['reading_layout']={'version':2,'claim_locations':{}}
    return n

class GuideLayoutTests(unittest.TestCase):
    def test_opening_and_full_sections(self):
        n=note_fixture();text=guide.render(n,'one')
        self.assertLess(text.index('适用棋手：'),text.index('## 打法评价'))
        for h in ('定阵条件','阵容组成与运营节奏','关键效果牌','制敌手段','克制手段','附录'):
            self.assertIn('## '+h,text)
        self.assertNotIn('## 运营路线与后期组合',text)
        self.assertIn('### 前期英雄组成与运营',text)
        self.assertIn('共同机制',text);self.assertNotIn('乙棋手',text)

    def test_roundtrip_and_common_private_edits(self):
        n=note_fixture();text=guide.render(n,'one')
        self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))
        p=guide.parse(text.replace('共同机制','共同机制补充').replace('甲棋手独立开局','甲独立新开局'),n,'one')
        self.assertEqual(p['common']['核心机制'],'共同机制补充')
        self.assertEqual(p['branch']['前期运营'],'甲独立新开局')

    def test_member_edit_and_evaluation_edit(self):
        n=note_fixture();text=guide.render(n,'one')
        p=guide.parse(text.replace('甲（可选）：','甲（必需）：'),n,'one')
        branches.apply_sections(n,'one',{'成员与替换':p['branch']['成员与替换']})
        self.assertEqual(branches.project(n,'one')['meta']['compositions']['early'][0]['necessity'],'required')

    def test_missing_fields_are_not_covered_by_headings(self):
        rows=guide.coverage(note_fixture(),'one')
        self.assertEqual(rows['early.awakening']['status'],'missing')
        self.assertEqual(rows['auction1.budget']['status'],'missing')
        self.assertEqual(rows['effect_cards']['status'],'missing')

    def test_shared_claim_copy_keeps_new_semantic_location(self):
        n=note_fixture();n['meta']['player_branches'][1]['claim_refs'].append('one')
        n['reading_layout']['claim_locations']['one']=['第一轮拍卖']
        branches.apply_sections(n,'one',{'前期运营':'甲修改共享结论'})
        claim=next(c for c in branches.project(n,'one')['claims'] if c['text']=='甲修改共享结论')
        self.assertEqual(guide.location(n,claim),['第一轮拍卖'])

    def test_shared_claim_copy_remaps_branch_overview(self):
        from overview import default_overview
        n=note_fixture();a=n['meta']['player_branches'][0];n['meta']['player_branches'][1]['claim_refs'].append('one')
        a['overrides']['overview']=default_overview(n['meta'])
        a['overrides']['overview']['presets'][0]['stages']['early']['claim_refs']=['one']
        branches.apply_sections(n,'one',{'前期运营':'甲概览新内容'})
        p=branches.project(n,'one');refs=p['meta']['overview']['presets'][0]['stages']['early']['claim_refs']
        self.assertTrue(refs);self.assertNotIn('one',refs)
        self.assertTrue(set(refs)<={c['id'] for c in p['claims']})

    def test_independent_condition_and_inference_are_visible(self):
        n=note_fixture();n['claims'][0].update(condition='只有特定前提',inference=True)
        text=guide.render(n,'one');self.assertIn('只有特定前提',text);self.assertIn('推测',text)
        self.assertEqual(guide.parse(text,n,'one'),guide.initial_sections(n,'one'))

    def test_coverage_invalidated_when_claim_text_changes(self):
        n=note_fixture();c=n['claims'][0]
        n['reading_layout']['coverage']={'one':{'equipment':{'claim_refs':['common'],'status':'covered','claim_hashes':{'common':guide.claim_hash(c)}}}}
        self.assertEqual(guide.coverage(n,'one')['equipment']['status'],'covered')
        c['text']='已经不包含装备信息'
        self.assertEqual(guide.coverage(n,'one')['equipment']['status'],'needs_review')

    def test_heading_changes_rejected(self):
        n=note_fixture();text=guide.render(n,'one')
        with self.assertRaises(ValueError):guide.parse(text.replace('## 制敌手段','## 换标题'),n,'one')

    def test_all_claims_have_exact_primary_block(self):
        n=note_fixture();blocks=guide.blocks(n,'one')
        ids=[b['claim'] for b in blocks if b.get('claim')]
        self.assertCountEqual(ids,[c['id'] for c in branches.project(n,'one')['claims']])

    def test_new_layout_sync_preserves_common_and_private_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);wxq.init_store(root)
            wxq.atomic_json(root/'entities/players.json',[{'id':'player:1','name':'甲'},{'id':'player:2','name':'乙'}])
            workspace.persist(root,[note_fixture()])
            a=root/'knowledge/lineups/测试打法-甲.md';b=root/'knowledge/lineups/测试打法-乙.md'
            a.write_text(a.read_text('utf8').replace('共同机制','同步共同机制').replace('甲棋手独立开局','甲的新开局'),encoding='utf8')
            self.assertEqual(markdown_sync.scan(root)['issues'],[])
            self.assertIn('同步共同机制',b.read_text('utf8'));self.assertNotIn('甲的新开局',b.read_text('utf8'))
            self.assertIn('甲的新开局',a.read_text('utf8'))

    def test_real_migration_preserves_primary_claims_and_common_chapters(self):
        from migrate_guide_reading import migrate
        root=Path(__file__).resolve().parents[4]
        import json_store, json_document
        if json_store.enabled(root):
            items=workspace.notes(root)
            self.assertTrue(items)
            for note in items:
                text=json_document.markdown(note['document'])
                self.assertEqual(json_document.markdown(json_document.parse(text)),text)
                self.assertEqual(len({n['id'] for n in note['document']['nodes']}),len(note['document']['nodes']))
            return
        items,_=migrate(workspace.notes(root),wxq.entities(root))
        for n in items:
            if not guide.enabled(n):continue
            if not branches.enabled(n):
                # Imported common lineups may use the semantic reader without binding a player.
                from lineup_layout import reading_document
                document=reading_document(n)
                self.assertEqual(document['note_id'],n['id'])
                self.assertTrue(document['sections'])
                continue
            headings=[]
            for b in n['meta']['player_branches']:
                text=guide.render(n,b['id']);guide.parse(text,n,b['id'])
                headings.append(re.findall(r'^## .+$',text,re.M))
                ids=[x['claim'] for x in guide.blocks(n,b['id']) if x.get('claim')]
                available={c['id'] for c in branches.project(n,b['id'])['claims']}
                supporting=n.get('reading_layout',{}).get('supporting_claim_refs',{})
                hidden={cid for cid,refs in supporting.items() if available.intersection([refs] if isinstance(refs,str) else refs)}
                # v4 retains fine-grained evidence internally and renders its explicit summary once.
                self.assertCountEqual(ids,available-hidden)
                self.assertTrue(set(ids).isdisjoint(hidden))
                self.assertNotRegex(text,r'见[“本]|参见|## (?:路线与装备取舍|运营路线选择|棋手决策选择)')
            self.assertTrue(all(x==headings[0] for x in headings))

if __name__=='__main__':unittest.main()
