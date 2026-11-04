"""Release behavior is tested with real independent Git checkouts, no services."""
import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error
import threading
import time
import subprocess

sys.path.insert(0, str(Path(__file__).parents[1] / 'frontend'))
import test_website_sync as fixtures
git = fixtures.git
FixtureSync = fixtures.FixtureSync

spec = importlib.util.spec_from_file_location('website_release', Path(__file__).parent / 'release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseTests(unittest.TestCase):
    def test_remote_probes_do_not_hold_the_save_lock(self):
        from website_sync import sync_lock
        manager=self.manager();probe=manager.remote_head;calls=[]
        def remote(root):
            with sync_lock(manager.state_dir):calls.append(root)
            return probe(root)
        manager.remote_head=remote
        self.assertEqual(manager.update()['state'],'unchanged')
        self.assertTrue(calls)

    def test_release_probes_and_bulk_image_backup_allow_saves(self):
        from website_sync import sync_lock
        manager=self.manager();other=self.other()
        images=self.root/'website-data/images';images.mkdir(parents=True);(images/'test.img').write_bytes(b'image bytes')
        # These are immutable published files in the fixture, not a dirty user edit.
        git(self.root,'add','website-data');git(self.root,'commit','-m','images');git(self.root,'push')
        git(other,'pull','--ff-only')
        (other/'remote.txt').write_text('new');git(other,'add','.');git(other,'commit','-m','remote');git(other,'push')
        probe=manager.remote_head;copy=module.snapshot_os_images;calls=[]
        def remote(root):
            with sync_lock(manager.state_dir):calls.append('probe')
            return probe(root)
        def bulk(root,destination):
            with sync_lock(manager.state_dir):calls.append('images')
            return copy(root,destination)
        manager.remote_head=remote;manager.build=lambda _:None;manager.restart=lambda:None;manager.healthy=lambda:True
        with patch.object(module,'snapshot_os_images',side_effect=bulk):
            self.assertEqual(manager.update()['state'],'deployed')
        self.assertIn('images',calls);self.assertGreaterEqual(calls.count('probe'),2)
        backups=list((manager.state_dir/'update-backups').glob('release-*'))
        self.assertEqual((backups[0]/'website-data/images/test.img').read_bytes(),b'image bytes')

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

    def test_health_waits_for_slow_startup_beyond_thirty_seconds(self):
        clock=[0.0]
        def response(*args,**kwargs):
            if clock[0]<45:
                raise urllib.error.URLError('still starting')
            body=BytesIO(b'{"ok":true}'); body.status=200
            return body
        with patch.object(module.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(module.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)), \
                patch.object(module.urllib.request,'urlopen',side_effect=response):
            self.assertTrue(self.manager().healthy())
        self.assertEqual(clock[0],45)

    def test_health_wait_has_bounded_timeout(self):
        clock=[0.0]
        with patch.object(module.time,'monotonic',side_effect=lambda:clock[0]), \
                patch.object(module.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)), \
                patch.object(module.urllib.request,'urlopen',side_effect=urllib.error.URLError('unavailable')):
            self.assertFalse(self.manager().healthy(timeout=3))
        self.assertEqual(clock[0],3)

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

    def test_candidate_reuses_local_objects_then_becomes_independent(self):
        manager=self.manager();candidate=manager.releases/'cached'
        other=self.other()
        (other/'new-content.txt').write_text('only on remote')
        git(other,'add','.');git(other,'commit','-m','new remote content');git(other,'push')
        # file:// uses the Git transport rather than its local-clone shortcut.
        upstream=self.origin.as_uri()
        manager.clone_candidate(candidate,upstream,self.root)
        self.assertEqual(git(candidate,'remote','get-url','origin'),upstream)
        self.assertEqual(git(candidate,'rev-parse','HEAD'),git(other,'rev-parse','HEAD'))
        self.assertEqual((candidate/'new-content.txt').read_text(),'only on remote')
        self.assertFalse((self.root/'new-content.txt').exists())
        self.assertFalse((candidate/'.git/objects/info/alternates').exists())
        git(candidate,'fsck','--full')

    def test_uploaded_publisher_imports_helpers_from_serving_release(self):
        uploaded=self.base/'os-tutorial-release.py'
        uploaded.write_bytes(Path(module.__file__).read_bytes())
        source="import runpy,sys;sys.path[:0]=[sys.argv[1],sys.argv[2]];sys.argv=[sys.argv[3],'--help'];runpy.run_path(sys.argv[0],run_name='__main__')"
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-c',source,str(root/'frontend'),str(root/'deploy'),str(uploaded)],
            capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--base-dir',result.stdout)

    def test_clone_has_separate_long_timeout_and_preserves_failed_active_site(self):
        manager=self.manager();candidate=manager.releases/'slow'
        with patch.object(module.subprocess,'run',side_effect=subprocess.TimeoutExpired('git clone',900)) as run:
            with self.assertRaisesRegex(RuntimeError,'900'):
                manager.clone_candidate(candidate,'git@example.test:site.git',self.root)
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('--reference')+1],str(self.root))
        self.assertIn('--dissociate',args)
        self.assertIn('--progress',args)
        self.assertEqual(run.call_args.kwargs['timeout'],900)
        self.assertEqual(run.call_args.kwargs['env']['GIT_TERMINAL_PROMPT'],'0')
        self.assertEqual(manager.current.resolve(),self.root)

    def test_first_clone_needs_no_existing_reference(self):
        manager=self.manager()
        with patch.object(module.subprocess,'run') as run:
            manager.clone_candidate(manager.releases/'first','git@example.test:site.git',None)
        self.assertNotIn('--reference',run.call_args.args[0])

    def test_publication_waits_for_an_existing_sync_job(self):
        from website_sync import sync_lock
        manager=self.manager();entered=threading.Event();release=threading.Event();errors=[];results=[]
        def holder():
            with sync_lock(self.sync.state_dir):entered.set();release.wait(5)
        lock_thread=threading.Thread(target=holder);lock_thread.start();self.assertTrue(entered.wait(2))
        def update():
            try:results.append(manager.update())
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=update);thread.start()
        try:
            time.sleep(.1)
            self.assertTrue(thread.is_alive(),'publisher failed instead of waiting for active sync')
        finally:release.set();lock_thread.join();thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(results[0]['state'],'unchanged')


if __name__ == '__main__':
    unittest.main()

