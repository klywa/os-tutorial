import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from crawler import Store

class StagingLinksTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);wxq.init_store(self.root);self.store=Store(self.root)
 def source(self,n):
  return workspace.register_source(self.root,{'url':f'https://www.bilibili.com/video/BV123456789{n}','title':'测试'})
 def test_staging_union_restart_clear_conflict_and_ignore(self):
  from source_staging import Staging
  self.source(1);self.source(2);s=Staging(self.root)
  a=s.add(['BV1234567891:p1']);s.add(['BV1234567891:p1','BV1234567892:p1'])
  self.assertEqual(len(Staging(self.root).get()['items']),2)
  with self.assertRaises(workspace.Conflict):s.clear(a['revision'])
  row=workspace.sources(self.root)[0]
  from source_edit import save_metadata
  save_metadata(self.root,row['id'],{'revision':row.get('manual_revision',''),'ignored':True},self.store)
  s.prune();self.assertEqual(len(s.get()['items']),1)
 def test_parse_parts_merges_and_rejects_external_urls(self):
  from link_jobs import parse_links
  r=parse_links('BV1234567891\nhttps://www.bilibili.com/video/BV1234567891?p=2\nhttps://evil.test/a\nBV1234567892?p=3')
  self.assertEqual(len(r['videos']),2);self.assertIsNone(r['videos'][0]['parts']);self.assertEqual(r['videos'][1]['parts'],[3]);self.assertEqual(len(r['invalid']),1)
 def test_link_batch_has_scoped_parts_and_no_keyword_filter(self):
  from link_jobs import start_links,scope_for
  r=start_links(self.store,'https://www.bilibili.com/video/BV1234567891?p=2')
  self.assertEqual(scope_for(self.store,'BV1234567891'),[2]);self.assertEqual(r['job']['config']['kind'],'links')
  start_links(self.store,'BV1234567891')
  self.assertIsNone(scope_for(self.store,'BV1234567891'))
 def test_truncated_download_is_network_error(self):
  from acquisition_errors import describe_error
  self.assertEqual(describe_error('Downloaded 15469949 bytes, expected 39150901 bytes')['category'],'network')
 def test_part_scope_append_completion_and_shared_cancel(self):
  from link_jobs import start_links,record_parts,mark_part,scope_for
  bv='BV1234567891';a=start_links(self.store,bv+'?p=2')['job'];task=self.store.claim()
  record_parts(self.store,bv,[{'playlist_index':i} for i in [1,2,3]])
  mark_part(self.store,bv,2,'succeeded',generation=task['generation'])
  b=start_links(self.store,bv+'?p=3')['job']
  self.store.finish_task(bv,'succeeded',generation=task['generation'])
  self.assertEqual(self.store.job(a['id'])['counts']['succeeded'],1)
  self.assertEqual(self.store.job(b['id'])['counts']['queued'],1)
  self.store.delete_job(a['id']);self.assertEqual(scope_for(self.store,bv),[3]);self.assertTrue(self.store.requested(bv))
  task=self.store.claim();mark_part(self.store,bv,3,'succeeded',generation=task['generation']);self.store.finish_task(bv,'succeeded',generation=task['generation'])
  self.assertEqual(self.store.job(b['id'])['counts']['succeeded'],1)
 def test_network_rounds_durable_and_cancelled_not_recovered(self):
  from link_jobs import start_links
  bv='BV1234567891';job=start_links(self.store,bv)['job'];task=self.store.claim()
  self.store.finish_task(bv,'failed','Downloaded 2 bytes, expected 3 bytes',generation=task['generation'])
  self.store.adopt_network_failures()
  self.assertIsNone(Store(self.root).claim())
  for expected in [1,2,3]:
   with self.store.db() as db:
    row=db.execute('SELECT * FROM network_retries').fetchone();self.assertEqual(row['attempt'],expected)
    db.execute("UPDATE network_retries SET next_retry_at='2000-01-01'")
   task=self.store.claim();self.assertIsNotNone(task)
   self.store.finish_task(bv,'failed','Downloaded 2 bytes, expected 3 bytes',generation=task['generation']);self.store.adopt_network_failures()
  self.assertEqual(self.store.tasks()[0]['state'],'failed')
  self.store.retry(job['id']);self.assertIsNotNone(self.store.claim())
  self.store.control_task(bv,'delete');self.store.adopt_network_failures();self.assertEqual(self.store.tasks()[0]['state'],'cancelled')
 def test_resume_guard_quarantines_changed_object_and_bad_range(self):
  from download_resume import ResumeGuard,ObjectChanged
  folder=self.root/'download';folder.mkdir();partial=folder/'audio.m4a.part'
  guard=ResumeGuard({'outtmpl':str(folder/'audio.%(ext)s')})
  guard.begin({'id':'a','format_id':'audio'});partial.write_bytes(b'old');guard.response({'Content-Length':'10'},False)
  with self.assertRaises(ObjectChanged):guard.response({'Content-Range':'bytes 3-19/20'},True)
  self.assertFalse(partial.exists());self.assertTrue(list(folder.glob('failed-downloads/*/audio.m4a.part')))
  partial.write_bytes(b'old2');guard.response({'Content-Length':'10'},True)
  self.assertFalse(partial.exists())
  partial.write_bytes(b'bad-offset')
  with self.assertRaises(ObjectChanged):guard.response({'Content-Range':'bytes 0-9/10'},'bytes=4-')
  self.assertFalse(partial.exists());self.assertEqual(len(list(folder.glob('failed-downloads/*/audio.m4a.part'))),3)
 def test_stopping_one_batch_preserves_shared_stage(self):
  from link_jobs import start_links
  bv='BV1234567891';a=start_links(self.store,bv+'?p=2')['job'];b=start_links(self.store,bv+'?p=2')['job'];task=self.store.claim()
  self.store.finish_task(bv,'running',progress={'phase':'downloading'},generation=task['generation'])
  self.store.stop_phase(a['id'],'stop-download')
  self.assertEqual(self.store.tasks()[0]['state'],'running')
  self.store.stop_phase(b['id'],'stop-download')
  self.assertEqual(self.store.tasks()[0]['state'],'paused')
 def test_cleanup_preview_rechecks_links_and_retains_linked(self):
  from lineup_cleanup import Cleanup
  from lineup_catalog import LineupCatalog
  catalog=LineupCatalog(self.root)
  # Existing explicit associations alone protect a lineup; titles are not inferred.
  wxq.atomic_json(self.root/'entities/heroes.json',[{'id':'card:1','name':'甲'},{'id':'card:2','name':'乙'}])
  catalog.save({'name':'A','heroes':['card:1']});catalog.save({'name':'B','heroes':['card:2']})
  a,b=catalog.roster()
  with catalog.topics.db() as db:
   db.execute('INSERT INTO lineup_notes VALUES(?,?)',(a['id'],'explicit-note'))
  cleanup=Cleanup(self.root);preview=cleanup.preview()
  self.assertEqual([r['id'] for r in preview['keep']],[a['id']])
  with catalog.topics.db() as db:db.execute('UPDATE topic_lineups SET revision=revision+1 WHERE id=?',(b['id'],))
  with self.assertRaises(workspace.Conflict):cleanup.apply(preview['token'])
  preview=cleanup.preview();result=cleanup.apply(preview['token'])
  self.assertEqual(result['removed'],[b['id']]);self.assertTrue(Path(result['backup']).is_file())
 def test_single_part_media_keeps_real_count_and_skips_other_parts(self):
  import media
  from reference_store import export_transcripts,transcript_errors
  from link_jobs import start_links
  bv='BV1234567891';seen=[]
  sub={'language':'zh-CN','automatic':False,'url':'https://example.test/sub','raw':{'body':[{'from':0,'to':1,'content':'教学'}]},'segments':[{'start':0,'end':1,'text':'教学'}]}
  def fetch(video,part,duration):seen.append(part);return sub
  with patch('media.download_entry') as download,patch('media.transcribe') as asr:
   rows=media.prepare(self.root,'https://www.bilibili.com/video/'+bv+'?p=2',require_frames=False,entry_fetcher=lambda:[{'id':str(p),'playlist_index':p,'title':'分P','duration':2} for p in [1,2,3]],subtitle_fetcher=fetch)
  self.assertEqual(seen,[2]);self.assertEqual(rows[0]['id'],bv+':p2');download.assert_not_called();asr.assert_not_called()
  self.assertEqual(wxq.read_json(wxq.source_dir(self.root,bv+':p2')/'metadata.json')['part_count'],3)
  workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/'+bv+'?p=2','title':'分P'})
  self.assertFalse(export_transcripts(self.root,[bv+':p2'])['errors']);self.assertFalse(transcript_errors(self.root,bv+':p2'))
  self.assertEqual(start_links(self.store,bv+'?p=2')['completed'],1)
  self.assertEqual(start_links(self.store,bv)['completed'],0)
 def test_full_request_restart_does_not_trust_old_single_part_count(self):
  import media,crawler_worker
  from reference_store import export_transcripts
  from link_jobs import start_links,record_parts
  from unittest.mock import MagicMock
  bv='BV1234567891'
  sub={'language':'zh-CN','automatic':False,'url':'https://example.test/sub','raw':{'body':[{'from':0,'to':1,'content':'教学'}]},'segments':[{'start':0,'end':1,'text':'教学'}]}
  entries=[{'id':str(p),'playlist_index':p,'title':'测试','duration':2} for p in [1,2,3]]
  media.prepare(self.root,'https://www.bilibili.com/video/'+bv+'?p=1',require_frames=False,entry_fetcher=lambda:entries[:1],subtitle_fetcher=lambda *a:sub)
  workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/'+bv+'?p=1','title':'测试'});export_transcripts(self.root,[bv+':p1'])
  # Discovery survived a previous run, but legacy P1 still incorrectly says count=1.
  record_parts(self.store,bv,entries);job=start_links(self.store,bv)['job'];task=self.store.claim()
  adapter=MagicMock();adapter.entries.return_value=entries;adapter.subtitles.return_value=sub
  with patch('bilibili.Bilibili',return_value=adapter),patch('media.transcribe') as asr:
   result=crawler_worker.run(self.root,bv,generation=task['generation'])
  self.assertEqual({r['id'] for r in result},{bv+':p1',bv+':p2',bv+':p3'});asr.assert_not_called();adapter.download.assert_not_called()
  self.store.finish_task(bv,'succeeded',generation=task['generation']);self.assertEqual(self.store.job(job['id'])['counts']['succeeded'],1)
