import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from crawler import Store
from link_jobs import parse_links
import video_titles as titles

BV='BV1234567891'
class VideoTitleTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);wxq.init_store(self.root);self.store=Store(self.root)
 def seed(self,title=''):
  with self.store.db() as db:db.execute('INSERT INTO videos VALUES(?,?)',(BV,__import__('json').dumps({'bvid':BV,'url':'https://www.bilibili.com/video/'+BV,'title':title,'keywords':['保留']})))
 def test_link_check_never_uses_bv_as_title(self):
  self.assertEqual(parse_links(BV)['videos'][0]['title'],'')
 def test_adapter_preserves_multipart_names(self):
  from bilibili import Bilibili
  adapter=Bilibili.__new__(Bilibili)
  adapter.request=lambda *args:{'title':'视频总标题','pages':[{'cid':1,'page':1,'part':'教学'},{'cid':2,'page':2,'part':'纯享'}]}
  entries=adapter.entries(BV);self.seed(BV)
  titles.sync_entries(self.root,self.store,BV,entries)
  rows=wxq.read_json(self.root/'knowledge/source-registry.json')
  self.assertEqual([r['title'] for r in rows],['视频总标题 p01 教学','视频总标题 p02 纯享'])
  with self.store.db() as db:data=__import__('json').loads(db.execute('SELECT data FROM videos WHERE bvid=?',(BV,)).fetchone()[0])
  self.assertEqual(data['title'],'视频总标题')
 def test_sync_before_acquisition_and_preserve_distinct_parts(self):
  self.seed(BV)
  titles.sync_entries(self.root,self.store,BV,[{'playlist_index':1,'title':'真实标题一'},{'playlist_index':2,'title':'真实标题二'}])
  rows={r['id']:r for r in wxq.read_json(self.root/'knowledge/source-registry.json',[])}
  self.assertEqual(rows[BV+':p1']['title'],'真实标题一');self.assertEqual(rows[BV+':p2']['title'],'真实标题二')
  with self.store.db() as db:data=__import__('json').loads(db.execute('SELECT data FROM videos WHERE bvid=?',(BV,)).fetchone()[0])
  self.assertEqual(data['title'],'真实标题一');self.assertEqual(data['keywords'],['保留'])
 def test_manual_values_and_notes_survive_late_metadata(self):
  self.seed('人工任务标题')
  wxq.atomic_json(self.root/'knowledge/source-registry.json',[{'id':BV+':p1','url':'https://www.bilibili.com/video/'+BV,'title':'人工标题','notes':'人工备注','manual_values':{'title':'界面修改'}}])
  titles.sync_entries(self.root,self.store,BV,[{'playlist_index':1,'title':'自动标题'}])
  row=wxq.read_json(self.root/'knowledge/source-registry.json')[0]
  self.assertEqual(row['title'],'人工标题');self.assertEqual(row['notes'],'人工备注');self.assertEqual(row['manual_values']['title'],'界面修改')
 def test_cached_entries_are_used_without_network(self):
  self.seed(BV);folder=wxq.source_dir(self.root,BV+':p2');folder.mkdir(parents=True)
  wxq.atomic_json(folder/'metadata.json',{'id':BV+':p2','bvid':BV,'part':2,'title':'本地分P标题','url':'https://www.bilibili.com/video/'+BV+'?p=2'})
  report=titles.backfill(self.root,self.store,fetcher=lambda bv:(_ for _ in ()).throw(AssertionError('不应访问网络')))
  self.assertEqual(report['videos_updated'],1);self.assertEqual(report['unresolved'],[])
 def test_fetch_failure_is_reported_without_damaging_title(self):
  self.seed(BV)
  report=titles.backfill(self.root,self.store,fetcher=lambda bv:(_ for _ in ()).throw(ValueError('暂不可用')))
  self.assertEqual(report['unresolved'][0]['bvid'],BV)
 def test_recheck_latest_registry_value_under_lock(self):
  self.seed(BV)
  wxq.atomic_json(self.root/'knowledge/source-registry.json',[{'id':BV+':p1','url':'https://www.bilibili.com/video/'+BV,'title':'','notes':'备注'}])
  def fetch(bv):
   rows=wxq.read_json(self.root/'knowledge/source-registry.json');rows[0]['title']='后来人工标题';wxq.atomic_json(self.root/'knowledge/source-registry.json',rows)
   return [{'playlist_index':1,'title':'网络标题'}]
  titles.backfill(self.root,self.store,fetcher=fetch)
  self.assertEqual(wxq.read_json(self.root/'knowledge/source-registry.json')[0]['title'],'后来人工标题')

if __name__=='__main__':unittest.main()
