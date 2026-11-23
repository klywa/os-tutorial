"""Template proposals exercise private review against the real formal store."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import templates_store as library
from templates_proposals import TemplateProposals
from workspace import Conflict

ADMIN={'username':'admin','role':'admin'}
ALICE={'username':'alice','role':'annotator'}
BOB={'username':'bob','role':'annotator'}


def group(gid='example',text='先稳住。'):
    return {'id':gid,'name':'开局提醒','event_id':'os_4ef8f267133d9810',
        'scope':{'player_id':None,'lineup_note_id':None},'conditions':[],
        'utterances':[{'id':'line','text':text}],'related_entities':[]}


class TemplateProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'temp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.proposals=TemplateProposals(self.root,self.root/'raw/private.sqlite3')

    def submit(self,value=None,actor=ALICE):
        value=value or group()
        return self.proposals.submit(actor,{'revision':library.snapshot(self.root)['revision'],
            'changes':[{'kind':'group','action':'put','id':value['id'],'value':value}]})

    def action(self,actor,pid,action,data):
        item=next(p for p in self.proposals.list(ADMIN) if p['id']==pid)
        return self.proposals.action(actor,pid,action,{'proposal_revision':item['proposal_revision'],**data})

    def test_comment_edits_preserve_versions_authorship_and_direct_counts(self):
        import template_feedback as feedback
        gid = group()['id']
        library.apply(self.root, library.snapshot(self.root)['revision'],
                      [{'kind':'group','action':'put','id':gid,'value':group()}])
        create = lambda actor, **data: feedback.annotate(self.proposals, actor, {'group_id':gid,**data})
        thread = create(ALICE, body='原始留言')
        line = create(BOB, utterance_id='line', body='话术讨论')
        def post(actor, action, **data):
            return feedback.annotate(self.proposals, actor, data, thread['id'], action)
        post(BOB, 'reply', body='补充')
        edit = dict(message_index=0, message_revision=0, body='修订')
        with self.assertRaises(PermissionError): post(ADMIN, 'edit', **edit)
        current = post(ALICE, 'edit', **edit)
        self.assertEqual(current['messages'][0]['body'], '修订')
        self.assertEqual(current['messages'][0]['revisions'][0]['body'], '原始留言')
        with self.assertRaises(Conflict): post(ALICE, 'edit', **{**edit, 'body':'过期草稿'})
        post(BOB, 'edit', message_index=1, message_revision=0, body='修订后的回复')
        post(ADMIN, 'close')
        self.assertCountEqual(feedback.comment_counts(self.proposals), [
            {'group_id':gid,'utterance_id':None,'count':1},
            {'group_id':gid,'utterance_id':line['utterance_id'],'count':1},
        ])

    def test_preexisting_proposal_cannot_change_a_later_fixed_utterance(self):
        saved=library.apply(self.root,library.snapshot(self.root)['revision'],
            [{'kind':'group','action':'put','id':'example','value':group()}])
        candidate=self.submit(group(text='提案覆盖'))
        fixed=library.set_utterance_fixed(self.root,saved['revision'],'example','line',True,'admin')
        with self.assertRaises(Conflict):
            self.action(ADMIN,candidate['id'],'approve',{'changes':candidate['changes']})
        with self.assertRaises(Conflict):
            self.submit(group(text='新提案覆盖'))
        self.assertEqual(library.snapshot(self.root)['groups'],fixed['groups'])

    def test_private_submit_and_admin_approval(self):
        item=self.submit()
        self.assertEqual(library.snapshot(self.root)['groups'],[])
        self.assertEqual(self.proposals.list(BOB),[])
        self.assertEqual(len(self.proposals.list(ADMIN)),1)
        with self.assertRaises(PermissionError):self.action(BOB,item['id'],'approve',{})
        result=self.action(ADMIN,item['id'],'approve',{})
        self.assertEqual(result['status'],'approved')
        self.assertEqual(library.snapshot(self.root)['groups'],[group()])
        self.assertEqual(self.action(ADMIN,item['id'],'approve',{})['status'],'approved')

    def test_reject_selected_group_keeps_other_changes_pending(self):
        groups = [group('first'), group('second')]
        groups[1]['name'] = '第二条提醒'
        proposal = self.proposals.submit(ALICE, {
            'revision': library.snapshot(self.root)['revision'],
            'changes': [{'kind':'group','action':'put','id':row['id'],'value':row} for row in groups],
        })
        request = {'proposal_revision':proposal['proposal_revision'],'change_ids':[0]}
        with self.assertRaises(PermissionError):
            self.proposals.action(ALICE,proposal['id'],'reject',request)
        result = self.proposals.action(ADMIN,proposal['id'],'reject',request)
        self.assertEqual(result['status'],'pending')
        self.assertEqual([row['id'] for row in result['changes']],['second'])
        self.assertEqual([row['id'] for row in result['reviews'][-1]['submitted']],['first'])
        self.assertEqual(self.proposals.action(ADMIN,proposal['id'],'reject',request),result)
        accepted = self.action(ADMIN,proposal['id'],'approve',{})
        self.assertEqual(accepted['status'],'partially_approved')
        self.assertEqual([row['id'] for row in library.snapshot(self.root)['groups']],['second'])

    def test_card_previews_only_return_visible_pending_group_changes(self):
        first=self.submit()
        second=self.submit(group('another'),BOB)
        self.assertEqual([row['proposal_id'] for row in self.proposals.card_previews(ALICE)],[first['id']])
        self.assertCountEqual([row['proposal_id'] for row in self.proposals.card_previews(ADMIN)],[first['id'],second['id']])
        row=self.proposals.card_previews(BOB)[0]
        self.assertIsNone(row['base'])
        self.assertEqual(row['change'],second['changes'][0])
        self.assertNotIn('submission',row)
        self.action(ALICE,first['id'],'withdraw',{})
        self.assertEqual(self.proposals.card_previews(ALICE),[])
        with self.assertRaises(PermissionError):self.proposals.card_previews({'role':'viewer','username':'alice'})

    def test_card_edit_and_accept_completes_only_that_group_and_retries(self):
        def put(value):return {'kind':'group','action':'put','id':value['id'],'value':value}
        suggestions=[put(group()),put(group('another'))]
        item=self.proposals.submit(ALICE,{'revision':library.snapshot(self.root)['revision'],'changes':suggestions})
        preview=next(row for row in self.proposals.card_previews(ALICE) if row['change']['id']=='example')
        self.assertEqual((preview.get('change_index'),preview.get('proposal_revision')),(0,item['proposal_revision']))
        revised=put(group(text='管理员定稿。'))
        request={'proposal_revision':item['proposal_revision'],'change_ids':[0],'changes':[revised],'complete_group':True}
        with self.assertRaises(PermissionError):self.proposals.action(ALICE,item['id'],'approve',request)
        saved=self.proposals.action(ADMIN,item['id'],'approve',request)
        self.assertEqual(saved['status'],'pending')
        self.assertEqual(saved['changes'],suggestions[1:])
        self.assertEqual(saved['reviews'][-1]['submitted'],suggestions[:1])
        self.assertEqual(saved['reviews'][-1]['changes'],[revised])
        self.assertEqual(library.snapshot(self.root)['groups'],[revised['value']])
        self.assertEqual(self.proposals.action(ADMIN,item['id'],'approve',request),saved)

    def test_card_editor_changes_delete_into_draft_without_writing_formal_group(self):
        put=lambda value:{'kind':'group','action':'put','id':value['id'],'value':value}
        base=group()
        current=library.apply(self.root,library.snapshot(self.root)['revision'],[put(base)])
        item=self.proposals.submit(ALICE,{'revision':current['revision'],'changes':[{'kind':'group','action':'delete','id':base['id']}]})
        edited=group(text='新的说法。')
        saved=self.action(ALICE,item['id'],'edit',{'change_ids':[0],'group_editor':{'group':edited}})
        self.assertEqual(saved['changes'],[put(edited)])
        self.assertEqual(saved['submission']['changes'][0]['action'],'delete')
        self.assertEqual(library.snapshot(self.root)['groups'],[base])

    def test_card_editor_forks_action_and_publishes_only_required_parameters(self):
        def put(value,kind='group'):return {'kind':kind,'action':'put','id':value['id'],'value':value}
        event={'id':'custom-action','name':'测试动作参数','category':'测试','parameters':[]}
        base={**group(),'event_id':event['id'],'expression':'','editor_mode':'text'}
        current=library.apply(self.root,library.snapshot(self.root)['revision'],[put(event,'event'),put(base)])
        item=self.proposals.submit(ALICE,{'revision':current['revision'],'changes':[put({**base,'name':'编辑稿'})]})
        parameter={'id':'parameter-code','key':'arg1','type':'text','name':'动作参数'}
        extra={'id':'parameter-unused','key':'arg2','type':'text','name':'额外参数'}
        new_event={**event,'parameters':[parameter,extra]}
        draft={**base,'expression':'arg1 is "李白"'}
        saved=self.action(ALICE,item['id'],'edit',{'change_ids':[0],'group_editor':{'group':draft,'event':new_event}})
        staged=saved['changes'][0]
        self.assertNotEqual(staged['id'],base['id'])
        self.assertEqual(library.snapshot(self.root)['groups'],[base])
        preview=self.action(ADMIN,item['id'],'approve',{'change_ids':[0],'group_editor':{'preview':True}})
        self.assertEqual(preview['parameters'],['动作参数'])
        with self.assertRaises(Conflict):self.action(ADMIN,item['id'],'approve',{'change_ids':[0],'group_editor':{}})
        accepted=self.action(ADMIN,item['id'],'approve',{'change_ids':[0],'group_editor':{'dependency_token':preview['dependency_token']}})
        self.assertEqual([row['kind'] for row in accepted['changes']],['event'])
        after=library.snapshot(self.root)
        self.assertEqual(next(row for row in after['events'] if row['id']==event['id'])['parameters'],[parameter])
        self.assertIn(base,after['groups'])
        self.assertIn(staged['id'],[row['id'] for row in after['groups']])

    def test_card_review_merges_independent_conditions_and_conflicts_on_the_same_condition(self):
        put=lambda value:{'kind':'group','action':'put','id':value['id'],'value':value}
        base={**group(),'expression':'玩家.等级 >= 3 and 玩家.血量 >= 2','editor_mode':'text'}
        saved=library.apply(self.root,library.snapshot(self.root)['revision'],[put(base)])
        first=self.submit({**base,'expression':'玩家.等级 >= 3 and 玩家.血量 >= 8'})
        saved=library.apply(self.root,saved['revision'],[put({**base,'expression':'玩家.等级 >= 4 and 玩家.血量 >= 2'})])
        self.action(ADMIN,first['id'],'approve',{})
        merged=library.snapshot(self.root)
        self.assertEqual(merged['groups'][0]['expression'],'(玩家.等级 >= 4 and 玩家.血量 >= 8)')
        base=merged['groups'][0]
        final={**base,'expression':'玩家.等级 >= 5 and 玩家.血量 >= 8'}
        second=self.submit(final)
        concurrent=library.apply(self.root,merged['revision'],[put({**base,'expression':'玩家.等级 >= 6 and 玩家.血量 >= 8'})])
        with self.assertRaisesRegex(Conflict,'正式条件'):
            self.action(ADMIN,second['id'],'approve',{'change_ids':[0],'group_editor':{}})
        self.assertEqual(library.snapshot(self.root),concurrent)
        self.action(ADMIN,second['id'],'approve',{'change_ids':[0],'group_editor':{'group':final,'resolve_conditions':concurrent['revision']}})
        self.assertEqual(library.snapshot(self.root)['groups'][0]['expression'],final['expression'])

    def test_card_fixed_and_status_controls_are_staged_until_approval(self):
        from template_workflow import review_status_change
        base=group()
        put=lambda value:{'kind':'group','action':'put','id':value['id'],'value':value}
        current=library.apply(self.root,library.snapshot(self.root)['revision'],[put(base)])
        current=library.set_utterance_fixed(self.root,current['revision'],base['id'],'line',True,'admin')
        status=review_status_change(current,base['id'],ALICE,'initial_reviewed')
        item=self.proposals.submit(ALICE,{'revision':current['revision'],'source':'review-status','changes':[status]},workflow_source='review-status')
        operation={'change_ids':[0],'group_editor':{'fixed':{'id':'line','value':False}}}
        with self.assertRaises(PermissionError):self.action(ALICE,item['id'],'edit',operation)
        unfixed=self.action(ADMIN,item['id'],'edit',operation)
        draft=deepcopy(unfixed['changes'][0]['value'])
        draft['utterances'][0]['text']='解除固定后的编辑。'
        edited=self.action(ADMIN,item['id'],'edit',{'change_ids':[0],'group_editor':{'group':draft}})
        self.assertEqual(edited['source'],'editor')
        self.assertTrue(library.snapshot(self.root)['groups'][0]['utterances'][0]['fixed'])
        self.action(ADMIN,item['id'],'edit',{'change_ids':[0],'group_editor':{'status':'final_reviewed'}})
        self.action(ADMIN,item['id'],'approve',{'change_ids':[0],'group_editor':{}})
        saved=library.snapshot(self.root)['groups'][0]
        self.assertEqual(saved['review_status'],'final_reviewed')
        self.assertEqual(saved['utterances'],draft['utterances'])

    def test_single_utterance_flags_do_not_read_or_validate_formal_library(self):
        item=self.submit()
        for field,actor in [('ignore',ALICE),('fixed',ADMIN)]:
            data={'proposal_revision':item['proposal_revision'],'change_ids':[0],
                  'group_editor':{field:{'id':'line','value':True}}}
            with patch.object(library,'snapshot',side_effect=AssertionError('loaded formal library')), \
                 patch.object(library,'preview_changes',side_effect=AssertionError('validated formal library')):
                item=self.proposals.action(actor,item['id'],'edit',data)
                self.assertEqual(self.proposals.action(actor,item['id'],'edit',data)['proposal_revision'],item['proposal_revision'])
        self.assertTrue(item['changes'][0]['value']['utterances'][0]['ignored'])
        self.assertTrue(item['changes'][0]['value']['utterances'][0]['fixed'])

    def test_unrelated_save_allowed_but_touched_record_stale_rejected(self):
        item=self.submit()
        library.apply(self.root,library.snapshot(self.root)['revision'],
            [{'kind':'group','action':'put','id':'other','value':group('other')}])
        self.action(ADMIN,item['id'],'approve',{})
        changed=group(text='新的建议。');item=self.submit(changed)
        library.apply(self.root,library.snapshot(self.root)['revision'],
            [{'kind':'group','action':'put','id':'example','value':group(text='管理员版本。')}])
        with self.assertRaises(Conflict):self.action(ADMIN,item['id'],'approve',{})
        self.assertEqual(self.proposals.list(ALICE)[-1]['status'],'pending')

    def test_partial_approval_and_recovery_after_formal_save(self):
        state=library.snapshot(self.root)
        item=self.proposals.submit(ALICE,{'revision':state['revision'],'changes':[
            {'kind':'group','action':'put','id':key,'value':group(key)} for key in ('one','two')]})
        result=self.action(ADMIN,item['id'],'approve',{'change_ids':[0]})
        self.assertEqual(result['status'],'pending')
        self.assertEqual([g['id'] for g in library.snapshot(self.root)['groups']],['one'])
        # A durable receipt allows recovery after canonical data was saved but SQLite failed.
        original=self.proposals._finish_receipt
        with patch.object(self.proposals,'_finish_receipt',side_effect=OSError('power loss')):
            with self.assertRaises(OSError):self.action(ADMIN,item['id'],'approve',{})
        self.proposals._finish_receipt=original
        self.proposals.recover()
        self.assertEqual(self.proposals.list(ALICE)[0]['status'],'approved')
        self.assertEqual(len(library.snapshot(self.root)['groups']),2)

    def test_withdraw_and_no_viewer_private_access(self):
        item=self.submit()
        with self.assertRaises(PermissionError):self.proposals.list({'username':'reader','role':'viewer'})
        with self.assertRaises(PermissionError):self.action(BOB,item['id'],'withdraw',{})
        self.assertEqual(self.action(ALICE,item['id'],'withdraw',{})['status'],'withdrawn')

    def test_partial_approval_does_not_rebase_unselected_records(self):
        changes=[{'kind':'group','action':'put','id':key,'value':group(key)} for key in ('one','two')]
        item=self.proposals.submit(ALICE,{'revision':library.snapshot(self.root)['revision'],'changes':changes})
        library.apply(self.root,library.snapshot(self.root)['revision'],[
            {'kind':'group','action':'put','id':'two','value':group('two','管理员新文。')}])
        self.action(ADMIN,item['id'],'approve',{'change_ids':[0]})
        with self.assertRaises(Conflict):self.action(ADMIN,item['id'],'approve',{})
        self.assertEqual(next(g for g in library.snapshot(self.root)['groups'] if g['id']=='two')['utterances'][0]['text'],'管理员新文。')

    def test_missing_or_stale_proposal_revision_is_rejected(self):
        item=self.submit()
        with self.assertRaises(Conflict):self.proposals.action(ADMIN,item['id'],'approve',{})
        with self.assertRaises(Conflict):self.proposals.action(ALICE,item['id'],'withdraw',{'proposal_revision':'old'})

    def test_reviewed_draft_partial_approval_history_and_retry(self):
        base=group()
        def put(value):return {'kind':'group','action':'put','id':value['id'],'value':value}
        library.apply(self.root,library.snapshot(self.root)['revision'],[put(base)])
        suggested={**group(text='编辑员建议。'),'name':'新名称'}
        item=self.submit(suggested)
        final={**suggested,'utterances':[{'id':'line','text':'审核后话术。'}]}
        data={'proposal_revision':item['proposal_revision'],'changes':[put(final)]}
        with self.assertRaises(PermissionError):self.proposals.action(BOB,item['id'],'edit',data)
        edited=self.proposals.action(ADMIN,item['id'],'edit',data)
        self.assertEqual(library.snapshot(self.root)['groups'],[base])
        first={'proposal_revision':edited['proposal_revision'],'changes':[put({**base,'name':final['name']})]}
        partial=self.proposals.action(ADMIN,item['id'],'approve',first)
        self.assertEqual(partial['status'],'pending')
        self.assertEqual(self.proposals.action(ADMIN,item['id'],'approve',first),partial)
        preview=self.proposals.card_previews(ALICE)[0]
        self.assertEqual(preview['base'],{**base,'name':final['name']})
        self.assertEqual(preview['change']['value'],final)
        result=self.action(ADMIN,item['id'],'approve',{})
        self.assertEqual(self.proposals.card_previews(ALICE),[])
        self.assertEqual(library.snapshot(self.root)['groups'],[final])
        self.assertEqual(result['submission'],{'before':{'group:example':base},'changes':[put(suggested)]})
        self.assertEqual([r['action'] for r in result['reviews']],['edit','approve','approve'])
        self.assertEqual(result['reviews'][-1]['after'],{'group:example':final})

    def test_rebase_requires_version_actually_reviewed(self):
        item=self.submit()
        current=group(text='正式修改。')
        change={'kind':'group','action':'put','id':current['id'],'value':current}
        library.apply(self.root,library.snapshot(self.root)['revision'],[change])
        conflict=self.proposals.list(ADMIN)[0]['conflicts']['group:example']
        self.assertEqual(conflict['current'],current)
        with self.assertRaises(PermissionError):
            self.action(ALICE,item['id'],'edit',{'rebase':{'group:example':conflict['revision']}})
        self.assertEqual(self.proposals.list(ADMIN)[0]['conflicts']['group:example'],conflict)
        with self.assertRaises(Conflict):self.action(ADMIN,item['id'],'edit',{'rebase':{'group:example':'old'}})
        self.action(ADMIN,item['id'],'edit',{'rebase':{'group:example':conflict['revision']}})
        self.assertEqual(self.proposals.list(ADMIN)[0]['conflicts'],{})
        self.action(ADMIN,item['id'],'approve',{})
        self.assertEqual(library.snapshot(self.root)['groups'],[group()])

    def test_author_can_revise_pending_draft_but_stale_reviewer_cannot_overwrite_it(self):
        item=self.submit()
        value=group(text='编辑员补充说明。')
        change={**item['changes'][0],'value':value}
        updated=self.action(ALICE,item['id'],'edit',{'changes':[change]})
        self.assertEqual(updated['changes'],[change])
        with self.assertRaises(Conflict):
            self.proposals.action(ADMIN,item['id'],'approve',{'proposal_revision':item['proposal_revision']})
        self.assertEqual(library.snapshot(self.root)['groups'],[])

    def test_warning_seen_tracks_entity_changes_not_summary_shape(self):
        from types import SimpleNamespace
        import json_store
        import templates_http
        hero={'id':'hero:1','name':'示例英雄','category':'heroes','effect':'原机制'}
        path=self.root/'entities/heroes.json';json_store.write_file(path,[hero])
        groups=[group('one'),group('two')]
        for value in groups:
            value['event_id']='hero_select'
            value['conditions']=[{'id':'hero-condition','parameter_key':'hero','operator':'eq','value':{'id':hero['id'],'name':hero['name']}}]
        library.apply(self.root,library.snapshot(self.root)['revision'],[
            {'kind':'group','action':'put','id':g['id'],'value':g} for g in groups])
        json_store.write_file(path,[{**hero,'effect':'新机制'}])
        server=SimpleNamespace(root=self.root,state_dir=self.root/'state')
        def warnings():return templates_http.get(server,ALICE,'/api/templates/warnings','/api/templates/warnings')
        first=warnings();self.assertTrue(first['unseen'])
        templates_http.mutate(server,ALICE,'/api/templates/warnings/seen','POST',{'notification_revision':first['notification_revision']})
        self.assertFalse(warnings()['unseen'])
        self.assertEqual(warnings()['unseen_items'],[])
        groups[0]['utterances'][0]['text']='只改话术，不变更实体。'
        library.apply(self.root,library.snapshot(self.root)['revision'],[
            {'kind':'group','action':'put','id':'one','value':groups[0]}])
        self.assertFalse(warnings()['unseen'])
        second=next(w for w in warnings()['items'] if w['group_id']=='two')
        confirmation={'group_id':'two','revision':second['revision']}
        with self.assertRaises(PermissionError):
            templates_http.mutate(server,ALICE,'/api/templates/warnings/confirm','POST',confirmation)
        self.assertIn('two',[w['group_id'] for w in warnings()['items']])
        templates_http.mutate(server,ADMIN,'/api/templates/warnings/confirm','POST',confirmation)
        self.assertNotIn('two',[w['group_id'] for w in warnings()['items']])
        self.assertFalse(warnings()['unseen'])
        json_store.write_file(path,[{**hero,'effect':'第三次机制'}])
        self.assertTrue(warnings()['unseen'])

    def test_login_summary_only_contains_new_entity_deltas(self):
        from types import SimpleNamespace
        import json_store
        import templates_http
        heroes=[{'id':'hero:'+str(i),'name':'英雄'+str(i),'category':'heroes','effect':'原机制'} for i in (1,2)]
        path=self.root/'entities/heroes.json';json_store.write_file(path,heroes)
        groups=[group('one'),group('two')]
        for value,hero in zip(groups,heroes):
            value['event_id']='hero_select'
            value['conditions']=[{'id':'hero-condition','parameter_key':'hero','operator':'eq','value':{'id':hero['id'],'name':hero['name']}}]
        library.apply(self.root,library.snapshot(self.root)['revision'],[
            {'kind':'group','action':'put','id':g['id'],'value':g} for g in groups])
        server=SimpleNamespace(root=self.root,state_dir=self.root/'state')
        def warnings():return templates_http.get(server,ALICE,'/api/templates/warnings','/api/templates/warnings')
        heroes[0]['effect']='新机制';json_store.write_file(path,heroes)
        first=warnings();templates_http.mutate(server,ALICE,'/api/templates/warnings/seen','POST',{'notification_revision':first['notification_revision']})
        heroes[1]['effect']='新机制';json_store.write_file(path,heroes)
        second=warnings()
        self.assertEqual(len(second['items']),2)
        self.assertEqual([item['group_id'] for item in second['unseen_items']],['two'])

    def test_rejected_formal_revision_does_not_leave_approval_receipt(self):
        item=self.submit()
        with patch.object(library,'apply',side_effect=Conflict('concurrent CLI save')):
            with self.assertRaises(Conflict):self.action(ADMIN,item['id'],'approve',{})
        self.assertFalse(self.proposals.receipt.exists())
        self.assertEqual(self.proposals.list(ALICE)[0]['status'],'pending')


if __name__=='__main__':unittest.main()
