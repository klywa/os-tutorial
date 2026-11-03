"""Three-way synchronization uses disposable Git repos and canonical schema6 pairs."""
from copy import deepcopy
from pathlib import Path
import subprocess,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store as store
import knowledge_git
from website_sync import SyncManager,sync_lock

def git(root,*args):
    result=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    return result.stdout.strip()

class KnowledgeGitTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'raw/reports/knowledge-sync-20261103/test-temp';folder.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.left=self.base/'left';self.left.mkdir()
        git(self.left,'init','-b','master');self.identity(self.left)
        (self.left/'.gitignore').write_text('raw/\nentities/\n',encoding='utf-8')
        store.initialize(self.left)
        records=[]
        for name in ('a','b'):
            records.append({'body':{'schema_version':6,'leading':'','nodes':[
                {'type':'heading','id':'h-'+name,'level':1,'title':name,'space':' ','separator':'\n\n'},
                {'type':'entry','id':'e-'+name,'key':'原理','show_key':True,'value':'共同原文','separator':'\n\n'},
                {'type':'entry','id':'e-'+name+'-2','key':'运营','show_key':True,'value':'另一段','separator':'\n\n'}]},
                'metadata':{'schema_version':6,'id':name,'type':'other','title':name,'path':'knowledge/other/'+name+'.json',
                            'aliases':[],'entities':[],'core':[],'claim_annotations':[],'history':[]}})
        store.save(self.left,records,storage_version=2)
        git(self.left,'add','.');git(self.left,'commit','-m','baseline')
        self.origin=self.base/'origin.git';git(self.base,'clone','--bare',str(self.left),str(self.origin))
        git(self.left,'remote','add','origin',str(self.origin))
        self.right=self.base/'right';git(self.base,'clone',str(self.origin),str(self.right));self.identity(self.right)

    def identity(self,root):
        git(root,'config','user.name','Sync Test');git(root,'config','user.email','sync@example.invalid')

    def change(self,root,nid,text,node=None):
        record=store.load_record(root,nid);body=deepcopy(record['body'])
        next(n for n in body['nodes'] if n['id']==(node or 'e-'+nid))['value']=text
        store.edit(root,nid,{'revision':record['metadata']['revision'],'document':body})
        git(root,'add','knowledge','knowledge-history');git(root,'commit','-m','edit '+nid)

    def merge(self,preferred='right'):
        git(self.right,'push','origin','master')
        candidate=self.base/'candidate';git(self.base,'clone',str(self.left),str(candidate));self.identity(candidate)
        git(candidate,'remote','set-url','origin',str(self.origin));git(candidate,'fetch','origin','master')
        left=git(candidate,'rev-parse','HEAD');right=git(candidate,'rev-parse','FETCH_HEAD')
        result=knowledge_git.merge_branches(candidate,left,right,preferred=preferred,origin='test')
        return candidate,result

    def text(self,root,nid,node=None):
        return next(n['value'] for n in store.load_record(root,nid)['body']['nodes'] if n['id']==(node or 'e-'+nid))

    def test_different_notes_merge_and_rebuild_index(self):
        self.change(self.left,'a','本地修改');self.change(self.right,'b','网站修改')
        candidate,result=self.merge()
        self.assertTrue(result['handled']);self.assertEqual(result['conflict_note_ids'],[])
        self.assertEqual(self.text(candidate,'a'),'本地修改');self.assertEqual(self.text(candidate,'b'),'网站修改')
        self.assertEqual(store.validate(candidate)['errors'],[])
        self.assertEqual(git(candidate,'status','--porcelain'),'')

    def test_different_paragraphs_in_one_note_merge(self):
        self.change(self.left,'a','本地原理');self.change(self.right,'a','网站运营','e-a-2')
        candidate,result=self.merge()
        self.assertEqual(result['conflict_note_ids'],[])
        self.assertEqual(self.text(candidate,'a'),'本地原理');self.assertEqual(self.text(candidate,'a','e-a-2'),'网站运营')

    def test_conflict_keeps_preferred_note_and_publishes_other_note(self):
        self.change(self.left,'a','本地冲突');self.change(self.left,'b','本地不冲突')
        self.change(self.right,'a','网站正在展示')
        candidate,result=self.merge()
        self.assertEqual(result['conflict_note_ids'],['a'],result)
        self.assertEqual(self.text(candidate,'a'),'网站正在展示');self.assertEqual(self.text(candidate,'b'),'本地不冲突')
        self.assertTrue(list((candidate/'knowledge-sync/requests').glob('*.json')))
        self.assertEqual(store.validate(candidate)['errors'],[])

    def test_plain_code_conflict_remains_unmerged(self):
        for root,text in [(self.left,'local code'),(self.right,'remote code')]:
            (root/'program.py').write_text(text);git(root,'add','program.py');git(root,'commit','-m','code')
        # Independent additions to the same code path must not be selected for us.
        with self.assertRaisesRegex(RuntimeError,'program.py'):
            self.merge()

    def test_server_pin_uses_actual_serving_note_not_github(self):
        self.change(self.left,'a','网站实际展示');self.change(self.right,'a','GitHub另一版')
        candidate,result=self.merge(preferred='left')
        self.assertEqual(result['conflict_note_ids'],['a'],result)
        self.assertEqual(self.text(candidate,'a'),'网站实际展示')

    def manager(self):
        class FixtureSync(SyncManager):
            def _validate(self,root):
                self_errors=store.validate(root)['errors']
                if self_errors:raise ValueError(str(self_errors))
        return FixtureSync(self.left,self.base/'state')

    def test_website_sync_imports_requests_without_installing_remote_body(self):
        self.change(self.left,'a','网站展示');self.change(self.right,'a','远端冲突')
        self.change(self.right,'b','远端其它笔记');git(self.right,'push','origin','master')
        manager=self.manager()
        result=manager.retry_canonical()
        self.assertEqual(result['conflict_note_ids'],['a'],result)
        self.assertEqual(self.text(self.left,'a'),'网站展示')
        self.assertEqual(self.text(self.left,'b'),'共同原文')
        # Imported immutable events are queued once, then reach a stable state.
        for _ in range(3):
            if result['state']!='pending':break
            result=manager.retry_canonical()
        self.assertEqual(result['state'],'pending-deploy',result)
        self.assertEqual(result['conflict_note_ids'],['a'])
        self.assertEqual(git(self.left,'status','--porcelain'),'')

    def test_network_phase_allows_other_note_save_and_preserves_it(self):
        from unittest.mock import patch
        import website_sync
        manager=self.manager();original=website_sync.git;called=[]
        def during_network(root,*args,**kwargs):
            if args[:2]==('fetch','origin') and not called:
                called.append(True)
                with sync_lock(manager.state_dir):
                    record=store.load_record(self.left,'b');body=deepcopy(record['body'])
                    body['nodes'][1]['value']='网络等待时保存'
                    store.edit(self.left,'b',{'revision':record['metadata']['revision'],'document':body})
                    manager.enqueue()
            return original(root,*args,**kwargs)
        with patch.object(website_sync,'git',side_effect=during_network):
            result=manager.retry_canonical()
        self.assertTrue(result.get('more_pending'))
        self.assertEqual(self.text(self.left,'b'),'网络等待时保存')
        result=manager.retry_canonical()
        self.assertEqual(result['state'],'synced')

    def test_third_version_from_pending_ancestor_changes_group_revision(self):
        import knowledge_conflicts as conflicts
        base=store.load_record(self.left,'a');incoming=deepcopy(base)
        incoming['body']['nodes'][1]['value']='原有另一版'
        conflicts.write_request(self.left,conflicts.create_request(base,base,incoming))
        git(self.left,'add','knowledge-sync');git(self.left,'commit','-m','existing pending request')
        git(self.left,'push','origin','master');git(self.right,'pull','--ff-only')
        old=conflicts.get_group(self.left,'a')['revision']
        self.change(self.right,'a','后来第三版')
        candidate,result=self.merge(preferred='left')
        group=conflicts.get_group(candidate,'a')
        self.assertNotEqual(group['revision'],old)
        self.assertEqual(len(group['request_ids']),2)
        self.assertTrue(any(v['body']['nodes'][1]['value']=='后来第三版' for v in group['variants']))

    def test_failed_candidate_is_retained_for_inspection(self):
        from website_sync import candidate_checkout
        with self.assertRaisesRegex(RuntimeError,'故障验证目录已保留'):
            with candidate_checkout(self.base/'state') as folder:
                (folder/'diagnostic.txt').write_text('failed candidate')
                raise RuntimeError('模拟推送失败')
        self.assertTrue((folder/'diagnostic.txt').exists())

if __name__=='__main__':unittest.main()

