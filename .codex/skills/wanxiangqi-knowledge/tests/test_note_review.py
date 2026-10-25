import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import json_document
import json_store
import note_review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[4] / 'raw/test-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.root = Path(self.temp.name)
        record = {'body': json_document.parse('# 测试\n\n## 英雄\n\n原文。\n'),
                  'metadata': {'id': 'test', 'type': 'other', 'title': '测试', 'path': 'knowledge/other/测试.json'}}
        json_store.save(self.root, [record])

    def tearDown(self):
        self.temp.cleanup()

    def test_versions_include_baseline_and_changes_but_not_noop(self):
        before = json_store.notes(self.root)[0]
        body = before['document']; body['nodes'][-1]['value'] = '新文。'
        saved = json_store.edit(self.root, 'test', {'revision': before['revision'], 'document': body})
        versions = note_review.versions(self.root, 'test')
        self.assertEqual(len(versions), 2)
        self.assertEqual(note_review.version(self.root, 'test', versions[0]['id'])['record']['body'], saved['document'])
        json_store.edit(self.root, 'test', {'revision': saved['revision'], 'document': saved['document']})
        self.assertEqual(len(note_review.versions(self.root, 'test')), 2)

    def test_snapshot_failure_does_not_publish_body_and_recovery_finishes(self):
        before = json_store.notes(self.root)[0]
        body = before['document']; body['nodes'][-1]['value'] = '新文。'
        write = json_store.write_file
        def fail(path, value):
            if 'versions' in Path(path).parts:
                raise OSError('snapshot failed')
            return write(path, value)
        with patch.object(json_store, 'write_file', side_effect=fail):
            with self.assertRaises(OSError):
                json_store.edit(self.root, 'test', {'revision': before['revision'], 'document': body})
        disk = json_store.read(self.root / 'knowledge/other/测试.json')
        self.assertEqual(disk['nodes'][-1]['value'], '原文。')
        json_store.recover(self.root)
        self.assertEqual(len(note_review.versions(self.root, 'test')), 2)

    def test_comment_concurrency_and_anchor_changes(self):
        note = json_store.notes(self.root)[0]
        node = note['document']['nodes'][-1]
        comment = note_review.mutate(self.root, {'note_id': 'test', 'node_id': node['id'], 'text': '补充条件', 'note_revision': note['revision']})
        self.assertEqual(note_review.annotations(self.root, status='open')[0]['anchor_state'], 'current')
        updated = note_review.mutate(self.root, {'id': comment['id'], 'revision': comment['revision'], 'text': '说明原因'})
        with self.assertRaises(ValueError):
            note_review.mutate(self.root, {'id': comment['id'], 'revision': comment['revision'], 'text': '覆盖'})
        body = note['document']; body['nodes'][-1]['value'] = '人工新文'
        json_store.edit(self.root, 'test', {'revision': note['revision'], 'document': body})
        self.assertEqual(note_review.annotations(self.root)[0]['anchor_state'], 'changed')
        with self.assertRaises(ValueError):
            note_review.complete(self.root, updated['id'], {'revision': updated['revision'], 'result_revision': 'wrong', 'result': '完成'})

    def test_review_commit_authorizes_only_target_and_completion_is_idempotent(self):
        note = json_store.notes(self.root)[0]
        comment = note_review.mutate(self.root, {'note_id': 'test', 'node_id': note['document']['nodes'][-1]['id'],
                                                'text': '说明原因', 'note_revision': note['revision']})
        # A real manual edit makes this node protected before annotating it again.
        record = json_store.records(self.root)[0]
        record['metadata']['node_annotations'] = {comment['node_id']: {'origin': 'manual'}}
        json_store.save(self.root, [record])
        record = json_store.records(self.root)[0]
        record['body']['nodes'][-1]['value'] = '待确认'
        record['review_refs'] = [{'id': comment['id'], 'revision': comment['revision']}]
        with patch('wxq.entities', return_value=[]):
            json_store.commit(self.root, [record])
        saved = json_store.records(self.root)[0]
        self.assertEqual(saved['body']['nodes'][-1]['value'], '待确认')
        with patch('wxq.validate_store', return_value={'errors': []}):
            payload = {'revision': comment['revision'], 'result_revision': saved['metadata']['revision'], 'result': '已标记缺项'}
            done = note_review.complete(self.root, comment['id'], payload)
            self.assertEqual(done['status'], 'resolved')
            self.assertEqual(note_review.complete(self.root, comment['id'], payload)['revision'], done['revision'])

    def test_history_restores_evidence_only_for_exact_historical_content(self):
        record = json_store.records(self.root)[0]
        node_id = record['body']['nodes'][-1]['id']
        record['metadata']['claim_annotations'] = [{'id': 'c', 'text_ref': node_id, 'kind': 'mechanic', 'evidence': [{'source': 's'}]}]
        json_store.save(self.root, [record])
        note = json_store.notes(self.root)[0]
        old_body = __import__('copy').deepcopy(note['document'])
        note['document']['nodes'][-1]['value'] = '人工改写'
        changed = json_store.edit(self.root, 'test', {'revision': note['revision'], 'document': note['document']})
        old_version = next(v for v in note_review.versions(self.root, 'test') if v['body_sha256'] == json_store.digest(old_body))
        with patch.object(json_store, 'check_evidence'):
            restored = json_store.edit(self.root, 'test', {'revision': changed['revision'], 'document': old_body, 'restore_version': old_version['id']})
        self.assertEqual(restored['claims'][0]['evidence'], [{'source': 's'}])
        old_body['nodes'][-1]['value'] = '继续编辑新话术'
        edited = json_store.edit(self.root, 'test', {'revision': restored['revision'], 'document': old_body, 'restore_version': old_version['id']})
        self.assertEqual(edited['claims'][0]['evidence'], [])

    def test_editorial_review_is_scoped_and_manual_edit_invalidates_completion_receipt(self):
        note = json_store.notes(self.root)[0]
        target = note['document']['nodes'][-1]['id']
        comment = note_review.mutate(self.root, {'note_id': 'test', 'node_id': target, 'text': '措辞精简', 'note_revision': note['revision']})
        refs = [{'id': comment['id'], 'revision': comment['revision']}]
        body = __import__('copy').deepcopy(note['document'])
        body['nodes'][1]['title'] = '越界标题'
        with self.assertRaises(ValueError):
            note_review.apply_editorial(self.root, {'note_id': 'test', 'revision': note['revision'], 'document': body, 'review_refs': refs})
        body['nodes'][1]['title'] = note['document']['nodes'][1]['title']
        body['nodes'][-1]['value'] = '精简原文'
        saved = note_review.apply_editorial(self.root, {'note_id': 'test', 'revision': note['revision'], 'document': body, 'review_refs': refs})
        self.assertEqual(saved['document']['nodes'][-1]['value'], '精简原文')
        self.assertEqual(json_store.records(self.root)[0]['metadata']['review_receipts'], refs)
        body['nodes'][-1]['value'] = '后续人工修改'
        json_store.edit(self.root, 'test', {'revision': saved['revision'], 'document': body})
        self.assertEqual(json_store.records(self.root)[0]['metadata'].get('review_receipts'), [])

    def test_history_does_not_rewrite_unchanged_supporting_evidence(self):
        record = json_store.records(self.root)[0]
        record['body']['supporting_nodes'] = [{'id': 'support', 'type': 'entry', 'key': '正文', 'show_key': False, 'value': '支撑结论'}]
        record['metadata']['claim_annotations'] = [{'id': 'support-claim', 'text_ref': 'support', 'kind': 'mechanic', 'evidence': [{'source': 'historical'}]}]
        json_store.save(self.root, [record])
        historical = note_review.versions(self.root, 'test')[0]['id']
        before = json_store.records(self.root)[0]
        before['metadata']['claim_annotations'][0].update(origin='manual', evidence=[])
        after = __import__('copy').deepcopy(before)
        after['body']['nodes'][-1]['value'] = '无关正文变化'
        with patch.object(json_store, 'check_evidence'):
            note_review.restore_evidence(self.root, 'test', historical, before, after)
        self.assertEqual(after['metadata']['claim_annotations'][0]['evidence'], [])
        self.assertEqual(after['metadata']['claim_annotations'][0]['origin'], 'manual')


if __name__ == '__main__':
    unittest.main()
