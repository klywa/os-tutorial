import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from website_sync import SyncManager, SyncBusy, SyncBlocked, sync_lock


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


class FixtureSync(SyncManager):
    def _validate(self, root):
        for path in (root / 'knowledge').rglob('*.json'):
            json.loads(path.read_text(encoding='utf-8'))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.origin = self.base / 'origin.git'
        git(self.base, 'init', '--bare', str(self.origin))
        self.root = self.base / 'active'
        git(self.base, 'clone', str(self.origin), str(self.root))
        self.identity(self.root)
        (self.root / 'knowledge/players').mkdir(parents=True)
        (self.root / 'knowledge/players/a.json').write_text('{"value": 1}\n')
        (self.root / 'README.md').write_text('initial\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'initial')
        git(self.root, 'branch', '-M', 'master')
        git(self.root, 'push', '-u', 'origin', 'master')
        self.sync = FixtureSync(self.root, self.base / 'state')

    def identity(self, root):
        git(root, 'config', 'user.name', 'Test Bot')
        git(root, 'config', 'user.email', 'bot@example.test')

    def save(self, value):
        (self.root / 'knowledge/players/a.json').write_text(json.dumps({'value': value})+'\n')
        with sync_lock(self.sync.state_dir):
            return self.sync.record_save()

    def other(self):
        root = self.base / 'other'
        git(self.base, 'clone', str(self.origin), str(root))
        self.identity(root)
        return root

    def test_save_push_excludes_unrelated_even_staged(self):
        (self.root / 'README.md').write_text('local change')
        git(self.root, 'add', 'README.md')
        self.assertEqual(self.save(2)['state'], 'synced')
        self.assertEqual(git(self.origin, 'show', 'master:README.md'), 'initial')
        self.assertIn('README.md', git(self.root, 'diff', '--cached', '--name-only'))
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), git(self.origin, 'rev-parse', 'master'))

    def test_recovery_runs_before_changed_files_are_selected(self):
        validate=self.sync._validate
        recovered=[]
        def recover_and_validate(root):
            if root==self.root and not recovered:
                (root/'knowledge/players/a.json').write_text('{"value": 99}\n')
                recovered.append(True)
            validate(root)
        self.sync._validate=recover_and_validate
        with sync_lock(self.sync.state_dir):self.sync.retry()
        self.assertEqual(json.loads(git(self.origin,'show','master:knowledge/players/a.json'))['value'],99)

    def test_remote_advance_merges_and_pushes(self):
        other = self.other()
        (other / 'remote.txt').write_text('remote')
        git(other, 'add', '.'); git(other, 'commit', '-m', 'remote'); git(other, 'push')
        self.assertEqual(self.save(2)['state'], 'pending-deploy')
        self.assertFalse((self.root / 'remote.txt').exists())
        self.assertEqual(json.loads(git(self.origin, 'show', 'master:knowledge/players/a.json'))['value'], 2)

    def test_conflict_preserves_save_and_clean_merge_state(self):
        other = self.other()
        (other / 'knowledge/players/a.json').write_text('{"value": 3}\n')
        git(other, 'add', '.'); git(other, 'commit', '-m', 'remote'); git(other, 'push')
        self.assertEqual(self.save(2)['state'], 'conflict')
        self.assertEqual(json.loads((self.root / 'knowledge/players/a.json').read_text())['value'], 2)
        self.assertFalse((self.root / '.git/MERGE_HEAD').exists())
        self.assertEqual(self.sync.status()['state'], 'conflict')

    def test_offline_retains_commit_then_retry_pushes(self):
        git(self.root, 'remote', 'set-url', 'origin', str(self.base / 'missing.git'))
        self.assertEqual(self.save(2)['state'], 'pending')
        git(self.root, 'remote', 'set-url', 'origin', str(self.origin))
        with sync_lock(self.sync.state_dir):
            self.assertEqual(self.sync.retry()['state'], 'synced')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), git(self.origin, 'rev-parse', 'master'))

    def test_pending_sync_blocks_new_record_save(self):
        git(self.root, 'remote', 'set-url', 'origin', str(self.base / 'missing.git'))
        self.assertEqual(self.save(2)['state'], 'pending')
        with sync_lock(self.sync.state_dir):
            with self.assertRaises(SyncBlocked):
                self.sync.record_save()

    def test_invalid_remote_knowledge_does_not_modify_active(self):
        other = self.other()
        (other / 'knowledge/players/b.json').write_text('not json')
        git(other, 'add', '.'); git(other, 'commit', '-m', 'invalid remote'); git(other, 'push')
        original = git(self.root, 'rev-parse', 'HEAD')
        with sync_lock(self.sync.state_dir):
            self.assertEqual(self.sync.retry()['state'], 'conflict')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), original)
        self.assertFalse((self.root / 'knowledge/players/b.json').exists())

    def test_other_notes_are_committed_but_other_knowledge_categories_excluded(self):
        (self.root / 'knowledge/other').mkdir()
        (self.root / 'knowledge/cards').mkdir()
        (self.root / 'knowledge/other/a.json').write_text('{"note": "allowed"}')
        (self.root / 'knowledge/cards/a.json').write_text('{"note": "excluded"}')
        self.assertEqual(self.save(2)['state'], 'synced')
        self.assertIn('allowed', git(self.origin, 'show', 'master:knowledge/other/a.json'))
        self.assertIn('knowledge/cards/a.json', self.sync.status()['dirty'])

    def test_states_have_safe_messages_and_failed_validation_retains_saved_file(self):
        self.assertTrue(self.sync.status().get('message'))
        saved = self.root / 'knowledge/players/a.json'
        saved.write_text('invalid json')
        with sync_lock(self.sync.state_dir):
            status = self.sync.record_save()
        self.assertEqual(status['state'], 'conflict')
        self.assertEqual(saved.read_text(), 'invalid json')
        self.assertTrue(status.get('message'))
        self.assertNotIn(str(self.root), status['message'])
        self.assertIn('knowledge/players/a.json', status['dirty'])

    def test_lock_contends_across_processes(self):
        with sync_lock(self.sync.state_dir):
            script = 'from website_sync import sync_lock, SyncBusy; import sys\ntry:\n with sync_lock(sys.argv[1]): pass\nexcept SyncBusy: sys.exit(7)'
            child = subprocess.run([sys.executable, '-c', script, str(self.sync.state_dir)], cwd=Path(__file__).parent)
            self.assertEqual(child.returncode, 7)


if __name__ == '__main__':
    unittest.main()

