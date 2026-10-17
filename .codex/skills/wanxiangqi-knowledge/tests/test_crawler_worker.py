import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).parents[4]
sys.path.insert(0,str(ROOT/'frontend'))
sys.path.insert(0,str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts'))
import wxq
import workspace
import crawler_worker
from crawler import Store, cached_video
from reference_store import export_transcripts
from processing_lock import file_lock


class WorkerTests(unittest.TestCase):
    def test_web_frame_failure_keeps_transcript_and_media_cli_remains_strict(self):
        import media,subprocess
        from unittest.mock import MagicMock
        outcome,folder=self.seed()
        context=MagicMock();context.__enter__.return_value.extract_info.return_value={'id':'123','title':'测试','duration':3}
        for required,stage in [(False,'prepared'),(True,'failed')]:
            with patch('yt_dlp.YoutubeDL',return_value=context),patch('media.extract_frames',side_effect=subprocess.CalledProcessError(1,['ffmpeg'])):
                result=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=required)
            self.assertEqual(result[0]['stage'],stage)
            self.assertTrue((folder/'media.mp4').exists())
            if not required:
                self.assertTrue(wxq.read_json(folder/'state.json')['warnings'])
                self.assertFalse(export_transcripts(self.root,[outcome['id']])['errors'])
                # Remove only the fixture export index so the strict CLI path is exercised next.
                wxq.atomic_json(self.root/'raw/index.json',{'sources':{}})

    def test_verified_artifacts_reconcile_only_old_frame_failure(self):
        import media
        outcome,folder=self.seed()
        export_transcripts(self.root,[outcome['id']])
        frame=folder/'frames/verified.jpg';frame.parent.mkdir();frame.write_bytes(b'\xff\xd8\xfffixture')
        wxq.atomic_json(folder/'frames.json',[{'time':10,'path':'frames/verified.jpg','reviewed':True,'observation':'已核对'}])
        old={'stage':'failed','error':"Command ['ffmpeg', '-frames:v', '1'] returned non-zero exit status 1"}
        wxq.atomic_json(folder/'state.json',old)
        self.assertTrue(media.reconcile_frame_failure(self.root,outcome['id']))
        self.assertEqual(wxq.read_json(folder/'state.json')['stage'],'prepared')
        self.assertNotIn('error',wxq.read_json(folder/'state.json'))
        self.assertEqual(wxq.read_json(folder/'frames.json')[0]['observation'],'已核对')
        self.assertEqual(wxq.read_json(folder/'recovered-frame-error.json'),old)
        wxq.atomic_json(folder/'state.json',old)
        manifest=wxq.read_json(folder/'frames.json');manifest[0]['reviewed']=False;wxq.atomic_json(folder/'frames.json',manifest)
        self.assertFalse(media.reconcile_frame_failure(self.root,outcome['id']))
        manifest[0]['reviewed']=True;wxq.atomic_json(folder/'frames.json',manifest);frame.unlink()
        self.assertFalse(media.reconcile_frame_failure(self.root,outcome['id']))
        self.assertEqual(wxq.read_json(folder/'state.json'),old)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        wxq.init_store(self.root)
        Store(self.root)

    def test_interrupted_conversion_never_publishes_partial_media(self):
        import media
        target = self.root / 'audio.wav'
        def interrupted(args):
            Path(args[-1]).write_bytes(b'partial')
            raise RuntimeError('interrupted')
        with patch('media.shell', side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                media.convert_media(['-i', 'input.mp4'], target)
        self.assertFalse(target.exists())
        def complete(args):
            Path(args[-1]).write_bytes(b'complete')
        with patch('media.shell', side_effect=complete):
            media.convert_media(['-i', 'input.mp4'], target)
        self.assertEqual(target.read_bytes(), b'complete')

    def seed(self,part=1,count=1,segments=None):
        sid=f'BV1234567890:p{part}'
        folder=wxq.source_dir(self.root,sid)
        wxq.atomic_json(folder/'metadata.json',{'id':sid,'bvid':'BV1234567890','title':'测试视频',
            'url':f'https://www.bilibili.com/video/BV1234567890?p={part}','part':part,'part_count':count})
        asr={'model':'large-v3','segments':segments if segments is not None else [{'id':1,'start':0,'end':3,'text':'真实转写在此测试中使用fixture'}]}
        wxq.atomic_json(folder/'asr.raw.json',asr)
        wxq.atomic_json(folder/'asr.corrected.json',asr)
        wxq.atomic_json(folder/'corrections.json',[])
        wxq.atomic_json(folder/'state.json',{'stage':'prepared','needs_review':True})
        wxq.atomic_text(folder/'media.mp4','fixture-media')
        wxq.atomic_text(folder/'audio.wav','fixture-audio')
        return {'id':sid,'stage':'prepared'},folder

    def test_each_part_exports_and_cleans_media_without_depositing(self):
        one,f1=self.seed(1,2)
        two,f2=self.seed(2,2)
        with patch('crawler_worker.media.prepare.__wrapped__',return_value=[one,two]):
            crawler_worker.run(self.root,'BV1234567890')
        for folder in [f1,f2]:
            self.assertFalse((folder/'media.mp4').exists())
            self.assertFalse((folder/'audio.wav').exists())
            self.assertTrue((folder/'asr.raw.json').exists())
        self.assertEqual(len(wxq.read_json(self.root/'raw/index.json')['sources']),2)
        self.assertTrue(cached_video(self.root,'BV1234567890'))
        self.assertTrue(all(r['knowledge_status']=='unprocessed' for r in workspace.sources(self.root)))

    def test_human_transcript_is_preserved(self):
        outcome,folder=self.seed()
        self.assertEqual(export_transcripts(self.root,[outcome['id']])['errors'],[])
        path=self.root/'raw/BV1234567890_p1.md'
        path.write_text('人工完整修订文字稿','utf8')
        with patch('crawler_worker.media.prepare.__wrapped__',return_value=[outcome]):
            crawler_worker.run(self.root,'BV1234567890')
        self.assertEqual(path.read_text('utf8'),'人工完整修订文字稿')

    def test_stale_asr_is_not_accepted_as_cached_success(self):
        outcome,folder=self.seed()
        export_transcripts(self.root,[outcome['id']])
        self.assertTrue(cached_video(self.root,'BV1234567890'))
        asr=wxq.read_json(folder/'asr.corrected.json')
        asr['segments'][0]['text']='已修订的ASR，但尚未导出'
        wxq.atomic_json(folder/'asr.corrected.json',asr)
        self.assertFalse(cached_video(self.root,'BV1234567890'))

    def test_failure_retains_recovery_material(self):
        outcome,folder=self.seed()
        with patch('crawler_worker.media.prepare.__wrapped__',return_value=[{**outcome,'stage':'failed','error':'download failed'}]):
            with self.assertRaises(RuntimeError):
                crawler_worker.run(self.root,'BV1234567890')
        self.assertTrue((folder/'media.mp4').exists())

    def test_no_speech_gets_explicit_transcript(self):
        outcome,folder=self.seed(segments=[])
        with patch('crawler_worker.media.prepare.__wrapped__',return_value=[outcome]):
            crawler_worker.run(self.root,'BV1234567890')
        self.assertIn('未检测到语音',(self.root/'raw/BV1234567890_p1.md').read_text('utf8'))

    def test_shared_source_lock_rejects_concurrent_cli(self):
        with file_lock(self.root/'raw/crawler/locks/BV1234567890.lock'):
            with self.assertRaises(workspace.Busy):
                crawler_worker.run(self.root,'BV1234567890')

    def test_parallel_exports_preserve_both_manifest_entries(self):
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor
        import reference_store
        one,folder=self.seed()
        two='BV2345678901:p1'
        target=wxq.source_dir(self.root,two)
        import shutil
        shutil.copytree(folder,target)
        metadata=wxq.read_json(target/'metadata.json')
        metadata.update(id=two,bvid='BV2345678901',url='https://www.bilibili.com/video/BV2345678901?p=1')
        wxq.atomic_json(target/'metadata.json',metadata)
        barrier=threading.Barrier(2)
        render=reference_store.render_transcript
        def slow_render(*args):
            time.sleep(.1)
            return render(*args)
        def export(sid):
            barrier.wait(timeout=3)
            return export_transcripts(self.root,[sid])
        with patch('reference_store.render_transcript',side_effect=slow_render):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(export,[one['id'],two]))
        self.assertTrue(all(not r['errors'] for r in results))
        self.assertEqual(len(wxq.read_json(self.root/'raw/index.json')['sources']),2)


if __name__=='__main__':
    unittest.main()
