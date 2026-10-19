import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import media,wxq
from crawler import Store,Runtime
from bilibili import Bilibili,BilibiliError

class AcquisitionRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);wxq.init_store(self.root)
 def task(self):
  store=Store(self.root);job=store.new_job({});store.discover(job['id'],{'bvid':'BV1234567890'},'',True)
  return store,store.claim()
 def test_subtitle_success_does_not_require_media_formats(self):
  sub={'language':'zh-CN','automatic':False,'url':'https://x/a','raw':{'body':[{'from':0,'to':1,'content':'教学'}]},'segments':[{'start':0,'end':1,'text':'教学'}]}
  with patch('yt_dlp.YoutubeDL') as ydl:
   ydl.return_value.__enter__.return_value.extract_info.side_effect=RuntimeError('No video formats found')
   result=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=False,
    entry_fetcher=lambda:[{'id':'1','playlist_index':1,'title':'测试','duration':2}],subtitle_fetcher=lambda *args:sub)
  self.assertEqual(result[0]['stage'],'prepared');ydl.assert_not_called()
 def test_failed_worker_result_is_not_replaced_by_log_tail(self):
  store,task=self.task();runtime=Runtime(self.root)
  class Process:
   returncode=1
   def poll(self):return 1
  def launch(*args,**kwargs):
   store.finish_task(task['bvid'],'failed','明确错误：412',generation=task['generation'])
   return Process()
  with patch('crawler.subprocess.Popen',side_effect=launch):runtime.process_task(task)
  self.assertEqual(store.tasks()[0]['error'],'明确错误：412')
 def test_structured_failure_and_success_cleanup(self):
  store,task=self.task()
  store.finish_task(task['bvid'],'failed','HTTP 412',progress={'phase':'fetching_subtitles'},generation=task['generation'])
  detail=store.tasks()[0]['error_info'];self.assertEqual(detail['code'],412);self.assertEqual(detail['phase'],'fetching_subtitles')
  store.finish_task(task['bvid'],'succeeded',generation=task['generation'])
  self.assertIsNone(store.tasks()[0]['error_info'])
 def test_adapter_discovers_parts_without_formats(self):
  adapter=object.__new__(Bilibili)
  with patch.object(adapter,'request',return_value={'title':'测试','owner':{'name':'作者'},'pages':[{'page':2,'cid':9,'duration':5}]}):
   rows=adapter.entries('BV1234567890')
  self.assertEqual(rows[0]['playlist_index'],2);self.assertEqual(rows[0]['cid'],9)
 def test_shared_gate_cooldown_is_endpoint_specific(self):
  from acquisition_network import NetworkGate,Deferred
  a=NetworkGate(self.root,interval=0);b=NetworkGate(self.root,interval=0)
  a.defer('subtitles',60)
  with self.assertRaises(Deferred):b.wait('subtitles')
  b.wait('media')
 def test_subtitle_failure_refreshes_once_and_attempts_audio(self):
  import crawler_worker
  store,task=self.task()
  with patch('bilibili.Bilibili') as factory:
   client=factory.return_value;client.entries.return_value=[{'id':'1','title':'测试','duration':2}]
   client.subtitles.side_effect=BilibiliError(412,'受限')
   client.download.side_effect=RuntimeError('音频诊断')
   with self.assertRaisesRegex(RuntimeError,'音频诊断'):crawler_worker.run(self.root,task['bvid'],generation=task['generation'])
  self.assertEqual(client.subtitles.call_count,2);client.refresh_session.assert_called_once();client.download.assert_called_once()
  reason=wxq.read_json(wxq.source_dir(self.root,task['bvid']+':p1')/'subtitle-fallback.json')
  self.assertEqual(reason['code'],412)
 def test_audio_fallback_uses_no_video_or_frames(self):
  audio=self.root/'download.m4a';audio.write_bytes(b'audio')
  def convert(args,target):Path(target).write_bytes(b'wav')
  with patch('media.convert_media',side_effect=convert),patch('media.audio_seconds',return_value=2),patch('media.transcribe',return_value={'segments':[]}) as asr,patch('media.extract_frames') as frames:
   fetch=MagicMock(return_value=({},audio))
   result=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=False,
    entry_fetcher=lambda:[{'id':'1','title':'测试','duration':2}],subtitle_fetcher=lambda *args:None,download_callback=fetch)
  self.assertEqual(result[0]['stage'],'prepared');asr.assert_called_once();frames.assert_not_called()
  self.assertEqual(fetch.call_args.args[1]['format'],'bestaudio/best')
 def test_restore_only_once_and_never_restores_stopped(self):
  store,task=self.task();store.finish_task(task['bvid'],'failed','No video formats found',generation=task['generation'])
  self.assertEqual(store.restore_recoverable(),[task['bvid']]);self.assertEqual(store.restore_recoverable(),[])
  store.finish_task(task['bvid'],'failed','HTTP 412');store.control_task(task['bvid'],'delete')
  self.assertEqual(store.restore_recoverable(),[])
 def test_shared_probe_is_not_repeated_by_other_process(self):
  from acquisition_network import NetworkGate,Deferred
  a=NetworkGate(self.root,0);b=NetworkGate(self.root,0)
  a.defer('subtitles');a.probe('subtitles');b.wait('subtitles')
  a.defer('subtitles');b.probe('subtitles')
  with self.assertRaises(Deferred):a.wait('subtitles')
 def test_format_error_is_not_a_risk_error(self):
  from acquisition_errors import describe_error
  self.assertEqual(describe_error('No video formats found')['category'],'formats')
  self.assertEqual(describe_error(BilibiliError(-404,'不存在'))['category'],'unavailable')
 def test_export_resume_does_not_require_network_even_after_failure(self):
  folder=wxq.source_dir(self.root,'BV1234567890:p1')
  wxq.atomic_json(folder/'metadata.json',{'id':'BV1234567890:p1','part_count':1})
  wxq.atomic_json(folder/'asr.raw.json',{'model':'large-v3','segments':[]})
  wxq.atomic_json(folder/'asr.corrected.json',{'model':'large-v3','segments':[]})
  wxq.atomic_json(folder/'state.json',{'stage':'failed','error':'旧错误'})
  discovery=MagicMock(side_effect=RuntimeError('不应访问网络'))
  result=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=False,entry_fetcher=discovery)
  discovery.assert_not_called();self.assertEqual(result[0]['stage'],'prepared')
 def test_complete_source_never_downgrades_on_reuse(self):
  folder=wxq.source_dir(self.root,'BV1234567890:p1')
  wxq.atomic_json(folder/'metadata.json',{'id':'BV1234567890:p1','part_count':1})
  for name in ['asr.raw.json','asr.corrected.json']:wxq.atomic_json(folder/name,{'model':'large-v3','segments':[]})
  state={'stage':'complete','human_review':'kept'};wxq.atomic_json(folder/'state.json',state)
  result=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=False)
  self.assertEqual(result[0]['stage'],'complete');self.assertEqual(wxq.read_json(folder/'state.json'),state)
 def test_session_switch_and_clear_never_load_previous_identity(self):
  from types import SimpleNamespace
  from yt_dlp.cookies import YoutubeDLCookieJar
  one=self.root/'one.txt';two=self.root/'two.txt'
  for p in [one,two]:p.write_text('# Netscape HTTP Cookie File\n',encoding='utf-8')
  adapter=object.__new__(Bilibili);adapter.root=self.root
  adapter.ydl=SimpleNamespace(params={'cookiefile':str(one)},cookiejar=YoutubeDLCookieJar())
  with patch.object(adapter,'_refresh_session') as refresh:
   adapter.refresh_session();adapter.refresh_session();self.assertEqual(refresh.call_count,1)
   adapter.ydl.params['cookiefile']=str(two);adapter.refresh_session();self.assertEqual(refresh.call_count,2)
   adapter.ydl.params['cookiefile']='';adapter.refresh_session();self.assertEqual(refresh.call_count,3)
 def test_failure_code_and_download_phase_survive_part_boundary(self):
  from acquisition_errors import AcquisitionFailure,describe_error
  with patch('media.download_entry',side_effect=BilibiliError(412,'音频受限')):
   results=media.prepare(self.root,'https://www.bilibili.com/video/BV1234567890',require_frames=False,
    entry_fetcher=lambda:[{'id':'1','title':'测试','duration':2}],subtitle_fetcher=lambda *args:None)
  result=describe_error(AcquisitionFailure(results),'checking_subtitles')
  self.assertEqual(result['category'],'risk');self.assertEqual(result['code'],412);self.assertEqual(result['phase'],'downloading')
 def test_current_task_failure_replaces_stale_source_error(self):
  import workspace
  from crawler import source_rows
  store,task=self.task();sid=task['bvid']+':p1'
  workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/'+task['bvid'],'title':'测试'})
  wxq.atomic_json(wxq.source_dir(self.root,sid)/'state.json',{'stage':'failed','error':'HTTP 412 遗留错误'})
  store.finish_task(task['bvid'],'failed','No video formats found')
  row=source_rows(self.root,store)[0];self.assertEqual(row['error'],'No video formats found')
  store.finish_task(task['bvid'],'queued')
  row=source_rows(self.root,store)[0];self.assertEqual(row['error'],'');self.assertEqual(row['acquisition_error'],'')
 def test_request_start_limit_is_shared_across_processes(self):
  import subprocess
  code="import sys,time;from acquisition_network import NetworkGate;NetworkGate(sys.argv[1],.12).wait('media');print(time.time())"
  children=[subprocess.Popen([sys.executable,'-X','utf8','-c',code,str(self.root)],cwd=ROOT/'frontend',stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
  values=[]
  for child in children:
   out,err=child.communicate(timeout=15);self.assertEqual(child.returncode,0,err.decode());values.append(float(out))
  self.assertGreaterEqual(abs(values[0]-values[1]),.09)
