"""Authenticated public template routes and transactional review boundaries."""
import json
import unittest
from types import SimpleNamespace
import test_website as fixtures
from test_templates_proposals import group

def portable_group():
    return {'id':'example','name':'开局提醒','event_id':'battle_prepare',
            'scope':{'player_id':None,'lineup_note_id':None},'conditions':[],'utterances':['先稳住。']}


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

    def test_writer_proposal_private_and_approved_formal_export(self):
        self.user('alice')
        code,state,_=self.call('/os-tutorial/api/templates');self.assertEqual(code,200,state)
        data={'revision':state['revision'],'changes':[{'kind':'group','action':'put','id':'example','value':group()}]}
        code,result,_=self.call('/os-tutorial/api/templates/changes','POST',data)
        self.assertEqual(code,200,result);pid=result['proposal']['id']
        self.assertEqual(self.call('/os-tutorial/api/templates/export')[1]['groups'],[])
        self.user('bob');self.assertEqual(self.call('/os-tutorial/api/templates/proposals')[1],[])
        self.assertEqual(self.call('/os-tutorial/api/templates/proposals/'+pid+'/approve','POST',{})[0],403)
        self.user('klywa')
        proposal=self.call('/os-tutorial/api/templates/proposals')[1][0]
        code,result,_=self.call('/os-tutorial/api/templates/proposals/'+pid+'/approve','POST',{'proposal_revision':proposal['proposal_revision']})
        self.assertEqual(code,200,result)
        exported=self.call('/os-tutorial/api/templates/export')[1]
        self.assertEqual(exported['schema_version'],2)
        self.assertEqual(exported['groups'],[portable_group()])
        self.assertEqual(self.call('/os-tutorial/api/templates/changes','POST',data)[0],409)

    def test_import_preview_does_not_write_and_commit_rechecks(self):
        self.user('klywa')
        document=self.call('/os-tutorial/api/templates/export')[1];document['groups']=[portable_group()]
        code,preview,_=self.call('/os-tutorial/api/templates/import/preview','POST',{'document':document})
        self.assertEqual(code,200,preview);self.assertFalse(preview['errors'])
        self.assertEqual(self.call('/os-tutorial/api/templates')[1]['groups'],[])
        code,result,_=self.call('/os-tutorial/api/templates/import/commit','POST',preview)
        self.assertEqual(code,200,result)
        self.assertEqual(self.call('/os-tutorial/api/templates/export?group_ids=example')[1]['groups'],[portable_group()])
        self.assertEqual(self.call('/os-tutorial/api/templates/import/commit','POST',preview)[0],409)


if __name__=='__main__':unittest.main()
