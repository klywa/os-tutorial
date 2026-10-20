"""Source lists use one consistent knowledge snapshot, regardless of source count."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
sys.path.insert(0, str(ROOT / 'frontend'))
import workspace
import wxq


class SourceProjectionTests(unittest.TestCase):
    def test_unchanged_asr_is_not_reparsed_on_every_poll_and_edits_are_seen(self):
        import crawler
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as folder:
            root=Path(folder);wxq.init_store(root);store=crawler.Store(root)
            sid='BV1234567890:p1';target=wxq.source_dir(root,sid)
            wxq.atomic_json(target/'metadata.json',{'id':sid,'url':'https://www.bilibili.com/video/BV1234567890'})
            corrected=target/'asr.corrected.json'
            wxq.atomic_json(corrected,{'segments':[{'text':'正文'}]})
            wxq.atomic_text(root/'raw/text.md','文字稿')
            wxq.atomic_json(root/'raw/index.json',{'sources':{sid:{'path':'raw/text.md'}}})
            with patch.object(wxq,'read_json',wraps=wxq.read_json) as read:
                crawler.source_rows(root,store);crawler.source_rows(root,store)
            calls=[c for c in read.call_args_list if Path(c.args[0])==corrected]
            self.assertEqual(len(calls),1,'unchanged full ASR should not be loaded for each list poll')
            wxq.atomic_json(corrected,{'segments':[]})
            self.assertEqual(crawler.source_rows(root,store)[0]['transcript_status'],'no_speech')

    def test_subset_keeps_annotations_from_canonical_registry_alias(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as folder:
            root=Path(folder)
            wxq.init_store(root)
            row=workspace.register_source(root,{'url':'https://example.com/video','title':'人工标题','notes':'保留备注'})
            row.update(manual_values={'ignored':True},manual_revision='manual-version')
            wxq.atomic_json(root/'knowledge/source-registry.json',[row])
            wxq.atomic_json(root/'raw/sources/platform123_p1/metadata.json',
                            {'id':'platform123:p1','url':'https://example.com/video','title':'采集标题'})
            expected=workspace.sources(root)
            actual=workspace.sources(root,source_ids=['platform123:p1'])
            self.assertEqual(actual,expected)
            self.assertTrue(actual[0]['manual_values']['ignored'])
            self.assertEqual(workspace.sources(root,source_ids=[row['id']]),[])

    def test_sources_read_notes_once_and_keep_current_and_history_reviews(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as folder:
            root = Path(folder)
            sids = ['BV1234567890:p1', 'BV1234567891:p1']
            for sid in sids:
                target = wxq.source_dir(root, sid)
                wxq.atomic_json(target / 'metadata.json', {'id': sid, 'url':
                    'https://www.bilibili.com/video/' + sid.split(':')[0] + '?p=1'})
                wxq.atomic_json(target / 'state.json', {'stage': 'complete'})
                wxq.atomic_json(target / 'review.json', {'approved': True, 'checked_intervals': [[0, 12]]})
            note = {'id': 'one', 'title': '笔记',
                    'claims': [{'evidence': [{'source': sids[0], 'start': 5, 'end': 10}]}],
                    'history': [{'previous': {'claims': [{'evidence': [
                        {'source': sids[1], 'start': 5, 'end': 20}]}]}}]}
            with patch.object(workspace, 'notes', return_value=[note]) as read_notes:
                rows = {r['id']: r for r in workspace.sources(root)}
            self.assertEqual(read_notes.call_count, 1, 'knowledge index must not be reread for each source')
            self.assertEqual(rows[sids[0]]['knowledge_status'], 'deposited')
            self.assertEqual(rows[sids[1]]['knowledge_status'], 'submitted')
            self.assertFalse(rows[sids[1]]['reviewed'])
            self.assertEqual(rows[sids[1]]['linked_notes'], [{'id': 'one', 'title': '笔记'}])
