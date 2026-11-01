"""Role ceilings, legacy configuration and browser-local debug identities."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'frontend'))
from website_auth import Auth, Unconfigured


class RoleTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'temp').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'temp');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'accounts.json'
        self.value={'schema_version':2,'sessionSecret':'s'*48,'sessionTtlHours':168,'accounts':[
            {'username':'klywa','password':'aa2025','role':'admin'},
            {'username':'test1','password':'aa2025','role':'annotator'}]}
        self.write();self.auth=Auth(self.path,'/os-tutorial')

    def write(self):self.path.write_text(json.dumps(self.value),encoding='utf-8')
    def login(self,name):
        status,cookie=self.auth.login(name,'aa2025','test')
        self.assertEqual(status,200)
        return cookie.split(';')[0]

    def test_admin_switches_down_and_back_without_elevating_annotator(self):
        cookie=self.login('klywa')
        self.assertEqual(self.auth.actor(cookie)['role'],'admin')
        lowered=self.auth.switch_role(cookie,'annotator').split(';')[0]
        self.assertEqual(self.auth.actor(lowered)['account_role'],'admin')
        self.assertEqual(self.auth.actor(lowered)['role'],'annotator')
        restored=self.auth.switch_role(lowered,'admin').split(';')[0]
        self.assertEqual(self.auth.actor(restored)['role'],'admin')
        writer=self.login('test1')
        self.assertEqual(self.auth.actor(writer)['allowed_roles'],['annotator'])
        with self.assertRaises(PermissionError):self.auth.switch_role(writer,'admin')

    def test_config_role_or_password_change_revokes_sessions(self):
        cookie=self.login('klywa')
        self.value['accounts'][0]['role']='annotator';self.write()
        self.assertIsNone(self.auth.actor(cookie))
        cookie=self.login('test1')
        self.value['accounts'][1]['password']='changed';self.write()
        self.assertIsNone(self.auth.actor(cookie))

    def test_legacy_users_are_administrators_and_invalid_role_fails_closed(self):
        self.value.pop('schema_version');self.value['users']=self.value.pop('accounts')[:1]
        self.value['users'][0].pop('role');self.write()
        self.assertEqual(self.auth.actor(self.login('klywa'))['role'],'admin')
        self.value['users'][0]['role']='superuser';self.write()
        with self.assertRaises(Unconfigured):self.auth.config()

    def test_browser_local_switch_does_not_change_another_browser(self):
        from website_auth import LocalAuth
        local=LocalAuth(Path(self.tmp.name)/'local.json')
        self.assertEqual(local.actor(None)['role'],'admin')
        cookie=local.switch_role(None,'annotator').split(';')[0]
        self.assertEqual(local.actor(cookie)['role'],'annotator')
        self.assertEqual(local.actor(None)['role'],'admin')
        self.assertNotIn('Secure',cookie)
        self.assertEqual(local.actor(local.switch_role(cookie,'admin').split(';')[0])['role'],'admin')


if __name__=='__main__':unittest.main()
