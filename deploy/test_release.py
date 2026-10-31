"""Release behavior is tested with real independent Git checkouts, no services."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'frontend'))
import test_website_sync as fixtures
git = fixtures.git
FixtureSync = fixtures.FixtureSync

spec = importlib.util.spec_from_file_location('website_release', Path(__file__).parent / 'release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseTests(unittest.TestCase):
    setUp = fixtures.SyncTests.setUp
    identity = fixtures.SyncTests.identity
    other = fixtures.SyncTests.other

    def manager(self):
        base = self.base / 'site'
        (base / 'releases').mkdir(parents=True)
        manager = module.ReleaseManager(base, self.sync.state_dir)
        manager.current = self.root
        manager._switch = lambda path: setattr(manager, 'current', path)
        manager.sync_class = FixtureSync
        return manager

    def test_stale_release_never_switches(self):
        manager = self.manager()
        snapshot = manager.snapshot()
        (self.root / 'README.md').write_text('unsaved work')
        with self.assertRaises(module.StaleRelease):
            manager.assert_unchanged(snapshot)
        self.assertEqual(manager.current.resolve(), self.root)

    def test_failed_health_rolls_back_and_restarts_old_release(self):
        manager = self.manager()
        candidate = manager.releases / 'new'
        git(self.base, 'clone', str(self.origin), str(candidate))
        calls = []
        manager.restart = lambda: calls.append(manager.current.resolve())
        manager.healthy = lambda: False
        with self.assertRaises(RuntimeError):
            manager.activate(candidate, manager.snapshot())
        self.assertEqual(manager.current.resolve(), self.root)
        self.assertEqual(calls, [candidate, self.root])

    def test_build_failure_keeps_old_release(self):
        manager = self.manager()
        other = self.other()
        (other / 'remote.txt').write_text('new')
        git(other, 'add', '.'); git(other, 'commit', '-m', 'remote'); git(other, 'push')
        def fail(_):
            raise RuntimeError('build failure')
        manager.build = fail
        with self.assertRaisesRegex(RuntimeError, 'build failure'):
            manager.update()
        self.assertEqual(manager.current.resolve(), self.root)
        self.assertFalse((self.root / 'remote.txt').exists())

    def test_successful_update_activates_independent_checkout(self):
        manager = self.manager()
        other = self.other()
        (other / 'remote.txt').write_text('new')
        git(other, 'add', '.'); git(other, 'commit', '-m', 'remote'); git(other, 'push')
        manager.build = lambda _: None
        manager.restart = lambda: None
        manager.healthy = lambda: True
        self.assertEqual(manager.update()['state'], 'deployed')
        self.assertNotEqual(manager.current, self.root)
        self.assertEqual((manager.current / 'remote.txt').read_text(), 'new')
        self.assertFalse((self.root / 'remote.txt').exists())
        self.assertEqual(FixtureSync(manager.current, self.sync.state_dir).status()['state'], 'synced')

    def test_remote_advance_during_build_prevents_activation(self):
        manager = self.manager()
        other = self.other()
        (other / 'remote.txt').write_text('new')
        git(other, 'add', '.'); git(other, 'commit', '-m', 'remote'); git(other, 'push')
        def advance(_):
            (other / 'remote.txt').write_text('newer')
            git(other, 'add', '.'); git(other, 'commit', '-m', 'advance'); git(other, 'push')
        manager.build = advance
        with self.assertRaises(module.StaleRelease):
            manager.update()
        self.assertEqual(manager.current.resolve(), self.root)

    def test_rebuild_forces_build_and_switch_at_same_sha(self):
        manager = self.manager()
        manager.rebuild = True
        built = []
        manager.build = lambda candidate: built.append(candidate)
        manager.restart = lambda: None
        manager.healthy = lambda: True
        self.assertEqual(manager.update()['state'], 'deployed')
        self.assertEqual(built, [manager.current])
        self.assertNotEqual(manager.current, self.root)
        self.assertEqual(git(manager.current, 'rev-parse', 'HEAD'), git(self.root, 'rev-parse', 'HEAD'))

    def test_same_sha_does_not_build(self):
        manager = self.manager()
        manager.build = lambda _: self.fail('unchanged release rebuilt')
        self.assertEqual(manager.update()['state'], 'unchanged')


if __name__ == '__main__':
    unittest.main()

