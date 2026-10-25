import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import json_store,json_document
import reader_store as reader

class ReaderTests(unittest.TestCase):
    def setUp(self):
        folder=Path(__file__).resolve().parents[4]/'raw/test-temp';folder.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=folder);self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.record={'body':json_document.parse('# 测试\n\n## 技能\n\n**英雄：** 独特正文关键字\n'),
                     'metadata':{'id':'test','type':'other','title':'测试','path':'knowledge/other/测试.json','entities':['card:1'],'aliases':['简称']}}
        json_store.save(self.root,[self.record])
    def test_catalog_excludes_body_and_does_not_reload_note(self):
        reader.rebuild(self.root)
        with patch.object(json_store,'load_record',side_effect=AssertionError('catalog loaded full note')):
            result=reader.catalog(self.root)
        self.assertTrue(result['ready']);self.assertEqual(len(result['notes']),1)
        self.assertNotIn('document',result['notes'][0]);self.assertEqual(result['notes'][0]['claims'],[])
        self.assertLess(len(str(result)),5000)
    def test_search_and_external_change_invalidate(self):
        reader.rebuild(self.root)
        self.assertEqual(reader.search(self.root,'独特正文 关键字')['ids'],['test'])
        self.assertEqual(reader.search(self.root,'独特 不存在')['ids'],[])
        record=json_store.load_record(self.root,'test');record['body']['nodes'][-1]['value']='改过正文'
        json_store.write_file(self.root/record['metadata']['path'],record['body'])
        self.assertFalse(reader.catalog(self.root,schedule=False)['ready'])
    def test_incremental_save_refreshes_summary_and_search(self):
        reader.rebuild(self.root)
        record=json_store.load_record(self.root,'test');record['body']['nodes'][-1]['value']='更新后的词'
        json_store.save(self.root,[record],partial=True)
        self.assertEqual(reader.search(self.root,'更新后的词')['ids'],['test'])
        self.assertEqual(reader.search(self.root,'独特正文')['ids'],[])
    def test_options_do_not_project_all_notes(self):
        reader.rebuild(self.root)
        with patch('workspace.notes',side_effect=AssertionError('full library projection')):
            self.assertIn('factions',reader.options(self.root))
    def test_background_rebuild_never_holds_save_or_catalog(self):
        import threading,time
        entered=threading.Event();release=threading.Event();original=json_store.load_record
        def slow(*args,**kwargs):
            entered.set();release.wait(2);return original(*args,**kwargs)
        path=self.root/reader.FOLDER/'notes/test.json';path.unlink()
        with patch.object(json_store,'load_record',side_effect=slow):
            worker=reader.schedule_rebuild(self.root);self.assertTrue(entered.wait(1))
            try:
                t=time.perf_counter();cat=reader.catalog(self.root,schedule=False)
                self.assertLess(time.perf_counter()-t,.5);self.assertFalse(cat['ready'])
                record=original(self.root,'test');record['body']['nodes'][-1]['value']='重建期间保存'
                json_store.save(self.root,[record],partial=True)
            finally:
                release.set();worker.join(timeout=2)
        self.assertTrue(reader.catalog(self.root,schedule=False)['ready'])
    def test_valid_json_with_wrong_cache_shape_is_rebuilt(self):
        path=self.root/reader.FOLDER/'notes/test.json'
        for value in ([],{'summary':[]},None):
            json_store.write_file(path,value)
            self.assertFalse(reader.catalog(self.root,schedule=False)['ready'])
            reader.rebuild(self.root)
            self.assertTrue(reader.catalog(self.root,schedule=False)['ready'])

if __name__=='__main__':unittest.main()
