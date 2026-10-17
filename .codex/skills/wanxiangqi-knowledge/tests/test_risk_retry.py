import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timedelta

ROOT=Path(__file__).parents[4]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
from crawler import Store,BJ


class RiskRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.wxq-runtime/test-temp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root)

    def test_job_cooldown_survives_restart_and_does_not_duplicate_creator_job(self):
        c=self.store.save_creator({'name':'test','url':'https://space.bilibili.com/123','date_from':'2026-09-10'})
        job=self.store.check_creator(c['uid']);self.store.update_job(job['id'],state='failed',error='B站请求失败（-352）：风控')
        retry=self.store.defer_risk('job',job['id'],'B站请求失败（-352）：风控')
        self.assertEqual(retry['attempt'],1);self.assertIsNone(Store(self.root).next_pending())
        self.assertEqual(self.store.check_creator(c['uid'])['id'],job['id'])
        with patch('crawler.now',return_value=retry['next_retry_at']):self.assertEqual(self.store.next_pending()['id'],job['id'])
        self.store.update_job(job['id'],state='failed',error='-352')
        retry2=self.store.defer_risk('job',job['id'],'-352')
        self.assertEqual(retry2['attempt'],2)
        self.assertGreater(datetime.fromisoformat(retry2['next_retry_at']),datetime.fromisoformat(retry['next_retry_at']))
        self.store.delete_creator('123');self.assertIsNone(self.store.next_pending())

    def test_video_retry_invalidates_late_worker_and_preserves_stopped_tasks(self):
        job=self.store.new_job({'keywords':['test']});bv='BV1234567890'
        self.store.discover(job['id'],{'bvid':bv},'test',True);task=self.store.claim()
        self.store.finish_task(bv,'failed','HTTP Error 412',generation=task['generation'])
        retry=self.store.defer_risk('task',bv,'HTTP Error 412')
        self.store.finish_task(bv,'failed','late callback',generation=task['generation'])
        self.assertEqual(self.store.tasks()[0]['state'],'queued');self.assertIsNone(self.store.claim())
        with patch('crawler.now',return_value=retry['next_retry_at']):task2=self.store.claim()
        self.assertIsNotNone(task2);self.store.finish_task(bv,'succeeded',generation=task2['generation'])
        self.assertIsNone(self.store.risk_retry('task',bv))
        self.store.control_task(bv,'delete');self.assertIsNone(self.store.defer_risk('task',bv,'-352'))

    def test_login_errors_do_not_loop_and_stopped_batches_are_not_revived(self):
        j=self.store.new_job({'keywords':['test']});self.store.update_job(j['id'],state='failed')
        self.assertIsNone(self.store.defer_risk('job',j['id'],'B站请求失败（-101）：需要登录'))
        self.store.stop(j['id']);self.assertIsNone(self.store.defer_risk('job',j['id'],'-352'))

    def test_disabling_listener_cancels_scheduled_check(self):
        c=self.store.save_creator({'name':'test','url':'https://space.bilibili.com/123','date_from':'2026-09-10'})
        j=self.store.check_creator('123');self.store.update_job(j['id'],state='failed')
        retry=self.store.defer_risk('job',j['id'],'-352');self.store.save_creator({**c,'enabled':False})
        with patch('crawler.now',return_value=retry['next_retry_at']):self.assertIsNone(self.store.next_pending())

    def test_session_refresh_preserves_login_and_uses_site_issued_anonymous_cookies(self):
        from bilibili import Bilibili
        from unittest.mock import Mock
        adapter=object.__new__(Bilibili);adapter.ie=Mock();adapter.ie._get_cookies.return_value={'SESSDATA':'existing','buvid3':'existing-device'}
        adapter.request=Mock(return_value={'b_3':'server-device','b_4':'server-device4'})
        adapter.refresh_session()
        self.assertEqual(adapter.ie._wbi_key_cache,{})
        adapter.ie._set_cookie.assert_called_once_with('.bilibili.com','buvid4','server-device4')

    def test_scan_recovers_after_cooldown_with_fresh_session(self):
        from crawler import Runtime
        from bilibili import BilibiliError
        runtime=Runtime(self.root);self.addCleanup(runtime.close)
        self.store.save_creator({'name':'test','url':'https://space.bilibili.com/123','date_from':'2026-09-10'})
        job=self.store.check_creator('123')
        with patch('crawler.Bilibili') as adapter:
            adapter.return_value.creator_page.side_effect=BilibiliError(-352,'风控')
            runtime.scan(job)
        runtime.store.adopt_risk_failures();retry=self.store.risk_retry('job',job['id'])
        self.assertIsNotNone(retry);self.assertFalse(self.store.creators()[0].get('last_success'))
        with patch('crawler.now',return_value=retry['next_retry_at']),patch('crawler.Bilibili') as adapter:
            adapter.return_value.creator_page.return_value=([],False)
            runtime.scan(self.store.job(job['id']))
            adapter.assert_called_once_with('',refresh=True)
        self.assertEqual(self.store.job(job['id'])['state'],'scanned')
        self.assertIsNone(self.store.risk_retry('job',job['id']))
        self.assertTrue(self.store.creators()[0]['last_success'])
