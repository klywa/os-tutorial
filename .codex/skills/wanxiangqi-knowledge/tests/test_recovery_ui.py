import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).parents[4]
sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq
from crawler import Store
from reference_store import transcript_errors, repair_transcript_index
from bilibili import Bilibili, BilibiliError


class RecoveryTests(unittest.TestCase):
    def test_edit_delete_race_cannot_resurrect_listener(self):
        from contextlib import contextmanager
        import threading
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as tmp:
            store=Store(Path(tmp));creator=store.save_creator({'url':'https://space.bilibili.com/123','name':'test','date_from':'2026-09-10'})
            original=store.db;read=threading.Event();deleted=threading.Event();errors=[];main=threading.get_ident()
            class Cursor:
                def __init__(self,cursor):self.cursor=cursor
                def fetchone(self):
                    value=self.cursor.fetchone();self.cursor.close();read.set();deleted.wait(.25);return value
            class Connection:
                def __init__(self,db):self.db=db
                def execute(self,sql,args=()):
                    cursor=self.db.execute(sql,args)
                    return Cursor(cursor) if sql.startswith('SELECT data FROM creators') else cursor
            @contextmanager
            def connection():
                with original() as db:yield Connection(db) if threading.get_ident()==main else db
            def remove():
                read.wait(2)
                try:store.delete_creator('123')
                except Exception as exc:errors.append(str(exc))
                deleted.set()
            store.db=connection;thread=threading.Thread(target=remove);thread.start()
            store.save_creator({**creator,'name':'edited'});thread.join(3);store.db=original
            self.assertFalse(errors);self.assertFalse(thread.is_alive());self.assertEqual(store.creators(),[])

    def test_invalid_wav_header_is_recoverable(self):
        import media
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as tmp:
            audio=Path(tmp)/'audio.wav';audio.write_bytes(b'not a RIFF WAV header')
            with self.assertRaises(RuntimeError):media.audio_seconds(audio)

    def test_delete_creator_stops_discovery_preserves_dispatched_video(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as tmp:
            store = Store(Path(tmp))
            c = store.save_creator({'url': 'https://space.bilibili.com/123', 'name': '测试', 'date_from': '2026-09-10'})
            job = store.check_creator(c['uid'])
            store.begin_scan(job['id'])
            store.discover(job['id'], {'bvid': 'BV1234567890', 'title': '视频'}, '', True)
            store.delete_creator(c['uid'])
            self.assertEqual(store.creators(), [])
            self.assertEqual(store.tasks()[0]['state'], 'queued')
            self.assertIsNotNone(store.claim())
            self.assertFalse(store.discover(job['id'], {'bvid': 'BV1234567891'}, '', True))
            store.creator_result('123')
            self.assertEqual(store.creators(), [])

    def test_legacy_hashes_are_validated_without_overwriting_text(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as tmp:
            root = Path(tmp); wxq.init_store(root)
            sid = 'BV1234567890:p1'; folder = wxq.source_dir(root, sid); folder.mkdir(parents=True, exist_ok=True)
            wxq.atomic_json(folder / 'metadata.json', {'id': sid, 'url': 'https://www.bilibili.com/video/BV1234567890', 'title': '测试', 'duration': 10})
            data = {'segments': [{'id': 0, 'start': 0, 'end': 2, 'text': '测试'}]}
            for name in ['asr.raw.json', 'asr.corrected.json']: wxq.atomic_json(folder / name, data)
            from reference_store import export_transcripts
            self.assertFalse(export_transcripts(root, [sid])['errors'])
            index = wxq.read_json(root / 'raw/index.json'); del index['sources'][sid]['corrected_sha256']; wxq.atomic_json(root / 'raw/index.json', index)
            self.assertTrue(transcript_errors(root, sid))
            self.assertTrue(repair_transcript_index(root, sid))
            self.assertEqual(transcript_errors(root, sid), [])
            target = root / index['sources'][sid]['path']; target.write_text('人工内容', encoding='utf8')
            index = wxq.read_json(root / 'raw/index.json'); del index['sources'][sid]['corrected_sha256']; wxq.atomic_json(root / 'raw/index.json', index)
            self.assertFalse(repair_transcript_index(root, sid))
            self.assertEqual(target.read_text('utf8'), '人工内容')

    def test_registered_raw_export_keeps_original_provenance(self):
        import reference_store as ref
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as tmp:
            root=Path(tmp);wxq.init_store(root);sid='BV123:p1';folder=wxq.source_dir(root,sid);folder.mkdir(parents=True,exist_ok=True)
            for name in ['asr.raw.json','asr.corrected.json']:wxq.atomic_json(folder/name,{'segments':[]})
            target=root/'raw/old.md';target.write_text('旧版原始ASR文字稿',encoding='utf8')
            row={'path':'raw/old.md','transcript_file':'asr.raw.json','raw_sha256':ref.digest((folder/'asr.raw.json').read_bytes()),'output_sha256':ref.digest(target.read_bytes())}
            wxq.atomic_json(root/'raw/index.json',{'sources':{sid:row}})
            self.assertTrue(ref.repair_transcript_index(root,sid));self.assertEqual(ref.transcript_errors(root,sid),[])
            self.assertEqual(target.read_text('utf8'),'旧版原始ASR文字稿')

    def test_risk_rejection_is_not_retried_as_network_error(self):
        adapter = object.__new__(Bilibili); adapter.ie = Mock()
        adapter.ie._download_json.return_value = {'code': -352, 'message': '风控校验失败'}
        with patch('bilibili.time.sleep'):
            with self.assertRaises(BilibiliError) as caught: adapter.request('test', {})
        self.assertEqual(caught.exception.category, 'risk')
        self.assertEqual(adapter.ie._download_json.call_count, 1)

    def test_network_download_reextracts_and_stops_after_three_attempts(self):
        import media
        downloader = Mock(); downloader.prepare_filename.return_value = 'download.mp4'; downloader.extract_info.side_effect = [OSError('network'), OSError('network'), {'id': 'ok'}]
        context = Mock(); context.__enter__ = Mock(return_value=downloader); context.__exit__ = Mock(return_value=False)
        with patch('yt_dlp.YoutubeDL', return_value=context), patch('media.time.sleep'):
            media.download_entry('https://example.com/video', {})
        self.assertEqual(downloader.extract_info.call_count, 3)

    def test_bad_audio_is_quarantined_and_replaced_before_asr(self):
        import media, wave
        with tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp') as tmp:
            root=Path(tmp);sid='BV123:p1';folder=wxq.source_dir(root,sid);folder.mkdir(parents=True)
            wxq.atomic_json(folder/'metadata.json',{'duration':10})
            (folder/'audio.wav').write_bytes(b'corrupt')
            wxq.atomic_json(folder/'asr.progress.json',{'segments':[{'text':'bad'}]})
            source=folder/'repair-audio.m4a';source.write_bytes(b'fresh')
            def convert(args,target):
                with wave.open(str(target),'wb') as out:
                    out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0'*320000)
            with patch('media.download_entry',return_value=({},source)),patch('media.convert_media',side_effect=convert):
                media.repair_audio(root,sid,'https://example.com',{})
            self.assertEqual(media.audio_seconds(folder/'audio.wav'),10)
            self.assertFalse((folder/'asr.progress.json').exists())
            self.assertEqual(len(list((folder/'failed-media').glob('*/audio.wav'))),1)
