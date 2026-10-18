import sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from crawler import Store,source_rows,batch_paths
from source_edit import save_metadata
from topics import TopicStore,validate_result
from topic_model import LocalModel

class TopicTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);wxq.init_store(self.root);self.store=Store(self.root);self.topics=TopicStore(self.root)
  self.sid=workspace.register_source(self.root,{'url':'https://example.com/topic','title':'主题'})['id']
 def test_ignored_projection_and_paths(self):
  wxq.atomic_text(self.root/'raw/text.md','正文');wxq.atomic_json(self.root/'raw/index.json',{'sources':{self.sid:{'path':'raw/text.md'}}})
  row=source_rows(self.root,self.store)[0]
  save_metadata(self.root,self.sid,{'revision':row['revision'],'ignored':True,'topic_players':[]},self.store)
  self.assertTrue(source_rows(self.root,self.store)[0]['ignored'])
  self.assertEqual(batch_paths(self.root,[self.sid])['paths'],[])
 def test_roster_ids_aliases_and_no_automatic_new_names(self):
  roster=self.topics.save_roster({'names':['甲阵容','乙阵容']})
  first=roster[0];self.topics.save_roster({'id':first['id'],'name':'甲阵容','aliases':['别称'],'enabled':True})
  self.assertEqual(self.topics.map_lineup('别称'),first['id']);self.assertIsNone(self.topics.map_lineup('未知'))
  self.assertEqual(self.topics.save_roster({'names':['甲阵容']})[0]['id'],first['id'])
 def test_evidence_must_be_real_and_player_id_valid(self):
  players=[{'id':'player:1','name':'棋手甲'}]
  data={'players':[{'id':'player:1','evidence':'这是棋手甲的教学'}],'lineups':[{'name':'甲阵容','evidence':'这是棋手甲的教学，甲阵容'}]}
  self.assertTrue(validate_result(data,'这是棋手甲的教学，甲阵容',players)['players'])
  with self.assertRaises(ValueError):validate_result(data,'没有该引文',players)
  data['players'][0]['id']='hero:1'
  with self.assertRaises(ValueError):validate_result(data,'这是棋手甲的教学，甲阵容',players)
 def test_evidence_must_identify_its_subject(self):
  with self.assertRaises(ValueError):validate_result({'players':[{'id':'player:1','evidence':'队友全部牺牲'}],'lineups':[]},'棋手甲教学。队友全部牺牲。',[{'id':'player:1','name':'棋手甲'}])
  self.assertFalse(validate_result({'players':[],'lineups':[{'name':'甲阵容','evidence':'队友全部牺牲'}]},'甲阵容教学。队友全部牺牲。',[])['lineups'][0]['grounded'])
 def test_model_proposed_mapping_needs_confirmation_even_if_name_exists(self):
  rows,task=self.ready();uid=self.topics.save_roster({'names':['甲阵容']})[0]['id']
  self.topics.control('extract',self.sid);task=self.topics.claim()
  self.topics.finish(task,{'players':[],'lineups':[{'name':'甲阵容','evidence':'一段真实但不含对应名称的引文','grounded':False}]})
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[])
  candidate=self.topics.pending()[0];self.topics.resolve(candidate['id'],{'target':uid})
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[uid])
 def test_confirmed_alias_in_evidence_allows_canonical_mapping(self):
  rows,task=self.ready();uid=self.topics.save_roster({'names':['甲阵容']})[0]['id']
  self.topics.save_roster({'id':uid,'name':'甲阵容','aliases':['甲别称'],'enabled':True})
  self.topics.control('extract',self.sid);task=self.topics.claim()
  self.topics.finish(task,{'players':[],'lineups':[{'name':'甲阵容','evidence':'甲别称教学','grounded':False}]})
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[uid]);self.assertEqual(self.topics.pending(),[])
 def test_queue_skip_ignored_and_stale_completion(self):
  rows=[{'id':self.sid,'title':'标题','ignored':False,'transcript_path':None}]
  self.topics.sync(rows);self.assertEqual(self.topics.snapshot()['counts'].get('waiting'),1)
  rows[0]['ignored']=True;self.topics.sync(rows)
  self.assertEqual(self.topics.snapshot()['counts'].get('ignored'),1)
 def ready(self):
  p=self.root/'raw/text.md';wxq.atomic_text(p,'这是棋手甲的教学，主讲甲阵容。')
  wxq.atomic_json(self.root/'raw/index.json',{'sources':{self.sid:{'path':'raw/text.md'}}})
  rows=[{'id':self.sid,'title':'标题','transcript_path':str(p)}]
  self.topics.sync(rows);self.topics.setting('validated',True)
  return rows,self.topics.claim()
 def test_confirmation_alias_and_import_collision(self):
  rows,task=self.ready();self.topics.finish(task,{'players':[],'lineups':[{'name':'甲别称','evidence':'这是棋手甲的教学'}]})
  uid=self.topics.save_roster({'names':['甲阵容']})[0]['id']
  candidate=self.topics.pending()[0]
  self.topics.resolve(candidate['id'],{'target':uid,'remember_alias':True})
  self.assertEqual(self.topics.map_lineup('甲别称'),uid)
  with self.assertRaises(ValueError):self.topics.save_roster({'names':['甲别称']})
  self.assertEqual(len(self.topics.roster()),1)
 def test_late_results_and_manual_clear(self):
  rows,task=self.ready();rows[0]['title']='新标题';self.topics.sync(rows)
  self.assertFalse(self.topics.finish(task,{'players':[{'id':'player:1'}]}))
  task=self.topics.claim();self.topics.finish(task,{'players':[{'id':'player:1'}]})
  rows[0]['manual_values']={'topic_players':[]}
  self.assertEqual(self.topics.project(rows)[0]['topic_players'],[])
  del rows[0]['manual_values']['topic_players']
  self.assertEqual(self.topics.project(rows)[0]['topic_players'],['player:1'])
 def test_pending_has_context_and_ignored_is_hidden(self):
  rows,task=self.ready();self.topics.finish(task,{'lineups':[{'name':'甲阵容','evidence':'这是棋手甲的教学'}]})
  self.assertIn('主讲',self.topics.pending()[0]['context'])
  rows[0]['ignored']=True;self.topics.sync(rows);self.assertEqual(self.topics.pending(),[])
  rows[0]['ignored']=False;self.topics.sync(rows)
  self.assertEqual(self.topics.snapshot()['counts'].get('queued'),1)
 def test_model_bad_json_retry_and_name_identity(self):
  model=LocalModel(self.root);answers=[{'choices':[{'message':{'content':'broken json'}}]}, {'choices':[{'message':{'content':'{"kind":"教学","players":[{"name":"棋手甲","evidence":"这是棋手甲的教学"}],"lineups":[]}'}}]}]
  with patch.object(model,'request',side_effect=answers) as request:
   result=model.ask('正文',[{'id':'player:1','name':'棋手甲'}],'这是棋手甲的教学')
  self.assertEqual(request.call_count,2);self.assertEqual(result['players'][0]['id'],'player:1')
  retry_schema=request.call_args.args[1]['response_format']['json_schema']['schema']
  self.assertIn('这是棋手甲的教学',retry_schema['properties']['players']['items']['oneOf'][0]['properties']['evidence']['enum'])
  with patch.object(model,'request',return_value=answers[0]) as request:
   with self.assertRaises(ValueError):model.ask('正文',[],'这是合法原文')
  self.assertEqual(request.call_count,2)
 def test_long_input_full_coverage_and_cancel(self):
  model=LocalModel(self.root);text='甲'*8000;covered=[]
  def ask(content,players,valid):
   import json
   covered.append(json.loads(content)['transcript']);return {'players':[],'lineups':[]}
  with patch.object(model,'tokens',side_effect=lambda value:list(range(8000)) if value==text else [1]),patch.object(model,'decode',side_effect=lambda ids:'甲'*len(ids)),patch.object(model,'ask',side_effect=ask):
   result=model.extract('标题',text,[])
  self.assertEqual(result['provenance']['chunks'],3);self.assertEqual(sum(map(len,covered)),8400)
  with patch.object(model,'tokens',return_value=[1]),patch.object(model,'decode',return_value='甲'):
   with self.assertRaises(InterruptedError):model.extract('标题','甲',[],cancelled=lambda:True)
 def test_restart_retry_preserves_old_values_and_pause_gate(self):
  rows,task=self.ready();self.topics.finish(task,{'players':[{'id':'player:1'}]})
  self.topics.control('extract',self.sid);task=self.topics.claim();self.topics.finish(task,{},'超时')
  self.assertEqual(TopicStore(self.root).project(rows)[0]['topic_players'],['player:1'])
  self.topics.control('retry');self.topics.control('pause');self.assertIsNone(self.topics.claim())
  self.topics.control('resume');self.assertIsNotNone(self.topics.claim())
 def test_no_speech_does_not_use_title_and_missing_waits(self):
  rows,_=self.ready();rows[0]['transcript_status']='no_speech'
  self.topics.sync(rows);self.assertIsNone(self.topics.claim())
  self.assertEqual(self.topics.snapshot()['counts'].get('no_speech'),1)
 def test_topic_http_and_metadata_conflict(self):
  import json,threading,urllib.request,urllib.error
  import server
  wxq.atomic_json(self.root/'entities/players.json',[{'id':'player:1','name':'棋手甲'}])
  http=server.create_server(self.root,0);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  base=f'http://127.0.0.1:{http.server_port}'
  def request(path,method='GET',payload=None):
   req=urllib.request.Request(base+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,method=method,headers={'Origin':base,'Content-Type':'application/json'})
   with urllib.request.urlopen(req) as response:return json.load(response)
  try:
   self.assertEqual(request('topics/catalog')['topic_players'][0]['id'],'player:1')
   roster=request('topics/lineups','POST',{'names':['甲阵容']})
   row=request('sources')[0]
   edited=request('sources/'+self.sid,'PUT',{'revision':row['revision'],'topic_players':['player:1'],'topic_lineups':[roster[0]['id']],'ignored':True})
   self.assertTrue(edited['ignored']);self.assertEqual(edited['topic_players'],['player:1'])
   with self.assertRaises(urllib.error.HTTPError) as failure:request('sources/'+self.sid,'PUT',{'revision':row['revision'],'ignored':False})
   self.assertEqual(failure.exception.code,409)
   with patch('server.crawler.source_rows',side_effect=AssertionError('暂停不应等待来源文件扫描')):
    self.assertTrue(request('topics/control','POST',{'action':'pause'})['paused'])
   self.assertEqual(request('topics/candidates'),[])
  finally:http.shutdown();http.server_close();thread.join(5)
 def test_successful_rerun_removes_old_lineup_candidates(self):
  rows,task=self.ready();uid=self.topics.save_roster({'names':['甲阵容']})[0]['id']
  self.topics.control('extract',self.sid);task=self.topics.claim()
  self.topics.finish(task,{'players':[],'lineups':[{'name':'甲阵容','evidence':'这是棋手甲的教学'}]})
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[uid])
  self.topics.control('extract',self.sid);task=self.topics.claim();self.topics.finish(task,{'players':[],'lineups':[]})
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[]);self.assertEqual(self.topics.pending(),[])
 def test_disabled_or_renamed_lineup_keeps_existing_mapping(self):
  rows,task=self.ready();self.topics.finish(task,{'players':[],'lineups':[{'name':'甲阵容','evidence':'这是棋手甲的教学'}]})
  uid=self.topics.save_roster({'names':['甲阵容']})[0]['id']
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[uid])
  self.topics.save_roster({'id':uid,'name':'新正式名','aliases':[],'enabled':False})
  self.assertEqual(self.topics.project(rows)[0]['topic_lineups'],[uid])
 def test_multiple_evidence_for_one_player_has_one_tag(self):
  rows,task=self.ready();self.topics.finish(task,{'players':[{'id':'player:1','evidence':'原文甲'},{'id':'player:1','evidence':'原文乙'}],'lineups':[]})
  self.assertEqual(self.topics.project(rows)[0]['topic_players'],['player:1'])
 def test_model_download_resume_and_bad_checksum_keeps_old_file(self):
  import hashlib,subprocess
  from install_topic_model import download
  path=self.root/'model.gguf';path.write_bytes(b'old');part=path.with_suffix(path.suffix+'.part');part.write_bytes(b'partial')
  expected=hashlib.sha256(b'complete').hexdigest()
  def resumed(args,**kwargs):part.write_bytes(b'complete');return subprocess.CompletedProcess(args,0)
  with patch('install_topic_model.subprocess.run',side_effect=resumed) as run:
   download('https://example.com/model',path,expected)
  self.assertIn('--continue-at',run.call_args.args[0]);self.assertEqual(path.read_bytes(),b'complete');self.assertFalse(part.exists())
  with patch('install_topic_model.subprocess.run',side_effect=lambda *a,**k:part.write_bytes(b'broken')):
   with self.assertRaises(ValueError):download('https://example.com/model',path,hashlib.sha256(b'new version').hexdigest())
  self.assertEqual(path.read_bytes(),b'complete');self.assertTrue(part.exists())
 def test_ignored_save_immediately_invalidates_running_topic_task(self):
  rows,task=self.ready();folder=wxq.source_dir(self.root,self.sid);folder.mkdir(parents=True,exist_ok=True)
  wxq.atomic_json(folder/'asr.raw.json',{'segments':[{'text':'正文'}]})
  current=source_rows(self.root,self.store)[0]
  save_metadata(self.root,self.sid,{'revision':current['revision'],'ignored':True},self.store)
  self.assertFalse(self.topics.finish(task,{'players':[],'lineups':[]}))
  self.assertEqual(self.topics.snapshot()['counts'].get('ignored'),1)
 def test_model_news_cannot_fill_topics_even_when_entities_are_returned(self):
  model=LocalModel(self.root);response={'choices':[{'message':{'content':'{"kind":"资讯","players":[{"name":"棋手甲","evidence":"更新加强了棋手甲"}],"lineups":[]}'}}]}
  with patch.object(model,'request',return_value=response):
   self.assertEqual(model.ask('更新公告',[{'id':'player:1','name':'棋手甲'}],'更新加强了棋手甲'),{'players':[],'lineups':[]})
 def test_worker_restart_recovers_running_task(self):
  from unittest.mock import MagicMock
  import topic_worker
  rows,task=self.ready();model=MagicMock();model.process=None;model.extract.return_value={'players':[],'lineups':[]}
  with patch.object(topic_worker,'LocalModel',return_value=model),patch.object(topic_worker,'source_rows',return_value=rows),patch.object(topic_worker,'transcript_errors',return_value=[]),patch.object(topic_worker.time,'sleep',side_effect=InterruptedError('end isolated run')):
   with self.assertRaises(InterruptedError):topic_worker.run(self.root)
  self.assertEqual(self.topics.snapshot()['counts'].get('succeeded'),1);self.assertTrue(model.close.called)
 def test_worker_releases_idle_model(self):
  from unittest.mock import MagicMock
  import topic_worker
  self.topics.setting('paused',True);model=MagicMock();model.process=object();model.last_used=0
  def stop(_):
   self.assertEqual(model.close.call_count,1);raise InterruptedError('end isolated run')
  with patch.object(topic_worker,'LocalModel',return_value=model),patch.object(topic_worker,'source_rows',return_value=[]),patch.object(topic_worker.time,'monotonic',return_value=400),patch.object(topic_worker.time,'sleep',side_effect=stop):
   with self.assertRaises(InterruptedError):topic_worker.run(self.root)
 def test_long_summary_cannot_introduce_unseen_topics(self):
  model=LocalModel(self.root);part={'players':[{'id':'player:1','evidence':'棋手甲教学'}],'lineups':[{'name':'甲阵容','evidence':'甲阵容教学'}]}
  invented={'players':[{'id':'player:2','evidence':'棋手乙教学'}],'lineups':[{'name':'乙阵容','evidence':'乙阵容教学'}]}
  with patch.object(model,'tokens',side_effect=[[1],list(range(5000)),[1]]),patch.object(model,'decode',return_value='正文'),patch.object(model,'ask',side_effect=[part,part,invented]):
   result=model.extract('标题','正文',[{'id':'player:1','name':'棋手甲'},{'id':'player:2','name':'棋手乙'}])
  self.assertEqual(result['players'],[]);self.assertEqual(result['lineups'],[])
 def test_verified_raw_export_repairs_without_corrected_asr(self):
  import hashlib
  from reference_store import repair_transcript_index,transcript_errors
  folder=wxq.source_dir(self.root,self.sid);folder.mkdir(parents=True,exist_ok=True)
  raw=folder/'asr.raw.json';wxq.atomic_json(raw,{'segments':[{'text':'原始有效语音'}]})
  text=self.root/'raw/text.md';wxq.atomic_text(text,'原始有效文字稿')
  entry={'path':'raw/text.md','transcript_file':'asr.raw.json','raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(text.read_bytes()).hexdigest()}
  wxq.atomic_json(self.root/'raw/index.json',{'sources':{self.sid:entry}})
  self.assertTrue(repair_transcript_index(self.root,self.sid));self.assertEqual(transcript_errors(self.root,self.sid),[])
  self.assertEqual(text.read_text('utf-8'),'原始有效文字稿');self.assertFalse((folder/'asr.corrected.json').exists())
  self.assertTrue(list((self.root/'raw/reports/index-upgrades').glob('*.json')))
  wxq.atomic_json(raw,{'segments':[{'text':'后来变化的ASR'}]})
  self.assertFalse(repair_transcript_index(self.root,self.sid));self.assertEqual(text.read_text('utf-8'),'原始有效文字稿')
