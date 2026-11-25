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
            {'username':'reviewer','password':'aa2025','role':'quality'},
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

    def test_related_copy_retains_fixed_and_ignored_through_direct_and_proposal_saves(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        _,state,_=self.call(api)
        events={event['name']:event['id'] for event in state['events']}
        source=dict(group(),event_id=events['解释为何购买英雄'],syntax_version='0.4',
                    expression='',extra_key='吕布',utterances=[
                        {'id':'line','text':'吕布可补充输出。'},
                        {'id':'second','text':'买下吕布补充战力。','ignored':True}])
        def save(state,value,**details):
            return self.call(api+'/changes','POST',{'revision':state['revision'],'changes':[
                {'kind':'group','action':'put','id':value['id'],'value':value,**details}]})
        code,state,_=save(state,source)
        self.assertEqual(code,200,state)
        state=self.call(api)[1]
        code,error,_=self.call(api+'/utterances/fixed','POST',dict(
            revision=state['revision'],group_id=source['id'],utterance_id='second',fixed=True))
        self.assertEqual(code,409,error)
        self.assertIn('只能固定或忽略',error['error'])
        code,state,_=self.call(api+'/utterances/fixed','POST',dict(
            revision=state['revision'],group_id=source['id'],utterance_id='line',fixed=True))
        self.assertEqual(code,200,state)
        state=self.call(api)[1]
        fixed_source=next(g for g in state['groups'] if g['id']==source['id'])
        newly_ignored=dict(fixed_source,utterances=[dict(fixed_source['utterances'][0],ignored=True),fixed_source['utterances'][1]])
        code,error,_=save(state,newly_ignored)
        self.assertEqual(code,409,error)
        self.assertIn('只能固定或忽略',error['error'])
        def target(gid,name):
            return dict(source,id=gid,name=gid,event_id=events[name],utterances=[
                {'id':gid+'-line','text':'吕布可补充输出。','fixed':True},
                {'id':gid+'-second','text':'买下吕布补充战力。','ignored':True}])
        direct=target('direct','解释为何选择英雄')
        self.assertEqual(save(state,direct)[0],409)
        forged=dict(direct,utterances=[dict(direct['utterances'][0],text='改写固定句。'),direct['utterances'][1]])
        code,error,_=save(state,forged,related_copy_source=source['id'])
        self.assertEqual(code,409,error)
        self.assertIn('话术内容',error['error'])
        code,state,_=save(state,direct,related_copy_source=source['id'])
        self.assertEqual(code,200,state)
        self.assertEqual(next(g for g in state['groups'] if g['id']=='direct')['utterances'],direct['utterances'])
        state=self.call(api)[1]
        self.user('alice')
        proposed=target('proposed','解释为何选择英雄')
        code,data,_=save(state,proposed,related_copy_source=source['id'])
        self.assertEqual(code,200,data)
        proposal=data['proposal']
        self.user('klywa')
        code,data,_=self.call(api+'/proposals/'+proposal['id']+'/approve','POST',{
            'proposal_revision':proposal['proposal_revision'],'change_ids':[0],'group_editor':{}})
        self.assertEqual(code,200,data)
        saved=self.call(api)[1]
        self.assertEqual(next(g for g in saved['groups'] if g['id']=='proposed')['utterances'],proposed['utterances'])

    def test_inline_event_move_keeps_group_ids_conditions_and_fixed_speech(self):
        self.check_inline_event_move(annotator=False)

    def test_inline_event_proposal_requires_approval_for_the_entire_group(self):
        self.check_inline_event_move(annotator=True)

    def check_inline_event_move(self, *, annotator):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        state=self.call(api)[1]
        first,second='auction-first','auction-second'
        events=[{'kind':'event','action':'put','id':gid,'value':{'id':gid,
                 'name':f'解释为何竞拍目标英雄（第{number}次拍卖）','category':'解释类','parameters':[]}}
                for number,gid in enumerate((first,second),1)]
        rows=[dict(group('auction-'+str(level)),event_id=first,syntax_version='0.4',
                   expression=f'我方.等级 >= {level}',extra_key='小乔') for level in (3,4)]
        code,state,_=self.call(api+'/changes','POST',{'revision':state['revision'],'changes':events+[
            {'kind':'group','action':'put','id':row['id'],'value':row} for row in rows]})
        self.assertEqual(code,200,state)
        state=self.call(api)[1]
        code,state,_=self.call(api+'/utterances/fixed','POST',{
            'revision':state['revision'],'group_id':rows[0]['id'],'utterance_id':'line','fixed':True})
        self.assertEqual(code,200,state)
        code,thread,_=self.call(api+'/comments','POST',{
            'group_id':rows[0]['id'],'utterance_id':'line','body':'移动后仍能看到这条批注'})
        self.assertEqual(code,200,thread)
        if annotator:
            self.user('alice')
        code,state,_=self.call(api+'/changes','POST',{'revision':state['revision'],'inline_trigger':True,
            'group_patches':[{'id':row['id'],'fields':{'set':{'event_id':second,
                'name':'解释为何竞拍小乔（第2次拍卖）'},'remove':[]}} for row in rows]})
        self.assertEqual(code,200,state)
        if annotator:
            proposal=state['proposal']
            self.assertTrue(proposal['inline_trigger'])
            self.assertEqual([row['id'] for row in proposal['changes']],[row['id'] for row in rows])
            self.user('klywa')
            self.assertTrue(all(row['event_id']==first for row in self.call(api)[1]['groups']))
            path=api+'/proposals/'+proposal['id']+'/approve'
            approval={'proposal_revision':proposal['proposal_revision']}
            self.assertEqual(self.call(path,'POST',{**approval,'change_ids':[0]})[0],400)
            code,state,_=self.call(path,'POST',approval)
            self.assertEqual(code,200,state)
        actual={row['id']:row for row in self.call(api)[1]['groups']}
        self.assertEqual(set(actual),{row['id'] for row in rows})
        for row in rows:
            self.assertEqual(actual[row['id']]['event_id'],second)
            self.assertEqual(actual[row['id']]['expression'],row['expression'])
        self.assertTrue(actual[rows[0]['id']]['utterances'][0]['fixed'])
        code,comments,_=self.call(api+'/comments?group_id='+rows[0]['id'])
        self.assertEqual(code,200,comments)
        self.assertIn('移动后仍能看到这条批注',json.dumps(comments,ensure_ascii=False))

    def test_formal_rename_merges_speech_and_transfers_utterance_comments(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        state=self.call(api)[1]
        event=next(row['id'] for row in state['events'] if row['name']=='解释为何购买英雄')
        first=dict(group('a','保留固定句。'),event_id=event,syntax_version='0.4',
                   expression='我方.等级 >= 3',extra_key='吕布')
        second=dict(group('b','人工修改过的另一句。'),event_id=event,syntax_version='0.4',
                    expression='(我方.等级>=3)',extra_key='吕布',name='待改名',priority=15)
        code,state,_=self.call(api+'/changes','POST',{'revision':state['revision'],'changes':[
            {'kind':'group','action':'put','id':row['id'],'value':row} for row in (first,second)]})
        self.assertEqual(code,200,state)
        state=self.call(api)[1]
        for gid in ('a','b'):
            code,state,_=self.call(api+'/utterances/fixed','POST',{
                'revision':state['revision'],'group_id':gid,'utterance_id':'line','fixed':True})
            self.assertEqual(code,200,state)
        code,state,_=self.call(api+'/groups/a/review','POST',{'revision':state['revision'],'status':'final_reviewed'})
        self.assertEqual(code,200,state)
        code,thread,_=self.call(api+'/comments','POST',{'group_id':'b','utterance_id':'line','body':'原句批注'})
        self.assertEqual(code,200,thread)
        code,saved,_=self.call(api+'/changes','POST',{'revision':state['revision'],
            'group_patches':[{'id':'b','fields':{'set':{'name':first['name']},'remove':[]}}]})
        self.assertEqual(code,200,saved)
        self.assertEqual(saved['merged_groups'],{'b':'a'})
        survivor,=self.call(api)[1]['groups']
        self.assertEqual(survivor['id'],'a')
        self.assertEqual(survivor['priority'],15)
        self.assertIsNone(survivor['review_status'])
        self.assertNotIn('reviewed_by',survivor)
        original,moved=survivor['utterances']
        self.assertEqual(original,{'id':'line','text':'保留固定句。','fixed':True})
        self.assertEqual((moved['text'],moved['fixed']),('人工修改过的另一句。',True))
        threads=self.call(api+'/comments?group_id=a')[1]['items']
        self.assertEqual([(row['id'],row['utterance_id']) for row in threads],[(thread['id'],moved['id'])])
        history=self.call(api+'/groups/a/revisions')[1]['items']
        self.assertTrue(any((entry.get('value') or {}).get('id')=='b' for entry in history))

    def test_formal_legacy_copy_with_identical_speech_keeps_review(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        state=self.call(api)[1]
        original=group('legacy-original')
        code,state,_=self.call(api+'/changes','POST',{'revision':state['revision'],'changes':[
            {'kind':'group','action':'put','id':original['id'],'value':original}]})
        self.assertEqual(code,200,state)
        code,state,_=self.call(api+'/groups/legacy-original/review','POST',{
            'revision':state['revision'],'status':'final_reviewed'})
        self.assertEqual(code,200,state)
        reviewed=state['groups'][0]
        draft=dict(original,id='copy',expression='',editor_mode='text',
                   utterances=[dict(original['utterances'][0],id='copy-line')])
        code,state,_=self.call(api+'/changes','POST',{'revision':state['revision'],'changes':[
            {'kind':'group','action':'put','id':draft['id'],'value':draft}]})
        self.assertEqual(code,200,state)
        self.assertEqual(state['merged_groups'],{'copy':'legacy-original'})
        self.assertEqual(state['groups'],[reviewed])

    def test_formal_approval_returns_canonical_group_after_copy_merge(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        state=self.call(api)[1]
        event=next(row['id'] for row in state['events'] if row['name']=='解释为何购买英雄')
        other_event=next(row['id'] for row in state['events'] if row['name']=='解释为何选择英雄')
        first=dict(group('first'),event_id=event,syntax_version='0.4',expression='',extra_key='吕布')
        others=[dict(first,id='other-event',event_id=other_event),dict(first,id='other-key',extra_key='赵云'),
                dict(first,id='other-condition',expression='我方.等级 >= 3')]
        def save(revision,rows):
            return self.call(api+'/changes','POST',{'revision':revision,'changes':[
                {'kind':'group','action':'put','id':row['id'],'value':row} for row in rows]})
        code,state,_=save(state['revision'],[first,*others])
        self.assertEqual(code,200,state)
        state=self.call(api)[1]
        self.user('alice')
        draft=dict(first,id='copy',utterances=[{'id':'copy-line','text':'补上另一句。'}])
        code,result,_=save(state['revision'],[draft])
        self.assertEqual(code,200,result)
        item=result['proposal']
        self.assertEqual(item['changes'][0]['id'],'copy')
        self.assertEqual(len(self.call(api)[1]['groups']),4)
        self.user('klywa')
        approval=api+'/proposals/'+item['id']+'/approve'
        request={'proposal_revision':item['proposal_revision'],'change_ids':[0],'group_editor':{},'compact':True}
        code,result,_=self.call(approval,'POST',request)
        self.assertEqual(code,200,result)
        self.assertEqual(result['formal_write']['merged_groups'],{'copy':'first'})
        self.assertEqual([row['id'] for row in result['formal_write']['changes']],['first'])
        survivor=next(row for row in self.call(api)[1]['groups'] if row['id']=='first')
        self.assertEqual([row['text'] for row in survivor['utterances']],['先稳住。','补上另一句。'])
        self.assertEqual(len(self.call(api)[1]['groups']),4)
        self.assertEqual(self.call(approval,'POST',request)[1]['formal_write'],result['formal_write'])
        decisions=self.call(api+'/history?group_id=first')[1]['items']
        self.assertTrue(any(row.get('proposal_id')==item['id'] and row['after']['id']=='first' for row in decisions))

    def test_editor_fixes_changed_text_and_can_edit_it_again(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        _, state, _=self.call(api)
        def save(state,value):
            code,result,_=self.call(api+'/changes','POST',{'revision':state['revision'],
                'changes':[{'kind':'group','action':'put','id':'example','value':value}]})
            self.assertEqual(code,200,result)
            return result
        state=save(state,group())
        self.assertFalse(state['groups'][0]['utterances'][0].get('fixed',False))
        self.user('reviewer')
        for text in ('第一次人工修改','第二次人工修改'):
            value=state['groups'][0]
            value['utterances'][0]['text']=text
            state=save(state,value)
            self.assertEqual(state['groups'][0]['utterances'][0],{'id':'line','text':text,'fixed':True})
        request={'revision':state['revision'],'group_id':'example','utterance_id':'line','fixed':False}
        self.assertEqual(self.call(api+'/utterances/fixed','POST',request)[0],403)
        self.user('klywa')
        code, state, _=self.call(api+'/utterances/fixed','POST',request)
        self.assertEqual(code,200,state)
        state=save(state,state['groups'][0])
        self.assertFalse(state['groups'][0]['utterances'][0].get('fixed',False))
        self.user('alice')
        value=group(text='经审批的修改')
        code,result,_=self.call(api+'/changes','POST',{'revision':state['revision'],
            'changes':[{'kind':'group','action':'put','id':'example','value':value}]})
        self.assertEqual(code,200,result)
        proposal=result['proposal']
        self.assertFalse(self.call(api)[1]['groups'][0]['utterances'][0].get('fixed',False))
        self.user('klywa')
        code,result,_=self.call(api+'/proposals/'+proposal['id']+'/approve','POST',
            {'proposal_revision':proposal['proposal_revision']})
        self.assertEqual(code,200,result)
        self.assertEqual(self.call(api)[1]['groups'][0]['utterances'][0],
                         {'id':'line','text':'经审批的修改','fixed':True})

    def test_new_utterances_are_fixed_when_formally_saved(self):
        api='/os-tutorial/api/templates'
        self.user('klywa')
        def save(value):
            state=self.call(api)[1]
            code,result,_=self.call(api+'/changes','POST',{'revision':state['revision'],
                'changes':[{'kind':'group','action':'put','id':'example','value':value}]})
            self.assertEqual(code,200,result)
            return result
        save(group())
        value=self.call(api)[1]['groups'][0]
        value['utterances'].extend([{'id':'direct','text':'人工新增的第一句。'},
                                    {'id':'ignored','text':'暂不启用。','ignored':True}])
        save(value)
        rows=self.call(api)[1]['groups'][0]['utterances']
        self.assertTrue(rows[1]['fixed'])
        self.assertFalse(rows[2].get('fixed',False))
        self.user('alice')
        value=self.call(api)[1]['groups'][0]
        value['utterances'].append({'id':'proposed','text':'经审批的新增话术。'})
        proposal=save(value)['proposal']
        self.assertEqual(len(self.call(api)[1]['groups'][0]['utterances']),3)
        self.user('klywa')
        code,result,_=self.call(api+'/proposals/'+proposal['id']+'/approve','POST',
            {'proposal_revision':proposal['proposal_revision']})
        self.assertEqual(code,200,result)
        self.assertTrue(self.call(api)[1]['groups'][0]['utterances'][-1]['fixed'])

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
        document['note']='只保存在文件中的随手笔记'
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
        exported=self.call('/os-tutorial/api/templates/export?group_ids='+gid)[1]
        self.assertEqual(exported['groups'],[{**portable_group(), 'event_name':'解释为何准备战斗'}])
        self.assertNotIn('note',exported)
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
