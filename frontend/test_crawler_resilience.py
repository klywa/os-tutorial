import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq
import workspace
from acquisition_errors import describe_error
from crawler import Store


class ClassificationTests(unittest.TestCase):
    def test_report_url_is_not_a_network_failure(self):
        self.assertEqual(describe_error('broken data; see https://github.com/yt-dlp/yt-dlp')['category'], 'processing')
        self.assertEqual(describe_error('Unable to extract initial state; see https://github.com/yt-dlp')['category'], 'extractor')

    def test_transient_and_permanent_errors(self):
        for error, category, recoverable in [
            (workspace.Busy('知识库正在保存，请稍后重试'), 'busy', True),
            ('WinError 32 file is in use', 'busy', True),
            (PermissionError('Permission denied'), 'storage', False),
            ('HTTP Error 500', 'network', True),
            ('工作进程异常退出（退出码3221225477）', 'crash', True),
            ('HTTP Error 412', 'risk', True),
            ('You have exceeded the rate limit. Try again later', 'risk', True),
            ('HTTP Error 401', 'login', False),
            ('HTTP Error 404', 'unavailable', False),
            ('corrected_sha256 mismatch', 'validation', False),
        ]:
            with self.subTest(error=str(error)):
                detail = describe_error(error)
                self.assertEqual(detail['category'], category)
                self.assertEqual(detail['recoverable'], recoverable)


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / 'temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        clock=patch('crawler.now',return_value='2026-11-02T09:00:00+08:00')
        clock.start();self.addCleanup(clock.stop)
        wxq.init_store(self.root)
        self.store = Store(self.root)
        self.job = self.store.new_job({})
        self.store.discover(self.job['id'], {'bvid': 'BV1234567890'}, '', True)

    def fail(self, message='Connection reset', progress=None):
        task = self.store.claim()
        self.assertIsNotNone(task)
        self.store.finish_task(task['bvid'], 'failed', message, progress=progress, generation=task['generation'])
        return task

    def test_network_retry_does_not_stop_after_three_and_restart_keeps_deadline(self):
        for attempt in range(1, 7):
            task = self.fail()
            self.store.adopt_network_failures()
            retry = self.store.retry_status('task', task['bvid'])
            self.assertEqual(retry['attempt'], attempt)
            from datetime import datetime,timedelta
            seconds=(60,300,900,1800)[min(attempt-1,3)]
            self.assertEqual(retry['next_retry_at'],(datetime.fromisoformat('2026-11-02T09:00:00+08:00')+timedelta(seconds=seconds)).isoformat())
            self.assertIsNone(self.store.claim())
            restarted = Store(self.root)
            self.assertEqual(restarted.retry_status('task', task['bvid']), retry)
            with self.store.db() as db:
                db.execute("UPDATE acquisition_retries SET next_retry_at='2000-01-01T00:00:00+08:00'")
                db.execute("UPDATE network_retries SET next_retry_at='2000-01-01T00:00:00+08:00'")

    def test_failure_preserves_progress_and_success_clears_retry(self):
        task = self.store.claim()
        self.store.finish_task(task['bvid'], 'running', progress={'phase': 'transcribing', 'source': 'BV1234567890:p2', 'processed_seconds': 99}, generation=task['generation'])
        self.store.finish_task(task['bvid'], 'failed', '工作进程异常退出（退出码3221225477）', generation=task['generation'])
        row = self.store.tasks()[0]
        self.assertEqual(json.loads(row['progress'])['processed_seconds'], 99)
        self.assertEqual(row['error_info']['phase'], 'transcribing')
        self.store.adopt_network_failures()
        self.assertEqual(self.store.retry_status('task', task['bvid'])['category'], 'crash')
        self.store.finish_task(task['bvid'], 'succeeded', generation=self.store.tasks()[0]['generation'])
        self.assertIsNone(self.store.retry_status('task', task['bvid']))

    def test_busy_tag_retries_without_click_and_permanent_error_stays_failed(self):
        self.store.queue_tags('manual', 'BV1234567890', ['测试'])
        with patch.object(self.store, 'apply_acquisition_tags', side_effect=workspace.Busy('知识库正在保存，请稍后重试')):
            self.store.process_tags()
        with self.store.db() as db:
            row = dict(db.execute('SELECT * FROM acquisition_tags').fetchone())
        self.assertEqual(row['state'], 'pending')
        from crawler_retries import tag_target
        retry = self.store.retry_status('tag', tag_target('manual', 'BV1234567890'))
        self.assertEqual(retry['category'], 'busy')
        with patch.object(self.store, 'apply_acquisition_tags') as apply:
            self.assertEqual(self.store.process_tags(), 0)
            apply.assert_not_called()
        with self.store.db() as db: db.execute("UPDATE acquisition_retries SET next_retry_at='2000-01-01T00:00:00+08:00'")
        with patch.object(self.store, 'apply_acquisition_tags', side_effect=PermissionError('Permission denied')):
            self.store.process_tags()
        with self.store.db() as db: self.assertEqual(db.execute('SELECT state FROM acquisition_tags').fetchone()[0], 'failed')

    def test_stopped_job_cannot_be_revived_by_retry(self):
        task = self.fail()
        self.store.stop(self.job['id'])
        self.store.adopt_network_failures()
        self.assertIsNone(self.store.retry_status('task', task['bvid']))
        self.assertIsNone(self.store.claim())

    def test_scan_backoff_and_manual_risk_cooldown_are_respected(self):
        self.store.update_job(self.job['id'], state='failed', error='Connection reset')
        self.store.adopt_network_failures()
        self.assertIsNone(self.store.next_pending())
        self.assertFalse(self.store.begin_scan(self.job['id']))
        retry = self.store.retry_status('job', self.job['id'])
        self.store.adopt_network_failures()
        self.assertEqual(self.store.retry_status('job', self.job['id']), retry)

    def test_manual_retry_clears_stale_display_but_preserves_risk_gate(self):
        task=self.fail()
        self.store.adopt_network_failures()
        self.store.retry(self.job['id'],[task['bvid']])
        item=self.store.job(self.job['id'])['items'][0]
        self.assertIsNone(item['retry'])
        self.assertNotIn('next_retry_at',item['progress'])
        task=self.store.claim()
        self.store.finish_task(task['bvid'],'failed','HTTP Error 412',generation=task['generation'])
        self.store.adopt_risk_failures()
        self.store.retry(self.job['id'],[task['bvid']])
        self.assertIsNone(self.store.claim())
        self.assertIsNotNone(self.store.job(self.job['id'])['items'][0]['retry'])

    def test_risk_retry_also_preserves_source_and_recovery_profile(self):
        task=self.fail('HTTP Error 412',{'phase':'transcribing','source':'BV1234567890:p2','asr_profile':'cpu_safe','processed_seconds':88})
        self.store.adopt_risk_failures()
        progress=json.loads(self.store.tasks()[0]['progress'])
        self.assertEqual(progress['source'],'BV1234567890:p2')
        self.assertEqual(progress['asr_profile'],'cpu_safe')
        self.assertEqual(progress['last_phase'],'transcribing')

    def test_old_generation_cannot_overwrite_retry(self):
        task = self.fail()
        self.store.adopt_network_failures()
        self.store.finish_task(task['bvid'], 'succeeded', generation=task['generation'])
        self.assertEqual(self.store.tasks()[0]['state'], 'queued')

    def test_restarted_dead_worker_enters_crash_backoff_and_keeps_cpu_profile(self):
        from worker_diagnostics import Diagnostic
        task=self.store.claim()
        diagnostic=Diagnostic(self.root,task['bvid'],task['generation'])
        diagnostic.event('transcribing',device='cuda')
        self.store.recover_tasks()
        self.store.restore_recoverable()
        retry=self.store.retry_status('task',task['bvid'])
        self.assertIsNotNone(retry)
        self.assertEqual(retry['category'],'crash')
        self.assertEqual(json.loads(self.store.tasks()[0]['progress'])['asr_profile'],'cpu_safe')
        self.assertIsNone(self.store.claim())

    def test_real_child_exit_has_parent_receipt_and_cpu_recovery(self):
        import subprocess
        from crawler import Runtime
        from worker_diagnostics import Diagnostic
        task=self.store.claim();runtime=Runtime(self.root);self.addCleanup(runtime.close)
        child_code=("import sys,os;sys.path.insert(0,"+repr(str(ROOT/'frontend'))+");"
                    "from worker_diagnostics import Diagnostic;d=Diagnostic("+repr(str(self.root))+","+repr(task['bvid'])+","+str(task['generation'])+");"
                    "d.event('transcribing',device='cuda');os._exit(37)")
        launch=subprocess.Popen
        def child(*args,**kwargs):
            return launch([sys.executable,'-u','-c',child_code],**kwargs)
        with patch('crawler.subprocess.Popen',side_effect=child):runtime.process_task(task)
        diagnostic=Diagnostic(self.root,task['bvid'],task['generation'])
        self.assertEqual(diagnostic.read()['exit_code'],37)
        self.assertTrue(diagnostic.path.with_suffix('.log').is_file())
        self.store.adopt_network_failures()
        self.assertEqual(json.loads(self.store.tasks()[0]['progress'])['asr_profile'],'cpu_safe')
        self.assertEqual(self.store.retry_status('task',task['bvid'])['category'],'crash')

    def test_tag_newer_version_is_not_marked_done_by_old_worker(self):
        self.store.queue_tags('manual', 'BV1234567890', ['旧标签'])
        def newer(item):
            self.store.queue_tags('manual', 'BV1234567890', ['新标签'])
        with patch.object(self.store, 'apply_acquisition_tags', side_effect=newer):
            self.store.process_tags()
        with self.store.db() as db:
            row = db.execute('SELECT state,tags FROM acquisition_tags').fetchone()
        self.assertEqual(row['state'], 'pending')
        self.assertIn('新标签', json.loads(row['tags']))

    def test_paused_creator_does_not_run_tag_work(self):
        creator=self.store.save_creator({'url':'https://space.bilibili.com/123','name':'测试','date_from':'2026-10-01'})
        self.store.stop(self.store.creators()[0]['job_id'])
        with patch.object(self.store,'_process_tag_item') as apply:
            self.store.process_tags()
            apply.assert_not_called()

    def test_busy_real_workspace_lock_preserves_manual_data_then_recovers(self):
        import threading
        sid='BV1234567890:p1'
        workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/BV1234567890?p=1','title':'人工标题','notes':'人工备注'})
        self.store.queue_tags('manual','BV1234567890',['新标签'])
        errors=[]
        def process():
            try:self.store.process_tags()
            except Exception as exc:errors.append(exc)
        with workspace.store_lock(self.root):
            thread=threading.Thread(target=process);thread.start();thread.join(timeout=4)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        from crawler_retries import tag_target
        self.assertEqual(self.store.retry_status('tag',tag_target('manual','BV1234567890'))['category'],'busy')
        with self.store.db() as db:db.execute("UPDATE acquisition_retries SET next_retry_at='2000-01-01T00:00:00+08:00'")
        self.store.process_tags()
        row=next(r for r in workspace.sources(self.root) if r['id']==sid)
        self.assertEqual(row['title'],'人工标题');self.assertEqual(row['notes'],'人工备注')
        self.assertIn('新标签',row['manual_values']['tags'])


