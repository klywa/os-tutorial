from copy import deepcopy
from unittest.mock import patch

import test_proposals as fixture
from edit_locks import EditLocks
from note_import import request
from workspace import Conflict


class NoteImportTests(fixture.unittest.TestCase):
    setUp = fixture.ProposalTests.setUp
    note = fixture.ProposalTests.note
    action = fixture.ProposalTests.action

    def send(self, body, actor=fixture.AUTHOR, request_id='note-import-request'):
        self.store.edit_locks = EditLocks(self.store)
        payload = {'note_id':'n','client_id':'browser-test-client','request_id':request_id,'document':body}
        return payload, request(self.store,actor,'preview',payload)

    def test_paragraphs_use_normal_approval_and_keep_insert_order(self):
        before = self.note()
        updated = deepcopy(before['body'])
        updated['nodes'] = [*self.nodes[:2],fixture.entry('a','new'),fixture.entry('d','first'),
                            fixture.entry('e','second'),*self.nodes[4:]]
        payload, preview = self.send(updated,fixture.ADMIN)
        self.assertEqual([r['kind'] for r in preview['items']],['update','insert','insert','delete'])
        submit = {**payload,'revision':preview['revision']}
        result = request(self.store,fixture.ADMIN,'submit',submit)
        self.assertEqual(self.note(),before)
        self.assertEqual(request(self.store,fixture.ADMIN,'submit',submit),result)
        edit,first,second,delete = (self.store.get(fixture.ADMIN,i) for i in result['ids'])
        self.assertTrue(all(i['status']=='pending' for i in (edit,first,second,delete)))
        self.action(delete)
        self.action(second)
        self.action(first)
        self.action(edit,'reject')
        self.assertEqual([n['value'] for n in self.note()['body']['nodes'] if n['type']=='entry'],
                         ['old','first','second','old'])
        self.assertEqual(request(self.store,fixture.ADMIN,'submit',submit),result)

    @patch('json_store.check_evidence')
    def test_evidence_only_existing_paragraph_and_new_paragraph(self, check):
        before = self.note()
        source = {'source':'BV1cZpA66E98:p1','start':10,'end':20}
        body = deepcopy(before['body'])
        body['nodes'].insert(3,fixture.entry('new','有据的新段落'))
        pack = {'notes':[{'body':body,'metadata':{'id':'n','claim_annotations':[
            {'id':'upload-a','text_ref':key,'inference':True,'evidence':[source]} for key in ('a','new')]}}]}
        payload, preview = self.send(pack)
        self.assertEqual(len(preview['items']),2)
        self.assertEqual(preview['items'][0]['base_node'],preview['items'][0]['proposed_node'])
        check.side_effect = ValueError('来源未登记')
        with self.assertRaisesRegex(ValueError,'来源未登记'):
            request(self.store,fixture.AUTHOR,'preview',payload)
        check.side_effect = None
        result = request(self.store,fixture.AUTHOR,'submit',{**payload,'revision':preview['revision']})
        self.assertEqual(self.note(),before)
        for pid in result['ids']:
            self.action(self.store.get(fixture.ADMIN,pid))
        claims = self.note()['metadata']['claim_annotations']
        self.assertEqual(len(claims),2)
        self.assertTrue(all(c['inference'] and c['evidence']==[source] for c in claims))

    def test_invalid_scope_no_change_and_stale_preview(self):
        body = deepcopy(self.note()['body'])
        payload, preview = self.send(body)
        self.assertFalse(preview['items'])
        with self.assertRaisesRegex(ValueError,'另一篇'):
            request(self.store,fixture.AUTHOR,'preview',{**payload,'document':{'body':body,'metadata':{'id':'other'}}})
        body['nodes'][1]['title']='另一章'
        with self.assertRaisesRegex(ValueError,'标题'):
            request(self.store,fixture.AUTHOR,'preview',payload)
        body['nodes'][1]['title']='Chapter'
        body['nodes'][2:4]=reversed(body['nodes'][2:4])
        with self.assertRaisesRegex(ValueError,'顺序'):
            request(self.store,fixture.AUTHOR,'preview',payload)
        body['nodes'][2:4]=reversed(body['nodes'][2:4])
        body['nodes'][2]['value']='旧底稿上的修改'
        preview=request(self.store,fixture.AUTHOR,'preview',payload)
        current=self.note()
        current['body']['nodes'][2]['value']='正式库上的并发修改'
        fixture.json_store.edit(self.root,'n',{'revision':current['metadata']['revision'],'document':current['body']},public=True)
        with self.assertRaises(Conflict):
            request(self.store,fixture.AUTHOR,'submit',{**payload,'revision':preview['revision']})

    def test_author_cannot_confirm_and_admin_can_save_a_merged_draft(self):
        body = deepcopy(self.note()['body'])
        body['nodes'][2]['value']='上传版'
        payload, preview = self.send(body)
        result = request(self.store,fixture.AUTHOR,'submit',{**payload,'revision':preview['revision']})
        item = self.store.get(fixture.ADMIN,result['ids'][0])
        with self.assertRaises(fixture.ProposalForbidden):
            self.action(item,actor=fixture.AUTHOR)
        locks = self.store.edit_locks
        lease = locks.acquire(fixture.ADMIN,{'note_id':'n','client_id':'review-window',
                                            'resource':{'kind':'entry','id':'a'}})
        outcome = self.store.action(fixture.ADMIN,item['id'],'approve',{
            'revision':item['revision'],'client_id':'review-window',
            'lease':{k:lease[k] for k in ('id','token')},
            'proposed_node':{**item['proposed_node'],'value':'管理员合并稿'},
        })
        self.assertEqual(outcome['status'],'approved')
        self.assertEqual(self.note()['body']['nodes'][2]['value'],'管理员合并稿')
        self.assertEqual(self.store.audit_history(fixture.ADMIN,proposal_id=item['id'])['items'][0]['kind'],'draft_edit')
