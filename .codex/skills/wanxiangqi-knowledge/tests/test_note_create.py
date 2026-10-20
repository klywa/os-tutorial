from pathlib import Path
import sys,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import workspace,wxq


class CreateNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);wxq.init_store(self.root)
        wxq.atomic_json(self.root/'entities/players.json',[{'id':'player:1','name':'测试棋手','category':'players','aliases':[]}])

    def payload(self,kind='lineup',title='测试阵容',request='request-123'):
        return {'type':kind,'title':'测试棋手' if kind=='player' else title,'aliases':[' 别名 ','别名'],'request_id':request,**({'player_id':'player:1'} if kind=='player' else {})}

    def test_all_types_create_complete_files_without_inventing_claims(self):
        for kind in ('lineup','player','other'):
            with self.subTest(kind=kind):
                n=workspace.create_note(self.root,self.payload(kind,request='request-'+kind))
                self.assertEqual(n['claims'],[]);self.assertEqual(n['aliases'],['别名'])
                self.assertTrue((self.root/n['path']).is_file());self.assertTrue(n['revision'])
                self.assertEqual(n['entities'],['player:1'] if kind=='player' else [])
                if kind=='lineup':
                    self.assertEqual(n['meta']['players'],[])
                    self.assertTrue((self.root/n['path']).with_suffix('.json').exists())

    def test_retry_returns_same_note_after_edit_and_rejects_different_payload(self):
        body=self.payload();n=workspace.create_note(self.root,body)
        workspace.edit(self.root,n['id'],{'revision':n['revision'],'title':'后续人工名称'})
        retry=workspace.create_note(self.root,body)
        self.assertEqual(retry['id'],n['id']);self.assertEqual(retry['title'],'后续人工名称')
        self.assertEqual(len(workspace.notes(self.root)),1)
        with self.assertRaises(workspace.Conflict):workspace.create_note(self.root,{**body,'title':'不同请求内容'})

    def test_same_type_name_conflicts_but_other_type_allowed(self):
        workspace.create_note(self.root,self.payload())
        with self.assertRaises(workspace.Conflict):workspace.create_note(self.root,self.payload(request='request-another'))
        workspace.create_note(self.root,self.payload('player',request='request-player'))
        self.assertEqual(len(workspace.notes(self.root)),2)

    def test_concurrent_retry_is_once_and_same_title_has_one_winner(self):
        def call(i):
            try:return workspace.create_note(self.root,self.payload(request='request-'+str(i)))['id']
            except workspace.Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(call,range(2)))
        self.assertEqual(ids.count('conflict'),1);self.assertEqual(len(workspace.notes(self.root)),1)
        body=self.payload(title='可重试新笔记',request='request-retry')
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:workspace.create_note(self.root,body),range(2)))
        self.assertEqual(rows[0]['id'],rows[1]['id']);self.assertEqual(len(workspace.notes(self.root)),2)

    def test_interrupted_create_recovers_without_duplicate(self):
        with patch.object(workspace,'apply_transaction',side_effect=OSError('模拟中断')):
            with self.assertRaises(OSError):workspace.create_note(self.root,self.payload())
        self.assertTrue((self.root/'knowledge/pending-save.json').exists())
        n=workspace.create_note(self.root,self.payload())
        self.assertEqual(workspace.notes(self.root)[0]['id'],n['id'])
        self.assertEqual(len(workspace.notes(self.root)),1)
        self.assertFalse((self.root/'knowledge/pending-save.json').exists())

    def test_invalid_inputs_do_not_create_records(self):
        for update in ({'type':'bad'},{'title':''},{'title':'ASCII only'},{'aliases':'bad'},{'request_id':''}):
            with self.subTest(update=update),self.assertRaises(ValueError):workspace.create_note(self.root,{**self.payload(),**update})
        self.assertEqual(workspace.notes(self.root),[])


if __name__=='__main__':unittest.main()
