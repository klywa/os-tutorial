from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import wxq,workspace,player_branches
TEST_TEMP=Path(__file__).parents[4]/'.wxq-runtime/test-temp'

class BackupLocationTests(unittest.TestCase):
    def test_knowledge_updates_keep_distinct_external_versions(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as td:
            root=Path(td);p=root/'knowledge/lineups/阵容.md'
            wxq.atomic_text(p,'first');wxq.atomic_text(p,'second');wxq.atomic_text(p,'third')
            files=list((root/'raw/backups/knowledge/lineups').glob('阵容.md.*.bak'))
            self.assertEqual(sorted(f.read_text('utf-8') for f in files),['first','second'])
            self.assertFalse(list((root/'knowledge').rglob('*.bak*')))
            wxq.atomic_text(p,'third');self.assertEqual(len(list((root/'raw/backups/knowledge').rglob('*.bak'))),2)

    def test_obsolete_migration_and_recovery_never_write_knowledge_backups(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as td:
            root=Path(td);wxq.init_store(root);p=root/'knowledge/lineups/旧名.md'
            p.write_text('original','utf-8')
            with workspace.store_lock(root):
                transaction=workspace.make_transaction(root,[],[p.relative_to(root).as_posix()])
                wxq.atomic_json(root/'knowledge/pending-save.json',transaction)
                workspace.recover(root);workspace.recover(root)
            self.assertFalse(p.exists());self.assertFalse(list((root/'knowledge').rglob('*.bak*')))
            self.assertEqual([f.read_text('utf-8') for f in (root/'raw/backups/knowledge/lineups').glob('旧名.md.*.bak')],['original'])

    def test_removing_final_lineup_clears_player_adaptations(self):
        player={'id':'p','type':'player','player_id':'player:1','lineup_adaptations':[{'lineup':'deleted'}]}
        player_branches.update_player_adaptations([player])
        self.assertEqual(player.get('lineup_adaptations',[]),[])

if __name__=='__main__':unittest.main()
