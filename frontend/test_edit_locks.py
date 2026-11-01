"""Leases use real SQLite and canonical note fixtures, never Git/network."""
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store
from proposals import ProposalStore
from edit_locks import EditLocks,EditLocked
from workspace import Conflict

A={'username':'alice','role':'annotator','account_role':'annotator'}
B={'username':'bob','role':'annotator','account_role':'annotator'}
ADMIN={'username':'admin','role':'admin','account_role':'admin'}


class EditLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'temp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.nodes=[{'id':'t','type':'heading','level':1,'title':'Lease note'},
                    {'id':'h','type':'heading','level':2,'title':'Chapter'},
                    {'id':'a','type':'entry','key':'one','show_key':True,'value':'old'},
                    {'id':'b','type':'entry','key':'two','show_key':True,'value':'old'}]
        json_store.save(self.root,[{'body':{'schema_version':6,'nodes':self.nodes},
            'metadata':{'id':'n','type':'other','title':'Lease note','path':'knowledge/other/n.json'}}])
        self.store=ProposalStore(self.root,self.root/'private/proposals.sqlite3')
        self.now=[1000.0];self.locks=EditLocks(self.store,clock=lambda:self.now[0])

    def acquire(self,actor=A,client='client-a',node='a',**extra):
        return self.locks.acquire(actor,{'note_id':'n','client_id':client,
            'resource':{'kind':'entry','id':node},**extra})

    def test_same_entry_exclusive_different_entries_parallel(self):
        lease=self.acquire()
        with self.assertRaises(EditLocked):self.acquire(B,'client-b')
        self.assertEqual(self.acquire(B,'client-b','b')['baseline']['node']['id'],'b')
        self.assertEqual(self.acquire()['id'],lease['id'])

    def test_same_account_different_tabs_are_not_one_owner(self):
        self.acquire()
        with self.assertRaises(EditLocked):self.acquire(A,'client-b')

    def test_admin_takeover_revokes_only_target_and_old_release_cannot_unlock(self):
        old=self.acquire();other=self.acquire(A,'client-a','b')
        with self.assertRaises(EditLocked):self.acquire(ADMIN,'admin-tab')
        new=self.acquire(ADMIN,'admin-tab',takeover=True)
        self.locks.release(A,{'client_id':'client-a','leases':[{'id':old['id'],'token':old['token']}]})
        view=self.locks.list(A,'n','client-a')
        self.assertIn(old['id'],[x['id'] for x in view['revoked']])
        self.assertEqual(next(x for x in view['revoked'] if x['id']==old['id'])['reason'],'admin_takeover')
        self.assertEqual({x['id'] for x in view['leases']},{new['id'],other['id']})

    def test_guest_and_annotator_takeover_are_rejected(self):
        with self.assertRaises(PermissionError):self.locks.list(None,'n','client-a')
        self.acquire()
        with self.assertRaises(PermissionError):self.acquire(B,'client-b',takeover=True)

    def test_presence_never_leaks_credentials_or_baselines(self):
        lease=self.acquire()
        rows=self.locks.list(B,'n','client-b')['leases']
        self.assertEqual(rows[0]['owner'],'alice')
        self.assertNotIn('token',rows[0]);self.assertNotIn('baseline',rows[0])
        self.assertNotIn(lease['token'],str(rows))

    def test_expiry_heartbeat_and_restart_invalidate_old_tokens(self):
        lease=self.acquire();self.now[0]+=15
        renewed=self.locks.renew(A,{'client_id':'client-a','leases':[{'id':lease['id'],'token':lease['token']}]})
        self.assertEqual(renewed['leases'][0]['expires_at'],1075)
        self.now[0]=1076
        self.assertEqual(self.locks.renew(A,{'client_id':'client-a','leases':[lease]})['lost'][0]['reason'],'expired')
        fresh=self.acquire(B,'client-b')
        restarted=EditLocks(self.store,clock=lambda:self.now[0])
        self.assertEqual(restarted.renew(B,{'client_id':'client-b','leases':[fresh]})['lost'][0]['reason'],'server_restart')
        with self.assertRaises(EditLocked):self.locks.acquire(A,{'note_id':'n','client_id':'client-a','resource':{'kind':'entry','id':'b'}})

    def test_other_administrators_are_not_forcibly_revoked(self):
        first=self.acquire(ADMIN,'admin-one')
        second=self.acquire({'username':'other','role':'admin'},'admin-two')
        self.assertEqual(len(self.locks.list(ADMIN,'n','admin-one')['leases']),2)
        with self.assertRaises(EditLocked):self.acquire()

    def test_insert_slots_are_separate_resources(self):
        resource={'kind':'slot','section_id':'h','left_id':'a'}
        self.locks.acquire(A,{'note_id':'n','client_id':'client-a','resource':resource})
        with self.assertRaises(EditLocked):self.locks.acquire(B,{'note_id':'n','client_id':'client-b','resource':resource})
        self.acquire(B,'client-b','a')

    def delta(self,lease,kind='update',value='new',request='request-one'):
        node={**self.nodes[2],'value':value} if kind=='update' else {'id':'client-new','type':'entry','key':'new','show_key':True,'value':value}
        return {'note_id':'n','client_id':lease['client_id'],'request_id':request,
                'changes':[{'kind':kind,'lease':{'id':lease['id'],'token':lease['token']},'node':node}]}

    def test_different_entry_deltas_survive_unrelated_approval(self):
        left=self.acquire();right=self.acquire(B,'client-b','b')
        first=self.store.submit_delta(A,self.delta(left))['items'][0]
        self.store.action(ADMIN,first['id'],'approve',{'revision':1})
        payload=self.delta(right,request='request-two');payload['changes'][0]['node']={**self.nodes[3],'value':'second'}
        second=self.store.submit_delta(B,payload)['items'][0]
        self.assertEqual(second['node_id'],'b')
        self.assertEqual(json_store.load_record(self.root,'n')['body']['nodes'][2]['value'],'new')

    def test_slot_submission_is_idempotent_and_releases_lease(self):
        lease=self.locks.acquire(A,{'note_id':'n','client_id':'client-a',
            'resource':{'kind':'slot','section_id':'h','left_id':'a'}})
        payload=self.delta(lease,'insert')
        first=self.store.submit_delta(A,payload)
        second=self.store.submit_delta(A,payload)
        self.assertEqual(first,second)
        self.assertEqual(self.locks.list(A,'n','client-a')['leases'],[])
        payload['changes'][0]['node']['value']='different'
        with self.assertRaises(Conflict):self.store.submit_delta(A,payload)

    def test_approval_preempts_only_target_and_rejects_replayed_submission(self):
        first=self.acquire();item=self.store.submit_delta(A,self.delta(first))['items'][0]
        editing=self.acquire(B,'client-b');other=self.acquire(A,'client-a','b')
        self.store.action(ADMIN,item['id'],'approve',{'revision':1})
        with self.assertRaises(EditLocked) as denied:self.store.submit_delta(B,self.delta(editing,request='stale-save'))
        self.assertEqual(denied.exception.reason,'admin_takeover')
        self.assertEqual(self.locks.renew(A,{'client_id':'client-a','leases':[other]})['lost'],[])

    def test_private_proposal_edit_requires_canonical_lease(self):
        item=self.store.submit_delta(A,self.delta(self.acquire()))['items'][0]
        with self.assertRaises((ValueError,EditLocked)):
            self.store.update(A,item['id'],{'revision':1,'proposed_node':item['proposed_node']})
        blocker=self.acquire(B,'client-b')
        with self.assertRaises(EditLocked):self.acquire()
        lease=self.acquire(ADMIN,'admin-tab',takeover=True)
        updated=self.store.update(ADMIN,item['id'],{'revision':1,'proposed_node':{**item['proposed_node'],'value':'reviewed'},'client_id':'admin-tab','lease':lease})
        self.assertEqual(updated['revision'],2)
        self.assertEqual(self.locks.renew(B,{'client_id':'client-b','leases':[blocker]})['lost'][0]['reason'],'admin_takeover')

    def test_delta_cannot_change_other_node_hidden_fields_or_use_wrong_token(self):
        lease=self.acquire();payload=self.delta(lease)
        payload['changes'][0]['node']['id']='b'
        with self.assertRaises(ValueError):self.store.submit_delta(A,payload)
        payload=self.delta(lease);payload['changes'][0]['node']['show_key']=False
        with self.assertRaises(ValueError):self.store.submit_delta(A,payload)
        payload=self.delta(lease);payload['changes'][0]['lease']['token']='forged'
        with self.assertRaises(EditLocked):self.store.submit_delta(A,payload)

    def test_changed_entry_does_not_reuse_obsolete_acquisition(self):
        lease=self.acquire()
        json_store.edit(self.root,'n',{'revision':self.store._note('n')['metadata']['revision'],
            'document':{'schema_version':6,'nodes':[dict(n,value='changed') if n['id']=='a' else n for n in self.nodes]}})
        fresh=self.acquire()
        self.assertNotEqual(fresh['id'],lease['id'])
        self.assertEqual(fresh['baseline']['node']['value'],'changed')

    def test_admin_entry_save_receipt_recovers_without_duplicate_insert(self):
        lease=self.locks.acquire(ADMIN,{'note_id':'n','client_id':'admin-tab',
            'resource':{'kind':'slot','section_id':'h','left_id':'a'}})
        payload=self.delta(lease,'insert')
        with patch.object(self.locks,'remember',side_effect=OSError('request transaction failed')):
            with self.assertRaises(OSError):self.store.apply_changes(ADMIN,payload)
        self.assertTrue(self.store.recovery_pending())
        # The Git worker constructs a bare store; recovery must not reset epoch.
        ProposalStore(self.root,self.store.db_path).recover()
        result=self.store.apply_changes(ADMIN,payload)
        self.assertEqual(len(result['document']['nodes']),len(self.nodes)+1)

    def test_bare_store_approval_recovery_restores_takeover_reason(self):
        item=self.store.submit_delta(A,self.delta(self.acquire()))['items'][0]
        lease=self.acquire(B,'client-b')
        with patch.object(self.store,'_put',side_effect=OSError('commit interrupted')):
            with self.assertRaises(OSError):self.store.action(ADMIN,item['id'],'approve',{'revision':1})
        ProposalStore(self.root,self.store.db_path).recover()
        view=self.locks.list(B,'n','client-b')
        self.assertEqual(next(v for v in view['revoked'] if v['id']==lease['id'])['reason'],'admin_takeover')


if __name__=='__main__':unittest.main()
