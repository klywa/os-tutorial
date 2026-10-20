from copy import deepcopy
from pathlib import Path
import sys,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import workspace,wxq

class PlayerIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp=Path(__file__).parents[4]/'.wxq-runtime/test-temp';tmp.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=tmp);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);wxq.init_store(self.root)
        wxq.atomic_json(self.root/'entities/players.json',[
            {'id':'player:1','name':'昭君','category':'players','aliases':[]},
            {'id':'player:2','name':'闹闹','category':'players','aliases':[]}])

    def body(self,request='request-player',**extra):
        return {'type':'player','title':'昭君','player_id':'player:1','aliases':[],
                'request_id':request,**extra}

    def test_create_binds_identity_and_retry_and_duplicate(self):
        n=workspace.create_note(self.root,self.body())
        self.assertEqual(n['player_id'],'player:1');self.assertEqual(n['entities'],['player:1'])
        self.assertEqual(n['path'],'knowledge/players/昭君.md')
        self.assertEqual(workspace.create_note(self.root,self.body())['id'],n['id'])
        with self.assertRaises(workspace.Conflict):
            workspace.create_note(self.root,self.body('request-second',title='昭君另一篇'))
        self.assertEqual(len(workspace.notes(self.root)),1)

    def test_cannot_rename_or_rebind_player_through_edit(self):
        n=workspace.create_note(self.root,self.body())
        for change in ({'title':'昭君：新玩法'},{'player_id':'player:2'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                workspace.edit(self.root,n['id'],{'revision':n['revision'],**change})
        self.assertEqual(workspace.notes(self.root)[0]['player_id'],'player:1')

    def test_shared_persist_rejects_duplicate_and_unknown_identity(self):
        n=workspace.create_note(self.root,self.body())
        with workspace.store_lock(self.root):
            duplicate={**deepcopy(n),'id':'another-id','path':'knowledge/players/重复.md'}
            with self.assertRaises(ValueError):workspace.persist(self.root,[n,duplicate])
            with self.assertRaises(ValueError):workspace.persist(self.root,[{**deepcopy(n),'player_id':'player:2'}])
        for pid in ('player:missing','card:1',''):
            with self.subTest(pid=pid),self.assertRaises(ValueError):
                workspace.create_note(self.root,self.body('request-other',player_id=pid))

    def test_legacy_import_resolves_identity_and_reuses_existing_note(self):
        n=workspace.create_note(self.root,self.body())
        incoming={'id':'legacy-new-id','type':'player','title':'昭君：冻结教学',
                  'entities':['player:1'],'core':[],'claims':[]}
        wxq.commit_notes(self.root,[incoming])
        rows=workspace.notes(self.root)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],n['id'])
        self.assertEqual(rows[0]['title'],'昭君')
        self.assertIn('昭君：冻结教学',rows[0]['aliases'])

    def test_ambiguous_legacy_import_is_rejected(self):
        for entities in ([],['player:1','player:2']):
            with self.subTest(entities=entities),self.assertRaises(ValueError):
                wxq.commit_notes(self.root,[{'id':'old','type':'player','title':'攻略',
                    'entities':entities,'core':[],'claims':[]}])

    def test_shared_paths_are_canonical_and_unmanaged_target_is_protected(self):
        n={'id':'imported','type':'player','title':'昭君：教学','player_id':'player:1',
           'path':'knowledge/players/带后缀.md','entities':['player:1'],'core':[],'claims':[]}
        with workspace.store_lock(self.root):workspace.persist(self.root,[n])
        self.assertEqual(workspace.notes(self.root)[0]['path'],'knowledge/players/昭君.md')
        wxq.atomic_text(self.root/'knowledge/players/闹闹.md','手写未管理内容')
        with self.assertRaises(ValueError):workspace.create_note(self.root,self.body('request-two',title='闹闹',player_id='player:2'))
        self.assertEqual((self.root/'knowledge/players/闹闹.md').read_text('utf-8'),'手写未管理内容')

    def test_concurrent_creation_same_player_has_one_winner(self):
        def call(i):
            try:return workspace.create_note(self.root,self.body('request-'+str(i)))['id']
            except workspace.Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(call,range(2)))
        self.assertEqual(result.count('conflict'),1)
        self.assertEqual(len(workspace.notes(self.root)),1)

    def test_migration_moves_file_and_keeps_id_history_and_links(self):
        from player_identity import migrate
        old={'id':'old-player','type':'player','title':'昭君：冻结教学',
             'path':'knowledge/players/昭君－冻结教学.md','entities':['player:1'],
             'core':[],'claims':[],'aliases':[],'history':[]}
        # Simulate the actual legacy index, before the new shared invariant.
        wxq.atomic_json(self.root/'knowledge/index.json',{'notes':[old]})
        wxq.atomic_text(self.root/old['path'],'# 旧文件\n')
        migrate(self.root)
        first=workspace.notes(self.root)
        self.assertEqual(first[0]['id'],'old-player')
        self.assertEqual(first[0]['title'],'昭君')
        self.assertEqual(first[0]['path'],'knowledge/players/昭君.md')
        self.assertIn('昭君：冻结教学',first[0]['aliases'])
        self.assertFalse((self.root/old['path']).exists())
        self.assertTrue((self.root/(old['path']+'.bak')).exists())
        migrate(self.root);self.assertEqual(workspace.notes(self.root),first)

if __name__=='__main__':unittest.main()
