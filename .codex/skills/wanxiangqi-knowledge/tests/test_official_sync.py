import sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import official_sync as sync
import json_store,wxq

class SyncTests(unittest.TestCase):
    def test_rotating_video_signature_and_timestamps_are_not_content_changes(self):
        a={'retrieved_at':'before','properties':{'url':'http://video2.osgame.qq.com/signature/expiry/CDNResources/publish/1.mp4'}}
        b={'retrieved_at':'after','properties':{'url':'http://video2.osgame.qq.com/new-signature/new-expiry/CDNResources/publish/1.mp4'}}
        self.assertEqual(sync.semantic(a),sync.semantic(b))
        b['properties']['url']=b['properties']['url'].replace('1.mp4','2.mp4')
        self.assertNotEqual(sync.semantic(a),sync.semantic(b))
    def setUp(self):
        base=Path(__file__).resolve().parents[4]/'raw/test-temp';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def test_schedule_one_catchup_and_backoff(self):
        t=datetime(2026,10,25,8,tzinfo=sync.BJ)
        self.assertTrue(sync.due(self.root,'09:00',t))
        wxq.atomic_json(self.root/sync.STATE,{'window':sync.window('09:00',t)})
        self.assertFalse(sync.due(self.root,'09:00',t))
        self.assertTrue(sync.due(self.root,'09:00',t+timedelta(hours=2)))
        wxq.atomic_json(self.root/sync.STATE,{'retry_at':(t+timedelta(hours=3)).isoformat()})
        self.assertFalse(sync.due(self.root,'09:00',t))
        self.assertTrue(sync.due(self.root,'09:00',t+timedelta(days=1)))
        sync.configure(self.root,{'enabled':False})
        self.assertFalse(sync.due(self.root,'09:00',t+timedelta(days=1)))
        sync.configure(self.root,{'action':'retry'})
        self.assertTrue(sync.due(self.root,'09:00',t))
    def test_manifest_recovery_and_checksum(self):
        stage=self.root/'raw/official-sync/runs/test/file.json';json_store.write_file(stage,{'new':True})
        manifest={'files':[{'path':'entities/players.json','stage':stage.relative_to(self.root).as_posix(),'sha256':json_store.digest({'new':True})}],
            'notes':None,'success':{'state':'success'}}
        wxq.atomic_json(self.root/sync.JOURNAL,manifest)
        with patch.object(json_store,'write_file',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):sync.recover(self.root)
        self.assertTrue((self.root/sync.JOURNAL).exists())
        self.assertNotEqual(sync.status(self.root)['state'],'success')
        sync.recover(self.root)
        self.assertEqual(json_store.read(self.root/'entities/players.json'),{'new':True})
        self.assertEqual(sync.status(self.root)['state'],'success')
        sync.recover(self.root)
    def test_publication_noop_target_only_and_missing_options(self):
        import official
        from test_official_profiles import sample
        b=official.normalize(sample(),'https://official.test/data','today')
        first=sync.publish(self.root,b,self.root/'raw/official-sync/runs/one',apply_notes=True)
        self.assertEqual(first['updated_notes'],1)
        row=json_store.read(self.root/'knowledge/index.meta.json')['notes'][0]
        before=json_store.read(self.root/row['path'])
        second=sync.publish(self.root,b,self.root/'raw/official-sync/runs/two',apply_notes=True)
        self.assertEqual(second['updated_notes'],0)
        self.assertEqual(second['changed_ids'],[])
        self.assertEqual(before,json_store.read(self.root/row['path']))
        broken=__import__('copy').deepcopy(b)
        broken['players']['player:1']['properties']['official_cards'].pop('card:11')
        with self.assertRaisesRegex(ValueError,'保留原数据'):sync.publish(self.root,broken,self.root/'raw/official-sync/runs/broken')
        self.assertEqual(before,json_store.read(self.root/row['path']))
    def test_failed_fetch_keeps_prior_data_and_retries(self):
        wxq.atomic_json(self.root/'entities/players.json',[{'id':'old'}])
        with patch('official.fetch',side_effect=OSError('offline')):
            with self.assertRaises(OSError):sync.run(self.root)
        self.assertEqual(wxq.read_json(self.root/'entities/players.json'),[{'id':'old'}])
        self.assertEqual(sync.status(self.root)['state'],'failed')
        self.assertIsNotNone(sync.status(self.root)['retry_at'])
    def test_edit_defers_old_official_manifest_and_uses_current_revision(self):
        import official
        from test_official_profiles import sample
        sync.publish(self.root,official.normalize(sample(),'https://official.test','today'),self.root/'raw/official-sync/runs/first',apply_notes=True)
        row=json_store.read(self.root/'knowledge/index.meta.json')['notes'][0]
        record=json_store.load_record(self.root,row['id']);old_revision=record['metadata']['revision']
        original=__import__('copy').deepcopy(record['body'])
        record['body']['nodes'][2]['value']='最新官方正文'
        journal=json_store.save(self.root,[record],partial=True,prepare_only=True)
        wxq.atomic_json(self.root/sync.JOURNAL,{'files':[],'notes':journal,'success':{'state':'success'}})
        json_store.edit(self.root,row['id'],{'revision':old_revision,'document':original})
        self.assertEqual(json_store.load_record(self.root,row['id'])['body']['nodes'],original['nodes'])
        self.assertTrue(list((self.root/'raw/official-sync/pending-notes').glob('*.json')))
    def test_image_publication_keeps_concurrent_unrelated_mappings(self):
        import official
        from test_official_profiles import sample
        wxq.atomic_json(self.root/'entities/assets/index.json',{'version':1,'assets':{'concurrent':{'path':'concurrent.img'}},'entities':{'unrelated':{'thumb':'concurrent'}}})
        images={'_manifest':{'assets':{'new':{'path':'new.img'}},'entities':{'player:1':{'thumb':'new'},'unrelated':{'thumb':'stale'}}},'_entity_ids':['player:1']}
        sync.publish(self.root,official.normalize(sample(),'https://official.test','today'),self.root/'raw/official-sync/runs/images',images)
        saved=wxq.read_json(self.root/'entities/assets/index.json')
        self.assertEqual(saved['entities']['unrelated']['thumb'],'concurrent')
        self.assertEqual(saved['entities']['player:1']['thumb'],'new')
        self.assertIn('concurrent',saved['assets'])
    def test_interrupted_manual_run_is_retryable_after_success_today(self):
        t=datetime.now(sync.BJ)
        wxq.atomic_json(self.root/sync.STATE,{'state':'running','window':sync.window('09:00',t)})
        self.assertEqual(sync.status(self.root)['state'],'failed')
        self.assertTrue(sync.due(self.root,'09:00',t))

if __name__=='__main__':unittest.main()
