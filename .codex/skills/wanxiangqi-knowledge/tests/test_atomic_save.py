import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[4]
sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq
import workspace
from crawler import Runtime, error_info


def denied(code=5):
    exc = PermissionError('file in use')
    exc.winerror = code
    return exc


class AtomicSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'test.json'
        self.path.write_text('old', encoding='utf-8')

    def test_transient_replace_retries_preserve_backup(self):
        original = Path.replace
        calls = []
        def replace(source, target):
            calls.append(source)
            if len(calls) < 3:
                raise denied(32)
            return original(source, target)
        with patch.object(Path, 'replace', replace), patch.object(wxq.time, 'sleep') as sleep:
            self.assertTrue(wxq.atomic_text(self.path, 'new'))
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [.05, .1])
        self.assertEqual(self.path.read_text(), 'new')
        self.assertEqual(self.path.with_suffix('.json.bak').read_text(), 'old')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_persistent_denial_is_bounded_and_original_survives(self):
        with patch.object(Path, 'replace', side_effect=denied()) as replace, patch.object(wxq.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                wxq.atomic_text(self.path, 'new')
        self.assertEqual(replace.call_count, 6)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [.05, .1, .2, .4, .8])
        self.assertEqual(self.path.read_text(), 'old')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_other_errors_are_not_retried(self):
        with patch.object(Path, 'replace', side_effect=OSError('disk full')) as replace, patch.object(wxq.time, 'sleep') as sleep:
            with self.assertRaises(OSError):
                wxq.atomic_text(self.path, 'new')
        self.assertEqual(replace.call_count, 1)
        sleep.assert_not_called()

    def test_read_retries_during_windows_replace(self):
        with patch.object(Path, 'read_text', side_effect=[denied(5), '{"ok":true}']), patch.object(wxq.time, 'sleep') as sleep:
            self.assertEqual(wxq.read_json(self.path), {'ok':True})
        sleep.assert_called_once_with(.05)

    @unittest.skipUnless(os.name == 'nt', 'Windows CRT errors')
    def test_backup_crt_access_denied_is_retried(self):
        original = wxq.shutil.copy2
        calls = []
        def copy(source, target):
            calls.append(source)
            if len(calls) == 1:
                raise PermissionError(13, 'Permission denied')
            return original(source, target)
        with patch.object(wxq.shutil, 'copy2', copy), patch.object(wxq.time, 'sleep') as sleep:
            wxq.atomic_text(self.path, 'new')
        sleep.assert_called_once_with(.05)
        self.assertEqual(self.path.with_suffix('.json.bak').read_text(), 'old')

    def test_cancel_during_backoff_leaves_original(self):
        cancelled = threading.Event()
        with patch.object(Path, 'replace', side_effect=denied(33)) as replace, patch.object(wxq.time, 'sleep', side_effect=lambda _:cancelled.set()):
            with self.assertRaises(InterruptedError):
                wxq.atomic_text(self.path, 'new', cancelled=cancelled.is_set)
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(self.path.read_text(), 'old')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_real_windows_reader_temporarily_blocks_replace(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.path), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        probe = self.root / 'probe.tmp'
        probe.write_text('probe')
        try:
            with self.assertRaises(PermissionError) as error:
                probe.replace(self.path)
            self.assertIn(error.exception.winerror, [5, 32, 33])
            timer = threading.Timer(.08, lambda: kernel.CloseHandle(handle))
            timer.start()
            try:
                self.assertTrue(wxq.atomic_text(self.path, 'new'))
            finally:
                timer.join()
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(self.path.read_text(), 'new')

    def test_parallel_registration_preserves_all_records_and_annotations(self):
        wxq.init_store(self.root)
        workspace.register_source(self.root, {'url':'https://example.com/0','title':'人工标题','notes':'人工备注'})
        errors = []
        done = threading.Event()
        def reader():
            while not done.is_set():
                try: wxq.read_json(self.root / 'knowledge/source-registry.json', [])
                except Exception as exc: errors.append(exc)
        thread = threading.Thread(target=reader)
        thread.start()
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda n: workspace.register_source(self.root, {'url':f'https://example.com/{n}','title':'自动','notes':''}, preserve_annotations=True, wait=True), range(12)))
        finally:
            done.set(); thread.join()
        self.assertEqual(errors, [])
        rows = wxq.read_json(self.root / 'knowledge/source-registry.json')
        self.assertEqual(len(rows), 12)
        self.assertEqual(next(r for r in rows if r['url'].endswith('/0'))['notes'], '人工备注')

    def test_storage_error_category(self):
        info = error_info("[WinError 5] 拒绝访问: source-registry.json")
        self.assertEqual(info['category'], 'storage')
        self.assertIn('占用', info['hint'])

    def test_scan_save_failure_preserves_checkpoint_and_retry_deduplicates(self):
        wxq.init_store(self.root)
        runtime = Runtime(self.root)
        self.addCleanup(runtime.close)
        creator = runtime.store.create_creator({'url':'https://space.bilibili.com/123','name':'UP','date_from':'2026-09-10','enabled':True})
        job = runtime.store.check_creator(creator['uid'])
        row = {'bvid':'BV1234567890','url':'https://www.bilibili.com/video/BV1234567890','title':'视频','description':'','published':'2026-10-01','view_count':10,'duration':60}
        from unittest.mock import Mock
        adapter = Mock(); adapter.creator_page.return_value = ([row], False)
        with patch('crawler.Bilibili', return_value=adapter), patch('crawler.register_discovered', side_effect=denied()):
            runtime.scan(job)
        self.assertEqual(runtime.store.job(job['id'])['state'], 'failed')
        self.assertFalse(runtime.store.creators()[0].get('last_success'))
        runtime.store.retry(job['id'])
        with patch('crawler.Bilibili', return_value=adapter):
            runtime.scan(runtime.store.job(job['id']))
        self.assertEqual(runtime.store.job(job['id'])['state'], 'scanned')
        self.assertTrue(runtime.store.creators()[0].get('last_success'))
        self.assertEqual(len(runtime.store.tasks()), 1)
        self.assertEqual(len(wxq.read_json(self.root/'knowledge/source-registry.json')), 1)

    def test_stop_or_delete_during_scan_backoff_cancels_save(self):
        from unittest.mock import Mock
        wxq.init_store(self.root)
        runtime = Runtime(self.root)
        self.addCleanup(runtime.close)
        runtime.store.create_creator({'url':'https://space.bilibili.com/123','name':'UP','date_from':'2026-09-10'})
        row = {'bvid':'BV1234567890','url':'https://www.bilibili.com/video/BV1234567890','title':'视频','description':'','published':'2026-10-01','view_count':10,'duration':60}
        adapter = Mock(); adapter.creator_page.return_value = ([row], False)
        for operation in ['stop','delete']:
            # Persistent UP tasks are removed via their listener; ordinary search jobs remain deletable.
            job = runtime.store.check_creator('123') if operation=='stop' else runtime.store.new_job({'keywords':['视频'],'mode':'preview'})
            adapter.search_page.return_value = ([row], False)
            control = runtime.store.stop if operation=='stop' else runtime.store.delete_job
            with patch('crawler.Bilibili', return_value=adapter), patch.object(Path, 'replace', side_effect=denied()), patch.object(wxq.time, 'sleep', side_effect=lambda _:control(job['id'])):
                runtime.scan(job)
            self.assertEqual(runtime.store.job(job['id'], False)['state'], 'stopped' if operation=='stop' else 'deleted')
            self.assertFalse(runtime.store.creators()[0].get('last_success'))
