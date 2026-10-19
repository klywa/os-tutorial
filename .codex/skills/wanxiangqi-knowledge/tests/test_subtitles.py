import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / 'frontend'))
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
import media
import wxq
import workspace
from bilibili import subtitle_candidates, subtitle_segments, Bilibili, BilibiliError
from reference_store import export_transcripts, transcript_errors, transcript_snapshot, save_transcript
from crawler import Store, source_rows, batch_paths, cached_video


class SubtitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        wxq.init_store(self.root)

    def subtitle(self):
        return {'language': 'zh-CN', 'automatic': False, 'url': 'https://aisubtitle.hdslb.com/test.json',
                'raw': {'body': [{'from': 0, 'to': 2, 'content': '王者万象棋教学'}]},
                'segments': [{'id': 0, 'start': 0, 'end': 2, 'text': '王者万象棋教学'}]}

    def prepare(self, fetch):
        entry = {'id': '1', 'title': '测试', 'duration': 3, 'uploader': '甲'}
        ctx = MagicMock()
        ctx.__enter__.return_value.extract_info.return_value = entry
        with patch('yt_dlp.YoutubeDL', return_value=ctx), patch('media.ffmpeg', return_value='ffmpeg'), \
             patch('media.download_entry') as download, patch('media.transcribe') as asr, patch('media.extract_frames') as frames:
            result = media.prepare(self.root, 'https://www.bilibili.com/video/BV1234567890',
                                   require_frames=False, subtitle_fetcher=fetch)
        return result, download, asr, frames

    def test_manual_then_auto_and_language_priority(self):
        rows = [{'lan': 'ai-zh', 'subtitle_url': '//x/auto'}, {'lan': 'en', 'subtitle_url': '//x/en'},
                {'lan': 'zh-TW', 'subtitle_url': '//x/tw'}, {'lan': 'zh-CN', 'subtitle_url': '//x/cn'}]
        self.assertEqual([r['lan'] for r in subtitle_candidates(rows)], ['zh-CN', 'zh-TW', 'ai-zh'])

    def test_validate_segments(self):
        self.assertEqual(subtitle_segments(self.subtitle()['raw'], 3)[0]['text'], '王者万象棋教学')
        for body in [[], [{'from': 2, 'to': 1, 'content': '错误'}], [{'from': 0, 'to': 99, 'content': '错误'}],
                     [{'from': 0, 'to': 1, 'content': ''}], [{'from': float('nan'), 'to': 1, 'content': '错误'}]]:
            with self.assertRaises(ValueError):
                subtitle_segments({'body': body}, 3)

    def test_direct_export_read_edit_copy_and_reuse_without_asr(self):
        fetch = MagicMock(return_value=self.subtitle())
        result, download, asr, frames = self.prepare(fetch)
        self.assertEqual(result[0]['stage'], 'prepared')
        download.assert_not_called(); asr.assert_not_called(); frames.assert_not_called()
        sid = result[0]['id']
        folder = wxq.source_dir(self.root, sid)
        self.assertFalse((folder / 'asr.raw.json').exists())
        self.assertTrue((folder / 'subtitle.raw.json').exists())
        workspace.register_source(self.root, {'url': 'https://www.bilibili.com/video/BV1234567890/?p=1', 'title': '测试'})
        self.assertFalse(export_transcripts(self.root, [sid])['errors'])
        self.assertEqual(transcript_errors(self.root, sid), [])
        self.assertTrue(cached_video(self.root, 'BV1234567890'))
        rows = source_rows(self.root, Store(self.root))
        self.assertEqual(rows[0]['transcript_origin'], 'bilibili_subtitle')
        self.assertEqual(rows[0]['transcript_status'], 'ready')
        self.assertEqual(len(batch_paths(self.root, [sid])['paths']), 1)
        snap = transcript_snapshot(self.root, sid)
        self.assertIn('B站字幕', snap['text'])
        save_transcript(self.root, sid, {'text': snap['text'] + '\n人工修改', 'revision': snap['revision']})
        self.assertEqual(transcript_errors(self.root, sid), [])
        fetch.reset_mock()
        self.prepare(fetch)
        fetch.assert_not_called()
        self.assertTrue(transcript_snapshot(self.root, sid)['text'].endswith('人工修改'))

    def test_network_failure_does_not_fall_back_to_download(self):
        result, download, asr, _ = self.prepare(MagicMock(side_effect=BilibiliError(-352, '风控')))
        self.assertEqual(result[0]['stage'], 'failed')
        self.assertIn('-352', result[0]['error'])
        download.assert_not_called(); asr.assert_not_called()

    def test_missing_subtitles_uses_existing_download_path(self):
        result, download, _, _ = self.prepare(MagicMock(return_value=None))
        self.assertTrue(download.called)

    def test_subtitle_phases_allow_stop_download_and_protect_generation(self):
        store = Store(self.root)
        job = store.new_job({})
        store.discover(job['id'], {'bvid':'BV1234567890'}, '', True)
        task = store.claim()
        store.finish_task(task['bvid'], 'running', progress={'phase':'fetching_subtitles'}, generation=task['generation'])
        self.assertEqual(store.job(job['id'])['counts']['downloading'], 1)
        with self.assertRaises(ValueError):store.control_task(task['bvid'], 'stop-transcribe')
        store.control_task(task['bvid'], 'stop-download')
        self.assertFalse(store.finish_task(task['bvid'], 'succeeded', generation=task['generation']))

    def test_adapter_tries_valid_candidates_and_refuses_login_failure(self):
        adapter = object.__new__(Bilibili)
        adapter.ie = MagicMock(); adapter.request_interval = 0
        view = {'pages':[{'page':1,'cid':11,'duration':3}]}
        tracks = {'subtitle':{'subtitles':[{'lan':'zh-CN','subtitle_url':'https://x/manual'},
                                        {'lan':'ai-zh','subtitle_url':'https://x/auto'}]}}
        with patch.object(adapter, 'request', side_effect=[view, tracks]):
            adapter.ie._download_json.side_effect = [{'body':[]}, self.subtitle()['raw']]
            result = adapter.subtitles('BV1234567890', 1, 3)
        self.assertTrue(result['automatic'])
        self.assertEqual(adapter.ie._download_json.call_count, 2)
        with patch.object(adapter, 'request', side_effect=[view, {'need_login_subtitle':True}]):
            with self.assertRaises(BilibiliError):adapter.subtitles('BV1234567890', 1, 3)

    def test_worker_subtitle_path_queues_topics_and_never_calls_asr(self):
        import crawler_worker
        store = Store(self.root); job = store.new_job({})
        store.discover(job['id'], {'bvid':'BV1234567890'}, '', True)
        task = store.claim()
        entry = {'id':'1','title':'字幕测试','duration':3}
        ctx = MagicMock();ctx.__enter__.return_value.extract_info.return_value = entry
        with patch('yt_dlp.YoutubeDL',return_value=ctx), patch('bilibili.Bilibili') as adapter, \
             patch('media.download_entry') as download, patch('media.transcribe') as asr, patch('topics.TopicStore.sync') as sync:
            adapter.return_value.subtitles.return_value = self.subtitle()
            adapter.return_value.entries.return_value = [entry]
            outcomes = crawler_worker.run(self.root, task['bvid'], generation=task['generation'])
        self.assertEqual(outcomes[0]['stage'], 'prepared')
        self.assertTrue(sync.called)
        self.assertEqual(sync.call_args.args[0][0]['transcript_status'], 'ready')
        download.assert_not_called();asr.assert_not_called()

    def test_bad_json_candidate_falls_back_to_next_track(self):
        import json
        from yt_dlp.utils import ExtractorError
        adapter = object.__new__(Bilibili);adapter.ie = MagicMock();adapter.request_interval = 0
        tracks = {'subtitle':{'subtitles':[{'lan':'zh-CN','subtitle_url':'https://x/manual'},
                                        {'lan':'ai-zh','subtitle_url':'https://x/auto'}]}}
        error = ExtractorError('bad json', cause=json.JSONDecodeError('invalid', '', 0))
        with patch.object(adapter, 'request', side_effect=[{'pages':[{'page':1,'cid':1}]}, tracks]), patch('bilibili.time.sleep'):
            adapter.ie._download_json.side_effect = [error, self.subtitle()['raw']]
            self.assertTrue(adapter.subtitles('BV1234567890',1,3)['automatic'])

    def test_subtitle_can_be_manually_committed_validated_and_finished(self):
        sid = self.prepare(MagicMock(return_value=self.subtitle()))[0][0]['id']
        self.assertFalse(export_transcripts(self.root,[sid])['errors'])
        note = {'id':'subtitle-note','type':'other','title':'字幕核对测试','entities':[],
                'claims':[{'kind':'general_strategy','section':'操作','text':'核对后的测试说明',
                           'evidence':[{'source':sid,'start':0,'end':2}]}]}
        wxq.commit_notes(self.root,[note])
        self.assertEqual(wxq.validate_store(self.root)['errors'],[])
        wxq.atomic_json(wxq.source_dir(self.root,sid)/'review.json',{'approved':True,'checked_intervals':[[0,2]]})
        self.assertEqual(media.finish(self.root,sid)['stage'],'complete')

    def test_cli_can_fetch_frames_for_subtitle_without_asr(self):
        sid = self.prepare(MagicMock(return_value=self.subtitle()))[0][0]['id']
        self.assertFalse(export_transcripts(self.root,[sid])['errors'])
        folder = wxq.source_dir(self.root,sid)
        ctx = MagicMock();ctx.__enter__.return_value.extract_info.return_value = {'id':'1','title':'测试','duration':3}
        def download(*args):
            video=folder/'media.mp4';video.write_bytes(b'video');return {},video
        with patch('yt_dlp.YoutubeDL',return_value=ctx),patch('media.download_entry',side_effect=download) as fetch, \
             patch('media.extract_frames') as frames,patch('media.transcribe') as asr:
            media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=True)
        self.assertTrue(frames.called)
        fetch.assert_called_once();asr.assert_not_called()

    def test_each_part_independently_selects_subtitle_or_download(self):
        ctx=MagicMock();ctx.__enter__.return_value.extract_info.return_value={'entries':[
            {'id':'1','title':'第一P','duration':3,'playlist_index':1},
            {'id':'2','title':'第二P','duration':3,'playlist_index':2}]}
        fetch=MagicMock(side_effect=[self.subtitle(),None])
        with patch('yt_dlp.YoutubeDL',return_value=ctx),patch('media.download_entry',side_effect=RuntimeError('下载回退测试')) as download:
            results=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=False,subtitle_fetcher=fetch)
        self.assertEqual([r['id'] for r in results],['BV1234567890:p1','BV1234567890:p2'])
        self.assertEqual([r['stage'] for r in results],['prepared','failed'])
        self.assertEqual([c.args[1] for c in fetch.call_args_list],[1,2])
        download.assert_called_once()

