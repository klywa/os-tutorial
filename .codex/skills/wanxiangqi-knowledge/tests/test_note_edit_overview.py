import sys, tempfile, unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from test_player_branches import fixture
import workspace, wxq, player_branches as branches
from lineup_layout import reading_document


class NoteEditOverviewTests(unittest.TestCase):
    def setUp(self):
        temp_root=Path(__file__).parents[4]/'.wxq-runtime/test-temp'
        temp_root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        wxq.init_store(self.root)
        wxq.atomic_json(self.root/'entities/players.json',[{'id':'player:1','name':'甲','category':'players'},{'id':'player:2','name':'乙','category':'players'}])
        self.note=fixture()
        workspace.persist(self.root,[self.note])

    def test_title_only_save_updates_all_outputs_and_is_idempotent(self):
        old=deepcopy(workspace.notes(self.root)[0]);old_files=branches.documents(old)
        result=workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':'新测试打法','scopes':[]})
        self.assertEqual(result['title'],'新测试打法')
        self.assertEqual(result['path'],old['path'])
        self.assertEqual(result['claims'],old['claims'])
        self.assertIn('title',result['manual_fields'])
        self.assertEqual(result['history'][-1]['previous']['title'],old['title'])
        self.assertEqual(wxq.read_json((self.root/result['path']).with_suffix('.json')),result)
        self.assertIn('# 新测试打法',(self.root/result['path']).read_text('utf-8'))
        for path,text in branches.documents(result).items():
            self.assertEqual((self.root/path).read_text('utf-8'),text)
            self.assertIn(Path(path).name,(self.root/result['path']).read_text('utf-8'))
        for path in old_files:self.assertFalse((self.root/path).exists())
        again=workspace.edit(self.root,result['id'],{'revision':result['revision'],'title':result['title'],'scopes':[]})
        self.assertEqual(result,again)
        with self.assertRaises(workspace.Conflict):workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':'过期标题'})

    def test_title_and_branch_content_save_together_and_recover(self):
        old=workspace.notes(self.root)[0]
        original=wxq.atomic_json
        def fail_index(path,data,*args,**kwargs):
            if Path(path)==self.root/'knowledge/index.json':raise OSError('模拟中断')
            return original(path,data,*args,**kwargs)
        with patch.object(wxq,'atomic_json',side_effect=fail_index):
            with self.assertRaises(OSError):
                workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':'组合修改标题','scopes':[{'scope':'one','sections':{'前期运营':'新开局'}}]})
        workspace.recover(self.root)
        result=workspace.notes(self.root)[0]
        self.assertEqual(result['title'],'组合修改标题')
        self.assertIn('新开局',branches.documents(result)[branches.document_path(result,branches.branch(result,'one'))])
        self.assertNotIn('新开局',branches.documents(result)[branches.document_path(result,branches.branch(result,'two'))])
        self.assertFalse((self.root/'knowledge/pending-save.json').exists())

    def test_invalid_titles_do_not_write(self):
        old=workspace.notes(self.root)[0]
        before=(self.root/'knowledge/index.json').read_bytes()
        for title in ('','   ',None,42):
            with self.assertRaises(ValueError):workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':title,'scopes':[]})
        self.assertEqual((self.root/'knowledge/index.json').read_bytes(),before)

    def test_rename_does_not_overwrite_existing_unmanaged_file(self):
        old=workspace.notes(self.root)[0]
        path=self.root/'knowledge/lineups/冲突标题-甲.md';path.write_text('独立人工内容',encoding='utf-8')
        with self.assertRaises(workspace.Conflict):workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':'冲突标题','scopes':[]})
        self.assertEqual(path.read_text('utf-8'),'独立人工内容')
        self.assertEqual(workspace.notes(self.root)[0],old)

    def test_rename_rejects_collision_with_another_notes_main_file(self):
        old=workspace.notes(self.root)[0]
        other={'id':'other','type':'lineup','title':'另一篇笔记','path':'knowledge/lineups/新名字-甲.md','claims':[],'entities':[],'related':[]}
        workspace.persist(self.root,[old,other]);old=workspace.notes(self.root)[0]
        before=(self.root/other['path']).read_bytes()
        with self.assertRaises(workspace.Conflict):workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':'新名字','scopes':[]})
        self.assertEqual((self.root/other['path']).read_bytes(),before)

    def test_rename_rejects_sanitized_collision_with_other_managed_branches(self):
        old=workspace.notes(self.root)[0];other=deepcopy(old)
        other.update(id='another',title='另一个：打法',path='knowledge/lineups/另一稳定路径.md')
        workspace.persist(self.root,[old,other]);old=workspace.notes(self.root)[0]
        before=(self.root/'knowledge/index.json').read_bytes()
        with self.assertRaises(workspace.Conflict):workspace.edit(self.root,old['id'],{'revision':old['revision'],'title':'另一个－打法','scopes':[]})
        self.assertEqual((self.root/'knowledge/index.json').read_bytes(),before)

    def test_rename_recovery_preserves_concurrent_old_file_edit_as_conflict(self):
        old=deepcopy(workspace.notes(self.root)[0]);changed=deepcopy(old);changed['title']='事务新标题'
        transaction=workspace.make_transaction(self.root,[changed])
        path=branches.document_path(old,branches.branch(old,'one'))
        external=(self.root/path).read_text('utf-8').replace('甲棋手独立开局','事务外新增开局')
        (self.root/path).write_text(external,encoding='utf-8')
        wxq.atomic_json(self.root/'knowledge/pending-save.json',transaction)
        workspace.recover(self.root)
        self.assertEqual((self.root/path).read_text('utf-8'),external)
        import markdown_sync
        state=markdown_sync.status(self.root)
        self.assertTrue(any(i['path']==path for i in state['issues']))
        self.assertIn(path,state['files'])
        markdown_sync.resolve(self.root,old['id'],{'revision':workspace.notes(self.root)[0]['revision'],'action':'use_saved'})
        self.assertFalse((self.root/path).exists())
        self.assertFalse(markdown_sync.status(self.root)['issues'])

    def test_rename_updates_related_notes_and_player_adaptations(self):
        lineup=workspace.notes(self.root)[0]
        player={'id':'player-note','type':'player','title':'甲','player_id':'player:1','entities':['player:1'],'claims':[],'related':[{'id':lineup['id'],'title':lineup['title'],'type':'lineup'}]}
        workspace.persist(self.root,[lineup,player])
        lineup=workspace.notes(self.root)[0]
        workspace.edit(self.root,lineup['id'],{'revision':lineup['revision'],'title':'关联新标题','scopes':[]})
        player=next(n for n in workspace.notes(self.root) if n['type']=='player')
        self.assertEqual(player['related'][0]['title'],'关联新标题')
        adaptation=player['lineup_adaptations'][0]
        self.assertEqual(adaptation['title'],'关联新标题')
        self.assertTrue((self.root/adaptation['path']).is_file())

    def test_stage_projection_uses_visible_branch_blocks_and_keeps_original(self):
        n=fixture();n['reading_layout']={'version':4,'supporting_claim_refs':{'hidden':'one'}}
        for cid,section,text in [('hidden','前期运营','隐藏旧结论'),('middle','中期运营及应变','中期操作'),('late','后期运营及应变','后期操作'),('improve','成型后提升思路','提升优先级')]:
            n['claims'].append({'id':cid,'section':section,'text':text,'kind':'general_strategy','evidence':[]})
            n['meta']['player_branches'][0]['claim_refs'].append(cid)
        before=deepcopy(n);doc=reading_document(n,'one')
        operations=doc['overview_operations']
        self.assertIn('甲棋手独立开局',str(operations['early']))
        self.assertNotIn('隐藏旧结论',str(operations))
        self.assertIn('中期操作',str(operations['middle']))
        self.assertIn('后期操作',str(operations['late']))
        self.assertIn('提升优先级',str(operations['improvement']))
        self.assertIn('中期操作',str(doc['sections']))
        self.assertNotIn('甲棋手独立开局',str(reading_document(n,'two')['overview_operations']))
        self.assertEqual(n,before)

    def test_reader_reuses_teaching_blocks_for_stage_projection(self):
        import guide_layout
        n=fixture();n['reading_layout']={'version':4}
        real=guide_layout.blocks;calls=[]
        def blocks(note,bid):
            calls.append((id(note),bid));return real(note,bid)
        from lineup_layout import _reading_document
        with patch.object(guide_layout,'blocks',side_effect=blocks):
            _reading_document(n,'one');baseline=len(calls);calls.clear()
            doc=reading_document(n,'one')
        self.assertNotIn('_overview_blocks',doc)
        # One render for each branch and parsing the selected branch are legacy
        # work; the projection must add no extra render of the full family.
        self.assertEqual(len(calls),baseline)

    def test_legacy_stage_projection_without_branch(self):
        n=fixture();n['meta'].pop('player_branches');n['meta'].pop('common_claim_refs')
        doc=reading_document(n)
        self.assertIn('甲棋手独立开局',str(doc['overview_operations']['early']))
        self.assertEqual(doc['overview_operations']['improvement'],[])


if __name__=='__main__':unittest.main()
