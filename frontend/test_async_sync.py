"""Durable background synchronization with isolated Git repositories."""
import json
from pathlib import Path
import threading
import time
import sys
import unittest
from unittest.mock import patch

import test_website_sync as fixtures
import website_sync as sync


class AsyncSyncTests(unittest.TestCase):
    setUp=fixtures.SyncTests.setUp
    identity=fixtures.SyncTests.identity
    other=fixtures.SyncTests.other

    def dirty(self):
        (self.root/'knowledge/players/a.json').write_text('{"value":2}\n')

    def test_enqueue_is_durable_idempotent_and_never_runs_git_sync(self):
        self.dirty()
        with patch.object(self.sync,'retry',side_effect=AssertionError('request ran slow Git')):
            with sync.sync_lock(self.sync.state_dir):
                queued=self.sync.enqueue()
                duplicate=self.sync.enqueue()
        saved=json.loads((self.sync.state_dir/'sync.json').read_text())
        self.assertEqual(saved['state'],'pending')
        self.assertEqual(saved['phase'],'queued')
        self.assertEqual(saved['source_root'],str(self.root.resolve()))
        self.assertEqual(queued['job_id'],duplicate['job_id'])
        self.assertEqual(fixtures.git(self.origin,'show','master:knowledge/players/a.json'),'{'+'"value": 1'+'}')

    def test_light_status_never_scans_git(self):
        with patch.object(self.sync,'_head',side_effect=AssertionError('status invoked Git')), \
                patch.object(self.sync,'_changed',side_effect=AssertionError('status scans all files')):
            self.assertEqual(self.sync.status(light=True)['state'],'synced')

    def test_fast_push_does_not_clone_or_validate_twice(self):
        self.dirty()
        with patch.object(sync,'git',wraps=sync.git) as git, \
                patch.object(self.sync,'_validate',wraps=self.sync._validate) as validate:
            with sync.sync_lock(self.sync.state_dir):status=self.sync.retry()
        self.assertEqual(status['state'],'synced')
        self.assertEqual(validate.call_count,1)
        self.assertFalse(any('clone' in call.args for call in git.call_args_list))

    def test_verified_clean_retry_skips_validation_and_network(self):
        self.dirty()
        with sync.sync_lock(self.sync.state_dir):self.sync.retry()
        with patch.object(self.sync,'_validate',side_effect=AssertionError('clean retry validates')), \
                patch.object(sync,'git',wraps=sync.git) as git:
            with sync.sync_lock(self.sync.state_dir):status=self.sync.retry()
        self.assertEqual(status['state'],'synced')
        self.assertFalse(any('fetch' in call.args or 'clone' in call.args for call in git.call_args_list))

    def test_worker_recovers_unqueued_dirty_save_and_runs_only_once(self):
        self.dirty()
        worker=sync.SyncWorker(self.sync)
        self.assertTrue(worker.step())
        self.assertEqual(self.sync.status()['state'],'synced')
        with patch.object(self.sync,'retry',side_effect=AssertionError('duplicate worker push')):
            self.assertFalse(worker.step())

    def test_worker_retry_backoff_and_manual_conflict_retry(self):
        self.dirty()
        with sync.sync_lock(self.sync.state_dir):self.sync.enqueue()
        worker=sync.SyncWorker(self.sync,clock=lambda:1000)
        with patch.object(self.sync,'retry',return_value={'state':'pending','error':'offline'}):
            self.assertTrue(worker.step())
        status=self.sync.status(light=True)
        self.assertEqual(status['next_retry_at'],1030)
        self.assertEqual(status['phase'],'waiting-retry')
        with patch.object(self.sync,'retry',side_effect=AssertionError('too early')):
            self.assertFalse(worker.step())
        for now,expected in ((1030,1090),(1090,1210),(1210,1510),(1510,1810)):
            worker.clock=lambda:now
            with patch.object(self.sync,'retry',return_value={'state':'pending','error':'offline'}):worker.step()
            self.assertEqual(self.sync.status(light=True)['next_retry_at'],expected)
        worker.clock=lambda:1810
        with patch.object(self.sync,'retry',side_effect=lambda:self.sync._state('conflict','invalid content')):
            worker.step()
        with patch.object(self.sync,'retry',side_effect=AssertionError('conflict auto retry')):
            self.assertFalse(worker.step())
        with sync.sync_lock(self.sync.state_dir):self.sync.enqueue(force=True)
        self.assertTrue(worker.step())
        self.assertEqual(self.sync.status(light=True)['state'],'synced')

    def test_worker_contention_does_not_modify_job(self):
        self.dirty()
        worker=sync.SyncWorker(self.sync)
        with sync.sync_lock(self.sync.state_dir):
            self.sync.enqueue()
            before=(self.sync.state_dir/'sync.json').read_bytes()
            self.assertFalse(worker.step())
            self.assertEqual((self.sync.state_dir/'sync.json').read_bytes(),before)

    def test_managed_subprocess_is_cancelled_and_reaped(self):
        stop=threading.Event(); errors=[]
        marker=self.base/'child-started'
        def run():
            token=sync._cancellation.set(stop)
            try:
                sync.run_process([sys.executable,'-c',
                    f'from pathlib import Path; import time; Path({str(marker)!r}).write_text("ready"); time.sleep(60)'],
                    capture_output=True,text=True)
            except sync.SyncCancelled:errors.append('cancelled')
            finally:sync._cancellation.reset(token)
        with patch.object(sync,'_stop_child',wraps=sync._stop_child) as cleanup:
            thread=threading.Thread(target=run);thread.start()
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(marker.exists())
            stop.set();thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,['cancelled'])
            self.assertIsNotNone(cleanup.call_args.args[0].poll())

    def test_worker_close_preserves_job_and_next_start_completes_it(self):
        self.dirty()
        with sync.sync_lock(self.sync.state_dir):self.sync.enqueue()
        marker=self.base/'validation-started'
        original=self.sync._validate
        def delayed(root):
            sync.run_process([sys.executable,'-c',
                f'from pathlib import Path; import time; Path({str(marker)!r}).write_text("ready"); time.sleep(60)'],
                capture_output=True,text=True)
        self.sync._validate=delayed
        worker=sync.SyncWorker(self.sync).start()
        try:
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(marker.exists())
        finally:worker.close();self.sync._validate=original
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(self.sync.status(light=True)['state'],'pending')
        self.assertEqual(json.loads((self.root/'knowledge/players/a.json').read_text())['value'],2)
        self.assertTrue(sync.SyncWorker(self.sync).step())
        self.assertEqual(self.sync.status(light=True)['state'],'synced')

    def test_foreign_source_job_is_never_claimed_or_overwritten(self):
        self.dirty()
        with sync.sync_lock(self.sync.state_dir):self.sync.enqueue()
        path=self.sync.state_dir/'sync.json'
        value=json.loads(path.read_text());value['source_root']=str(self.base/'other-release')
        path.write_text(json.dumps(value));before=path.read_bytes()
        worker=sync.SyncWorker(self.sync)
        self.assertFalse(worker.step())
        self.assertTrue(worker.stop_event.is_set())
        with sync.sync_lock(self.sync.state_dir),self.assertRaises(sync.StaleSync):
            self.sync.enqueue(force=True)
        with sync.sync_lock(self.sync.state_dir),self.assertRaises(sync.StaleSync):
            self.sync.retry()
        self.assertEqual(path.read_bytes(),before)

    def test_old_release_cannot_publish_state_after_current_pointer_changes(self):
        self.dirty()
        with sync.sync_lock(self.sync.state_dir):self.sync.enqueue()
        path=self.sync.state_dir/'sync.json';before=path.read_bytes()
        self.sync.root=self.base/'site/releases/old'
        current=self.base/'site/current';current.parent.mkdir(parents=True);current.touch()
        with patch.object(Path,'resolve',return_value=self.base/'site/releases/new'):
            with self.assertRaises(sync.StaleSync):self.sync._state('synced')
        self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
