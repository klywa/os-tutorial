"""External acquisition must leave canonical knowledge and Git status untouched."""
import copy
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT/'frontend'), str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store as store
import official
import official_sync as sync
import workspace
import wxq
from test_official_profiles import sample


class QuietSyncTests(unittest.TestCase):
    def setUp(self):
        base = ROOT/'raw/test-temp'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        store.initialize(self.root)
        (self.root/'.gitignore').write_bytes((ROOT/'.gitignore').read_bytes())
        self.bundle = official.normalize(sample(), 'https://official.test/data', 'today')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'baseline')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.STDOUT).decode('utf-8')

    def knowledge(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in (self.root/'knowledge').rglob('*.json') if 'cards' not in p.relative_to(self.root/'knowledge').parts
                and p.name not in ('source-registry.meta.json', 'document-sources.meta.json')}

    def test_default_publication_and_repeat_keep_git_clean(self):
        before = self.knowledge()
        for i in range(2):
            report = sync.publish(self.root, self.bundle, self.root/f'raw/official-sync/runs/{i}')
            self.assertEqual(report['updated_notes'], 0)
            self.assertEqual(self.knowledge(), before)
            self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertTrue((self.root/'entities/players.json').exists())

    def test_worker_run_and_retry_keep_git_clean(self):
        with patch.object(sync, 'fetch_bundle', return_value=self.bundle), \
             patch('card_images.sync_images', return_value={'errors':[]}):
            sync.run(self.root)
            sync.configure(self.root, {'action':'retry'})
            sync.run(self.root)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_sources_annotations_and_documents_are_local(self):
        from crawler import Store, source_rows, register_discovered
        from source_edit import save_metadata
        import document_sources
        queue = Store(self.root)
        url = 'https://www.bilibili.com/video/BV1234567890'
        sid = workspace.register_source(self.root, {'url':url})['id']
        register_discovered(self.root, {'url':url, 'title':'外部标题', 'bvid':'BV1234567890'})
        row = source_rows(self.root, queue, source_ids=[sid])[0]
        save_metadata(self.root, sid, {'revision':row['revision'], 'tags':['标签'], 'notes':'备注'}, queue)
        doc = self.root/'raw/input.docx'
        with zipfile.ZipFile(doc, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>原始文档</w:t></w:r></w:p></w:body></w:document>')
        document_sources.register(self.root, doc)
        self.assertTrue(wxq.read_json(self.root/'knowledge/document-sources.json')['documents'])
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_explicit_apply_after_cache_sync_creates_notes(self):
        sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/cache')
        result = sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/apply', apply_notes=True)
        self.assertEqual(result['updated_notes'], 1)
        self.assertTrue(store.read(self.root/store.INDEX)['notes'])
        self.assertTrue(self.git('status', '--porcelain'))
        before = self.knowledge()
        changed = copy.deepcopy(self.bundle)
        changed['players']['player:1']['name'] += '新'
        sync.publish(self.root, changed, self.root/'raw/official-sync/runs/changed')
        self.assertEqual(before, self.knowledge())

    def test_legacy_official_manifest_and_pending_save_are_deferred_on_read(self):
        sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/first', apply_notes=True)
        nid = store.read(self.root/store.INDEX)['notes'][0]['id']
        record = store.load_record(self.root, nid)
        record['body']['nodes'][2]['value'] = '未授权的自动更新'
        journal = store.save(self.root, [record], origin='official', partial=True, prepare_only=True)
        journal.pop('origin', None)  # Existing installations have journals without this field.
        wxq.atomic_json(self.root/sync.JOURNAL, {'files':[], 'notes':journal, 'success':{'state':'success'}})
        wxq.atomic_json(self.root/store.JOURNAL, journal)  # Crash after shared journal was copied.
        before = self.knowledge()
        self.assertNotEqual(store.load_record(self.root, nid)['body']['nodes'][2].get('value'), '未授权的自动更新')
        workspace.recover(self.root)
        workspace.recover(self.root)
        self.assertEqual(before, self.knowledge())
        self.assertNotEqual(store.load_record(self.root, nid)['body']['nodes'][2].get('value'), '未授权的自动更新')
        self.assertTrue(list((self.root/'raw/official-sync/pending-notes').glob('*.json')))
        self.assertFalse((self.root/store.JOURNAL).exists())

    def test_standalone_old_official_save_is_deferred(self):
        sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/first', apply_notes=True)
        nid = store.read(self.root/store.INDEX)['notes'][0]['id']
        record = store.load_record(self.root, nid)
        record['body']['nodes'][2]['value'] = '旧自动事务'
        journal = store.save(self.root, [record], origin='official', partial=True, prepare_only=True)
        journal.pop('origin', None)
        wxq.atomic_json(self.root/store.JOURNAL, journal)
        before = self.knowledge()
        workspace.recover(self.root)
        self.assertEqual(before, self.knowledge())

    def test_cached_official_changes_are_applied_later_to_existing_notes(self):
        import json_document
        sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/first', apply_notes=True)
        data = sample()
        data['lords'][0]['talent'][0]['cards'][0]['desc'] = '明确更新后的机制'
        changed = official.normalize(data, 'https://official.test/data', 'later')
        before = self.knowledge()
        sync.publish(self.root, changed, self.root/'raw/official-sync/runs/cache')
        self.assertEqual(before, self.knowledge())
        sync.publish(self.root, changed, self.root/'raw/official-sync/runs/apply', apply_notes=True)
        nid = store.read(self.root/store.INDEX)['notes'][0]['id']
        self.assertIn('明确更新后的机制', json_document.markdown(store.load_record(self.root, nid)['body']))

    def test_cli_requires_explicit_apply_flag(self):
        with patch('sys.argv', ['wxq', '--root', str(self.root), 'sync-entities', '--apply-notes']), \
             patch('official.sync_official', return_value={}) as run:
            wxq.main()
        run.assert_called_once_with(self.root, apply_notes=True)

    def test_originless_metadata_only_journal_is_not_replayed(self):
        sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/first', apply_notes=True)
        nid = store.read(self.root/store.INDEX)['notes'][0]['id']
        record = store.load_record(self.root, nid)
        record['metadata']['aliases'] = ['旧自动别名']
        journal = store.save(self.root, [record], origin='usage_aliases', partial=True, prepare_only=True)
        journal.pop('origin')
        self.assertEqual(journal['versions'], [])
        wxq.atomic_json(self.root/store.JOURNAL, journal)
        before = self.knowledge()
        workspace.recover(self.root)
        self.assertEqual(before, self.knowledge())

    def test_partial_official_write_reads_baseline_without_rewriting_files(self):
        sync.publish(self.root, self.bundle, self.root/'raw/official-sync/runs/first', apply_notes=True)
        row = store.read(self.root/store.INDEX)['notes'][0]
        original = store.load_record(self.root, row['id'])
        record = copy.deepcopy(original)
        record['body']['nodes'][2]['value'] = '中断时已写入的新内容'
        journal = store.save(self.root, [record], origin='official', partial=True, prepare_only=True)
        journal.pop('origin')
        wxq.atomic_json(self.root/store.JOURNAL, journal)
        store.write_file(self.root/row['path'], journal['records'][0]['body'])
        before = self.knowledge()
        workspace.recover(self.root)
        self.assertEqual(before, self.knowledge())
        self.assertEqual(store.load_record(self.root, row['id']), original)
        self.assertEqual(store.records(self.root)[0], original)
        # A crash may also have published metadata before replacing the index.
        store.write_file(self.root/store.meta_path(row['path']), journal['records'][0]['metadata'])
        wxq.atomic_json(self.root/store.JOURNAL, journal)
        before = self.knowledge()
        workspace.recover(self.root)
        self.assertEqual(before, self.knowledge())
        self.assertEqual(store.load_record(self.root, row['id']), original)
        data = sample()
        data['lords'][0]['talent'][0]['cards'][0]['desc'] = '明确应用后恢复一致'
        changed = official.normalize(data, 'https://official.test/data', 'later')
        sync.publish(self.root, changed, self.root/'raw/official-sync/runs/repair', apply_notes=True)
        import json_document
        self.assertIn('明确应用后恢复一致', json_document.markdown(store.load_record(self.root, row['id'])['body']))
        self.assertEqual(store.read(self.root/row['path']), store.load_record(self.root, row['id'])['body'])


if __name__ == '__main__':
    unittest.main()
