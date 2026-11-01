from contextlib import closing
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontend'))
from website_sync import sync_lock
import update_sites as update

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / 'temp')
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.repo = self.parent / 'pokilot'
        self.repo.mkdir()
        self.git('init', '-b', 'app')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.repo / '.gitignore').write_text('data/\nnode_modules/\n')
        (self.repo / 'code.txt').write_text('old')
        self.git('add', '.'); self.git('commit', '-m', 'initial')
        self.origin = self.parent / 'origin.git'
        subprocess.run(['git','clone','--no-hardlinks','--bare',str(self.repo),str(self.origin)], check=True, capture_output=True)
        self.git('remote','add','origin',str(self.origin))
        (self.repo / 'data').mkdir()
        self.db = self.repo / 'data/pokilot.db'
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('create table notes(body text)')
            conn.execute("insert into notes values ('keep')")
        (self.repo / 'node_modules').mkdir()
        (self.repo / 'node_modules/offline').write_text('old-runtime')
        self.commands = []
    def git(self, *args):
        return subprocess.run(['git','-C',str(self.repo),*args], check=True, capture_output=True, text=True).stdout.strip()
    def advance(self,branch='app'):
        other = self.parent / 'other'
        subprocess.run(['git','clone','--no-hardlinks','--branch',branch,str(self.origin),str(other)],check=True,capture_output=True)
        for args in [('config','user.email','test@example.invalid'),('config','user.name','Test')]:
            subprocess.run(['git','-C',str(other),*args],check=True,capture_output=True)
        (other / 'code.txt').write_text('new')
        for args in [('add','.'),('commit','-m','new'),('push','origin',branch)]:
            subprocess.run(['git','-C',str(other),*args],check=True,capture_output=True)
    def runner(self, args, **kwargs):
        self.commands.append(args)
        if args[0] == 'git':
            return subprocess.run(args, **kwargs)
        output = ''
        if args[:3] == ['systemctl','show','pokilot.service']:
            output = f'WorkingDirectory={self.repo}/apps/web\nEnvironment={shlex.quote("POKILOT_DB="+str(self.db))} NEXT_PUBLIC_BASE_PATH=/pokilot\nUser=pokilot\n'
        return subprocess.CompletedProcess(args, 0, output, '')
    def manager(self, runner=None):
        return update.PokilotUpdater(self.repo, runner=runner or self.runner, health=lambda: True)
    def test_unchanged_does_not_stop_or_install(self):
        self.assertEqual(self.manager().update()['state'], 'unchanged')
        self.assertFalse(any('stop' in args or args[0]=='pnpm' for args in self.commands))

    def master_deployment(self):
        self.git('branch','-m','master')
        self.git('push','--set-upstream','origin','master')

    def test_existing_master_deployment_updates_its_master_without_switching(self):
        self.master_deployment(); self.advance('master')
        upstream=self.git('rev-parse','--abbrev-ref','@{upstream}')
        self.assertEqual(self.manager().update()['state'],'deployed')
        self.assertEqual(self.git('branch','--show-current'),'master')
        self.assertEqual(self.git('rev-parse','--abbrev-ref','@{upstream}'),upstream)
        self.assertEqual((self.repo/'code.txt').read_text(),'new')
        self.assertIn(['git','-C',str(self.repo),'fetch','origin','master'],self.commands)
        self.assertNotIn(['git','-C',str(self.repo),'fetch','origin','app'],self.commands)

    def test_unchanged_master_deployment_does_not_stop_or_build(self):
        self.master_deployment()
        self.assertEqual(self.manager().update()['state'],'unchanged')
        self.assertFalse(any('stop' in args or args[0]=='pnpm' for args in self.commands))

    def test_detached_head_is_rejected_before_fetch_or_stop(self):
        self.git('checkout','--detach')
        with self.assertRaisesRegex(RuntimeError,'分支'):
            self.manager().update()
        self.assertFalse(any('fetch' in args or 'stop' in args for args in self.commands))

    def test_mismatched_upstream_is_rejected_before_fetch_or_stop(self):
        self.git('config','branch.app.remote','origin')
        self.git('config','branch.app.merge','refs/heads/master')
        with self.assertRaisesRegex(RuntimeError,'上游'):
            self.manager().update()
        self.assertFalse(any('fetch' in args or 'stop' in args for args in self.commands))

    def test_branch_change_during_stop_is_rejected_without_changing_code(self):
        self.advance()
        def change_branch(args,**kwargs):
            if args==['systemctl','stop','pokilot.service']:
                self.git('branch','-m','other')
            return self.runner(args,**kwargs)
        with self.assertRaisesRegex(RuntimeError,'分支|变化'):
            self.manager(change_branch).update()
        self.assertEqual((self.repo/'code.txt').read_text(),'old')
        self.assertEqual(self.commands[-1],['systemctl','start','pokilot.service'])
    def test_dirty_tree_aborts_before_fetch_or_stop(self):
        (self.repo / 'code.txt').write_text('local work')
        with self.assertRaisesRegex(RuntimeError, '改动'):
            self.manager().update()
        self.assertFalse(any('fetch' in args or 'stop' in args for args in self.commands))
    def test_build_failure_restores_code_database_and_offline_runtime(self):
        self.advance()
        def fail_build(args, **kwargs):
            if args == ['pnpm','build']:
                with closing(sqlite3.connect(self.db)) as conn, conn:
                    conn.execute("delete from notes")
                (self.repo / 'node_modules/offline').write_text('broken')
                raise RuntimeError('build failed')
            return self.runner(args, **kwargs)
        with self.assertRaisesRegex(RuntimeError, 'build failed'):
            self.manager(fail_build).update()
        self.assertEqual((self.repo / 'code.txt').read_text(), 'old')
        self.assertEqual((self.repo / 'node_modules/offline').read_text(), 'old-runtime')
        with closing(sqlite3.connect(self.db)) as conn, conn:
            self.assertEqual(conn.execute('select body from notes').fetchall(), [('keep',)])
        self.assertTrue(list(self.parent.glob('pokilot-failed-*')))
        self.assertEqual(self.commands[-1], ['systemctl','start','pokilot.service'])
    def test_success_build_receives_explicit_db_and_basepath(self):
        self.advance()
        environments = []
        def runner(args, **kwargs):
            if args[0] == 'pnpm': environments.append((args, kwargs['env']))
            return self.runner(args, **kwargs)
        self.assertEqual(self.manager(runner).update()['state'], 'deployed')
        self.assertEqual((self.repo / 'code.txt').read_text(), 'new')
        self.assertEqual([args for args, env in environments],
                         [['pnpm','install','--frozen-lockfile'],['pnpm','db:migrate'],['pnpm','build']])
        self.assertTrue(all(env['POKILOT_DB']==str(self.db) and env['NEXT_PUBLIC_BASE_PATH']=='/pokilot' for _,env in environments))
    def test_update_merges_only_pinned_validated_sha_after_remote_advances(self):
        self.advance()
        pinned=subprocess.check_output(['git','--git-dir',str(self.origin),'rev-parse','app'],text=True).strip()
        original=self.manager()
        backup=original.backup
        def race(destination,old_head):
            backup(destination,old_head)
            other=self.parent/'other'
            (other/'data').mkdir(exist_ok=True)
            (other/'data/pokilot.db').write_text('remote accidental database')
            for args in [('add','-f','data/pokilot.db'),('commit','-m','bad database'),('push','origin','app')]:
                subprocess.run(['git','-C',str(other),*args],check=True,capture_output=True)
        original.backup=race
        original.update()
        self.assertEqual(self.git('rev-parse','HEAD'),pinned)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('select body from notes').fetchall(),[('keep',)])

    def test_database_added_then_deleted_in_remote_history_is_rejected(self):
        self.advance(); other=self.parent/'other'
        (other/'data').mkdir(exist_ok=True); (other/'data/pokilot.db').write_text('bad')
        for args in [('add','-f','data/pokilot.db'),('commit','-m','track db'),('rm','data/pokilot.db'),('commit','-m','remove db'),('push','origin','app')]:
            subprocess.run(['git','-C',str(other),*args],check=True,capture_output=True)
        with self.assertRaisesRegex(RuntimeError,'数据库'): self.manager().update()
        self.assertFalse(any('stop' in args for args in self.commands))

    def test_build_staging_live_database_triggers_rollback(self):
        self.advance()
        def stage_database(args,**kwargs):
            result=self.runner(args,**kwargs)
            if args==['pnpm','install','--frozen-lockfile']:
                self.git('add','-f','data/pokilot.db')
            return result
        with self.assertRaisesRegex(RuntimeError,'数据库'): self.manager(stage_database).update()
        self.assertEqual((self.repo/'code.txt').read_text(),'old')
        self.assertEqual(self.git('ls-files','--','data/pokilot.db'),'')

    def test_wrong_service_config_never_stops_site(self):
        def runner(args, **kwargs):
            if args[:3] == ['systemctl','show','pokilot.service']:
                return subprocess.CompletedProcess(args, 0, 'WorkingDirectory=/wrong', '')
            return self.runner(args, **kwargs)
        with self.assertRaisesRegex(RuntimeError, '配置'):
            self.manager(runner).update()
        self.assertFalse(any('stop' in args for args in self.commands))

    def test_service_basepath_prefix_is_not_accepted(self):
        def runner(args, **kwargs):
            result = self.runner(args, **kwargs)
            if args[:3] == ['systemctl','show','pokilot.service']:
                result.stdout = result.stdout.replace('/pokilot\n', '/pokilot-other\n')
            return result
        with self.assertRaisesRegex(RuntimeError, '配置'):
            self.manager(runner).update()
        self.assertFalse(any('stop' in args for args in self.commands))

    def test_snapshot_includes_committed_wal_and_approval_receipt(self):
        state = self.parent / 'state'
        state.mkdir()
        source = state / 'proposals.sqlite3'
        with closing(sqlite3.connect(source)) as conn:
            conn.execute('pragma journal_mode=WAL')
            conn.execute('create table proposals(body text)')
            conn.execute("insert into proposals values ('pending')")
            conn.commit()
            (state / 'proposals.sqlite3.approval.json').write_text('{"proposal_id":"one"}')
            (self.repo / 'knowledge').mkdir()
            (self.repo / 'knowledge/note.json').write_text('{"body":"approved"}')
            destination = self.parent / 'snapshot'
            update.snapshot_os(self.repo, state, destination)
            with closing(sqlite3.connect(destination / 'proposals.sqlite3')) as backup:
                self.assertEqual(backup.execute('select body from proposals').fetchall(), [('pending',)])
            self.assertEqual((destination / 'knowledge/note.json').read_text(), '{"body":"approved"}')
            self.assertEqual((destination / 'proposals.sqlite3.approval.json').read_text(), '{"proposal_id":"one"}')
            self.assertFalse((destination / 'proposals.sqlite3-wal').exists())

    def test_os_migration_waits_until_publisher_finishes_and_releases_sync_lock(self):
        import json
        base = self.parent / 'os'
        (base / 'current').mkdir(parents=True)
        state = self.parent / 'state'
        state.mkdir()
        auth = self.parent / 'admins.json'
        auth.write_text(json.dumps({'sessionSecret':'secret','users':[{'username':'owner','password':'keep'}]}))
        actions = []
        def runner(args, **kwargs):
            actions.append(args)
            if args == ['systemctl','start','os-tutorial-update.service']:
                self.assertIn('users', json.loads(auth.read_text()))
                with sync_lock(state):
                    pass  # A held parent lock here would deadlock/fail the child publisher.
            if args == ['systemctl','restart','os-tutorial.service']:
                self.assertEqual(json.loads(auth.read_text())['schema_version'], 2)
            return subprocess.CompletedProcess(args, 0, 'inactive' if 'show' in args else '', '')
        with patch.object(update, 'capability', return_value={'account_role':'guest'}):
            update.update_os(runner=runner, base=base, state_dir=state, auth=auth)
        self.assertEqual(actions[-2:], [['systemctl','start','os-tutorial-update.service'],
                                        ['systemctl','restart','os-tutorial.service']])
        self.assertTrue(list((state / 'update-backups').glob('*/release.txt')))

    @unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0, 'Linux root ownership integration')
    def test_root_snapshots_keep_parent_writable_for_service_owner(self):
        state = self.parent / 'owned-state'
        state.mkdir()
        os.chown(state, 65534, 65534)
        destination = state / 'update-backups/first'
        update.snapshot_os(self.repo, state, destination)
        info = destination.parent.stat()
        self.assertEqual((info.st_uid, info.st_gid, info.st_mode & 0o777), (65534,65534,0o750))
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)

    def test_orchestrator_stops_remaining_apps_on_failure(self):
        calls = []
        def fail():
            calls.append('os'); raise RuntimeError('failed')
        with self.assertRaises(RuntimeError):
            update.update_selected(True, True, fail, lambda: calls.append('pokilot'))
        self.assertEqual(calls, ['os'])
    def test_rollback_after_health_failure(self):
        self.advance()
        manager = self.manager()
        manager.health = lambda: False
        with self.assertRaisesRegex(RuntimeError, '健康'):
            manager.update()
        self.assertEqual((self.repo / 'code.txt').read_text(), 'old')

if __name__ == '__main__': unittest.main()

