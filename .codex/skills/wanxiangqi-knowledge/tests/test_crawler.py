import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / 'frontend'))
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
from crawler import Store, matches_filters, due_creators
from bilibili import BJ
from unittest.mock import patch
from crawler import Runtime, transcript, batch_paths, register_discovered, source_rows
import wxq
import workspace


class CrawlerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))

    def test_inclusive_beijing_dates_and_unknown_numbers(self):
        row = {'published': '2026-10-16', 'view_count': 100, 'duration': 60}
        f = {'date_from': '2026-10-16', 'date_to': '2026-10-16', 'min_views': 100, 'max_duration': 60}
        self.assertTrue(matches_filters(row, f))
        self.assertFalse(matches_filters({**row, 'view_count': None}, f))
        self.assertFalse(matches_filters({**row, 'published': '2026-10-15'}, f))

    def test_duplicate_discovery_merges_keywords_but_single_task(self):
        job = self.store.new_job({'keywords': ['甲', '乙']})
        row = {'bvid': 'BV1234567890', 'title': '标题'}
        self.store.discover(job['id'], row, '甲', True)
        self.store.discover(job['id'], row, '乙', True)
        snap = self.store.job(job['id'])
        self.assertEqual(len(snap['items']), 1)
        self.assertEqual(set(snap['items'][0]['keywords']), {'甲', '乙'})
        self.assertEqual(snap['items'][0]['state'], 'queued')
        other = self.store.new_job({})
        self.store.discover(other['id'], row, '丙', True)
        self.assertEqual(len(self.store.tasks()), 1)

    def test_preview_requires_selection_and_stop_blocks_claim(self):
        job = self.store.new_job({'mode': 'preview'})
        self.store.discover(job['id'], {'bvid': 'BV1234567890'}, '甲', False)
        self.assertIsNone(self.store.claim())
        self.store.enqueue(job['id'], ['BV1234567890'])
        self.store.stop(job['id'])
        self.assertIsNone(self.store.claim())

    def test_recovery_requeues_only_interrupted_tasks(self):
        job = self.store.new_job({})
        self.store.discover(job['id'], {'bvid': 'BV1234567890'}, '', True)
        task = self.store.claim()
        self.assertEqual(task['state'], 'running')
        self.store.recover()
        self.assertEqual(self.store.tasks()[0]['state'], 'queued')

    def test_uid_identity_and_daily_catchup(self):
        a = self.store.save_creator({'name': '甲', 'url': 'https://space.bilibili.com/123/video', 'date_from': '2026-10-01'})
        b = self.store.update_creator('123', {'name': '乙', 'url': 'https://space.bilibili.com/123', 'date_from': '2026-10-01'})
        self.assertEqual(a['uid'], b['uid'])
        self.assertEqual(len(self.store.creators()), 1)
        now = datetime(2026, 10, 16, 10, tzinfo=BJ)
        self.assertEqual(len(due_creators(self.store.creators(), '09:00', now)), 1)
        self.assertEqual(due_creators([{**b, 'last_success': now.isoformat()}], '09:00', now), [])

    def test_creator_blank_keywords_do_not_match_everything(self):
        row = self.store.save_creator({'url':'https://space.bilibili.com/123','date_from':'2026-10-01','keywords':['甲','','  ','甲']})
        self.assertEqual(row['keywords'], ['甲'])

    def test_paths_guard_missing_and_traversal(self):
        root = self.store.root
        wxq.atomic_text(root / 'raw/one.md', '完整文字稿')
        wxq.atomic_text(root / 'secret.txt', 'secret')
        wxq.atomic_json(root / 'raw/index.json', {'sources':{'a':{'path':'raw/one.md'},'b':{'path':'../secret.txt'}}})
        result = batch_paths(root, ['a','a','b','missing'])
        self.assertEqual(len(result['paths']),1)
        self.assertEqual(result['skipped'],2)
        self.assertTrue(Path(result['paths'][0]).is_absolute())
        with self.assertRaises(KeyError):
            transcript(root, 'b')

    def test_registration_preserves_manual_title_and_notes(self):
        wxq.init_store(self.store.root)
        workspace.register_source(self.store.root, {'url':'https://www.bilibili.com/video/BV1234567890','title':'人工标题','notes':'人工备注'})
        register_discovered(self.store.root, {'bvid':'BV1234567890','url':'https://www.bilibili.com/video/BV1234567890','title':'新标题'})
        row=workspace.sources(self.store.root)[0]
        self.assertEqual((row['title'],row['notes']),('人工标题','人工备注'))

    def test_scan_cap_and_duplicate_keywords(self):
        runtime = Runtime(self.store.root)
        wxq.init_store(self.store.root)
        job = runtime.store.new_job({'keywords':['甲','乙'],'mode':'preview','scan_limit':1})
        video={'bvid':'BV1234567890','url':'https://www.bilibili.com/video/BV1234567890','title':'教学','published':'2026-10-16','view_count':100,'duration':60}
        with patch('crawler.Bilibili') as adapter:
            adapter.return_value.search_page.return_value=([video,{**video,'bvid':'BV2345678901'}],True)
            runtime.scan(job)
        result=runtime.store.job(job['id'])
        self.assertEqual(result['scanned'],2)
        self.assertEqual(result['matched'],1)
        self.assertEqual(result['limited'],1)
        self.assertEqual(set(result['items'][0]['keywords']),{'甲','乙'})
        self.assertEqual(runtime.store.tasks(),[])

    def test_failed_space_check_does_not_advance_success(self):
        runtime=Runtime(self.store.root)
        runtime.store.save_creator({'url':'https://space.bilibili.com/123','date_from':'2026-10-01'})
        job=runtime.store.check_creator('123')
        with patch('crawler.Bilibili',side_effect=RuntimeError('412 风控')):
            runtime.scan(job)
        creator=runtime.store.creators()[0]
        self.assertNotIn('last_success',creator)
        self.assertIn('412',creator['error'])
        self.assertEqual(runtime.store.job(job['id'])['state'],'failed')

    def test_process_limit_does_not_block_second_keyword_attribution(self):
        job=self.store.new_job({'process_limit':1})
        self.store.discover(job['id'],{'bvid':'BV1234567890'},'甲',True)
        self.store.discover(job['id'],{'bvid':'BV1234567890'},'乙',True)
        self.store.discover(job['id'],{'bvid':'BV2345678901'},'甲',True)
        self.assertEqual(len(self.store.tasks()),1)
        self.assertEqual(len(self.store.job(job['id'])['items']),2)

    def test_claim_is_atomic_across_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        job=self.store.new_job({})
        self.store.discover(job['id'],{'bvid':'BV1234567890'},'',True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: self.store.claim(),range(2)))
        self.assertEqual(sum(r is not None for r in results),1)

    def test_dormant_queued_task_resumes_when_discovered_in_new_job(self):
        first=self.store.new_job({})
        video={'bvid':'BV1234567890'}
        self.store.discover(first['id'],video,'甲',True)
        self.store.stop(first['id'])
        self.assertIsNone(self.store.claim())
        second=self.store.new_job({})
        self.store.discover(second['id'],video,'乙',True)
        self.assertIsNotNone(self.store.claim())

    def test_failed_worker_spawn_is_retryable(self):
        runtime=Runtime(self.store.root)
        job=runtime.store.new_job({})
        runtime.store.discover(job['id'],{'bvid':'BV1234567890'},'',True)
        task=runtime.store.claim()
        with patch('crawler.subprocess.Popen',side_effect=OSError('cannot start worker')):
            runtime.process_task(task)
        self.assertEqual(runtime.store.tasks()[0]['state'],'failed')
        self.assertEqual(runtime.processes, {})

    def test_preview_projection_and_old_pending_are_not_lost(self):
        old=self.store.new_job({})
        self.store.discover(old['id'],{'bvid':'BV1234567890'},'甲',False)
        self.assertEqual(self.store.projections()['BV1234567890']['acquisition_state'],'preview')
        for _ in range(101):
            newer=self.store.new_job({})
            self.store.stop(newer['id'])
        self.assertEqual(self.store.next_pending()['id'],old['id'])

    def test_recovery_does_not_steal_a_surviving_worker(self):
        from processing_lock import file_lock
        job=self.store.new_job({})
        self.store.discover(job['id'],{'bvid':'BV1234567890'},'',True)
        self.store.claim()
        with file_lock(self.store.root/'raw/crawler/locks/BV1234567890.lock'):
            self.store.recover()
            self.assertEqual(self.store.tasks()[0]['state'],'running')
        self.store.recover()
        self.assertEqual(self.store.tasks()[0]['state'],'queued')


if __name__ == '__main__':
    unittest.main()
