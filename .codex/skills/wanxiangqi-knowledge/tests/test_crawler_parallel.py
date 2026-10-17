"""Deletion and concurrency contracts (no real media/network requests)."""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / 'frontend'))
import crawler


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.runtime = crawler.Runtime(Path(self.tmp.name))
        self.addCleanup(self.runtime.close)
        self.store = self.runtime.store

    def add(self, bv):
        job = self.store.new_job({'keywords': [bv]})
        self.store.discover(job['id'], {'bvid': bv}, '', True)
        self.store.update_job(job['id'], state='scanned')
        return job

    def test_delete_removes_history_and_dispatch_but_preserves_source_projection(self):
        job = self.add('BV1234567890')
        self.store.delete_job(job['id'])
        self.assertNotIn(job['id'], [j['id'] for j in self.store.jobs()])
        self.assertIsNone(self.store.claim())
        self.assertIn('BV1234567890', self.store.projections())
        self.assertEqual(self.store.tasks()[0]['state'], 'cancelled')
        self.store.update_job(job['id'], state='scanning')
        self.assertEqual(self.store.job(job['id'])['state'], 'deleted')

    def test_deleting_shared_job_keeps_other_video_request(self):
        one = self.add('BV1234567890')
        two = self.add('BV1234567890')
        self.store.delete_job(one['id'])
        self.assertTrue(self.store.requested('BV1234567890'))
        self.assertIsNotNone(self.store.claim())
        self.store.delete_job(two['id'])
        self.assertFalse(self.store.requested('BV1234567890'))

    def test_round_robin_claim_prefers_other_job_over_same_batch(self):
        one = self.add('BV1234567890')
        self.store.discover(one['id'], {'bvid': 'BV2345678901'}, '', True)
        self.add('BV3456789012')
        self.assertEqual(self.store.claim()['bvid'], 'BV1234567890')
        self.assertEqual(self.store.claim()['bvid'], 'BV3456789012')

    def test_scan_and_two_videos_run_concurrently_without_blocking_tick(self):
        self.add('BV1234567890')
        self.add('BV2345678901')
        scan_job = self.store.new_job({'keywords': ['search']})
        release = threading.Event()
        started = set()
        guard = threading.Lock()
        def block_media(task):
            with guard:
                started.add(task['bvid'])
            release.wait(5)
            self.store.finish_task(task['bvid'], 'succeeded')
        def block_scan(job):
            with guard:
                started.add(job['id'])
            release.wait(5)
        try:
            with patch.object(self.runtime, 'scan', side_effect=block_scan), patch.object(self.runtime, 'process_task', side_effect=block_media):
                before = time.monotonic()
                self.runtime.tick()
                self.assertLess(time.monotonic() - before, 1)
                deadline = time.monotonic() + 2
                while len(started) < 3 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(started, {'BV1234567890', 'BV2345678901', scan_job['id']})
        finally:
            release.set()

    def test_worker_limit_is_configurable_and_validated(self):
        self.assertEqual(self.store.settings()['parallelism'], 2)
        self.store.settings({'parallelism': 1})
        self.assertEqual(self.store.settings()['parallelism'], 1)
        with self.assertRaises(ValueError):
            self.store.settings({'parallelism': 0})

    def test_delete_running_shared_worker_only_cancels_last_request(self):
        from unittest.mock import Mock
        one = self.add('BV1234567890')
        two = self.add('BV1234567890')
        process = Mock(returncode=None)
        process.poll.side_effect = lambda: process.returncode
        cancelled = threading.Event()
        def terminate(p):
            p.returncode = -15
            cancelled.set()
        with patch('crawler.subprocess.Popen', return_value=process), patch('crawler.terminate_worker', side_effect=terminate):
            self.runtime.tick()
            deadline = time.monotonic() + 2
            while not self.runtime.processes and time.monotonic() < deadline:
                time.sleep(.01)
            self.store.delete_job(one['id'])
            self.assertFalse(cancelled.wait(.35))
            self.store.delete_job(two['id'])
            self.assertTrue(cancelled.wait(2))
            for future in self.runtime.workers.values():
                future.result(timeout=2)
        self.assertEqual(self.store.tasks()[0]['state'], 'cancelled')
        self.store.finish_task('BV1234567890', 'running', progress={'phase':'transcribing'})
        self.assertEqual(self.store.tasks()[0]['state'], 'cancelled')

    def test_surviving_worker_observes_deleted_job_without_http_parent(self):
        from crawler_worker import watch_requests
        job = self.add('BV1234567890')
        self.store.claim()
        stopped, cancelled = threading.Event(), threading.Event()
        thread = threading.Thread(target=watch_requests, args=(self.store,'BV1234567890',stopped,cancelled.set))
        thread.start()
        try:
            self.assertFalse(cancelled.wait(.1))
            self.store.delete_job(job['id'])
            self.assertTrue(cancelled.wait(2))
            self.assertEqual(self.store.tasks()[0]['state'], 'cancelled')
        finally:
            stopped.set()
            thread.join(timeout=2)

    def test_deleted_scan_cannot_register_late_results_or_be_restarted(self):
        job = self.store.new_job({'keywords':['late']})
        self.store.begin_scan(job['id'])
        self.store.delete_job(job['id'])
        self.assertFalse(self.store.discover(job['id'],{'bvid':'BV1234567890'},'late',True))
        self.store.resume(job['id'])
        self.assertEqual(self.store.job(job['id'])['state'],'deleted')
        self.assertEqual(self.store.projections(),{})

    def test_requeued_video_and_resumed_scan_do_not_replace_inflight_futures(self):
        from concurrent.futures import Future
        one = self.add('BV1234567890')
        self.store.claim()
        self.store.finish_task('BV1234567890','queued')
        self.store.resume(one['id'])
        self.runtime.workers['BV1234567890'] = media = Future()
        self.runtime.scans[one['id']] = scan = Future()
        self.runtime.tick()
        self.assertIs(self.runtime.workers['BV1234567890'],media)
        self.assertIs(self.runtime.scans[one['id']],scan)
        self.assertEqual(self.store.tasks()[0]['state'],'queued')

    def test_phase_stop_preserves_checkpoint_and_blocks_late_callbacks(self):
        job = self.add('BV1234567890')
        self.store.claim()
        progress = {'phase': 'transcribing', 'processed_seconds': 30, 'total_seconds': 100}
        self.store.finish_task('BV1234567890', 'running', progress=progress)
        with self.assertRaises(ValueError):
            self.store.control_task('BV1234567890', 'stop-download')
        self.store.control_task('BV1234567890', 'stop-transcribe')
        self.store.finish_task('BV1234567890', 'failed', 'late callback')
        self.store.recover()
        self.assertEqual(self.store.job(job['id'])['items'][0]['state'], 'paused')
        self.assertEqual(self.store.activity()[0]['progress'], progress)
        self.assertFalse(self.store.requested('BV1234567890'))
        self.assertIsNone(self.store.claim())
        self.store.control_task('BV1234567890', 'resume')
        self.assertIsNotNone(self.store.claim())

    def test_old_run_cannot_overwrite_resumed_video_after_lock_release(self):
        self.add('BV1234567890')
        old = self.store.claim()
        self.store.finish_task('BV1234567890', 'running', progress={'phase':'downloading'})
        self.store.control_task('BV1234567890', 'stop-download')
        self.store.control_task('BV1234567890', 'resume')
        self.store.finish_task('BV1234567890', 'failed', 'old run', generation=old['generation'])
        self.assertEqual(self.store.tasks()[0]['state'], 'queued')
        new = self.store.claim()
        self.assertFalse(self.store.requested('BV1234567890', old['generation']))
        self.store.finish_task('BV1234567890', 'succeeded', generation=old['generation'])
        self.assertEqual(self.store.tasks()[0]['state'], 'running')
        self.store.finish_task('BV1234567890', 'succeeded', generation=new['generation'])
        self.assertEqual(self.store.tasks()[0]['state'], 'succeeded')

    def test_global_activity_merges_shared_batches_and_video_delete(self):
        one = self.add('BV1234567890')
        two = self.add('BV1234567890')
        self.store.claim()
        rows = self.store.activity()
        self.assertEqual(len(rows), 1)
        self.assertEqual({j['id'] for j in rows[0]['jobs']}, {one['id'], two['id']})
        self.store.control_task('BV1234567890', 'delete')
        self.assertEqual(self.store.activity(), [])
        self.store.finish_task('BV1234567890', 'succeeded')
        self.assertEqual(self.store.tasks()[0]['state'], 'cancelled')

    def test_paused_worker_observes_stop_without_http_parent(self):
        from crawler_worker import watch_requests
        self.add('BV1234567890')
        self.store.claim()
        self.store.finish_task('BV1234567890', 'running', progress={'phase': 'downloading'})
        stopped, cancelled = threading.Event(), threading.Event()
        thread = threading.Thread(target=watch_requests, args=(self.store, 'BV1234567890', stopped, cancelled.set))
        thread.start()
        try:
            self.store.control_task('BV1234567890', 'stop-download')
            self.assertTrue(cancelled.wait(2))
            self.assertEqual(self.store.tasks()[0]['state'], 'paused')
        finally:
            stopped.set()
            thread.join(timeout=2)

    def test_cancel_watcher_rechecks_atomic_orphan_result(self):
        from crawler_worker import watch_requests
        from unittest.mock import Mock
        stopped=threading.Event()
        store=Mock()
        store.halted.return_value=False
        store.requested.return_value=False
        store.cancel_orphan.side_effect=lambda _: (stopped.set() or False)
        cancel=Mock()
        watch_requests(store,'BV1234567890',stopped,cancel)
        cancel.assert_not_called()


if __name__ == '__main__':
    unittest.main()
