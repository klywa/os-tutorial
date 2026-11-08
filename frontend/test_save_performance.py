"""Save performance contracts exercise real files/SQLite, never user data."""
import sys,tempfile,unittest,copy,json,http.client,threading,uuid
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store as store,knowledge_history as history,note_review,workspace,wxq,crawler
from source_edit import save_metadata
from source_staging import Staging

class SavePerformanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'temp');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  store.write_file(self.root/store.INDEX,{'schema_version':6,'storage_version':2,'notes':[],'aliases':{}})
  self.sid='BV1234567890:p1'
  self.record={'body':{'schema_version':6,'nodes':[{'id':'h','type':'heading','level':1,'title':'Sample'}, {'id':'e','type':'entry','key':'Text','show_key':True,'value':'Original'}]},'metadata':{'id':'sample','type':'other','title':'Sample','path':'knowledge/other/sample.json','claim_annotations':[{'id':'c','text_ref':'e','evidence':[{'source':self.sid,'start':0,'end':1}]}]}}
  store.save(self.root,[self.record])
  self.crawler=crawler.Store(self.root)
  workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/BV1234567890','title':'Video'})

 def test_warm_source_evidence_reuses_index_but_changes_invalidate_it(self):
  workspace._source_evidence.cache_clear()
  with patch.object(workspace,'_source_notes',wraps=workspace._source_notes) as scan:
   first=workspace.sources(self.root,source_ids=[self.sid]);workspace.sources(self.root,source_ids=[self.sid])
   self.assertEqual(scan.call_count,1)
   record=store.load_record(self.root,'sample');record['metadata']['title']='Renamed';record['body']['nodes'][0]['title']='Renamed';store.save(self.root,[record],partial=True)
   changed=workspace.sources(self.root,source_ids=[self.sid])
   self.assertEqual(scan.call_count,2)
  self.assertEqual(first[0]['linked_notes'][0]['title'],'Sample')
  self.assertEqual(changed[0]['linked_notes'][0]['title'],'Renamed')

 def test_single_source_never_globs_all_metadata(self):
  original=Path.glob
  def glob(path,pattern):
   if path==self.root/'raw/sources':raise AssertionError('single-source lookup enumerated every source folder')
   return original(path,pattern)
  with patch.object(Path,'glob',glob):workspace.sources(self.root,source_ids=[self.sid])

 def test_metadata_save_assembles_source_only_once_and_returns_current_revision(self):
  with patch.object(crawler,'source_rows',wraps=crawler.source_rows) as assemble:
   saved=save_metadata(self.root,self.sid,{'revision':'','ignored':True},self.crawler)
   self.assertEqual(assemble.call_count,1)
  self.assertTrue(saved['ignored']);self.assertTrue(saved['revision'])
  self.assertEqual(saved,crawler.source_rows(self.root,self.crawler,source_ids=[self.sid])[0])
  with self.assertRaises(workspace.Conflict):save_metadata(self.root,self.sid,{'revision':'','ignored':False},self.crawler)

 def test_prune_checks_only_changed_sources(self):
  staging=Staging(self.root);staging.add([self.sid])
  with patch.object(staging,'sources',wraps=staging.sources) as read:
   staging.prune(source_ids=[self.sid]);self.assertEqual(read.call_args.args,([self.sid],))

 def test_warm_versions_never_reread_old_snapshots_but_detect_corruption(self):
  expected=note_review._version_rows(self.root,'sample')
  archive=next((self.root/history.folder('sample')/'versions').glob('*.json'))
  original=store.read
  def read(path,*args,**kwargs):
   if Path(path)==archive:raise AssertionError('warm save rereads an old full snapshot')
   return original(path,*args,**kwargs)
  with patch.object(store,'read',side_effect=read):self.assertEqual(note_review._version_rows(self.root,'sample'),expected)
  archive.write_text('{}',encoding='utf-8')
  with self.assertRaises(ValueError):note_review._version_rows(self.root,'sample')

 def test_summary_cache_can_be_deleted_or_damaged_without_losing_versions(self):
  expected=note_review._version_rows(self.root,'sample')
  caches=list((self.root/'raw/knowledge/history-summaries').glob('*.json'))
  self.assertTrue(caches)
  for cache in caches:cache.write_text('bad json',encoding='utf-8')
  self.assertEqual(note_review._version_rows(self.root,'sample'),expected)
  for cache in caches:cache.unlink()
  self.assertEqual(note_review._version_rows(self.root,'sample'),expected)
  for malformed in ([1], 'broken', {'format':1,'note_id':'sample','entries':{'bad':[]},'checksum':store.digest({'bad':[]})}):
   for cache in caches:store.write_file(cache,malformed)
   self.assertEqual(note_review._version_rows(self.root,'sample'),expected)

 def test_entity_validation_reuses_catalog_and_detects_external_edits(self):
  wxq.atomic_json(self.root/'entities/heroes.json',[{'id':'hero','name':'Hero','category':'heroes'}])
  meta={'required_factions':[],'players':[],'core_heroes':['hero'],'compositions':{'early':[],'middle':[],'late':[]},'ban_conditions':[],'matchups':[]}
  workspace.validate_meta(self.root,meta)
  with patch.object(wxq,'entities',side_effect=AssertionError('unchanged entity catalog reread')):workspace.validate_meta(self.root,meta)
  wxq.atomic_json(self.root/'entities/heroes.json',[{'id':'new','name':'New','category':'heroes'}])
  with self.assertRaises(ValueError):workspace.validate_meta(self.root,meta)

 def test_local_and_public_http_saves_publish_timings_and_keep_conflicts(self):
  import server
  for public in (False,True):
   with self.subTest(public=public):
    config=self.root/'admins.json'
    store.write_file(config,{'sessionSecret':'s'*48,'sessionTtlHours':168,'users':[{'username':'tester','password':'never-log-this-secret'}]})
    http_server=server.create_server(self.root,0,public=public,origin='https://example.test',auth_config=config,state_dir=self.root/'site-state')
    http_server.sync=SimpleNamespace(status=lambda **kw:{'state':'synced'},enqueue=lambda:{'state':'pending'})
    thread=threading.Thread(target=http_server.serve_forever,daemon=True);thread.start()
    cookie='';prefix='/os-tutorial' if public else '';origin='https://example.test' if public else f'http://127.0.0.1:{http_server.server_port}'
    def call(path,method='GET',data=None):
     conn=http.client.HTTPConnection('127.0.0.1',http_server.server_port,timeout=10)
     conn.request(method,prefix+'/api/'+path,None if data is None else json.dumps(data),{'Content-Type':'application/json','Origin':origin,'Host':'example.test' if public else f'127.0.0.1:{http_server.server_port}','Cookie':cookie})
     res=conn.getresponse();result=(res.status,json.loads(res.read()),dict(res.getheaders()));conn.close();return result
    try:
     if public:
      status,_,headers=call('auth/login','POST',{'username':'tester','password':'never-log-this-secret'});self.assertEqual(status,200);cookie=headers['Set-Cookie'].split(';')[0]
     record=store.load_record(self.root,'sample');record['body']['nodes'][-1]['value']+=' changed'
     payload={'revision':record['metadata']['revision'],'document':record['body']}
     with self.assertLogs('save-performance',level='INFO') as logs:status,result,headers=call('notes/sample','PUT',payload)
     self.assertEqual(status,200,result)
     for stage in ('lock;dur=','read;dur=','history;dur=','write;dur=','assemble;dur=','total;dur='):self.assertIn(stage,headers['Server-Timing'])
     self.assertNotIn('Original',' '.join(logs.output));self.assertNotIn('never-log-this-secret',' '.join(logs.output))
     self.assertEqual(call('notes/sample','PUT',payload)[0],409)
     client='timing-client';status,lease,_=call('edit-locks/acquire','POST',{'note_id':'sample','client_id':client,'resource':{'kind':'entry','id':'e'}})
     self.assertEqual(status,200,lease)
     record=store.load_record(self.root,'sample');node={**record['body']['nodes'][-1],'value':'entry changed'}
     status,result,headers=call('notes/sample/entries','PUT',{'note_id':'sample','client_id':client,'request_id':uuid.uuid4().hex,'changes':[{'kind':'update','lease':{'id':lease['id'],'token':lease['token']},'node':node}]})
     self.assertEqual(status,200,result);self.assertIn('total;dur=',headers['Server-Timing'])
     if not public:
      status,result,headers=call('sources/'+self.sid,'PUT',{'revision':'','ignored':True})
      self.assertEqual(status,200,result);self.assertTrue(result['ignored']);self.assertIn('read;dur=',headers['Server-Timing'])
    finally:http_server.shutdown();thread.join();http_server.server_close()

if __name__=='__main__':unittest.main()
