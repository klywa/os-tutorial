import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
import media
from media import download_observed


class Response(io.BytesIO):
    status = 206
    def __init__(self, body, range_header):
        super().__init__(body)
        self.headers = {'Content-Range': range_header}


class TransportTests(unittest.TestCase):
    def test_decoded_duration_rejects_damaged_audio(self):
        base = ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            folder = Path(tmp) / 'raw/sources/BV1JGpM62EC5_p1'
            folder.mkdir(parents=True)
            (folder/'metadata.json').write_text('{"duration":3079}',encoding='utf8')
            with self.assertRaisesRegex(RuntimeError,'Decoded audio duration'):
                media.validate_audio_duration(Path(tmp),'BV1JGpM62EC5:p1',2517.9)
            media.validate_audio_duration(Path(tmp),'BV1JGpM62EC5:p1',3078.46)

    def test_complete_cache_with_416_without_total_uses_head_probe(self):
        base = ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            path = Path(tmp) / 'video.m4s'
            path.write_bytes(b'abc')
            with patch('urllib.request.urlopen', side_effect=[HTTPError('https://example.com',416,'range',{},None),Response(b'a','bytes 0-0/3')]):
                self.assertTrue(download_observed('https://example.com/video',path)['complete'])

    def test_bounded_requests_complete_all_chunks(self):
        base = ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            path = Path(tmp) / 'video.m4s'
            requests = []
            def fetch(req, timeout):
                requests.append(req.get_header('Range'))
                start = path.stat().st_size if path.exists() else 0
                return Response(b'abcdefghij'[start:start+4],
                                f'bytes {start}-{min(start+3,9)}/10')
            with patch('urllib.request.urlopen', side_effect=fetch):
                result = download_observed('https://example.com/video', path, chunk_bytes=4)
            self.assertEqual(requests, ['bytes=0-3', 'bytes=4-7', 'bytes=8-11'])
            self.assertTrue(result['complete'])
            self.assertEqual(path.read_bytes(), b'abcdefghij')

    def test_mismatched_range_never_appends(self):
        base = ROOT / 'raw/reports/test-fixtures'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            path = Path(tmp) / 'video.m4s'
            path.write_bytes(b'ab')
            with patch('urllib.request.urlopen', side_effect=lambda *a, **k: Response(b'cd', 'bytes 0-1/4')):
                with self.assertRaises(RuntimeError):
                    download_observed('https://example.com/video', path, chunk_bytes=4)
            self.assertEqual(path.read_bytes(), b'ab')


if __name__ == '__main__':
    unittest.main()
