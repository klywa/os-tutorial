import json
import sys
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import wxq,workspace
import markdown_sync as sync
from test_player_branches import fixture


class MarkdownSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        wxq.init_store(self.root)
        wxq.atomic_json(self.root/'entities/players.json',[{'id':'player:1','name':'甲','category':'players'},{'id':'player:2','name':'乙','category':'players'}])
        workspace.persist(self.root,[fixture()])
        self.a=self.root/'knowledge/lineups/测试打法-甲.md';self.b=self.root/'knowledge/lineups/测试打法-乙.md'

    def test_transaction_writes_schema5_entry_views_and_manifest(self):
        self.assertEqual(wxq.read_json(self.root/'knowledge/index.json')['schema_version'],5)
        self.assertIn('甲棋手独立开局',self.a.read_text('utf-8'))
        self.assertIn('测试打法-甲.md',(self.root/'knowledge/lineups/测试打法.md').read_text('utf-8'))
        self.assertIn('knowledge/lineups/测试打法-甲.md',wxq.read_json(self.root/'knowledge/markdown-sync.json')['files'])

    def test_common_edit_propagates_branch_edit_stays_private_and_keeps_history(self):
        self.a.write_text(self.a.read_text('utf-8').replace('共同机制','共同机制已人工修改').replace('甲棋手独立开局','甲棋手新开局'),encoding='utf-8')
        sync.scan(self.root)
        self.assertIn('共同机制已人工修改',self.b.read_text('utf-8'))
        self.assertNotIn('甲棋手新开局',self.b.read_text('utf-8'))
        note=workspace.notes(self.root)[0]
        c=next(c for c in note['claims'] if c['id']=='common')
        self.assertEqual(c['origin'],'manual');self.assertEqual(c['evidence'],[])
        self.assertTrue(note['history'])
        before=deepcopy(note);sync.scan(self.root)
        self.assertEqual(before,workspace.notes(self.root)[0])

    def test_simultaneous_common_conflict_preserves_both_files_and_can_resolve(self):
        self.a.write_text(self.a.read_text('utf-8').replace('共同机制','共同改法甲'),encoding='utf-8')
        self.b.write_text(self.b.read_text('utf-8').replace('共同机制','共同改法乙'),encoding='utf-8')
        state=sync.scan(self.root)
        self.assertEqual(state['issues'][0]['note'],'test')
        self.assertIn('共同改法甲',self.a.read_text('utf-8'));self.assertIn('共同改法乙',self.b.read_text('utf-8'))
        revision=workspace.notes(self.root)[0]['revision']
        sync.resolve(self.root,'test',{'revision':revision,'action':'use_saved'})
        self.assertIn('共同机制',self.a.read_text('utf-8'));self.assertEqual(sync.status(self.root)['issues'],[])

    def test_invalid_format_and_missing_file_do_not_delete_knowledge(self):
        note=deepcopy(workspace.notes(self.root)[0]);self.a.write_text('broken',encoding='utf-8')
        self.assertTrue(sync.scan(self.root)['issues'])
        self.assertEqual(workspace.notes(self.root)[0],note)
        self.a.unlink();self.assertTrue(sync.scan(self.root)['issues']);self.assertEqual(workspace.notes(self.root)[0],note)

    def test_web_save_syncs_external_first_and_rejects_stale_revision(self):
        original=workspace.notes(self.root)[0]
        self.a.write_text(self.a.read_text('utf-8').replace('共同机制','外部新机制'),encoding='utf-8')
        with self.assertRaises(workspace.Conflict):
            workspace.edit(self.root,'test',{'revision':original['revision'],'scope':'one','sections':{'前期运营':'网页开局'}})
        self.assertIn('外部新机制',self.b.read_text('utf-8'))

    def test_three_way_merges_independent_lines_but_rejects_same_line(self):
        self.assertEqual(sync.three_way('a\nb\nc','A\nb\nc','a\nb\nC'),'A\nb\nC')
        with self.assertRaises(ValueError):sync.three_way('a','A','B')

    def test_recovery_replays_branch_views_and_manifest(self):
        note=workspace.notes(self.root)[0]
        transaction=workspace.make_transaction(self.root,[note])
        transaction['expected_markdown'][self.a.relative_to(self.root).as_posix()]=None
        wxq.atomic_json(self.root/'knowledge/pending-save.json',transaction)
        self.a.unlink();workspace.recover(self.root)
        self.assertTrue(self.a.exists());self.assertFalse((self.root/'knowledge/pending-save.json').exists())

    def test_scoped_web_edit_does_not_replace_other_player_section(self):
        note=workspace.notes(self.root)[0]
        workspace.edit(self.root,'test',{'revision':note['revision'],'scope':'one','sections':{'前期运营':'甲网页新开局'}})
        self.assertIn('甲网页新开局',self.a.read_text('utf-8'))
        self.assertIn('乙棋手独立开局',self.b.read_text('utf-8'))
        self.assertNotIn('甲网页新开局',self.b.read_text('utf-8'))

    def test_recovery_never_overwrites_an_edit_made_after_transaction(self):
        transaction=workspace.make_transaction(self.root,workspace.notes(self.root))
        text=self.a.read_text('utf8').replace('共同机制','恢复期间外部修改')
        self.a.write_text(text,encoding='utf8')
        wxq.atomic_json(self.root/'knowledge/pending-save.json',transaction)
        workspace.recover(self.root)
        self.assertEqual(self.a.read_text('utf8'),text)
        self.assertTrue(sync.status(self.root)['issues'])

    def test_save_window_does_not_adopt_unreviewed_disk_hash(self):
        from unittest.mock import patch
        original=sync.outputs
        def during_outputs(*args,**kwargs):
            result=original(*args,**kwargs)
            self.a.write_text(self.a.read_text('utf8').replace('共同机制','窗口内外部修改'),encoding='utf8')
            return result
        with patch.object(sync,'outputs',side_effect=during_outputs):workspace.persist(self.root,deepcopy(workspace.notes(self.root)))
        self.assertIn('窗口内外部修改',self.a.read_text('utf8'));self.assertTrue(sync.status(self.root)['issues'])

    def test_atomic_two_scope_web_save_and_unknown_scope_rollback(self):
        note=workspace.notes(self.root)[0]
        with self.assertRaises(ValueError):workspace.edit(self.root,'test',{'revision':note['revision'],'scopes':[{'scope':'common','sections':{'核心机制':'不能写'}},{'scope':'missing','sections':{}}]})
        self.assertEqual(workspace.notes(self.root)[0],note)
        workspace.edit(self.root,'test',{'revision':note['revision'],'scopes':[{'scope':'common','sections':{'核心机制':'网页共通'}},{'scope':'one','sections':{'前期运营':'网页专属'}}]})
        self.assertIn('网页共通',self.b.read_text('utf8'));self.assertNotIn('网页专属',self.b.read_text('utf8'))

    def test_external_member_table_updates_structured_stage_and_preserves_other_branch(self):
        note=workspace.notes(self.root)[0]
        # Existing entity names are resolved without asking the writer to maintain IDs.
        text=self.a.read_text('utf8').replace('甲（可选）：','甲（必需）：')
        self.a.write_text(text,encoding='utf8');sync.scan(self.root)
        n=workspace.notes(self.root)[0]
        self.assertEqual(n['meta']['player_branches'][0]['overrides']['compositions']['early'][0]['necessity'],'required')
        self.assertEqual(n['meta']['player_branches'][1],note['meta']['player_branches'][1])

    def test_restart_reconciles_and_noop_scan_keeps_revision(self):
        self.a.write_text(self.a.read_text('utf8').replace('共同机制','重启同步'),encoding='utf8')
        watcher=sync.Watcher(self.root);watcher.start();watcher.close()
        self.assertIn('重启同步',self.b.read_text('utf8'))
        before=deepcopy(workspace.notes(self.root));sync.scan(self.root);self.assertEqual(before,workspace.notes(self.root))


if __name__=='__main__':unittest.main()