class DownloadFallbackTests(unittest.TestCase):
    def test_api_fallback_uses_verified_part_and_signed_playinfo(self):
        from bilibili import Bilibili
        from unittest.mock import Mock
        adapter = object.__new__(Bilibili)
        adapter.ie = Mock()
        adapter.ie.extract_formats.return_value = [{'url': 'https://cdn.example/audio.m4s', 'format_id': '30280'}]
        with patch.object(adapter, 'entries', return_value=[{'cid': 22, 'playlist_index': 2, 'title': '第二P', 'duration': 10}]), patch.object(adapter, 'request', return_value={'dash': {}}) as request:
            info = adapter.api_download_info('https://www.bilibili.com/video/BV1234567890?p=2')
        self.assertEqual(request.call_args.args[0], 'x/player/wbi/playurl')
        self.assertEqual(request.call_args.args[1]['cid'], 22)
        self.assertTrue(request.call_args.kwargs['signed'])
        self.assertEqual(info['id'], 'BV1234567890_p2')
        self.assertEqual(info['formats'][0]['format_id'], '30280')
        with patch.object(adapter, 'entries', return_value=[{'cid': 1, 'playlist_index': 1}]):
            with self.assertRaises(Exception):
                adapter.api_download_info('https://www.bilibili.com/video/BV1234567890?p=2')

    def test_worker_crash_has_independent_diagnostic_before_imports(self):
        import worker_diagnostics
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            record = worker_diagnostics.Diagnostic(Path(folder), 'BV1234567890', 7)
            record.event('starting', dependencies=False)
            record.event('transcribing', device='cuda', source='BV1234567890:p1')
            record.exit(3221225477)
            value = json.loads(record.path.read_text('utf-8'))
            self.assertEqual(value['phase'], 'transcribing')
            self.assertEqual(value['device'], 'cuda')
            self.assertEqual(value['exit_hex'], '0xC0000005')

    def test_conservative_asr_keeps_large_model_and_forces_cpu(self):
        import media
        from types import SimpleNamespace
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            root=Path(folder);wxq.init_store(root)
            model=Mock()
            pipeline=Mock()
            pipeline.transcribe.return_value=(iter([]),SimpleNamespace(duration=10,duration_after_vad=8,language='zh'))
            whisper=SimpleNamespace(WhisperModel=model,BatchedInferencePipeline=Mock(return_value=pipeline))
            with patch.dict(sys.modules,{'faster_whisper':whisper,'faster_whisper.audio':SimpleNamespace(decode_audio=Mock()),'ctranslate2':SimpleNamespace(get_cuda_device_count=lambda:1)}), patch('media.entities',return_value=[]), patch('media.validate_audio_duration'):
                media.transcribe(root,'BV1234567890:p1',root/'audio.wav',apply_corrections=False,
                    runtime_options={'device':'cpu','cpu_threads':2,'batch_size':1})
            self.assertEqual(model.call_args.args[0],'large-v3')
            self.assertEqual(model.call_args.kwargs['device'],'cpu')
            self.assertEqual(model.call_args.kwargs['cpu_threads'],2)
            self.assertEqual(pipeline.transcribe.call_args.kwargs['batch_size'],1)


if __name__ == '__main__':
    unittest.main()
