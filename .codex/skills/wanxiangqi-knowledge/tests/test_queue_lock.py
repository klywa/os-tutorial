"""Slow artifact reads must not own the acquisition queue's write lock."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / 'frontend'))
from crawler import Store
from link_jobs import start_links, reconcile
import wxq


class QueueLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root)
        self.bv = 'BV1234567890'
        self.job = start_links(self.store, self.bv)['job']
        self.task = self.store.claim()
        wxq.atomic_json(self.root / f'raw/sources/{self.bv}_p1/metadata.json',
                        {'id': self.bv + ':p1', 'part': 1, 'part_count': 1})

    def while_reading(self, operation):
        entered, release, wrote = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def slow(*args):
            entered.set()
            if not release.wait(4):
                raise TimeoutError('artifact read blocked')
            return []
        def run():
            try: operation()
            except BaseException as exc: errors.append(exc)
        def write():
            try:
                self.store.settings({'parallelism': 3})
                wrote.set()
            except BaseException as exc: errors.append(exc)
        with patch('reference_store.transcript_errors', side_effect=slow):
            reader = threading.Thread(target=run)
            reader.start()
            try:
                self.assertTrue(entered.wait(2))
                writer = threading.Thread(target=write)
                writer.start()
                try: self.assertTrue(wrote.wait(1), 'artifact validation holds queue write lock')
                finally:
                    release.set()
                    writer.join(5)
            finally:
                release.set()
                reader.join(5)
        self.assertFalse(reader.is_alive())
        self.assertEqual(errors, [])

    def test_enqueue_validation_allows_progress_write(self):
        other = self.store.new_job({'mode': 'preview'})
        self.store.discover(other['id'], {'bvid': self.bv}, '', False)
        self.while_reading(lambda: self.store.enqueue(other['id'], [self.bv]))

    def test_finish_validation_allows_progress_write(self):
        self.while_reading(lambda: self.store.finish_task(self.bv, 'succeeded', generation=self.task['generation']))

    def test_reconcile_validation_allows_progress_write(self):
        with self.store.db() as db:
            db.execute("UPDATE tasks SET state='succeeded' WHERE bvid=?", (self.bv,))
        self.while_reading(lambda: reconcile(self.store))

    def test_cancel_during_finish_inspection_rejects_late_artifacts(self):
        def cancel(*args):
            self.store.control_task(self.bv, 'delete')
            return []
        with patch('reference_store.transcript_errors', side_effect=cancel):
            self.store.finish_task(self.bv, 'succeeded', generation=self.task['generation'])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT state FROM tasks').fetchone()[0], 'cancelled')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM part_results').fetchone()[0], 0)

    def test_reconcile_rejects_snapshot_from_previous_generation(self):
        with self.store.db() as db:
            db.execute("UPDATE tasks SET state='succeeded'")
        def restart(*args):
            with self.store.db() as db:
                db.execute("UPDATE tasks SET state='queued',generation=generation+1")
            return []
        with patch('reference_store.transcript_errors', side_effect=restart):
            reconcile(self.store)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT state FROM tasks').fetchone()[0], 'queued')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM part_results').fetchone()[0], 0)

    def test_enqueue_keeps_part_result_written_during_inspection(self):
        from link_jobs import mark_part
        other = self.store.new_job({'mode': 'preview'})
        self.store.discover(other['id'], {'bvid': self.bv}, '', False)
        def finish_part(*args):
            mark_part(self.store, self.bv, 1, 'succeeded', generation=self.task['generation'])
            return ['not exported yet']
        with patch('reference_store.transcript_errors', side_effect=finish_part):
            self.store.enqueue(other['id'], [self.bv])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT state FROM part_results').fetchone()[0], 'succeeded')

    def test_enqueue_keeps_task_completed_during_inspection(self):
        from link_jobs import mark_part, record_parts
        record_parts(self.store, self.bv, [{'playlist_index': 1}])
        other = self.store.new_job({'mode': 'preview'})
        self.store.discover(other['id'], {'bvid': self.bv}, '', False)
        def complete(*args):
            mark_part(self.store, self.bv, 1, 'succeeded', generation=self.task['generation'])
            with self.store.db() as db:
                db.execute("UPDATE tasks SET state='succeeded' WHERE bvid=?", (self.bv,))
            return ['not exported when inspection began']
        with patch('reference_store.transcript_errors', side_effect=complete):
            self.store.enqueue(other['id'], [self.bv])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT state FROM part_results').fetchone()[0], 'succeeded')
            self.assertEqual(db.execute('SELECT state FROM tasks').fetchone()[0], 'succeeded')

    def test_single_part_completion_does_not_satisfy_new_whole_video_demand(self):
        from link_jobs import mark_part, record_parts
        record_parts(self.store, self.bv, [{'playlist_index': 1}, {'playlist_index': 2}])
        with self.store.db() as db:
            db.execute("UPDATE link_demands SET parts='[2]'")
        other = self.store.new_job({'mode': 'preview'})
        self.store.discover(other['id'], {'bvid': self.bv}, '', False)
        def complete_part(*args):
            mark_part(self.store, self.bv, 2, 'succeeded', generation=self.task['generation'])
            with self.store.db() as db:
                db.execute("UPDATE tasks SET state='succeeded' WHERE bvid=?", (self.bv,))
            return ['part 1 not exported']
        with patch('reference_store.transcript_errors', side_effect=complete_part):
            self.store.enqueue(other['id'], [self.bv])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT state FROM tasks').fetchone()[0], 'queued')
            self.assertEqual(db.execute('SELECT part FROM part_results').fetchone()[0], 2)
