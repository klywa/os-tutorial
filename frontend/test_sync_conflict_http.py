"""HTTP permission, optimistic concurrency and per-note sync boundaries."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_website as fixtures
import json_store as store
import knowledge_conflicts as conflicts
import workspace

class SyncConflictHttpTests(unittest.TestCase):
    setUp=fixtures.PublicHttpTests.setUp
    call=fixtures.PublicHttpTests.call
    login=fixtures.PublicHttpTests.login

    def seed(self):
        def record(nid):
            return {'body':{'schema_version':6,'nodes':[{'id':'h','type':'heading','level':1,'title':'Title '+nid},{'id':'a','type':'entry','key':'说明','show_key':True,'value':'base'}]},'metadata':{'id':nid,'type':'other','title':'Title '+nid,'path':'knowledge/other/'+nid+'.json','aliases':[],'private_secret':'NEVER_EXPOSE'}}
        b=record('n');l=deepcopy(b);r=deepcopy(b)
        l['body']['nodes'][1]['value']='current';r['body']['nodes'][1]['value']='incoming'
        with workspace.store_lock(self.root):
            store.save(self.root,[l,record('other')]);conflicts.write_request(self.root,conflicts.create_request(b,l,r))
        ids=['n']
        self.http.sync=SimpleNamespace(status=lambda **kw:{'state':'pending-deploy','conflict_note_ids':ids,'conflict_count':len(ids)},enqueue=lambda:{'state':'pending','conflict_note_ids':[],'conflict_count':0})

    def test_admin_conflict_routes_hide_metadata_and_check_auth(self):
        self.seed()
        self.assertEqual(self.call('/os-tutorial/api/sync-conflicts')[0],401)
        self.login()
        code,groups,_=self.call('/os-tutorial/api/sync-conflicts')
        self.assertEqual(code,200,groups);self.assertEqual(groups[0]['title'],'Title n')
        self.assertNotIn('NEVER_EXPOSE',json.dumps(groups));self.assertNotIn('metadata',json.dumps(groups))
        self.assertEqual(self.call('/os-tutorial/api/sync-conflicts/n')[0],200)
        # switch_role returns a new cookie, so explicitly adopt it.
        _,_,headers=self.call('/os-tutorial/api/auth/role','POST',{'role':'annotator'})
        self.cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/os-tutorial/api/sync-conflicts')[0],403)
        self.assertEqual(self.call('/os-tutorial/api/sync-conflicts/n/resolve','POST',{})[0],403)

    def test_note_gate_allows_other_notes_and_pending_deploy(self):
        self.seed();self.login()
        body=store.load_record(self.root,'n')['body']
        code,value,_=self.call('/os-tutorial/api/notes/n','PUT',{'revision':'old','document':body})
        self.assertEqual(code,423,value);self.assertEqual(value['reason'],'sync_conflict');self.assertEqual(value['resource'],{'note_id':'n'})
        other=store.load_record(self.root,'other')
        other['body']['nodes'][1]['value']='unaffected save'
        code,value,_=self.call('/os-tutorial/api/notes/other','PUT',{'revision':other['metadata']['revision'],'document':other['body']})
        self.assertEqual(code,200,value)
        self.assertEqual(self.call('/os-tutorial/api/auth/me')[1]['sync']['conflict_note_ids'],['n'])
        self.http.sync.status=lambda **kw:{'state':'conflict'}
        self.assertEqual(self.call('/os-tutorial/api/notes/other','PUT',{})[0],423)

    def test_resolution_origin_staleness_and_durable_result(self):
        self.seed();self.login()
        group=conflicts.get_group(self.root,'n')
        data={'revision':group['revision'],'note_revision':group['note_revision'],'choices':[{'conflict_id':c['id'],'action':'incoming','variant_id':c['variant_id']} for c in group['conflicts']]}
        path='/os-tutorial/api/sync-conflicts/n/resolve'
        self.assertEqual(self.call(path,'POST',data,origin='https://evil.test')[0],403)
        request=store.read(next((self.root/'knowledge-sync/requests').glob('*.json')))
        third=deepcopy(request['right']);third['body']['nodes'][1]['value']='third version'
        with workspace.store_lock(self.root):conflicts.write_request(self.root,conflicts.create_request(request['base'],request['left'],third))
        self.assertEqual(self.call(path,'POST',data)[0],409)
        group=conflicts.get_group(self.root,'n')
        data={'revision':group['revision'],'note_revision':group['note_revision'],'choices':[{'conflict_id':c['id'],'action':'incoming','variant_id':next(v['variant_id'] for v in c['variants'] if v['value']=='incoming')} for c in group['conflicts']]}
        self.assertTrue(conflicts.is_blocked(self.root,'n'))
        code,value,_=self.call(path,'POST',data)
        self.assertEqual(code,200,value);self.assertFalse(conflicts.is_blocked(self.root,'n'))
        self.assertEqual(store.load_record(self.root,'n')['body']['nodes'][1]['value'],'incoming')
        self.assertEqual(value['sync']['state'],'pending')
        self.assertNotIn('klywa',''.join(p.read_text('utf-8') for p in (self.root/'knowledge-sync/resolutions').glob('*/*.json')))
        self.assertEqual(value['sync']['conflict_count'],0)

    def test_conflicted_entries_block_but_proposal_drafts_continue(self):
        from site_access import proposal_store
        self.seed();self.login()
        data={'note_id':'n','client_id':'http-tab','request_id':'save-blocked','changes':[]}
        code,value,_=self.call('/os-tutorial/api/notes/n/entries','PUT',data)
        self.assertEqual(code,423,value);self.assertEqual(value['reason'],'sync_conflict')
        # Drafts keep their normal lease fencing while the canonical note is blocked.
        _,_,headers=self.call('/os-tutorial/api/auth/role','POST',{'role':'annotator'})
        self.cookie=headers['Set-Cookie'].split(';')[0]
        code,lease,_=self.call('/os-tutorial/api/edit-locks/acquire','POST',{'note_id':'n','client_id':'draft-tab','resource':{'kind':'entry','id':'a'}})
        self.assertEqual(code,200,lease)
        proposed={**store.load_record(self.root,'n')['body']['nodes'][1],'value':'draft while blocked'}
        code,value,_=self.call('/os-tutorial/api/proposals','POST',{'note_id':'n','client_id':'draft-tab','request_id':'new-draft','changes':[{'kind':'update','node':proposed,'lease':lease}]})
        self.assertEqual(code,200,value);item=value['items'][0]
        self.login()
        code,value,_=self.call('/os-tutorial/api/proposals/'+item['id']+'/approve','POST',{'revision':item['revision']})
        self.assertEqual(code,423,value);self.assertEqual(value['resource'],{'note_id':'n'})
        self.assertEqual(proposal_store(self.http).get({'username':'klywa','role':'admin'},item['id'])['status'],'pending')

    def test_other_note_entry_save_and_approval_continue_while_pending(self):
        from site_access import proposal_store
        self.seed();self.login()
        code,lease,_=self.call('/os-tutorial/api/edit-locks/acquire','POST',{'note_id':'other','client_id':'admin-tab','resource':{'kind':'entry','id':'a'}})
        self.assertEqual(code,200,lease)
        node={**store.load_record(self.root,'other')['body']['nodes'][1],'value':'independent entry save'}
        data={'note_id':'other','client_id':'admin-tab','request_id':'other-save','changes':[{'kind':'update','node':node,'lease':lease}]}
        code,value,_=self.call('/os-tutorial/api/notes/other/entries','PUT',data)
        self.assertEqual(code,200,value)
        service=proposal_store(self.http);record=store.load_record(self.root,'other')
        author={'username':'author','role':'annotator'}
        item=service.submit(author,{'note_id':'other','revision':record['metadata']['revision'],'scope_id':'a','nodes':[{**node,'value':'approved during pending'}]})['items'][0]
        code,value,_=self.call('/os-tutorial/api/proposals/'+item['id']+'/approve','POST',{'revision':item['revision']})
        self.assertEqual(code,200,value);self.assertEqual(value['status'],'approved')
        self.assertEqual(store.load_record(self.root,'other')['body']['nodes'][1]['value'],'approved during pending')

    def test_local_admin_status_and_resolution_without_network(self):
        import server,threading
        self.seed()
        local=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);local.root=self.root
        self.addCleanup(local.server_close)
        thread=threading.Thread(target=local.serve_forever,daemon=True);thread.start();self.addCleanup(local.shutdown)
        import http.client
        def call(path,method='GET',data=None):
            conn=http.client.HTTPConnection('127.0.0.1',local.server_port,timeout=5)
            conn.request(method,path,body=json.dumps(data) if data is not None else None,headers={'Content-Type':'application/json'})
            r=conn.getresponse();result=(r.status,json.loads(r.read()));conn.close();return result
        code,value=call('/api/auth/me');self.assertEqual(code,200);self.assertEqual(value['sync']['conflict_note_ids'],['n'])
        code,group=call('/api/sync-conflicts/n');self.assertEqual(code,200,group)
        data={'revision':group['revision'],'note_revision':group['note_revision'],'choices':[{'conflict_id':c['id'],'action':'current'} for c in group['conflicts']]}
        with patch('site_access.enqueue_sync',side_effect=AssertionError('local must not publish')):
            code,value=call('/api/sync-conflicts/n/resolve','POST',data)
        self.assertEqual(code,200,value);self.assertFalse(conflicts.is_blocked(self.root,'n'))

if __name__=='__main__':unittest.main()

