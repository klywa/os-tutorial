"""Public and loopback roles must share the same note/proposal boundary."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

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

    def acquire(self,nid,target,client='http-test-tab',takeover=False):
        code,data,_=self.call('/os-tutorial/api/edit-locks/acquire','POST',{'note_id':nid,'client_id':client,'resource':target,'takeover':takeover})
        self.assertEqual(code,200,data)
        return data

    def submit_entries(self,nid,changes):
        entries=[]
        for kind,target,node in changes:
            lease=self.acquire(nid,target)
            entries.append({'kind':kind,'lease':{'id':lease['id'],'token':lease['token']},**({'node':node} if node else {})})
        return self.call('/os-tutorial/api/proposals','POST',{'note_id':nid,'client_id':'http-test-tab','request_id':uuid.uuid4().hex,'changes':entries})

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
        self.assertEqual(self.call('/os-tutorial/api/edit-locks?note_id=n&client_id=http-tab-one')[0],401)
        self.assertEqual(self.call('/os-tutorial/api/proposals','POST',{})[0],401)
        self.assertEqual(self.switch('admin')[0],401)

    def test_http_fenced_deltas_takeover_and_multi_tab_isolation(self):
        import json_store
        nodes=[{'id':'t','type':'heading','level':1,'title':'Locks'},
            {'id':'h','type':'heading','level':2,'title':'Chapter'},
            {'id':'a','type':'entry','key':'A','show_key':True,'value':'old'},
            {'id':'b','type':'entry','key':'B','show_key':True,'value':'old'}]
        with fixtures.workspace.store_lock(self.root):
            json_store.save(self.root,[{'body':{'schema_version':6,'nodes':nodes},
                'metadata':{'id':'locked-note','type':'other','title':'Locks','path':'knowledge/other/locks.json'}}],partial=True)
        code,_,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':'test1','password':'aa2025'})
        self.assertEqual(code,200);self.cookie=headers['Set-Cookie'].split(';')[0];author=self.cookie
        lease=self.acquire('locked-note',{'kind':'entry','id':'a'})
        code,_,_=self.call('/os-tutorial/api/edit-locks/acquire','POST',{'note_id':'locked-note','client_id':'other-tab',
            'resource':{'kind':'entry','id':'a'}})
        self.assertEqual(code,423)
        self.acquire('locked-note',{'kind':'entry','id':'b'},client='other-tab')
        old={'note_id':'locked-note','client_id':'http-test-tab','request_id':'request-stale',
            'changes':[{'kind':'update','node':{**nodes[2],'value':'stale'},'lease':lease}]}
        self.assertEqual(self.call('/os-tutorial/api/proposals','POST',{'note_id':'locked-note',
            'revision':'unused','scope_id':'h','nodes':nodes[1:]})[0],400)
        self.login();self.acquire('locked-note',{'kind':'entry','id':'a'},client='admin-tab',takeover=True)
        presence=self.call('/os-tutorial/api/edit-locks?note_id=locked-note&client_id=admin-tab')[1]
        self.assertNotIn('token',json.dumps(presence))
        self.cookie=author
        code,result,_=self.call('/os-tutorial/api/proposals','POST',old)
        self.assertEqual(code,423,result);self.assertEqual(result['reason'],'admin_takeover')
        self.assertEqual(self.call('/os-tutorial/api/notes/locked-note/entries','PUT',old)[0],403)
        self.login()
        lease=self.acquire('locked-note',{'kind':'slot','section_id':'h','left_id':'b'},client='admin-tab')
        insert={'note_id':'locked-note','client_id':'admin-tab','request_id':'admin-save-one','changes':[
            {'kind':'insert','node':{'id':'fresh','type':'entry','key':'C','show_key':True,'value':'once'},
             'lease':{'id':lease['id'],'token':lease['token']}}]}
        state={'state':'synced'}
        self.http.sync=SimpleNamespace(status=lambda **kw:state,enqueue=lambda:state.update(state='pending') or state)
        self.assertEqual(self.call('/os-tutorial/api/notes/locked-note/entries','PUT',insert)[0],200)
        self.assertEqual(self.call('/os-tutorial/api/notes/locked-note/entries','PUT',insert)[0],200)
        self.assertEqual(len(json_store.resolve_note(self.root,'locked-note')['document']['nodes']),5)

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
        code,data,_=self.submit_entries(note['id'],[('update',{'kind':'entry','id':'entry'},changed),('insert',{'kind':'slot','section_id':'chapter','left_id':'entry'},fresh)])
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
        self.http.sync=SimpleNamespace(status=lambda **kwargs:{'state':'synced'},enqueue=lambda:pushed.append(True) or {'state':'pending','phase':'queued'})
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

    def test_approval_returns_while_git_is_blocked_and_proposals_remain_writable(self):
        import json_store
        from site_access import proposal_store
        from website_sync import SyncManager,SyncWorker
        nodes=[{'id':'t','type':'heading','level':1,'title':'异步审核'},
               {'id':'h','type':'heading','level':2,'title':'章节'},
               {'id':'e','type':'entry','key':'名称','show_key':True,'value':'旧正文'}]
        with fixtures.workspace.store_lock(self.root):
            json_store.save(self.root,[{'body':{'schema_version':6,'nodes':nodes},
                'metadata':{'id':'async-note','type':'other','title':'异步审核','path':'knowledge/other/异步审核.json'}}],partial=True)
        service=proposal_store(self.http)
        author={'username':'test1','role':'annotator','account_role':'annotator'}
        record=json_store.load_record(self.root,'async-note')
        item=service.submit(author,{'note_id':'async-note','revision':record['metadata']['revision'],
            'scope_id':'h','nodes':[nodes[1],{**nodes[2],'value':'确认正文'}]})['items'][0]
        manager=SyncManager(self.root,self.root/'state');self.http.sync=manager
        started=threading.Event();release=threading.Event()
        def blocked():
            manager._state('pending',phase='pushing');started.set()
            release.wait(8)
            return manager._state('synced')
        worker=SyncWorker(manager);worker.initialized=True;self.http.sync_worker=worker
        with patch.object(manager,'retry',side_effect=blocked):
            worker.start()
            try:
                self.login()
                path='/os-tutorial/api/proposals/'+item['id']+'/approve'
                code,result,_=self.call(path,'POST',{'revision':1})
                self.assertEqual(code,200,result)
                self.assertEqual(result['status'],'approved')
                self.assertEqual(result['sync']['state'],'pending')
                self.assertTrue(started.wait(3))
                self.assertFalse(release.is_set())
                self.assertEqual(json_store.resolve_note(self.root,'async-note')['document']['nodes'][2]['value'],'确认正文')
                self.assertEqual(self.call(path,'POST',{'revision':1})[0],200)
                self.assertEqual(self.call('/os-tutorial/api/notes/catalog')[0],200)
                self.assertEqual(self.call('/os-tutorial/api/notes/async-note','PUT',
                    {'revision':record['metadata']['revision'],'document':record['body']})[0],423)
                code,_,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':'test1','password':'aa2025'})
                self.cookie=headers['Set-Cookie'].split(';')[0]
                note=json_store.resolve_note(self.root,'async-note')
                code,pending,_=self.submit_entries('async-note',[('update',{'kind':'entry','id':'e'},{**nodes[2],'value':'下一份建议'})])
                self.assertEqual(code,200,pending)
                second=pending['items'][0]
                lease=self.acquire('async-note',{'kind':'entry','id':'e'})
                code,modified,_=self.call('/os-tutorial/api/proposals/'+second['id'],'PUT',
                    {'revision':1,'proposed_node':{**second['proposed_node'],'value':'再次修改建议'},'client_id':'http-test-tab','lease':lease})
                self.assertEqual(code,200,modified)
                self.assertEqual(self.call('/os-tutorial/api/proposals/'+second['id']+'/withdraw','POST',{'revision':2})[0],200)
                self.assertEqual(self.call('/os-tutorial/api/admin/sync/retry','POST',{})[0],403)
            finally:
                release.set();worker.close()

    def test_admin_manual_retry_enqueues_without_running_git(self):
        from website_sync import SyncManager
        self.http.sync=SyncManager(self.root,self.root/'state')
        self.http.sync._state('conflict','needs retry')
        self.login()
        with patch.object(self.http.sync,'retry',side_effect=AssertionError('HTTP invoked slow retry')):
            code,result,_=self.call('/os-tutorial/api/admin/sync/retry','POST',{})
        self.assertEqual(code,202,result)
        self.assertEqual(result['phase'],'queued')


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
