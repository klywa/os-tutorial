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
    return {'id':gid,'name':'开局提醒','event_id':'battle_prepare',
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

    def test_warning_seen_tracks_entity_changes_not_summary_shape(self):
        from types import SimpleNamespace
        import json_store
        import templates_http
        hero={'id':'hero:1','name':'示例英雄','category':'heroes','effect':'原机制'}
        path=self.root/'entities/heroes.json';json_store.write_file(path,[hero])
        groups=[group('one'),group('two')]
        for value in groups:
            value['event_id']='hero_buy'
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
        library.confirm_warning(self.root,'two',second['revision'])
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
            value['event_id']='hero_buy'
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
