"""Private proposals exercise real SQLite and canonical JSON transactions."""
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'frontend'), str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store
from workspace import Conflict, store_lock
from proposals import ProposalStore, ProposalForbidden

ADMIN = {'username':'admin','role':'admin','account_role':'admin'}
AUTHOR = {'username':'alice','role':'annotator','account_role':'admin'}
OTHER = {'username':'bob','role':'annotator','account_role':'annotator'}


def entry(nid, value='old'):
    return {'id':nid,'type':'entry','key':'说明','show_key':True,'value':value}


class ProposalTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'temp').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.nodes = [{'id':'t','type':'heading','level':1,'title':'Title'},
            {'id':'h','type':'heading','level':2,'title':'Chapter'},entry('a'),entry('b'),
            {'id':'z','type':'heading','level':2,'title':'Other'},entry('c')]
        with store_lock(self.root):
            json_store.save(self.root,[{'body':{'schema_version':6,'nodes':self.nodes},
                'metadata':{'id':'n','title':'Title','type':'other','path':'knowledge/other/n.json'}}])
        self.db = self.root/'private/proposals.sqlite3'
        self.store = ProposalStore(self.root,self.db)

    def note(self):
        return json_store.load_record(self.root,'n')

    def submit(self, nodes=None, actor=AUTHOR, scope='h'):
        return self.store.submit(actor,{'note_id':'n','revision':self.note()['metadata']['revision'],
            'scope_id':scope,'nodes':nodes if nodes is not None else [self.nodes[1],entry('a','new'),self.nodes[3]]})['items']

    def action(self, item, action='approve', actor=ADMIN):
        return self.store.action(actor,item['id'],action,{'revision':item['revision']})

    def test_submission_private_diff_and_partial_approval(self):
        items = self.submit([self.nodes[1],entry('a','new'),entry('x','insert')])
        self.assertEqual([i['kind'] for i in items],['update','insert','delete'])
        self.assertEqual(self.store.list(OTHER)['items'],[])
        self.assertEqual(len(self.store.list(ADMIN)['items']),3)
        self.assertEqual(self.note()['body']['nodes'],self.nodes)
        approved = self.action(items[0])
        self.assertEqual(approved['status'],'approved')
        self.assertEqual(self.action(approved)['status'],'approved')
        self.assertEqual(self.note()['body']['nodes'][2]['value'],'new')
        self.assertEqual(self.action(items[1],'reject')['status'],'rejected')
        self.assertEqual(self.action(items[2])['status'],'approved')
        self.assertNotIn('b',[n['id'] for n in self.note()['body']['nodes']])

    def test_private_list_reuses_one_readonly_record_and_get_never_scans(self):
        items=self.submit([self.nodes[1],entry('a','new'),entry('x','insert')])
        original=json_store.load_record
        def readonly(root,nid,*,clone=True):
            self.assertFalse(clone,'proposal read cloned historical metadata')
            return original(root,nid,clone=clone)
        with patch.object(json_store,'load_record',side_effect=readonly) as load:
            self.assertEqual(len(self.store.list(ADMIN)['items']),3)
            self.assertEqual(load.call_count,1)
        with patch.object(self.store,'_rows',side_effect=AssertionError('get scanned all proposals')):
            self.assertEqual(self.store.get(AUTHOR,items[0]['id'])['id'],items[0]['id'])
            with self.assertRaises(ProposalForbidden):self.store.get(OTHER,items[0]['id'])

    def test_approval_cleanup_failure_still_queues_and_recovers_sync(self):
        from types import SimpleNamespace
        from site_access import mutate_proposal
        from website_sync import SyncManager,SyncWorker
        item=self.submit()[0]
        manager=SyncManager(self.root,self.db.parent)
        worker=SyncWorker(manager);worker.initialized=True
        server=SimpleNamespace(root=self.root,state_dir=self.db.parent,proposals=self.store,
                               sync=manager,sync_worker=worker)
        path='/api/proposals/'+item['id']+'/approve'
        with patch.object(self.store,'_clear_receipt',side_effect=OSError('cleanup interrupted')):
            with self.assertRaises(OSError):mutate_proposal(server,ADMIN,path,'POST',{'revision':1},public=True)
        self.assertEqual(self.store.get(ADMIN,item['id'])['status'],'approved')
        self.assertEqual(self.note()['body']['nodes'][2]['value'],'new')
        duplicate=mutate_proposal(server,ADMIN,path,'POST',{'revision':1},public=True)
        self.assertEqual(duplicate['sync']['state'],'pending')
        with patch.object(manager,'_changed',return_value=['knowledge/other/n.json']), \
                patch.object(manager,'retry',side_effect=lambda:manager._state('synced')):
            self.assertTrue(worker.step())
        self.assertFalse(self.store.recovery_pending())

    def test_private_http_crud_never_recovers_outside_global_lock(self):
        from types import SimpleNamespace
        from site_access import mutate_proposal
        item=self.submit()[0]
        server=SimpleNamespace(root=self.root,state_dir=self.db.parent,proposals=self.store)
        with patch.object(self.store,'recovery_pending',return_value=False), \
                patch.object(self.store,'recover',side_effect=AssertionError('private path recovered without lock')):
            result=mutate_proposal(server,AUTHOR,'/api/proposals/'+item['id'],'PUT',
                                   {'revision':1,'proposed_node':entry('a','changed')})
        self.assertEqual(result['proposed_node']['value'],'changed')

    def test_private_transaction_refuses_new_receipt_after_outer_check(self):
        item=self.submit()[0]
        with patch.object(self.store,'_put',side_effect=OSError('DB transaction interrupted')):
            with self.assertRaises(OSError):self.action(item)
        self.assertTrue(self.store.recovery_pending())
        self.assertEqual(self.store.get(ADMIN,item['id'])['status'],'pending')
        with self.assertRaises(Conflict):
            self.store.update(AUTHOR,item['id'],{'revision':1,'proposed_node':entry('a','different')},_recover=False)
        with self.assertRaises(Conflict):
            self.store.action(AUTHOR,item['id'],'withdraw',{'revision':1},_recover=False)
        with self.assertRaises(Conflict):
            self.store.submit(AUTHOR,{'note_id':'n','revision':self.note()['metadata']['revision'],
                'scope_id':'h','nodes':[self.nodes[1],entry('a','other'),self.nodes[3]]},_recover=False)
        self.store.recover()
        self.assertEqual(self.store.get(ADMIN,item['id'])['status'],'approved')

    def test_effective_role_and_unauthorized_reads_do_not_create_database(self):
        fresh = self.root/'untouched/db.sqlite3'
        store = ProposalStore(self.root,fresh)
        with self.assertRaises(ProposalForbidden):store.list({'username':'admin','role':'readonly','account_role':'admin'})
        self.assertFalse(fresh.exists())
        item=self.submit()[0]
        with self.assertRaises(ProposalForbidden):self.action(item,actor=AUTHOR)
        with self.assertRaises(ProposalForbidden):self.store.update(OTHER,item['id'],{'revision':1,'proposed_node':entry('a','theft')})

    def test_scope_rejects_heading_reorder_hidden_fields_and_cross_section(self):
        bad = [
            [dict(self.nodes[1],title='Changed'),self.nodes[2],self.nodes[3]],
            [self.nodes[1],self.nodes[3],self.nodes[2]],
            [self.nodes[1],dict(self.nodes[2],secret=True),self.nodes[3]],
            [self.nodes[1],self.nodes[2],self.nodes[3],self.nodes[5]],
        ]
        for nodes in bad:
            with self.subTest(nodes=nodes),self.assertRaises(ValueError):self.submit(nodes)
        with self.assertRaises(ValueError):self.submit([entry('x')],scope='a')

    def test_insertions_keep_batch_order_when_approved_backwards(self):
        items=self.submit([self.nodes[1],entry('x','one'),entry('y','two'),self.nodes[2],self.nodes[3],entry('q','end')])
        for item in reversed(items):self.action(item)
        self.assertEqual([n.get('value') for n in self.note()['body']['nodes'][2:7]],['one','two','old','old','end'])

    def test_target_conflict_rebase_and_unrelated_edit(self):
        item=self.submit()[0]
        note=self.note();body=note['body'];body['nodes'][-1]['value']='unrelated'
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        self.action(item)
        item=self.submit([self.nodes[1],entry('a','another'),self.nodes[3]])[0]
        note=self.note();body=note['body'];body['nodes'][2]['value']='changed elsewhere'
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        with self.assertRaises(Conflict):self.action(item)
        self.assertTrue(self.store.list(AUTHOR)['items'][-1]['conflict'])
        rebased=self.store.update(ADMIN,item['id'],{'revision':1,'proposed_node':entry('a','merged'),'rebase':True})
        self.action(rebased)
        self.assertEqual(self.note()['body']['nodes'][2]['value'],'merged')

    def test_multi_author_pending_edits_withdraw_and_stale_revision(self):
        alice=self.submit()[0];bob=self.submit(actor=OTHER)[0]
        changed=self.store.update(AUTHOR,alice['id'],{'revision':1,'proposed_node':entry('a','edited')})
        self.assertEqual(changed['revision'],2)
        with self.assertRaises(Conflict):self.action(alice,'withdraw',AUTHOR)
        self.assertEqual(self.action(changed,'withdraw',AUTHOR)['status'],'withdrawn')
        self.assertEqual(self.store.list(OTHER)['items'][0]['id'],bob['id'])

    def test_crash_after_canonical_apply_recovers_without_duplicate_or_overwrite(self):
        item=self.submit([self.nodes[1],self.nodes[2],entry('x','once'),self.nodes[3]])[0]
        original=json_store.edit
        def crash(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('process died after canonical save')
        with patch('proposals.json_store.edit',side_effect=crash),self.assertRaises(RuntimeError):self.action(item)
        note=self.note();body=note['body'];body['nodes'][-1]['value']='later'
        original(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        self.store.recover()
        self.assertEqual(self.store.list(AUTHOR)['items'][0]['status'],'approved')
        self.assertEqual([n.get('value') for n in self.note()['body']['nodes']].count('once'),1)
        self.assertEqual(self.note()['body']['nodes'][-1]['value'],'later')

    def test_backup_includes_committed_wal_rows(self):
        self.submit()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            self.store.backup(self.root/'backup.sqlite3')
        copied=ProposalStore(self.root,self.root/'backup.sqlite3')
        self.assertEqual(copied.list(AUTHOR)['items'][0]['proposed_node']['value'],'new')

    def test_deleted_anchor_conflicts_and_rejected_sibling_does_not_break_order(self):
        items=self.submit([self.nodes[1],self.nodes[2],entry('x','one'),entry('y','two'),entry('q','three'),self.nodes[3]])
        self.action(items[1],'reject');self.action(items[2]);self.action(items[0])
        self.assertEqual([n.get('value') for n in self.note()['body']['nodes'][2:6]],['old','one','three','old'])
        item=self.submit([self.nodes[1],self.nodes[2],entry('r','blocked'),self.nodes[3]])[0]
        note=self.note();body=note['body'];body['nodes']=[n for n in body['nodes'] if n['id']!='a']
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        with self.assertRaises(Conflict):self.action(item)

    def test_delete_referenced_entry_cannot_detach_semantics(self):
        note=self.note();body=note['body'];body['semantics']={'overview':{'$text':'a'}}
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        item=self.submit([self.nodes[1],self.nodes[3]])[0]
        with self.assertRaises(ValueError):self.action(item)
        self.assertEqual(self.note()['body']['semantics'],{'overview':{'$text':'a'}})
        self.assertEqual(self.store.list(AUTHOR)['items'][0]['status'],'pending')

    def test_unkeyed_entry_value_edit_preserves_format(self):
        note=self.note();body=note['body'];body['nodes'][2]={'id':'a','type':'entry','key':'正文','show_key':False,'value':'plain','separator':'\n\n'}
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        edited=dict(body['nodes'][2],value='edited')
        item=self.submit([edited],scope='a')[0];self.action(item)
        self.assertEqual(self.note()['body']['nodes'][2],edited)
        with self.assertRaises(ValueError):self.submit([dict(edited,separator='')],scope='a')

    def test_descendant_headings_are_immutable_but_entries_are_editable(self):
        note=self.note();body=note['body'];body['nodes'].insert(3,{'id':'sub','type':'heading','level':3,'title':'Subchapter'})
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        scoped=body['nodes'][1:5];scoped[-1]=entry('b','nested')
        item=self.submit(scoped)[0];self.action(item)
        self.assertEqual(self.note()['body']['nodes'][4]['value'],'nested')
        with self.assertRaises(ValueError):self.submit([scoped[0],scoped[1],scoped[-1]])

    def test_crash_before_canonical_apply_does_not_approve_old_historical_body(self):
        # The proposed body once existed in history. A receipt alone must never
        # mistake that old state for the interrupted approval's successful save.
        first=self.submit()[0];self.action(first)
        note=self.note();body=note['body'];body['nodes'][2]['value']='old'
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        item=self.submit()[0]
        with patch('proposals.json_store.edit',side_effect=RuntimeError('before save')),self.assertRaises(RuntimeError):self.action(item)
        self.assertTrue(self.store.recovery_pending())
        self.store.recover()
        self.assertFalse(self.store.recovery_pending())
        self.assertEqual(self.store.list(AUTHOR)['items'][-1]['status'],'pending')
        self.assertEqual(self.note()['body']['nodes'][2]['value'],'old')

    def test_recover_canonical_prepared_journal_before_approval_receipt(self):
        item=self.submit()[0]
        original=json_store.recover
        def interrupt(root,*args,**kwargs):
            if (Path(root)/json_store.JOURNAL).exists():raise RuntimeError('canonical prepared')
            return original(root,*args,**kwargs)
        with patch('proposals.json_store.recover',side_effect=interrupt),self.assertRaises(RuntimeError):self.action(item)
        self.assertTrue((self.root/json_store.JOURNAL).exists())
        self.store.recover()
        self.assertEqual(self.store.list(AUTHOR)['items'][0]['status'],'approved')
        self.assertEqual(self.note()['body']['nodes'][2]['value'],'new')

    def test_receipt_cannot_be_consumed_from_another_release(self):
        item=self.submit()[0]
        with patch('proposals.json_store.edit',side_effect=RuntimeError('before save')),self.assertRaises(RuntimeError):self.action(item)
        wrong=ProposalStore(self.root/'different-release',self.db)
        with self.assertRaises(Conflict):wrong.recover()
        self.assertTrue(self.store.recovery_pending())
        self.store.recover()

    def test_approved_items_are_immutable(self):
        approved=self.action(self.submit()[0])
        with self.assertRaises(Conflict):self.store.update(ADMIN,approved['id'],{'revision':approved['revision'],'proposed_node':entry('a','changed')})
        with self.assertRaises(Conflict):self.action(approved,'reject')

    def test_pending_receipt_is_resolved_before_author_can_edit(self):
        item=self.submit()[0]
        original=json_store.edit
        def crash(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('after apply')
        with patch('proposals.json_store.edit',side_effect=crash),self.assertRaises(RuntimeError):self.action(item)
        with self.assertRaises(Conflict):self.store.update(AUTHOR,item['id'],{'revision':1,'proposed_node':entry('a','wrong')})
        saved=self.store.list(AUTHOR)['items'][0]
        self.assertEqual(saved['status'],'approved')
        self.assertEqual(saved['proposed_node']['value'],'new')

    def test_approval_receipt_tracks_canonical_label_normalization(self):
        item=self.submit([self.nodes[1],dict(entry('a','new'),key='**说明**'),self.nodes[3]])[0]
        original=json_store.edit
        def crash(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('after normalized apply')
        with patch('proposals.json_store.edit',side_effect=crash),self.assertRaises(RuntimeError):self.action(item)
        self.store.recover()
        self.assertEqual(self.store.list(AUTHOR)['items'][0]['status'],'approved')
        self.assertEqual(self.note()['body']['nodes'][2]['key'],'说明')

    def test_moved_approved_insert_cannot_pull_sibling_into_other_section(self):
        items=self.submit([self.nodes[1],self.nodes[2],entry('x','one'),entry('y','two'),self.nodes[3]])
        second=self.action(items[1])
        note=self.note();body=note['body'];moved=next(n for n in body['nodes'] if n['id']==second['node_id'])
        body['nodes']=[n for n in body['nodes'] if n['id']!=second['node_id']]+[moved]
        json_store.edit(self.root,'n',{'revision':note['metadata']['revision'],'document':body})
        self.action(items[0])
        self.assertEqual([n.get('value') for n in self.note()['body']['nodes'][2:5]],['old','one','old'])


if __name__=='__main__':unittest.main()

class Storage2ProposalTests(ProposalTests):
    def setUp(self):
        super().setUp()
        from migrate_knowledge_history import migrate
        migrate(self.root, apply=True)
