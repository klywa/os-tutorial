import sys
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import json_store as store
import json_document
import note_review


class IncrementalSaveTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[4] / 'raw/test-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.root = Path(self.temp.name)
        items = [{'body': json_document.parse(f'# {name}\n\n## 说明\n\n原文。\n'),
                  'metadata': {'id': name, 'type': 'other', 'title': name, 'path': f'knowledge/other/{name}.json'}} for name in ('a', 'b')]
        store.save(self.root, items)

    def tearDown(self):
        self.temp.cleanup()

    def test_single_edit_does_not_read_or_write_other_note(self):
        note = store.resolve_note(self.root, 'a')
        body = note['document']; body['nodes'][-1]['value'] = '新文。'
        original_read, original_write = store.read, store.write_file
        def read(path, *args, **kwargs):
            self.assertNotIn(Path(path).name, ('b.json', 'b.meta.json'))
            return original_read(path, *args, **kwargs)
        def write(path, value):
            self.assertNotIn(Path(path).name, ('b.json', 'b.meta.json'))
            return original_write(path, value)
        store._cached_read.cache_clear()
        with patch.object(store, 'read', side_effect=read), patch.object(store, 'write_file', side_effect=write):
            saved = store.edit(self.root, 'a', {'revision': note['revision'], 'document': body}, public=True)
            self.assertEqual(note_review.annotations(self.root, note_id='a'), [])
        self.assertEqual(saved['document']['nodes'], body['nodes'])
        self.assertEqual(saved.get('history'), [])

    def test_partial_journal_overlay_recovery_and_unchanged_files(self):
        note = store.resolve_note(self.root, 'a')
        untouched = {name: (self.root / ('knowledge/other/' + name)).read_bytes() for name in ('b.json', 'b.meta.json')}
        body = note['document']; body['nodes'][-1]['value'] = '事务新文。'
        original_write = store.write_file
        def fail(path, value):
            if Path(path).name == 'a.json':
                raise OSError('interrupted pair publication')
            return original_write(path, value)
        with patch.object(store, 'write_file', side_effect=fail):
            with self.assertRaises(OSError):
                store.edit(self.root, 'a', {'revision': note['revision'], 'document': body})
        journal = store.read(self.root / store.JOURNAL)
        self.assertTrue(journal['delta'])
        self.assertEqual(len(journal['records']), 1)
        self.assertEqual(len(store.records(self.root)), 2)
        self.assertEqual(store.resolve_note(self.root, 'b')['document']['nodes'][-1]['value'], '原文。')
        self.assertEqual(store.resolve_note(self.root, 'a')['document']['nodes'], body['nodes'])
        store.recover(self.root)
        for name, data in untouched.items():
            self.assertEqual((self.root / ('knowledge/other/' + name)).read_bytes(), data)

    def test_version_listing_uses_lightweight_index(self):
        # First call also supports old snapshot directories without an index.
        note_review.versions(self.root, 'a')
        original = store.read
        def read(path, *args, **kwargs):
            if Path(path).parent == note_review.version_folder(self.root, 'a'):
                self.assertEqual(Path(path).name, 'index.meta.json')
            return original(path, *args, **kwargs)
        with patch.object(store, 'read', side_effect=read):
            self.assertEqual(len(note_review.versions(self.root, 'a')), 1)

    def test_old_full_journal_remains_readable_and_recoverable(self):
        records = store.records(self.root)
        index = store.read(self.root / store.INDEX)
        store.write_file(self.root / store.JOURNAL, {'schema_version': 6, 'records': records, 'index': index, 'retired': []})
        self.assertEqual(store.records(self.root), records)
        store.recover(self.root)
        self.assertEqual(len(store.notes(self.root)), 2)

    def test_lineup_matchup_validation_only_needs_note_id_index(self):
        body = json_document.parse('# 阵容\n\n## 英雄\n\n正文。\n')
        body['semantics'] = {'players':['pending:player'], 'core_heroes':[], 'required_factions':[],
                             'compositions':{'early':[], 'middle':[], 'late':[]}, 'ban_conditions':[],
                             'matchups':[{'target':'b','text':'针对建议'}]}
        store.save(self.root, [{'body':body,'metadata':{'id':'lineup','type':'lineup','title':'阵容',
                    'player_id':'pending:player','path':'knowledge/lineups/阵容.json'}}], partial=True)
        note = store.resolve_note(self.root,'lineup');note['document']['nodes'][-1]['value']='新正文'
        with patch('workspace.notes', side_effect=AssertionError('must not project all notes for an ID lookup')):
            store.edit(self.root, 'lineup', {'revision':note['revision'],'document':note['document']}, public=True)

    def test_failed_edit_does_not_mutate_cached_history_or_metadata(self):
        note = store.resolve_note(self.root,'a')
        before = deepcopy(store.load_record(self.root,'a',clone=False))
        note['document']['nodes'][-1]['value']='未保存'
        with patch.object(store,'save',side_effect=OSError('write failure')):
            with self.assertRaises(OSError):
                store.edit(self.root,'a',{'revision':note['revision'],'document':note['document']})
        self.assertEqual(store.load_record(self.root,'a',clone=False),before)

    def test_advertised_pending_version_can_be_opened_before_disk_replay(self):
        note = store.resolve_note(self.root,'a');note['document']['nodes'][-1]['value']='待恢复新文'
        write = store.write_file
        def fail(path,value):
            if Path(path).parent == note_review.version_folder(self.root,'a'):
                raise OSError('snapshot not published yet')
            return write(path,value)
        with patch.object(store,'write_file',side_effect=fail):
            with self.assertRaises(OSError):store.edit(self.root,'a',{'revision':note['revision'],'document':note['document']})
        latest = note_review.versions(self.root,'a')[0]
        self.assertEqual(note_review.version(self.root,'a',latest['id'])['record']['body']['nodes'][-1]['value'],'待恢复新文')


if __name__ == '__main__':
    unittest.main()
