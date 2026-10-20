import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq
import workspace
from crawler import Store, source_rows, transcript, register_discovered
from source_edit import save_metadata
from reference_store import save_transcript, export_transcripts


class SourceEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);wxq.init_store(self.root);self.store=Store(self.root)
        self.url='https://www.bilibili.com/video/BV1234567890'
        self.sid=workspace.register_source(self.root,{'url':self.url,'title':'原题','notes':'备注'})['id']

    def test_metadata_manual_overrides_clear_and_conflict(self):
        row=source_rows(self.root,self.store)[0]
        edited=save_metadata(self.root,self.sid,{'revision':row['revision'],'title':'人工','author':'','published':'2026-10-01','view_count':12,'duration':0,'uid':'123','space_url':'https://space.bilibili.com/123','collected_at':'2026-10-17T09:00','keywords':['甲','甲'],'batches':['展示批次'],'notes':''},self.store)
        register_discovered(self.root,{'url':self.url,'title':'后来采集','bvid':'BV1234567890'})
        current=source_rows(self.root,Store(self.root))[0]
        self.assertEqual(current['title'],'人工');self.assertEqual(current['author'],'');self.assertEqual(current['keywords'],['甲'])
        self.assertEqual(current['notes'],'');self.assertEqual(current['batches'],['展示批次'])
        with self.assertRaises(workspace.Conflict):save_metadata(self.root,self.sid,{'revision':row['revision'],'title':'旧草稿'},self.store)
        self.assertNotEqual(edited['revision'],row['revision'])

    def test_identity_validation(self):
        revision=source_rows(self.root,self.store)[0]['revision']
        for changes in [{'view_count':-1},{'duration':float('nan')},{'published':'2026-02-31'},{'uid':123},{'space_url':'https://example.com/123'},{'url':'https://www.bilibili.com/video/BV0000000000'}]:
            with self.assertRaises(ValueError):save_metadata(self.root,self.sid,{'revision':revision,**changes},self.store)
        save_metadata(self.root,self.sid,{'revision':revision,'url':self.url+'?p=1'},self.store)

    def test_ignore_does_not_scan_unrelated_source_files(self):
        other=wxq.source_dir(self.root,'BV1234567891:p1')/'metadata.json'
        wxq.atomic_json(other,{'id':'BV1234567891:p1','url':'https://www.bilibili.com/video/BV1234567891'})
        read=wxq.read_json
        def guarded(path,*args,**kwargs):
            if Path(path)==other:raise AssertionError('single-source save scanned unrelated metadata')
            return read(path,*args,**kwargs)
        with patch.object(wxq,'read_json',side_effect=guarded):
            updated=save_metadata(self.root,self.sid,{'revision':'','ignored':True},self.store)
        self.assertTrue(updated['ignored'])

    def test_transcript_can_be_read_while_ignore_is_saving(self):
        expected=self.prepare_transcript();entered=threading.Event();release=threading.Event()
        write=wxq.atomic_json
        def slow(path,*args,**kwargs):
            if Path(path)==self.root/'knowledge/source-registry.json':
                entered.set()
                if not release.wait(5):raise TimeoutError('ignore save blocked')
            return write(path,*args,**kwargs)
        with ThreadPoolExecutor(max_workers=2) as pool,patch.object(wxq,'atomic_json',side_effect=slow):
            save=pool.submit(save_metadata,self.root,self.sid,{'revision':'','ignored':True},self.store)
            try:
                self.assertTrue(entered.wait(2))
                reading=pool.submit(transcript,self.root,self.sid)
                self.assertEqual(reading.result(timeout=1)['text'],expected['text'])
            finally:release.set()
            self.assertTrue(save.result(timeout=5)['ignored'])

    def prepare_transcript(self):
        folder=wxq.source_dir(self.root,self.sid);folder.mkdir(parents=True,exist_ok=True)
        wxq.atomic_json(folder/'metadata.json',{'id':self.sid,'title':'原题','url':self.url,'duration':30})
        asr={'model':'large-v3','segments':[{'id':0,'start':0,'end':10,'text':'原文'}]}
        for name in ['asr.raw.json','asr.corrected.json']:wxq.atomic_json(folder/name,asr)
        self.assertFalse(export_transcripts(self.root,[self.sid])['errors'])
        return transcript(self.root,self.sid)

    def test_transcript_edit_revision_backup_and_export_protection(self):
        old=self.prepare_transcript()
        new=save_transcript(self.root,self.sid,{'revision':old['revision'],'text':'人工正文'})
        self.assertEqual(new['text'],'人工正文')
        self.assertTrue(new['manual_edit'])
        with self.assertRaises(workspace.Conflict):save_transcript(self.root,self.sid,{'revision':old['revision'],'text':'旧草稿'})
        export_transcripts(self.root,[self.sid])
        self.assertEqual(transcript(self.root,self.sid)['text'],'人工正文')
        backups=list((self.root/'raw/reports/transcript-edits').rglob('*.md'))
        self.assertEqual(backups[0].read_text('utf-8'),old['text'])

    def test_transcript_save_failure_rolls_back_both_files(self):
        old=self.prepare_transcript();original=wxq.atomic_json
        def fail(path,data,*args,**kwargs):
            if Path(path)==self.root/'raw/index.json' and data['sources'][self.sid].get('manual_edit'):raise OSError('disk full')
            return original(path,data,*args,**kwargs)
        with patch.object(wxq,'atomic_json',side_effect=fail):
            with self.assertRaises(OSError):save_transcript(self.root,self.sid,{'revision':old['revision'],'text':'不能保存'})
        self.assertEqual(transcript(self.root,self.sid)['text'],old['text'])
        self.assertEqual(transcript(self.root,self.sid)['revision'],old['revision'])

    def test_transcript_path_escape_rejected(self):
        wxq.atomic_json(self.root/'raw/index.json',{'sources':{self.sid:{'path':'../outside.md'}}})
        with self.assertRaises((ValueError,KeyError)):save_transcript(self.root,self.sid,{'revision':'','text':'正文'})

    def test_concurrent_metadata_edit_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        revision=source_rows(self.root,self.store)[0]['revision']
        def edit(title):
            try:
                save_metadata(self.root,self.sid,{'revision':revision,'title':title},self.store)
                return 'saved'
            except workspace.Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sorted(pool.map(edit,['甲','乙'])),['conflict','saved'])

    def test_interrupted_transcript_save_recovers_on_startup(self):
        old=self.prepare_transcript();manifest=wxq.read_json(self.root/'raw/index.json')
        wxq.atomic_json(self.root/'raw/transcript-edit-pending.json',{'source':self.sid,'path':str(Path(old['path']).relative_to(self.root)),'text':old['text'],'manifest':manifest})
        wxq.atomic_text(Path(old['path']),'中断后的半成品')
        with workspace.store_lock(self.root):workspace.recover(self.root)
        self.assertEqual(transcript(self.root,self.sid)['text'],old['text'])
        self.assertFalse((self.root/'raw/transcript-edit-pending.json').exists())
