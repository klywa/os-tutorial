"""Public HTTP boundaries, signed sessions and offline dataset publishing."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'frontend'), str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import server
import workspace


class PublicHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'knowledge').mkdir()
        (self.root/'knowledge/index.meta.json').write_text('{"notes":[]}', encoding='utf-8')
        self.config = self.root/'admins.json'
        self.config.write_text(json.dumps({'sessionSecret':'s'*48,'sessionTtlHours':168,
            'users':[{'username':'klywa','password':'aa2025'}]}), encoding='utf-8')
        with patch('crawler.Runtime', side_effect=AssertionError('public must not create crawler')):
            self.http = server.create_server(self.root, 0, public=True, base_path='/os-tutorial',
                origin='https://klywa.xyz', auth_config=self.config, state_dir=self.root/'state')
        self.addCleanup(self.http.server_close)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.http.shutdown)
        self.cookie = ''

    def call(self, path, method='GET', data=None, origin='https://klywa.xyz', cookie=None, forwarded=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=10)
        headers = {'Host':'klywa.xyz','Content-Type':'application/json','Origin':origin,
                   'Cookie':self.cookie if cookie is None else cookie}
        if forwarded:headers['X-Forwarded-For']=forwarded
        conn.request(method, path, body=None if data is None else json.dumps(data), headers=headers)
        res = conn.getresponse()
        body = res.read()
        out = (res.status, json.loads(body) if body else {}, dict(res.getheaders()))
        conn.close()
        return out

    def login(self):
        code, data, headers = self.call('/os-tutorial/api/auth/login', 'POST',
                                      {'username':'klywa','password':'aa2025'})
        self.assertEqual(code, 200, data)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        return headers['Set-Cookie']

    def test_guest_can_read_and_cannot_write(self):
        code, data, _ = self.call('/os-tutorial/api/auth/me')
        self.assertEqual((code, data['mode'], data['role']), (200,'public','guest'))
        self.assertEqual(self.call('/os-tutorial/api/notes/catalog')[0], 200)
        self.assertEqual(self.call('/os-tutorial/api/dashboard')[0], 200)
        self.assertEqual(self.call('/os-tutorial/api/notes/n', 'PUT', {})[0], 401)
        self.assertEqual(self.call('/api/notes/catalog')[0], 404)

    def test_login_cookie_tampering_origin_and_logout(self):
        self.assertEqual(self.call('/os-tutorial/api/auth/login','POST',{'username':'klywa','password':'bad'})[0],401)
        cookie = self.login()
        for attribute in ('HttpOnly','Secure','SameSite=Lax','Path=/os-tutorial'):
            self.assertIn(attribute,cookie)
        self.assertEqual(self.call('/os-tutorial/api/auth/me')[1]['role'],'admin')
        self.assertEqual(self.call('/os-tutorial/api/auth/me',cookie=self.cookie+'x')[1]['role'],'guest')
        self.assertEqual(self.call('/os-tutorial/api/notes/n','PUT',{},origin='https://evil.example')[0],403)
        self.assertEqual(self.call('/os-tutorial/api/auth/logout','POST',{})[0],200)

    def test_disabled_routes_stay_disabled_for_admin_all_methods(self):
        self.login()
        for path in ('crawler/activity','crawler/creators/resume','sources','topics/catalog',
                     'official-sync/run','dashboard/usage/refresh','annotations','notes/n/versions'):
            for method in ('GET','POST','PUT','DELETE'):
                with self.subTest(path=path,method=method):
                    self.assertEqual(self.call('/os-tutorial/api/'+path,method,{} if method!='GET' else None)[0],404)

    def test_config_change_revokes_existing_session_and_fail_closed(self):
        self.login()
        self.config.write_text('{}',encoding='utf-8')
        self.assertEqual(self.call('/os-tutorial/api/auth/me')[1]['role'],'guest')
        self.assertEqual(self.call('/os-tutorial/api/auth/login','POST',{'username':'klywa','password':'aa2025'})[0],503)

    def test_login_rate_limit(self):
        codes=[self.call('/os-tutorial/api/auth/login','POST',{'username':'x','password':'x'})[0] for _ in range(12)]
        self.assertIn(429,codes)

    def test_proxy_client_rate_limit_does_not_lock_other_visitors(self):
        for _ in range(10):self.call('/os-tutorial/api/auth/login','POST',{'username':'x','password':'x'},forwarded='198.51.100.10')
        self.assertEqual(self.call('/os-tutorial/api/auth/login','POST',{'username':'klywa','password':'aa2025'},forwarded='203.0.113.20')[0],200)

    def test_admin_save_revision_and_pending_sync_keep_content(self):
        import json_store
        row={'id':'n','type':'other','title':'测试笔记','path':'knowledge/other/测试笔记.json','aliases':[]}
        body={'schema_version':6,'nodes':[{'id':'title','type':'heading','level':1,'title':'测试笔记'}]}
        with workspace.store_lock(self.root):
            json_store.save(self.root,[{'body':body,'metadata':row}],partial=True)
        state={'state':'synced'}
        def saved():state.update(state='pending');return state
        self.http.sync=SimpleNamespace(status=lambda:dict(state),record_save=saved)
        self.login()
        _,note,_=self.call('/os-tutorial/api/notes/n')
        revision=note['revision']
        code,_,_=self.call('/os-tutorial/api/notes/n','PUT',{'revision':'old','document':body})
        self.assertEqual(code,409)
        body['nodes'].append({'id':'detail','type':'entry','key':'说明','show_key':True,'value':'保留人工内容'})
        code,result,_=self.call('/os-tutorial/api/notes/n','PUT',{'revision':revision,'document':body})
        self.assertEqual(code,200,result)
        self.assertIn('保留人工内容',json.dumps(json_store.resolve_note(self.root,'n'),ensure_ascii=False))
        self.assertEqual(self.call('/os-tutorial/api/auth/me')[1]['sync']['state'],'pending')
        self.assertEqual(self.call('/os-tutorial/api/notes/n','PUT',{'revision':result['revision'],'document':body})[0],423)

    def test_reading_does_not_start_background_projection_threads(self):
        with patch('reader_store.schedule_rebuild',side_effect=AssertionError('public read spawned worker')):
            self.assertEqual(self.call('/os-tutorial/api/options')[0],200)

    def test_clean_release_can_start_while_publisher_holds_activation_lock(self):
        from website_sync import sync_lock
        with sync_lock(self.root/'state'):
            http=server.create_server(self.root,0,public=True,state_dir=self.root/'state')
            http.server_close()


class DatasetTests(unittest.TestCase):
    def test_durable_journal_is_recovered_before_validation_and_public_start(self):
        import website_data,json_store
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'knowledge').mkdir()
            (root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
            website_data.export(root)
            record={'body':{'schema_version':6,'nodes':[{'id':'h','type':'heading','level':1,'title':'已保存内容'}]},
                'metadata':{'id':'durable','type':'other','title':'已保存内容','path':'knowledge/other/已保存内容.json','aliases':[]}}
            journal=json_store.save(root,[record],prepare_only=True)
            json_store.write_file(root/json_store.JOURNAL,journal)
            self.assertFalse((root/record['metadata']['path']).exists())
            with self.assertRaises(ValueError):website_data.validate(root)
            http=server.create_server(root,0,public=True,state_dir=root/'state')
            http.server_close()
            self.assertTrue((root/record['metadata']['path']).exists())
            self.assertFalse((root/json_store.JOURNAL).exists())
            website_data.validate(root)

    def test_export_sanitizes_and_validates_hashes_without_runtime_secrets(self):
        import website_data
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'knowledge').mkdir()
            (root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
            (root/'entities').mkdir()
            (root/'entities/heroes.json').write_text(json.dumps([{'id':'hero:1','name':'英雄','category':'heroes',
                'properties':{'type':1},'local_path':'C:/secret','cookies':'SECRET'}]),encoding='utf-8')
            website_data.export(root)
            text=(root/'website-data/entities/heroes.json').read_text('utf-8')
            self.assertNotIn('SECRET',text)
            self.assertNotIn('C:/secret',text)
            website_data.validate(root)
            (root/'website-data/entities/heroes.json').write_text('[]',encoding='utf-8')
            with self.assertRaises(ValueError):website_data.validate(root)

    def test_export_never_overwrites_existing_published_matches(self):
        import website_data
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'knowledge').mkdir()
            (root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
            (root/'website-data').mkdir()
            path=root/'website-data/usage-matches.json'
            path.write_text('{"schema_version":1,"assignments":{}}',encoding='utf-8')
            before=path.read_bytes();website_data.export(root)
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
