"""Public and loopback roles must share the same note/proposal boundary."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import test_website as fixtures
import server


class PublicRoleHttpTests(fixtures.PublicHttpTests):
    def setUp(self):
        super().setUp()
        self.config.write_text(json.dumps({'schema_version':2,'sessionSecret':'s'*48,'sessionTtlHours':168,
            'accounts':[{'username':'klywa','password':'aa2025','role':'admin'},
                        {'username':'test1','password':'aa2025','role':'annotator'}]}),encoding='utf-8')

    def switch(self,role):
        code,data,headers=self.call('/os-tutorial/api/auth/role','POST',{'role':role})
        if code==200:self.cookie=headers['Set-Cookie'].split(';')[0]
        return code,data

    def test_effective_role_guards_formal_writes_and_restores_admin(self):
        self.login()
        code,data=self.switch('annotator')
        self.assertEqual(code,200,data)
        self.assertEqual((data['account_role'],data['role']),('admin','annotator'))
        self.assertEqual(self.call('/os-tutorial/api/notes/n','PUT',{})[0],403)
        self.assertEqual(self.call('/os-tutorial/api/notes','POST',{})[0],403)
        self.assertEqual(self.call('/os-tutorial/api/dashboard/usage/matches')[0],403)
        self.assertEqual(self.switch('admin')[0],200)

    def test_true_annotator_cannot_elevate_or_read_admin_sync(self):
        code,_,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':'test1','password':'aa2025'})
        self.assertEqual(code,200)
        self.cookie=headers['Set-Cookie'].split(';')[0]
        data=self.call('/os-tutorial/api/auth/me')[1]
        self.assertEqual(data['role'],'annotator')
        self.assertEqual(data['allowed_roles'],['annotator'])
        self.assertEqual(self.switch('admin')[0],403)
        self.assertEqual(self.call('/os-tutorial/api/admin/sync')[0],403)
        self.assertEqual(self.call('/os-tutorial/api/proposals')[0],200)

    def test_guests_cannot_access_private_proposals_or_switch_role(self):
        self.assertEqual(self.call('/os-tutorial/api/proposals')[0],401)
        self.assertEqual(self.call('/os-tutorial/api/proposals','POST',{})[0],401)
        self.assertEqual(self.switch('admin')[0],401)

    def test_annotator_submits_private_items_and_admin_partially_approves(self):
        import json_store
        body={'schema_version':6,'nodes':[{'id':'title','type':'heading','level':1,'title':'审核样例'},
            {'id':'chapter','type':'heading','level':2,'title':'运营'},
            {'id':'entry','type':'entry','key':'策略','show_key':True,'value':'原有内容'}]}
        record={'body':body,'metadata':{'id':'review-note','type':'other','title':'审核样例',
            'path':'knowledge/other/审核样例.json','aliases':[]}}
        with fixtures.workspace.store_lock(self.root):json_store.save(self.root,[record],partial=True)
        note=json_store.resolve_note(self.root,'review-note')
        self.config.write_text(json.dumps({'schema_version':2,'sessionSecret':'s'*48,'accounts':[
            {'username':'klywa','password':'aa2025','role':'admin'},
            {'username':'test1','password':'aa2025','role':'annotator'},
            {'username':'test2','password':'aa2025','role':'annotator'}]}),encoding='utf-8')
        code,_,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':'test1','password':'aa2025'})
        self.assertEqual(code,200);self.cookie=headers['Set-Cookie'].split(';')[0]
        changed={**body['nodes'][2],'value':'编写员建议'}
        fresh={'id':'fresh','type':'entry','key':'补充','show_key':True,'value':'尚未确认'}
        code,data,_=self.call('/os-tutorial/api/proposals','POST',{'note_id':note['id'],
            'revision':note['revision'],'scope_id':'chapter','nodes':[body['nodes'][1],changed,fresh]})
        self.assertEqual(code,200,data);self.assertEqual(len(data['items']),2)
        edited=next(i for i in data['items'] if i['kind']=='update')
        inserted=next(i for i in data['items'] if i['kind']=='insert')
        self.assertEqual(json_store.resolve_note(self.root,note['id'])['revision'],note['revision'])
        self.assertEqual(self.call('/os-tutorial/api/proposals/'+edited['id']+'/approve','POST',{'revision':1})[0],403)
        code,_,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':'test2','password':'aa2025'})
        self.assertEqual(code,200);self.cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/os-tutorial/api/proposals')[1]['items'],[])
        self.assertEqual(self.call('/os-tutorial/api/proposals/'+edited['id'],'PUT',{'revision':1,'proposed_node':changed})[0],403)
        self.login()
        pushed=[]
        self.http.sync=SimpleNamespace(status=lambda:{'state':'synced'},record_save=lambda:pushed.append(True))
        path='/os-tutorial/api/proposals/'+edited['id']+'/approve'
        code,approved,_=self.call(path,'POST',{'revision':1})
        self.assertEqual(code,200,approved);self.assertEqual(approved['status'],'approved')
        self.assertEqual(len(pushed),1)
        self.assertEqual(self.call(path,'POST',{'revision':1})[0],200)
        self.assertEqual(len(pushed),1)
        current=json_store.resolve_note(self.root,note['id'])['document']['nodes']
        self.assertEqual(current[2]['value'],'编写员建议');self.assertEqual(len(current),3)
        code,rejected,_=self.call('/os-tutorial/api/proposals/'+inserted['id']+'/reject','POST',{'revision':1})
        self.assertEqual((code,rejected['status']),(200,'rejected'))
        self.assertEqual(len(json_store.resolve_note(self.root,note['id'])['document']['nodes']),3)


class LocalRoleHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'temp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'knowledge').mkdir()
        (self.root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
        self.http=server.create_server(self.root,0,start_worker=False)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)

    def call(self,path,method='GET',data=None,cookie=''):
        origin=f'http://127.0.0.1:{self.http.server_port}'
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=10)
        conn.request(method,path,None if data is None else json.dumps(data),{'Content-Type':'application/json','Origin':origin,'Cookie':cookie})
        res=conn.getresponse();body=res.read();out=(res.status,json.loads(body),dict(res.getheaders()));conn.close();return out

    def test_debug_role_is_browser_scoped_and_never_grants_formal_writer(self):
        self.assertEqual(self.call('/api/auth/me')[1]['role'],'admin')
        code,data,headers=self.call('/api/auth/role','POST',{'role':'annotator'})
        self.assertEqual(code,200,data);cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/api/auth/me',cookie=cookie)[1]['role'],'annotator')
        self.assertEqual(self.call('/api/notes/catalog',cookie=cookie)[0],200)
        self.assertEqual(self.call('/api/notes/search?q=sample',cookie=cookie)[0],200)
        self.assertEqual(self.call('/api/notes/n','PUT',{},cookie)[0],403)
        self.assertEqual(self.call('/api/auth/me')[1]['role'],'admin')
        self.assertEqual(self.call('/api/auth/role','POST',{'role':'admin'},cookie)[0],200)

    def test_local_sync_identifies_exact_workspace_and_stops_only_local_admin(self):
        code,data,_=self.call('/api/local-service/status')
        self.assertEqual(code,200,data)
        self.assertEqual(Path(data['root']).resolve(),self.root.resolve())
        self.assertEqual((data['mode'],data['port']),('local',self.http.server_port))
        _,_,headers=self.call('/api/auth/role','POST',{'role':'annotator'})
        cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/api/local-service/stop','POST',{},cookie)[0],403)
        self.assertEqual(self.call('/api/local-service/stop','POST',{})[0],202)


if __name__=='__main__':unittest.main()
