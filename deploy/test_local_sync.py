"""Local synchronization tests use temporary Git remotes and a fake local service."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO
import urllib.error
import local_sync as sync
from website_data import verify_package

class Service:
    def __init__(self): self.active=True; self.events=[]; self.fail_stop=False; self.fail_start=False
    def running(self): return self.active
    def stop(self):
        self.events.append('stop')
        self.active=False
        if self.fail_stop: raise RuntimeError('stop failed after response')
    def restart(self):
        self.events.append('restart')
        if self.fail_start: raise RuntimeError('restart failed')
        self.active=True

class LocalSyncTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[1]/'temp'; base.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.root=self.base/'local'; self.root.mkdir()
        self.git(self.root,'init','-b','master'); self.identity(self.root)
        (self.root/'.gitignore').write_text('raw/\nfrontend/dist/\nfrontend/node_modules/\n')
        (self.root/'knowledge/players').mkdir(parents=True)
        (self.root/'knowledge/players/one.json').write_text('{"body":"original"}')
        (self.root/'frontend').mkdir(); (self.root/'frontend/server.py').write_text('# original\n')
        self.git(self.root,'add','.'); self.git(self.root,'commit','-m','initial')
        self.origin=self.base/'origin.git'
        self.git(self.base,'clone','--no-hardlinks','--bare',str(self.root),str(self.origin))
        self.git(self.root,'remote','add','origin',str(self.origin))
        self.service=Service(); self.validated=[]; self.builds=[]
    def git(self,root,*args):
        result=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,encoding='utf-8')
        if result.returncode: raise RuntimeError(result.stderr)
        return result.stdout.strip()
    def identity(self,root):
        self.git(root,'config','user.name','Test'); self.git(root,'config','user.email','test@example.invalid')
    def other(self):
        other=self.base/'other'; self.git(self.base,'clone','--no-hardlinks',str(self.origin),str(other)); self.identity(other)
        return other
    def remote_note(self,body):
        other=self.other(); (other/'knowledge/players/one.json').write_text(json.dumps({'body':body}))
        self.git(other,'add','.'); self.git(other,'commit','-m','remote'); self.git(other,'push','origin','master')
    def manager(self):
        def validate(root,export=False):
            self.validated.append((root,export))
            value=json.loads((root/'knowledge/players/one.json').read_text())
            if value['body']=='invalid': raise ValueError('invalid formal index')
        manager=sync.LocalSync(self.root,service=self.service,validate=validate,build=lambda paths,root:self.builds.append(paths))
        manager.recover=lambda: None
        return manager
    def test_publish_merges_remote_and_pushes_only_formal_files(self):
        self.remote_note('online')
        (self.root/'frontend/server.py').write_text('# local code\n')
        (self.root/'raw').mkdir(); (self.root/'raw/proposals.sqlite3').write_text('private')
        self.assertEqual(self.manager().publish()['state'],'published')
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'online')
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),self.git(self.origin,'rev-parse','master'))
        self.assertNotIn('raw/',self.git(self.origin,'ls-tree','-r','--name-only','master'))
        self.assertEqual(self.service.events,['stop','restart'])
    def test_invalid_remote_never_reaches_local_tree_or_remote_push(self):
        self.remote_note('invalid'); remote_before=self.git(self.origin,'rev-parse','master')
        (self.root/'frontend/server.py').write_text('# safe local\n')
        with self.assertRaisesRegex(ValueError,'invalid formal index'): self.manager().publish()
        self.assertEqual(self.git(self.origin,'rev-parse','master'),remote_before)
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'original')
        self.assertEqual(self.service.events,['stop','restart']); self.assertTrue(self.service.active)
        self.assertTrue(list((self.root/'raw/local-sync/candidates').iterdir()))
    def test_pull_dirty_refuses_before_stopping(self):
        (self.root/'frontend/server.py').write_text('# unsaved\n')
        with self.assertRaisesRegex(RuntimeError,'改动'): self.manager().pull()
        self.assertEqual(self.service.events,[])
    def test_pull_no_update_never_stops_or_builds(self):
        self.assertEqual(self.manager().pull()['state'],'unchanged')
        self.assertEqual(self.service.events,[]); self.assertEqual(self.builds,[])
    def test_pull_updates_notes_and_restarts_previously_running_service(self):
        self.remote_note('online')
        self.assertEqual(self.manager().pull()['state'],'updated')
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'online')
        self.assertEqual(self.service.events,['stop','restart'])
    def test_recovered_dirty_journal_blocks_pull_and_restores_service(self):
        self.remote_note('online'); manager=self.manager()
        def recover(): (self.root/'knowledge/players/one.json').write_text('{"body":"recovered local"}')
        manager.recover=recover
        with self.assertRaisesRegex(RuntimeError,'改动'): manager.pull()
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'recovered local')
        self.assertTrue(self.service.active)
    def test_no_running_service_is_not_started_by_pull(self):
        self.remote_note('online'); self.service.active=False
        self.manager().pull(); self.assertEqual(self.service.events,[])
    def test_stop_failure_restores_previously_running_service(self):
        self.service.fail_stop=True
        with self.assertRaisesRegex(RuntimeError,'stop failed'): self.manager().publish()
        self.assertTrue(self.service.active); self.assertEqual(self.service.events,['stop','restart'])
    def test_restart_failure_is_reported_without_losing_local_commit(self):
        (self.root/'frontend/server.py').write_text('# safe local\n'); self.service.fail_start=True
        with self.assertRaisesRegex(RuntimeError,'restart failed'): self.manager().publish()
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),self.git(self.origin,'rev-parse','master'))
        self.assertIn('safe local',(self.root/'frontend/server.py').read_text())
    def test_existing_private_local_commit_cannot_be_pushed_by_publish(self):
        (self.root/'secret.txt').write_text('private')
        self.git(self.root,'add','secret.txt'); self.git(self.root,'commit','-m','private local commit')
        before=self.git(self.origin,'rev-parse','master')
        with self.assertRaisesRegex(RuntimeError,'白名单'):
            self.manager().publish()
        self.assertEqual(self.git(self.origin,'rev-parse','master'),before)
        self.assertTrue(self.service.active)

    def test_deleted_private_history_is_not_uploaded(self):
        (self.root/'secret.txt').write_text('sensitive blob')
        self.git(self.root,'add','secret.txt'); self.git(self.root,'commit','-m','private addition')
        self.git(self.root,'rm','secret.txt'); self.git(self.root,'commit','-m','remove secret')
        before=self.git(self.origin,'rev-parse','master')
        with self.assertRaisesRegex(RuntimeError,'白名单'): self.manager().publish()
        self.assertEqual(self.git(self.origin,'rev-parse','master'),before)

    def test_failed_candidate_build_never_changes_active_code_or_runtime(self):
        self.remote_note('online')
        (self.root/'frontend/dist').mkdir()
        (self.root/'frontend/dist/index.html').write_text('old usable UI')
        before=self.git(self.root,'rev-parse','HEAD')
        manager=self.manager()
        def fail(paths, root):
            self.assertNotEqual(root,self.root)
            (root/'frontend/dist').mkdir(parents=True,exist_ok=True)
            (root/'frontend/dist/index.html').write_text('partial broken UI')
            raise RuntimeError('candidate build failed')
        manager.build=fail
        with self.assertRaisesRegex(RuntimeError,'candidate build failed'): manager.pull()
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),before)
        self.assertEqual((self.root/'frontend/dist/index.html').read_text(),'old usable UI')
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'original')
        self.assertTrue(self.service.active)

    def test_publish_build_failure_keeps_remote_and_remote_code_out_of_active(self):
        self.remote_note('online')
        before=self.git(self.origin,'rev-parse','master')
        (self.root/'frontend/server.py').write_text('# local work')
        manager=self.manager()
        def fail(paths,root): raise RuntimeError('candidate build failed')
        manager.build=fail
        with self.assertRaisesRegex(RuntimeError,'candidate build failed'): manager.publish()
        self.assertEqual(self.git(self.origin,'rev-parse','master'),before)
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'original')
        self.assertIn('local work',(self.root/'frontend/server.py').read_text())
        self.assertTrue(self.service.active)

    def test_activation_failure_restores_old_dist_and_modules_without_reset(self):
        manager=self.manager()
        candidate=self.root/'raw/candidate'
        for base,label in ((self.root,'old'),(candidate,'new')):
            for name in ('dist','node_modules'):
                (base/'frontend'/name).mkdir(parents=True,exist_ok=True)
                (base/'frontend'/name/'value').write_text(label)
        before=self.git(self.root,'rev-parse','HEAD')
        with patch.object(manager,'git',side_effect=RuntimeError('ff refused')):
            with self.assertRaisesRegex(RuntimeError,'ff refused'):
                manager.activate(candidate,'unreachable',['dist','node_modules'])
        for name in ('dist','node_modules'):
            self.assertEqual((self.root/'frontend'/name/'value').read_text(),'old')
            self.assertEqual((candidate/'frontend'/name/'value').read_text(),'new')
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),before)

    def test_true_stop_timeout_never_changes_git_and_recovery_waits_known_instance(self):
        clock=[0.0]
        service=sync.LocalService(self.root,stop_timeout=2,clock=lambda:clock[0],sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
        manager=self.manager(); manager.service=service
        response=BytesIO(b''); response.status=202
        restored=[]
        def restore():
            service.wait_stopped()
            restored.append(True)
        before=self.git(self.root,'rev-parse','HEAD')
        with patch.object(service,'running',return_value=True), patch.object(service,'occupied',side_effect=lambda:clock[0]<3), patch.object(service,'restart',side_effect=restore), patch.object(sync.urllib.request,'urlopen',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'超时'): manager.publish()
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),before)
        self.assertEqual(restored,[True]); self.assertFalse(service.stopping)
        self.assertFalse((self.root/'raw/local-sync/candidates').exists())

    def test_activation_success_switches_runtime_and_fast_forwards_code(self):
        manager=self.manager()
        self.remote_note('online')
        manager.git('fetch','origin','master')
        target=manager.git('rev-parse','FETCH_HEAD')
        candidate=self.root/'raw/candidate'
        for base,label in ((self.root,'old'),(candidate,'new')):
            for name in ('dist','node_modules'):
                (base/'frontend'/name).mkdir(parents=True,exist_ok=True)
                (base/'frontend'/name/'value').write_text(label)
        manager.activate(candidate,target,['dist','node_modules'])
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),target)
        for name in ('dist','node_modules'):
            self.assertEqual((self.root/'frontend'/name/'value').read_text(),'new')
        self.assertEqual(json.loads((self.root/'knowledge/players/one.json').read_text())['body'],'online')

    def test_staged_private_file_is_not_committed(self):
        (self.root/'secret.txt').write_text('not formal'); self.git(self.root,'add','secret.txt')
        (self.root/'frontend/server.py').write_text('# safe local\n')
        self.manager().publish()
        self.assertNotIn('secret.txt',self.git(self.origin,'ls-tree','-r','--name-only','master'))
        self.assertIn('secret.txt',self.git(self.root,'diff','--cached','--name-only'))

    def package(self, root):
        folder=root/'website-data'; folder.mkdir(exist_ok=True)
        payloads={'cards.json':'[\n  {"name":"中文卡牌"}\n]\n'.encode('utf-8'),
                  'images/example.img':b'\x89PNG\r\n\x1a\noriginal\r\nimage'}
        for name,body in payloads.items():
            path=folder/name; path.parent.mkdir(exist_ok=True)
            path.write_bytes(body)
        (folder/'manifest.json').write_bytes(json.dumps({'schema_version':1,'files':{
            name:hashlib.sha256(body).hexdigest() for name,body in payloads.items()
        }}).encode('utf-8'))
        return payloads

    def autocrlf_environment(self):
        config=self.base/'global.gitconfig'
        config.write_text('[core]\n autocrlf = true\n',encoding='utf-8')
        return patch.dict(os.environ,{'GIT_CONFIG_GLOBAL':str(config),'GIT_CONFIG_NOSYSTEM':'1'})

    def test_candidate_preserves_package_bytes_with_global_autocrlf(self):
        payloads=self.package(self.root)
        self.git(self.root,'add','website-data'); self.git(self.root,'commit','-m','offline package')
        with self.autocrlf_environment():
            candidate=self.manager().candidate()
        verify_package(candidate)
        for name,body in payloads.items():
            self.assertEqual((candidate/'website-data'/name).read_bytes(),body)
        self.assertEqual(self.git(candidate,'config','--local','core.autocrlf'),'false')

    def test_package_attributes_preserve_bytes_for_normal_autocrlf_clone(self):
        (self.root/'.gitattributes').write_bytes((sync.ROOT/'.gitattributes').read_bytes())
        payloads=self.package(self.root)
        self.git(self.root,'add','.'); self.git(self.root,'commit','-m','package attributes')
        clone=self.base/'normal-clone'
        with self.autocrlf_environment():
            self.git(self.base,'clone','--no-hardlinks',str(self.root),str(clone))
        verify_package(clone)
        for name,body in payloads.items():
            self.assertEqual((clone/'website-data'/name).read_bytes(),body)

    def test_publish_package_with_autocrlf_and_reject_real_corruption(self):
        payloads=self.package(self.root)
        manager=self.manager()
        manager.validate=lambda root,export=False:verify_package(root)
        with self.autocrlf_environment():
            self.assertEqual(manager.publish()['state'],'published')
        self.assertEqual(self.git(self.root,'rev-parse','HEAD'),self.git(self.origin,'rev-parse','master'))
        (self.root/'website-data/cards.json').write_bytes(payloads['cards.json']+b'corruption')
        with self.assertRaisesRegex(ValueError,'cards.json'):
            verify_package(self.root)

    def test_pull_package_with_autocrlf_preserves_verified_active_bytes(self):
        other=self.other()
        (other/'.gitattributes').write_bytes((sync.ROOT/'.gitattributes').read_bytes())
        payloads=self.package(other)
        self.git(other,'add','.'); self.git(other,'commit','-m','remote offline package')
        self.git(other,'push','origin','master')
        manager=self.manager()
        manager.validate=lambda root,export=False:verify_package(root)
        with self.autocrlf_environment():
            self.assertEqual(manager.pull()['state'],'updated')
        verify_package(self.root)
        for name,body in payloads.items():
            self.assertEqual((self.root/'website-data'/name).read_bytes(),body)

    def test_child_python_output_and_errors_are_utf8(self):
        manager=self.manager()
        environment={**os.environ,'PYTHONUTF8':'0','PYTHONIOENCODING':'cp936','SYNC_TEST_VALUE':'保留环境'}
        message='中文校验错误：cards.json'
        output=manager.run([sys.executable,'-c','import os; print(os.environ["SYNC_TEST_VALUE"])'],env=environment)
        self.assertEqual(output,'保留环境')
        with self.assertRaisesRegex(RuntimeError,message):
            manager.run([sys.executable,'-c',f'import sys; sys.stderr.write({message!r}); sys.exit(1)'],env=environment)

    def test_duplicate_cli_keeps_lock_and_reports_friendly_message(self):
        directory=self.root/'raw/local-sync'
        with sync.sync_lock(directory):
            with patch.object(sys,'argv',['local_sync.py','publish','--root',str(self.root)]), \
                    patch.object(sync.LocalSync,'publish') as publish, \
                    patch.object(sync.logging,'FileHandler',return_value=sync.logging.NullHandler()), \
                    self.assertLogs(level='ERROR') as logs:
                self.assertEqual(sync.main(),1)
            publish.assert_not_called()
            self.assertTrue((directory/'sync.lock').exists())
        text='\n'.join(logs.output)
        self.assertIn('另一项同步正在运行，请等待',text)
        self.assertNotIn('Traceback',text)
        with sync.sync_lock(directory):
            pass

class LocalServiceTests(unittest.TestCase):
    def test_foreign_workspace_never_receives_stop_request(self):
        service=sync.LocalService(Path(__file__).parents[1])
        response=BytesIO(json.dumps({'mode':'local','root':str(Path(__file__).parent),'port':8765}).encode())
        with patch.object(sync.urllib.request,'urlopen',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'其他项目'):
                service.running()

    def test_old_service_requires_manual_upgrade_instead_of_process_kill(self):
        service=sync.LocalService(Path(__file__).parents[1])
        error=urllib.error.HTTPError(service.url,404,'missing',{},None)
        with patch.object(sync.urllib.request,'urlopen',side_effect=error), patch.object(service,'occupied',return_value=True):
            with self.assertRaisesRegex(RuntimeError,r'Ctrl\+C'):
                service.running()

    def test_graceful_stop_can_wait_longer_than_ten_seconds(self):
        clock=[0.0]
        service=sync.LocalService(Path(__file__).parents[1],stop_timeout=600,clock=lambda:clock[0],sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
        response=BytesIO(b''); response.status=202
        with patch.object(sync.urllib.request,'urlopen',return_value=response), patch.object(service,'occupied',side_effect=lambda:clock[0]<25):
            service.stop()
        self.assertGreaterEqual(clock[0],25)
        self.assertFalse(service.stopping)

    def test_confirmed_stop_timeout_remains_stopping_for_recovery(self):
        clock=[0.0]
        service=sync.LocalService(Path(__file__).parents[1],stop_timeout=2,clock=lambda:clock[0],sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
        response=BytesIO(b''); response.status=202
        with patch.object(sync.urllib.request,'urlopen',return_value=response), patch.object(service,'occupied',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'超时'): service.stop()
        self.assertTrue(service.stopping)
        with patch.object(service,'occupied',return_value=False):
            service.wait_stopped()
        self.assertFalse(service.stopping)

    def test_missing_service_is_not_confused_with_old_unsupported_service(self):
        service=sync.LocalService(Path(__file__).parents[1])
        with patch.object(sync.urllib.request,'urlopen',side_effect=urllib.error.URLError('refused')), patch.object(service,'occupied',return_value=False):
            self.assertFalse(service.running())

if __name__=='__main__': unittest.main()
