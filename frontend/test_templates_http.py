"""Authenticated public template routes and transactional review boundaries."""
import json
import unittest
from types import SimpleNamespace
import test_website as fixtures
from test_templates_proposals import group

def portable_group():
    return {'name':'开局提醒','event_name':'准备战斗','scope':{'player':None,'lineup':None},
            'expression':'','effective_expression':'','priority':0,'editor_mode':'tree','condition_tree':{'kind':'all','children':[]},
            'utterances':['先稳住。']}


class TemplateHttpTests(unittest.TestCase):
    call=fixtures.PublicHttpTests.call
    login=fixtures.PublicHttpTests.login

    def setUp(self):
        fixtures.PublicHttpTests.setUp(self)
        self.config.write_text(json.dumps({'schema_version':2,'sessionSecret':'s'*48,'accounts':[
            {'username':'klywa','password':'aa2025','role':'admin'},
            {'username':'alice','password':'aa2025','role':'annotator'},
            {'username':'bob','password':'aa2025','role':'annotator'},
            {'username':'reader','password':'aa2025','role':'viewer'}]}))
        self.http.sync=SimpleNamespace(status=lambda **kw:{'state':'synced'},enqueue=lambda **kw:{'state':'pending'})

    def user(self,name):
        code,data,headers=self.call('/os-tutorial/api/auth/login','POST',{'username':name,'password':'aa2025'})
        self.assertEqual(code,200,data);self.cookie=headers['Set-Cookie'].split(';')[0]

    def test_guests_viewers_and_origin(self):
        self.assertEqual(self.call('/os-tutorial/api/templates')[0],401)
        self.user('reader')
        self.assertEqual(self.call('/os-tutorial/api/templates')[0],200)
        self.assertEqual(self.call('/os-tutorial/api/templates/export')[0],200)
        self.assertEqual(self.call('/os-tutorial/api/templates/proposals')[0],403)
        for suffix in ('changes','import/preview','import/commit','warnings/confirm','warnings/seen'):
            self.assertEqual(self.call('/os-tutorial/api/templates/'+suffix,'POST',{})[0],403)
        self.user('klywa')
        self.assertEqual(self.call('/os-tutorial/api/templates/changes','POST',{},origin='https://evil.example')[0],403)

    def test_only_admin_can_toggle_fixed_and_direct_import_cannot_unfix(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        _, state, _=self.call(api)
        code, saved, _=self.call(api+'/changes','POST',{'revision':state['revision'],
            'changes':[{'kind':'group','action':'put','id':'example','value':group()}]})
        self.assertEqual(code,200,saved)
        request={'revision':saved['revision'],'group_id':'example','utterance_id':'line','fixed':True}
        self.user('alice')
        self.assertEqual(self.call(api+'/utterances/fixed','POST',request)[0],403)
        self.user('klywa')
        code, fixed, _=self.call(api+'/utterances/fixed','POST',request)
        self.assertEqual(code,200,fixed)
        self.assertTrue(fixed['groups'][0]['utterances'][0]['fixed'])
        hand_built={'revision':fixed['revision'],'bypass_review':True,'reason':'测试直接导入',
                    'changes':[{'kind':'group','action':'put','id':'example','value':group(text='覆盖固定句')}]}
        self.assertEqual(self.call(api+'/import/commit','POST',hand_built)[0],409)
        self.assertEqual(self.call(api+'/history?latest=1')[1]['items'][0]['action'],'fix_utterance')
        self.assertEqual(self.call(api+'/utterances/fixed','POST',{**request,'revision':fixed['revision'],'fixed':False})[0],200)

    def test_writer_proposal_private_and_approved_formal_export(self):
        from unittest.mock import Mock
        enqueue=Mock(return_value={'state':'pending'})
        self.http.sync.enqueue=enqueue
        self.user('alice')
        code,state,_=self.call('/os-tutorial/api/templates');self.assertEqual(code,200,state)
        data={'revision':state['revision'],'changes':[{'kind':'group','action':'put','id':'example','value':group()}]}
        code,result,_=self.call('/os-tutorial/api/templates/changes','POST',data)
        self.assertEqual(code,200,result);pid=result['proposal']['id']
        self.assertEqual(self.call('/os-tutorial/api/templates/export')[1]['groups'],[])
        self.user('bob');self.assertEqual(self.call('/os-tutorial/api/templates/proposals')[1],[])
        self.assertEqual(self.call('/os-tutorial/api/templates/proposals/'+pid+'/approve','POST',{})[0],403)
        self.assertEqual(self.call('/os-tutorial/api/templates/proposals/'+pid+'/edit','POST',{})[0],403)
        self.user('klywa')
        proposal=self.call('/os-tutorial/api/templates/proposals')[1][0]
        proposal['changes'][0]['value']['utterances'][0]['text']='管理员确认用语。'
        code,edited,_=self.call('/os-tutorial/api/templates/proposals/'+pid+'/edit','POST',
            {'proposal_revision':proposal['proposal_revision'],'changes':proposal['changes']})
        self.assertEqual(code,200,edited)
        self.assertEqual(self.call('/os-tutorial/api/templates/export')[1]['groups'],[])
        enqueue.assert_not_called()
        accept={'proposal_revision':edited['proposal_revision'],'changes':edited['changes']}
        url='/os-tutorial/api/templates/proposals/'+pid+'/approve'
        code,result,_=self.call(url,'POST',accept)
        self.assertEqual(code,200,result)
        self.assertEqual(self.call(url,'POST',accept)[0],200)
        enqueue.assert_called_once()
        exported=self.call('/os-tutorial/api/templates/export')[1]
        self.assertEqual(exported['schema_version'],3)
        self.assertEqual(exported['groups'],[{**portable_group(), 'event_name':'解释为何准备战斗','utterances':['管理员确认用语。']}])
        self.assertEqual(self.call('/os-tutorial/api/templates/changes','POST',data)[0],409)

    def test_recover_approval_then_retry_failed_sync(self):
        import sqlite3
        from unittest.mock import Mock, patch
        from templates_http import proposal_store
        self.user('alice')
        state=self.call('/os-tutorial/api/templates')[1]
        data={'revision':state['revision'],'changes':[{'kind':'group','action':'put','id':'example','value':group()}]}
        item=self.call('/os-tutorial/api/templates/changes','POST',data)[1]['proposal']
        self.user('klywa')
        url='/os-tutorial/api/templates/proposals/'+item['id']+'/approve'
        accept={'proposal_revision':item['proposal_revision']}
        service=proposal_store(self.http)
        enqueue=Mock(side_effect=[OSError('queue unavailable'),{'state':'pending'}])
        self.http.sync.enqueue=enqueue
        with patch.object(service,'_finish_receipt',side_effect=sqlite3.OperationalError('busy')):
            self.assertEqual(self.call(url,'POST',accept)[0],503)
        self.assertTrue(service.receipt.exists())
        self.assertEqual(self.call(url,'POST',accept)[0],503)
        self.assertTrue(service.pending_sync.exists())
        self.assertEqual(self.call(url,'POST',accept)[0],200)
        self.assertFalse(service.pending_sync.exists())
        self.assertEqual(self.call(url,'POST',accept)[0],200)
        self.assertEqual(enqueue.call_count,2)
        self.assertEqual(len(self.call('/os-tutorial/api/templates/export')[1]['groups']),1)

    def test_import_preview_does_not_write_and_commit_rechecks(self):
        self.user('klywa')
        document=self.call('/os-tutorial/api/templates/export')[1];document['groups']=[portable_group()]
        code,preview,_=self.call('/os-tutorial/api/templates/import/preview','POST',{'document':document})
        self.assertEqual(code,200,preview);self.assertFalse(preview['errors'])
        self.assertEqual(self.call('/os-tutorial/api/templates')[1]['groups'],[])
        code,result,_=self.call('/os-tutorial/api/templates/import/commit','POST',preview)
        self.assertEqual(code,200,result)
        self.assertEqual(result['proposal']['status'],'pending')
        self.assertEqual(self.call('/os-tutorial/api/templates')[1]['groups'],[])
        direct={**preview,'bypass_review':True,'source':'fixture','batch_id':'batch-123'}
        url='/os-tutorial/api/templates/import/commit'
        self.assertEqual(self.call(url,'POST',direct)[0],400)
        self.user('alice')
        self.assertEqual(self.call(url,'POST',{**direct,'reason':'测试'})[0],403)
        self.user('klywa')
        code,result,_=self.call(url,'POST',{**direct,'reason':'已独立核对'})
        self.assertEqual(code,200,result)
        gid=preview['changes'][0]['id']
        audit=self.call('/os-tutorial/api/templates/history?group_id='+gid)[1]['items'][0]
        self.assertEqual((audit['source'],audit['reason'],audit['batch_id']),('fixture','已独立核对','batch-123'))
        self.assertEqual(self.call('/os-tutorial/api/templates/export?group_ids='+gid)[1]['groups'],[{**portable_group(), 'event_name':'解释为何准备战斗'}])
        self.assertEqual(self.call('/os-tutorial/api/templates/import/commit','POST',preview)[0],409)

    def test_formal_comments_survive_delete_and_capture_admin_decisions(self):
        prefix='/os-tutorial/api/templates'
        self.user('klywa')
        state=self.call(prefix)[1]
        row=group()
        code,state,_=self.call(prefix+'/changes','POST',{'revision':state['revision'],'changes':[{'kind':'group','action':'put','id':row['id'],'value':row}]})
        self.assertEqual(code,200,state)
        self.user('alice')
        uid=row['utterances'][0]['id']
        target={'group_id':row['id'],'utterance_id':uid,'body':'请核对原文'}
        self.assertEqual(self.call(prefix+'/comments','POST',{**target,'original_text':'错误原文'})[0],409)
        code,thread,_=self.call(prefix+'/comments','POST',target)
        self.assertEqual(code,200,thread)
        path=prefix+'/comments/'+thread['id']
        self.user('bob');self.assertEqual(self.call(path+'/reply','POST',{'body':'已复核'})[0],200)
        self.assertEqual(self.call(path+'/close','POST',{})[0],403)
        self.user('reader');self.assertEqual(self.call(prefix+'/comments')[0],403)
        self.user('klywa');self.assertEqual(self.call(path+'/close','POST',{})[0],200)
        self.assertEqual(self.call(prefix+'/comments')[1]['items'],[])
        self.assertEqual(self.call(path+'/reopen','POST',{})[0],200)
        code,state,_=self.call(prefix+'/changes','POST',{'revision':state['revision'],'changes':[{'kind':'group','action':'delete','id':row['id']}]})
        self.assertEqual(code,200,state)
        remaining=self.call(prefix+'/comments?status=open')[1]['items'][0]
        self.assertEqual(remaining['original_text'],row['utterances'][0]['text'])
        history=self.call(prefix+'/history?group_id='+row['id'])[1]['items']
        self.assertEqual([h['action'] for h in history],['delete','comment_reopen','comment_close','create'])
        self.assertEqual(self.call(prefix+'/history?latest=1')[1]['items'][0]['action'],'delete')


if __name__=='__main__':unittest.main()
