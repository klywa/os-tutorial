import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from crawler import Store,source_rows
from source_edit import save_metadata
from source_staging import Staging

class SourceAnnotationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);wxq.init_store(self.root);self.store=Store(self.root)
  self.source=workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/BV1234567890','title':'视频甲','notes':'原备注'})
  self.sid=self.source['id']
 def test_tags_default_normalization_manual_protection_and_clear(self):
  self.assertEqual(source_rows(self.root,self.store)[0]['tags'],[])
  with patch('topics.TopicStore.sync') as sync:
   row=save_metadata(self.root,self.sid,{'revision':'','tags':['  教学 ','','教学','进阶'],'notes':'多行\n备注'},self.store)
  self.assertEqual(row['tags'],['教学','进阶']);sync.assert_not_called()
  workspace.register_source(self.root,{'url':self.source['url'],'title':'新标题','notes':'自动备注'},preserve_annotations=True)
  self.assertEqual(source_rows(self.root,self.store)[0]['tags'],['教学','进阶'])
  with self.assertRaises(workspace.Conflict):save_metadata(self.root,self.sid,{'revision':'','tags':[]},self.store)
  row=save_metadata(self.root,self.sid,{'revision':row['revision'],'tags':[]},self.store)
  self.assertEqual(row['tags'],[]);self.assertEqual(row['notes'],'多行\n备注')
 def test_tag_catalog_includes_ignored_and_does_not_scan_sources(self):
  from source_edit import tag_catalog
  save_metadata(self.root,self.sid,{'revision':'','tags':['教学','进阶'],'ignored':True},self.store)
  with patch.object(workspace,'sources',side_effect=AssertionError('catalog must only read registry')):
   self.assertEqual(tag_catalog(self.root),['教学','进阶'])
 def test_invalid_tags_rejected_without_writes(self):
  for value in ['教学',[1],None]:
   with self.subTest(value=value),self.assertRaises(ValueError):save_metadata(self.root,self.sid,{'revision':'','tags':value},self.store)
  self.assertNotIn('manual_values',wxq.read_json(self.root/'knowledge/source-registry.json')[0])
 def test_prompt_snapshot_preserves_order_falls_back_and_tracks_only_prompt_fields(self):
  other=workspace.register_source(self.root,{'url':'https://example.com/no-transcript','title':'','notes':''})
  basket=Staging(self.root);basket.add([other['id'],self.sid])
  wxq.atomic_text(self.root/'raw/example.md','正文')
  wxq.atomic_json(self.root/'raw/index.json',{'sources':{self.sid:{'path':'raw/example.md'}}})
  first=basket.prompt()
  self.assertEqual(first['items'],[{'id':other['id'],'title':'','location':other['url'],'notes':''},
    {'id':self.sid,'title':'视频甲','location':str((self.root/'raw/example.md').resolve()),'notes':'原备注'}])
  edited=save_metadata(self.root,self.sid,{'revision':'','tags':['教学']},self.store)
  self.assertEqual(first['fingerprint'],basket.prompt()['fingerprint'])
  save_metadata(self.root,self.sid,{'revision':edited['revision'],'notes':'新备注'},self.store)
  self.assertNotEqual(first['fingerprint'],basket.prompt()['fingerprint'])
  (self.root/'raw/example.md').unlink()
  self.assertEqual(basket.prompt()['items'][1]['location'],self.source['url'])
  self.assertEqual(basket.paths()['paths'],[])
 def test_prompt_read_does_not_wait_for_unrelated_knowledge_writer(self):
  basket=Staging(self.root);basket.add([self.sid])
  with workspace.store_lock(self.root):
   self.assertEqual(basket.prompt()['items'][0]['title'],'视频甲')
 def test_prompt_retries_when_annotations_change_during_snapshot(self):
  basket=Staging(self.root);basket.add([self.sid]);read=basket.sources;calls=[]
  def concurrent(ids):
   rows=read(ids);calls.append(1)
   if len(calls)==1:
    registry=wxq.read_json(self.root/'knowledge/source-registry.json')
    registry[0]['notes']='并发新备注';wxq.atomic_json(self.root/'knowledge/source-registry.json',registry)
   return rows
  with patch.object(basket,'sources',side_effect=concurrent):result=basket.prompt()
  self.assertEqual(len(calls),2);self.assertEqual(result['items'][0]['notes'],'并发新备注')
