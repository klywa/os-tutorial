"""Atomic, independent public card snapshots and daily-worker scheduling."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1]/'.codex/skills/wanxiangqi-knowledge/scripts')]
import card_publication as cards
import json_store


class CardPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root/'state'

    def publish(self, name='英雄'):
        def export(root, target):
            target.mkdir(parents=True, exist_ok=True)
            json_store.write_file(target/'cards.json', [{'id':'hero:1','name':name,'sources':[]}])
            json_store.write_file(target/'images.json', {'entities':{},'assets':{}})
        with patch('website_data.export_cards', side_effect=export):
            return cards.publish(self.root, self.state)

    def test_atomic_versions_survive_failed_publish_and_code_release(self):
        first = self.publish()
        second = self.publish('新英雄')
        self.assertNotEqual(first, second)
        with self.assertRaises(cards.CardVersionChanged):cards.resolve(self.root,self.state,first)
        self.assertEqual([p.name for p in (self.state/'cards/versions').iterdir()],[second])
        with patch('website_data.export_cards', side_effect=ValueError('bad image')):
            with self.assertRaises(ValueError): cards.publish(self.root,self.state)
        self.assertEqual(cards.resolve(self.root/'new-release',self.state)[1],second)

    def test_no_change_reuses_version_and_rejects_unknown_or_unsafe_version(self):
        version = self.publish()
        self.assertEqual(self.publish(),version)
        for value in ('../escape','x'*64,'a'*64):
            with self.assertRaises(KeyError):cards.resolve(self.root,self.state,value)

    def test_initial_bundled_version_is_replaced_by_daily_sync(self):
        folder=self.root/'website-data';folder.mkdir()
        json_store.write_file(folder/'cards.json',[{'id':'hero:1','name':'随附快照','sources':[]}])
        json_store.write_file(folder/'images.json',{'entities':{},'assets':{}})
        _,version=cards.resolve(self.root,self.state)
        self.assertEqual(cards.publish(self.root,self.state,bundled=True),version)
        self.publish('官网新数据')
        with self.assertRaises(cards.CardVersionChanged):cards.resolve(self.root/'next-release',self.state,version)

    def test_status_is_public_safe_and_uses_publication_failure(self):
        self.publish()
        json_store.write_file(self.state/'cards/status.json', {'state':'failed','error':'secret /opt/path','last_success':'2026-11-04T01:00:00Z'})
        result=cards.status(self.root,self.state)
        self.assertEqual(result['state'],'failed')
        self.assertNotIn('/opt',result['error'])
        self.assertTrue(result['version'])

    def test_worker_does_not_touch_formal_notes_and_retries_unpublished_success(self):
        import card_daily
        self.publish()
        with patch.object(card_daily.official_sync,'due',return_value=False), patch.object(card_daily.official_sync,'run') as run:
            with patch.object(card_daily,'publish',return_value='a'*64) as publish:
                result=card_daily.tick(self.state,force=True)
                run.assert_called_once_with(self.state/'cards/workspace','09:00',apply_notes=False)
                publish.assert_called_once()
                self.assertEqual(result['state'],'success')
        with patch.object(card_daily.official_sync,'due',return_value=False), patch.object(card_daily.official_sync,'run') as run:
            self.assertEqual(card_daily.tick(self.state)['state'],'success')
            run.assert_not_called()

    def test_export_rejects_missing_referenced_image(self):
        from website_data import export_cards
        store=__import__('json_store')
        store.write_file(self.root/'entities/assets/index.json',{'entities':{'hero:1':{'thumb':'lost'}},'assets':{}})
        with self.assertRaises(ValueError):export_cards(self.root,self.root/'out')

    def test_status_detects_interrupted_publication(self):
        self.publish()
        json_store.write_file(self.state/'cards/status.json',{'state':'running'})
        self.assertEqual(cards.status(self.root,self.state)['state'],'failed')

    def test_real_worker_pipeline_keeps_notes_separate_and_retains_last_good_on_fetch_failure(self):
        import card_daily,official,wxq
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.codex/skills/wanxiangqi-knowledge/tests'))
        from test_official_profiles import sample
        buckets=official.normalize(sample(),'https://official.test/data','today')
        protected=self.root/'knowledge/other/manual.json'
        json_store.write_file(protected,{'manual':'人工笔记'})
        before=protected.read_bytes()
        with patch.object(card_daily.official_sync,'fetch_bundle',return_value=buckets),patch('card_images.sync_images',return_value={}):
            value=card_daily.tick(self.state,force=True)
        self.assertEqual(value['state'],'success')
        version=value['version']
        folder,_=cards.resolve(self.root,self.state)
        self.assertTrue(json_store.read(folder/'cards.json'))
        self.assertEqual(json_store.read(self.state/'cards/workspace/knowledge/index.meta.json')['notes'],[])
        with patch.object(card_daily.official_sync,'fetch_bundle',side_effect=OSError('offline')):
            with self.assertRaises(OSError):card_daily.tick(self.state,force=True)
        self.assertEqual(cards.resolve(self.root,self.state)[1],version)
        self.assertEqual(cards.status(self.root,self.state)['state'],'failed')
        self.assertEqual(protected.read_bytes(),before)

    def test_concurrent_worker_skips_without_acquiring_note_save_lock(self):
        import card_daily
        from processing_lock import file_lock
        from workspace import Busy
        from website_sync import sync_lock
        with file_lock(self.state/'cards/worker.lock'):
            with self.assertRaises(Busy):card_daily.tick(self.state)
        with sync_lock(self.state),patch.object(card_daily.official_sync,'run'),patch.object(card_daily,'publish',return_value='b'*64):
            self.assertEqual(card_daily.tick(self.state,force=True)['state'],'success')

    def test_failed_upstream_backoff_cannot_be_reported_as_publication_success(self):
        import card_daily
        self.publish()
        old={'state':'failed','last_success':'old-success','error':'upstream failed'}
        json_store.write_file(self.state/'cards/status.json',old)
        json_store.write_file(self.state/'cards/workspace/raw/official-sync/state.json',{'state':'failed','retry_at':'2099-01-01T00:00:00+08:00'})
        with patch.object(card_daily.official_sync,'due',return_value=False),patch.object(card_daily,'publish') as publish:
            result=card_daily.tick(self.state)
            self.assertEqual(result,old)
            publish.assert_not_called()


if __name__=='__main__':unittest.main()
