from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import wxq,workspace

class ObsoleteBackupTests(unittest.TestCase):
    def test_old_markdown_and_json_keep_distinct_recovery_copies(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);wxq.init_store(root)
            md=root/'knowledge/lineups/旧名称.md';data=md.with_suffix('.json')
            md.write_text('# 原正文\n','utf-8');data.write_text('{"original":true}\n','utf-8')
            with workspace.store_lock(root):workspace.persist(root,[],[md.relative_to(root).as_posix(),data.relative_to(root).as_posix()])
            self.assertFalse(md.exists());self.assertFalse(data.exists())
            self.assertEqual(next((root/'raw/backups/knowledge/lineups').glob('旧名称.md.*.bak')).read_text('utf-8'),'# 原正文\n')
            self.assertEqual(next((root/'raw/backups/knowledge/lineups').glob('旧名称.json.*.bak')).read_text('utf-8'),'{"original":true}\n')
            self.assertFalse(list((root/'knowledge').rglob('*.bak*')))

if __name__=='__main__':unittest.main()
