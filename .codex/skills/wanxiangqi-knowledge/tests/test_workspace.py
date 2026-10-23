import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import wxq
import workspace


class WorkspaceTests(unittest.TestCase):
    def test_reviewed_entity_paragraph_names_survive_shared_prepare(self):
        from unittest.mock import patch
        from copy import deepcopy
        note=self.seed()
        note['entities']=['card:extra']
        note['reading_layout']={'version':4,'entity_paragraphs':True}
        with patch.object(wxq,'entities',return_value=[{'id':'card:extra','name':'说明用实体'}]):
            workspace.prepare(self.root,[note])
            self.assertEqual(note['entity_names']['card:extra'],'说明用实体')
            first=deepcopy(note)
            workspace.prepare(self.root,[note])
            self.assertEqual(note,first)
            note['reading_layout'].pop('entity_paragraphs')
            workspace.prepare(self.root,[note])
            self.assertNotIn('card:extra',note['entity_names'])

    def test_explicit_target_does_not_create_reverse_overlap_links(self):
        from copy import deepcopy
        flexible={'id':'flexible','type':'lineup','title':'组合库','entities':['pending:共同英雄'],
                  'claims':[],'related':[],'meta':{'late_variants':[{'id':'late'}]}}
        explicit={'id':'explicit','type':'lineup','title':'明确关系攻略','entities':['pending:共同英雄'],
                  'claims':[],'related':[],'explicit_relationships':True}
        items=[deepcopy(flexible),deepcopy(explicit)]
        workspace.prepare(self.root,items)
        self.assertEqual(items[0]['related'],[])
        self.assertEqual(items[1]['related'],[])
        # Legacy overlap linking remains available when both notes opt into it.
        legacy=deepcopy(explicit);legacy.pop('explicit_relationships')
        items=[deepcopy(flexible),legacy]
        workspace.prepare(self.root,items)
        self.assertEqual([link['id'] for link in items[0]['related']],['explicit'])

    def test_replay_updates_recover_with_save_transaction(self):
        from unittest.mock import patch
        note=self.seed();path='knowledge/replays/reviewed.json'
        original=wxq.atomic_json
        def fail_replay(target,value):
            if Path(target)==self.root/path:raise OSError('interrupted replay')
            return original(target,value)
        with patch.object(wxq,'atomic_json',side_effect=fail_replay):
            with self.assertRaises(OSError):workspace.persist(self.root,[note],_replay_updates={path:{'notes':[note]}})
        self.assertTrue((self.root/'knowledge/pending-save.json').exists())
        workspace.recover(self.root)
        self.assertEqual(wxq.read_json(self.root/path)['notes'],workspace.notes(self.root))
        self.assertFalse((self.root/'knowledge/pending-save.json').exists())

    def setUp(self):
        temp_root = Path(__file__).parents[4] / '.wxq-runtime/test-temp'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        wxq.init_store(self.root)

    def seed(self, title='测试：打法'):
        note = {'id': 'stable', 'type': 'lineup', 'title': title, 'entities': [], 'core': [],
                'claims': [], 'related': []}
        wxq.atomic_json(self.root / 'knowledge/index.json', {'schema_version': 1, 'notes': [note]})
        wxq.atomic_text(self.root / 'knowledge/lineups/stable.md', wxq.render_note(note, {}))
        workspace.migrate(self.root)
        return workspace.notes(self.root)[0]

    def test_migrate_chinese_and_idempotent(self):
        note = self.seed()
        self.assertEqual(note['id'], 'stable')
        self.assertIn('测试', note['path'])
        self.assertNotIn('：', note['path'])
        self.assertFalse((self.root / 'knowledge/lineups/stable.md').exists())
        before = (self.root / 'knowledge/index.json').read_bytes()
        workspace.migrate(self.root)
        self.assertEqual(before, (self.root / 'knowledge/index.json').read_bytes())
        self.assertEqual(wxq.read_json(self.root / note['path'].replace('.md', '.json')), note)

    def test_manual_edit_survives_import_and_stale_edit_fails(self):
        note = self.seed()
        edited = workspace.edit(self.root, note['id'], {'revision': note['revision'],
            'sections': {'核心机制': '人工修订'}, 'meta': note['meta']})
        with self.assertRaises(workspace.Conflict):
            workspace.edit(self.root, note['id'], {'revision': note['revision'], 'sections': {}})
        merged = workspace.merge_note(edited, {**note, 'claims': [
            {'section': '核心机制', 'text': '视频新内容', 'kind': 'mechanic', 'evidence': []}]})
        self.assertEqual(merged['claims'][0]['text'], '人工修订')
        self.assertEqual(merged['claims'][0]['evidence'], [])
        self.assertTrue(merged['conflicts'])

    def test_bans_require_all_and_unknown_is_not_playable(self):
        note = self.seed()
        note['meta']['required_factions'] = ['faction:dahe']
        note['meta']['ban_conditions'] = [{'faction': 'faction:sanfen', 'status': 'playable', 'reason': ''}]
        self.assertEqual(workspace.availability(note, ['faction:dahe']), 'unplayable')
        self.assertEqual(workspace.availability(note, ['faction:sanfen']), 'playable')
        self.assertEqual(workspace.availability(note, ['faction:sanfen', 'faction:zhulu']), 'unknown')

    def test_pending_faction_is_available_for_filtering(self):
        note = self.seed()
        note['meta']['required_factions'] = ['pending:新阵营']
        workspace.edit(self.root, note['id'], {'revision':note['revision'],'meta':note['meta']})
        self.assertIn('pending:新阵营', [f['id'] for f in workspace.factions(self.root)])

    def test_sources_deduplicate_and_completion_requires_review(self):
        a = workspace.register_source(self.root, {'url': 'https://www.bilibili.com/video/BV123/?p=2&utm_source=x', 'title': '测试'})
        b = workspace.register_source(self.root, {'url': 'https://www.bilibili.com/video/BV123?p=2', 'title': '测试'})
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(len(workspace.sources(self.root)), 1)
        folder = self.root / 'raw/sources/BV123_p2'
        wxq.atomic_json(folder / 'metadata.json', {'id': 'BV123:p2', 'url': a['url'], 'title': '测试'})
        wxq.atomic_json(folder / 'state.json', {'stage': 'complete'})
        self.assertEqual(workspace.sources(self.root)[0]['knowledge_status'], 'unprocessed')

    def test_generic_registry_links_to_imported_platform_id(self):
        workspace.register_source(self.root, {'url': 'https://example.com/video', 'title': '待整理内容', 'notes': '关心后期'})
        folder = self.root / 'raw/sources/platform123_p1'
        wxq.atomic_json(folder / 'metadata.json', {'id':'platform123:p1','url':'https://example.com/video','title':'下载后的标题'})
        rows = workspace.sources(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], 'platform123:p1')
        self.assertEqual(rows[0]['notes'], '关心后期')
        workspace.register_source(self.root, {'url':'https://example.com/video','title':'人工标题','notes':'修改'}, 'platform123:p1')
        self.assertEqual(len(workspace.sources(self.root)), 1)

    def test_source_submission_requires_covered_review_to_be_deposited(self):
        note = self.seed()
        note['claims'] = [{'section':'核心机制','text':'已确认建议','kind':'mechanic',
                          'evidence':[{'source':'BV123:p1','start':10,'end':20}]}]
        wxq.atomic_json(self.root / 'knowledge/index.json', {'schema_version':2,'notes':[note]})
        folder=self.root / 'raw/sources/BV123_p1'
        wxq.atomic_json(folder / 'metadata.json', {'id':'BV123:p1','url':'https://www.bilibili.com/video/BV123?p=1','title':'来源'})
        wxq.atomic_json(folder / 'state.json', {'stage':'complete'})
        wxq.atomic_json(folder / 'review.json', {'approved':True,'checked_intervals':[[0,5]]})
        self.assertEqual(workspace.sources(self.root)[0]['knowledge_status'], 'submitted')
        wxq.atomic_json(folder / 'review.json', {'approved':True,'checked_intervals':[[10,20]]})
        self.assertEqual(workspace.sources(self.root)[0]['knowledge_status'], 'deposited')

    def test_lock_and_transaction_recovery(self):
        with workspace.store_lock(self.root):
            with self.assertRaises(workspace.Busy):
                with workspace.store_lock(self.root):
                    pass
        note = self.seed()
        wxq.atomic_json(self.root / 'knowledge/pending-save.json', {'index': {'schema_version': 2, 'notes': [note]}, 'obsolete': []})
        workspace.migrate(self.root)
        self.assertFalse((self.root / 'knowledge/pending-save.json').exists())

    def test_same_titles_get_persisted_chinese_suffix(self):
        wxq.commit_notes(self.root, [{'id': 'one', 'type': 'other', 'title': '同名笔记', 'claims': [], 'entities': []},
                                    {'id': 'two', 'type': 'other', 'title': '同名笔记', 'claims': [], 'entities': []}])
        paths = [n['path'] for n in workspace.notes(self.root)]
        self.assertEqual(paths, ['knowledge/other/同名笔记.md', 'knowledge/other/同名笔记（二）.md'])
        workspace.migrate(self.root)
        self.assertEqual(paths, [n['path'] for n in workspace.notes(self.root)])

    def test_edited_notes_can_be_replayed_without_fabricated_evidence(self):
        note = self.seed()
        edited = workspace.edit(self.root, note['id'], {'revision': note['revision'], 'sections': {'核心机制': '人工修订'}})
        wxq.commit_notes(self.root, [edited])
        self.assertEqual(workspace.notes(self.root)[0]['claims'][0]['origin'], 'manual')
        self.assertEqual(workspace.notes(self.root)[0]['claims'][0]['evidence'], [])

    def test_migration_preserves_unmanaged_edits_and_original_evidence(self):
        note = {'id':'prose','type':'other','title':'已有手写修订','entities':[], 'core':[], 'claims':[
            {'section':'知识内容','text':'旧结论','kind':'mechanic','evidence':[{'source':'BV1:p1','start':0,'end':1}]}]}
        wxq.atomic_json(self.root / 'knowledge/index.json', {'schema_version':1,'notes':[note]})
        wxq.atomic_text(self.root / 'knowledge/other/prose.md', '# 已有手写修订\n\n## 知识内容\n\n新的手写结论\n')
        workspace.migrate(self.root)
        migrated=workspace.notes(self.root)[0]
        self.assertEqual(migrated['claims'][0]['text'], '新的手写结论')
        self.assertTrue(migrated['history'])
        self.assertEqual(migrated['history'][0]['previous']['claims'][0]['evidence'][0]['source'], 'BV1:p1')


if __name__ == '__main__':
    unittest.main()
