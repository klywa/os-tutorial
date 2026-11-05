"""Authenticated read-only card APIs and version-pinned images."""
import http.client
import json
import unittest
from unittest.mock import patch
import test_website as fixtures
import json_store as store
import card_publication


class CardHttpTests(unittest.TestCase):
    setUp=fixtures.PublicHttpTests.setUp
    call=fixtures.PublicHttpTests.call
    login=fixtures.PublicHttpTests.login

    def test_snapshot_switch_during_detail_read_always_requests_refresh(self):
        self.login()
        for missing_file in (False,True):
            with self.subTest(missing_file=missing_file):
                version=self.package('旧卡'+str(missing_file));original=store.read;switched=False
                def read(path,default=None):
                    nonlocal switched
                    if not switched and path.name=='cards.json' and path.parent.name==version:
                        switched=True;self.package('新卡'+str(missing_file))
                        if missing_file:raise FileNotFoundError('snapshot removed during read')
                        return []
                    return original(path,default)
                with patch('website_server.store.read',side_effect=read):
                    code,data,_=self.call('/os-tutorial/api/cards/heroes:1?version='+version)
                self.assertEqual(code,409,data)
                self.assertEqual(data['reason'],'cards_version_changed')

    def package(self,name):
        def export(root,target):
            target.mkdir(parents=True,exist_ok=True)
            store.write_file(target/'cards.json',[{'id':'heroes:1','name':name,'sources':[]}])
            (target/'image.img').write_bytes(name.encode())
            store.write_file(target/'images.json',{'entities':{'heroes:1':{'thumb':'asset'}},'assets':{'asset':{'path':'image.img'}}})
        with patch('website_data.export_cards',side_effect=export):
            return card_publication.publish(self.root,self.root/'state')

    def test_roles_guest_conditionals_and_version_pinning(self):
        first=self.package('旧英雄')
        for path in ('cards','cards/status','cards/heroes:1','cards/heroes:1/images/thumb'):
            self.assertEqual(self.call('/os-tutorial/api/'+path)[0],401)
        self.config.write_text(json.dumps({'schema_version':2,'sessionSecret':'s'*48,'accounts':[
            {'username':role,'password':'test','role':role} for role in ('admin','annotator','viewer')]}))
        for role in ('admin','annotator','viewer'):
            code,_,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':role,'password':'test'})
            self.assertEqual(code,200)
            self.cookie=headers['Set-Cookie'].split(';')[0]
            code,rows,headers=self.call('/os-tutorial/api/cards')
            self.assertEqual(code,200)
            self.assertEqual(headers['X-Cards-Version'],first)
            self.assertIn(first,rows[0]['thumb_url'])
            self.assertEqual(self.call('/os-tutorial/api/cards/status')[1]['version'],first)
            self.assertEqual(self.call('/os-tutorial/api/official-sync/run','POST',{})[0],404)
        second=self.package('新英雄')
        self.assertNotEqual(first,second)
        code,data,_=self.call('/os-tutorial/api/cards/heroes:1?version='+first)
        self.assertEqual(code,409);self.assertEqual(data['reason'],'cards_version_changed')
        self.assertEqual(self.call('/os-tutorial/api/cards/heroes:1')[1]['name'],'新英雄')
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        conn.request('GET','/os-tutorial/api/cards/heroes:1/images/thumb?version='+first,headers={'Host':'klywa.xyz','Cookie':self.cookie})
        response=conn.getresponse();self.assertEqual(response.status,409);response.read();conn.close()
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        conn.request('GET','/os-tutorial/api/cards',headers={'Host':'klywa.xyz','If-None-Match':headers['ETag']})
        response=conn.getresponse();self.assertEqual(response.status,401);response.read();conn.close()


if __name__=='__main__':unittest.main()
