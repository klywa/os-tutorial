import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tutorial
from pipeline import run_batch


class PipelineTests(unittest.TestCase):
    def test_asr_starts_before_video_finishes_and_next_audio_downloads(self):
        base = tutorial.ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            root = Path(tmp)
            gate = threading.Event()
            audio_b = threading.Event()
            order = []
            jobs = [{'source': {'id': b + ':p1', 'title': b,
                      'url': 'https://www.bilibili.com/video/' + b + '/?p=1'},
                     'audio': 'audio-' + b, 'video': 'video-' + b}
                    for b in ['BV1JGpM62EC5', 'BV1tkHS6VECD']]
            def download(url, path):
                if url.startswith('video'):
                    if not gate.wait(5):
                        raise RuntimeError('ASR waited for full video')
                else:
                    path.write_bytes(b'audio')
                    if 'BV1tkHS6VECD' in url:
                        audio_b.set()
            def transcribe(root, sid, audio, model):
                self.assertEqual(audio.parent, root / 'raw/sources' / sid.replace(':', '_'))
                order.append(sid)
                if not audio_b.wait(5):
                    raise RuntimeError('Other source audio did not download concurrently')
                gate.set()
            result = run_batch(root, jobs, 'large-v3', download, transcribe, lambda *a: None)
            self.assertEqual([r['status'] for r in result], ['prepared', 'prepared'])
            self.assertEqual(len(order), 2)

    def test_legacy_record_skips_all_pipeline_work(self):
        base = tutorial.ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            root = Path(tmp)
            source = {'id': 'BV1JGpM62EC5:p1', 'title': '旧记录',
                      'url': 'https://www.bilibili.com/video/BV1JGpM62EC5/?p=1'}
            folder = root / 'proposal/tutorial/records'
            folder.mkdir(parents=True)
            (folder / '旧记录.md').write_text('old', encoding='utf8')
            def forbidden(*a):
                raise AssertionError('Existing source did work')
            result = run_batch(root, [{'source': source}], 'large-v3', forbidden, forbidden, forbidden)
            self.assertTrue(result[0]['reused_record'])
            self.assertFalse((root / 'raw').exists())

    def test_failed_transfer_does_not_prevent_other_source(self):
        base = tutorial.ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            root = Path(tmp)
            jobs = [{'source': {'id': b + ':p1', 'title': b,
                      'url': 'https://www.bilibili.com/video/' + b + '/'},
                     'audio': 'audio-' + b, 'video': 'video-' + b}
                    for b in ['BV1JGpM62EC5', 'BV1tkHS6VECD']]
            calls = []
            def download(url, path):
                if url == 'video-BV1JGpM62EC5':
                    raise RuntimeError('truncated')
                path.write_bytes(b'media')
            result = run_batch(root, jobs, 'large-v3', download,
                               lambda *a: None, lambda root, sid, model: calls.append(sid))
            self.assertEqual([r['status'] for r in result], ['failed', 'prepared'])
            self.assertEqual(calls, ['BV1tkHS6VECD:p1'])


if __name__ == '__main__':
    unittest.main()
