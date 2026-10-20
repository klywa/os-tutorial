import sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import wxq,workspace
from crawler import Store,config,source_rows

class MonitorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);wxq.init_store(self.root);self.store=Store(self.root)
 def creator(self,**extra):return self.store.save_creator({'url':'https://space.bilibili.com/123','name':'作者甲','date_from':'2026-10-01',**extra})
 def drain(self):
  for _ in range(10):
   if not self.store.process_tags():break
 def test_tags_validate_and_normalize(self):
  self.assertEqual(config({'tags':[' 甲 ','','甲','乙']})['tags'],['甲','乙'])
  for value in ['甲',None,[1]]:
   with self.assertRaises(ValueError):config({'tags':value})
 def test_one_task_across_scans_and_resume_policy(self):
  self.creator(tags=['攻略']);a=self.store.check_creator('123');self.store.update_job(a['id'],state='scanned');self.store.creator_result('123')
  b=self.store.check_creator('123');self.assertEqual(a['id'],b['id']);self.assertEqual(len(self.store.jobs()),1)
  self.store.stop(b['id']);self.assertEqual(self.store.creators()[0]['monitor_state'],'paused')
  self.store.resume_creators();self.assertEqual(self.store.job(a['id'],False)['state'],'pending')
  self.store.update_creator('123',{'url':'https://space.bilibili.com/123','date_from':'2026-10-01','enabled':False})
  self.store.resume_creators();self.assertEqual(self.store.creators()[0]['monitor_state'],'disabled')
  self.assertIsNone(self.store.next_pending())
 def test_restart_does_not_duplicate_or_skip_retry(self):
  self.creator();a=self.store.check_creator('123');self.store.begin_scan(a['id'])
  self.store.resume_creators();self.assertEqual(self.store.job(a['id'],False)['state'],'scanning')
  self.store.update_job(a['id'],state='failed',error='risk')
  with self.store.db() as db:db.execute("INSERT INTO risk_retries VALUES('job',?,1,'2099-01-01T00:00:00+08:00','risk')",(a['id'],))
  self.store.resume_creators();self.assertIsNone(self.store.next_pending());self.assertEqual(self.store.creators()[0]['monitor_state'],'retry_wait')
 def test_tag_queue_merges_existing_parts_and_preserves_annotations(self):
  from source_edit import save_metadata
  for part in [1,2]:
   row=workspace.register_source(self.root,{'url':f'https://www.bilibili.com/video/BV1234567890?p={part}','title':'旧标题'})
   save_metadata(self.root,row['id'],{'revision':'','tags':['人工'],'notes':'备注','ignored':True},self.store)
  job=self.store.new_job({'tags':['采集']});self.store.discover(job['id'],{'bvid':'BV1234567890','url':'https://www.bilibili.com/video/BV1234567890'},'',False)
  with patch('topics.TopicStore.sync') as sync:self.store.process_tags()
  rows=source_rows(self.root,self.store)
  self.assertEqual(len(rows),2)
  for row in rows:self.assertEqual(row['tags'],['人工','采集']);self.assertEqual(row['notes'],'备注');self.assertTrue(row['ignored'])
  sync.assert_not_called();self.assertEqual(self.store.tasks(),[])
 def test_creator_tag_change_backfills_and_keeps_old_tags(self):
  self.creator(tags=['旧']);job=self.store.check_creator('123')
  self.store.discover(job['id'],{'bvid':'BV1234567890','url':'https://www.bilibili.com/video/BV1234567890','author':'平台名'},'',False)
  self.drain();self.store.update_creator('123',{'url':'https://space.bilibili.com/123','date_from':'2026-10-01','name':'新名','tags':['新']});self.drain()
  row=source_rows(self.root,self.store)[0];self.assertEqual(row['tags'],['旧','作者甲','新','新名'])
 def test_legacy_jobs_group_without_removing_history(self):
  self.creator()
  with self.store.db() as db:
   for jid in ['old1','old2']:
    db.execute("INSERT INTO jobs(id,config,state,created,creator) VALUES(?,?,'scanned',?,'123')",(jid,json.dumps(config({})),jid))
    db.execute("INSERT INTO videos VALUES(?,?)",('BV'+jid,json.dumps({'bvid':'BV'+jid})))
    db.execute("INSERT INTO hits VALUES(?,?,'')",(jid,'BV'+jid))
  self.store.resume_creators();jobs=self.store.jobs();self.assertEqual(len(jobs),1);self.assertEqual(len(self.store.job(jobs[0]['id'])['items']),2)
  with self.store.db() as db:self.assertIsNotNone(db.execute("SELECT id FROM jobs WHERE id='old1'").fetchone())
  self.store.resume_creators();self.assertEqual(len(self.store.jobs()),1)
 def test_enable_and_resume_restore_dispatch_and_new_round(self):
  self.creator(enabled=False);job=self.store.creators()[0]['job_id']
  self.store.update_creator('123',{'url':'https://space.bilibili.com/123','date_from':'2026-10-01','enabled':True})
  self.assertEqual(self.store.next_pending()['id'],job)
  self.store.stop(job);self.store.resume(job);self.assertEqual(self.store.job(job,False)['scan_cancelled'],0)
 def test_scoped_link_tags_and_retry_draft_preservation(self):
  from link_jobs import start_links
  for p in [1,2]:workspace.register_source(self.root,{'url':f'https://www.bilibili.com/video/BV1234567890?p={p}'})
  start_links(self.store,'BV1234567890?p=2',tags=['分P'])
  with patch.object(self.store,'apply_acquisition_tags',side_effect=OSError('locked')):self.store.process_tags()
  with self.store.db() as db:self.assertEqual(db.execute("SELECT state FROM acquisition_tags").fetchone()[0],'failed')
  with self.store.db() as db:db.execute("UPDATE acquisition_tags SET state='pending'")
  self.drain();rows={r['id']:r for r in source_rows(self.root,self.store)}
  self.assertEqual(rows['BV1234567890:p1']['tags'],[]);self.assertEqual(rows['BV1234567890:p2']['tags'],['分P'])
 def test_tag_append_reads_latest_manual_value_and_new_parts(self):
  from source_edit import save_metadata
  row=workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/BV1234567890'})
  job=self.store.new_job({'tags':['采集']});self.store.discover(job['id'],{'bvid':'BV1234567890'},'',False)
  save_metadata(self.root,row['id'],{'revision':'','tags':['后来人工']},self.store)
  self.drain();workspace.register_source(self.root,{'url':'https://www.bilibili.com/video/BV1234567890?p=2'})
  self.store.queue_job_tags(job['id'],'BV1234567890');self.drain()
  rows={r['id']:r for r in source_rows(self.root,self.store)}
  self.assertEqual(rows[row['id']]['tags'],['后来人工','采集']);self.assertEqual(rows['BV1234567890:p2']['tags'],['采集'])
 def test_history_dispatch_pauses_resumes_and_retries_through_monitor(self):
  self.creator();jid=self.store.creators()[0]['job_id']
  with self.store.db() as db:
   db.execute("INSERT INTO jobs(id,config,state,created,creator) VALUES('history',?,'scanned','old','123')",(json.dumps(config({})),))
   db.execute("INSERT INTO videos VALUES('BV1234567890','{}')")
   db.execute("INSERT INTO hits VALUES('history','BV1234567890','')")
   db.execute("INSERT INTO dispatch VALUES('history','BV1234567890',1)")
   db.execute("INSERT INTO tasks(bvid,state,updated) VALUES('BV1234567890','failed','old')")
  self.store.ensure_monitor('123');self.store.retry(jid)
  self.assertEqual(self.store.tasks()[0]['state'],'queued')
  self.store.stop(jid);self.assertIsNone(self.store.claim())
  self.store.resume(jid);self.assertIsNotNone(self.store.claim())
  with self.assertRaises(ValueError):self.store.delete_job(jid)
 def test_retry_does_not_resume_paused_monitor_and_migration_keeps_cooldown(self):
  self.creator();jid=self.store.creators()[0]['job_id'];self.store.stop(jid);self.store.retry(jid)
  self.assertEqual(self.store.creators()[0]['monitor_state'],'paused')
  with self.store.db() as db:
   db.execute("INSERT INTO jobs(id,config,state,created,creator) VALUES('oldrisk',?,'pending','old','123')",(json.dumps(config({})),))
   db.execute("INSERT INTO risk_retries VALUES('job','oldrisk',2,'2099-01-01T00:00:00+08:00','risk')")
  self.store.ensure_monitor('123');self.store.resume(jid)
  self.assertIsNone(self.store.next_pending());self.assertEqual(self.store.risk_retry('job',jid)['attempt'],2)
 def test_readding_deleted_listener_starts_instead_of_inheriting_old_pause(self):
  self.creator();self.store.stop(self.store.creators()[0]['job_id']);self.store.delete_creator('123');self.creator()
  self.assertIsNotNone(self.store.next_pending());self.assertNotEqual(self.store.creators()[0]['monitor_state'],'paused')
