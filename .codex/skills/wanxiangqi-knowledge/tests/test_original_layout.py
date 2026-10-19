import re,sys,tempfile,unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from test_player_branches import fixture
import player_branches as branches,original_layout as layout,workspace,wxq,markdown_sync
from lineup_layout import _render_generic,reading_document


def original_fixture():
    note=fixture();legacy=deepcopy(note)
    legacy['meta'].pop('player_branches');legacy['meta'].pop('common_claim_refs')
    note['reading_layout']={'preserve_original':True,'sections':list(layout.split_chapters(_render_generic(legacy)))}
    return note


class OriginalLayoutTests(unittest.TestCase):
    def test_each_player_keeps_original_chapter_names_order_and_levels(self):
        note=original_fixture()
        for path,text in branches.documents(note).items():
            self.assertEqual(re.findall(r'^## (.+)$',text,re.M),note['reading_layout']['sections'])
            self.assertNotIn('## 通用打法',text);self.assertNotIn('## 甲打法',text)
            self.assertIn('共同机制',text)
        reading=reading_document(note,'one')
        self.assertEqual([s['title'] for s in reading['sections']],note['reading_layout']['sections'])

    def test_original_paragraph_edit_retains_explicit_scope_without_visible_ids(self):
        note=original_fixture();text=branches.documents(note)['knowledge/lineups/测试打法-甲.md']
        edited=text.replace('共同机制','共同机制新说明').replace('甲棋手独立开局','甲专属新开局')
        parsed=branches.parse_document(edited,note,'one')
        self.assertEqual(parsed['common']['核心机制'],'共同机制新说明')
        self.assertEqual(parsed['branch']['前期运营'],'甲专属新开局')
        self.assertEqual(note['claims'][0]['text'],'共同机制')

    def test_original_member_bullets_update_only_current_stage(self):
        note=original_fixture();text=branches.documents(note)['knowledge/lineups/测试打法-甲.md']
        parsed=branches.parse_document(text.replace('甲（可选）：','甲（必需）：'),note,'one')
        branches.apply_sections(note,'one',{'成员与替换':parsed['branch']['成员与替换']})
        self.assertEqual(note['meta']['player_branches'][0]['overrides']['compositions']['early'][0]['necessity'],'required')

    def test_changed_heading_is_reported_instead_of_reorganizing_note(self):
        note=original_fixture();text=branches.documents(note)['knowledge/lineups/测试打法-甲.md']
        with self.assertRaises(ValueError):branches.parse_document(text.replace('## 核心机制','## 新核心章节'),note,'one')

    def test_preserved_layout_sync_propagates_common_but_not_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);wxq.init_store(root)
            wxq.atomic_json(root/'entities/players.json',[{'id':'player:1','name':'甲'},{'id':'player:2','name':'乙'}])
            workspace.persist(root,[original_fixture()])
            path=root/'knowledge/lineups/测试打法-甲.md';other=root/'knowledge/lineups/测试打法-乙.md'
            path.write_text(path.read_text('utf8').replace('共同机制','原格式共同修改').replace('甲棋手独立开局','原格式甲开局'),encoding='utf8')
            state=markdown_sync.scan(root)
            self.assertEqual(state['issues'],[])
            self.assertIn('原格式共同修改',other.read_text('utf8'));self.assertNotIn('原格式甲开局',other.read_text('utf8'))
            self.assertIn('原格式甲开局',path.read_text('utf8'))


if __name__=='__main__':unittest.main()
