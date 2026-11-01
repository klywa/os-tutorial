"""The one-shot bootstrap uses uploaded code and fake system commands only."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
GIT_BASH=Path('C:/Program Files/Git/bin/bash.exe')
BASH=str(GIT_BASH) if os.name=='nt' and GIT_BASH.exists() else shutil.which('bash')


@unittest.skipUnless(BASH,'Bash not available')
class RecoverPublisherTests(unittest.TestCase):
    def run_script(self,*,active='failed',exit_code=0,locked=False,uploaded=True):
        with tempfile.TemporaryDirectory(dir=ROOT/'temp') as folder:
            root=Path(folder);commands=root/'commands';commands.mkdir()
            mocks={'id':'printf "0\\n"','install':'exit 0',
                'flock':f'exit {1 if locked else 0}',
                'systemctl':f'printf "{active}\\n"',
                'runuser':f'printf "%s\\n" "$*" > runner-args\ncat > runner-input\nexit {exit_code}'}
            for name,body in mocks.items():
                path=commands/name;path.write_bytes(('#!/usr/bin/env bash\n'+body+'\n').encode());path.chmod(0o755)
            script=(ROOT/'deploy/recover-os-tutorial-update.sh').read_text(encoding='utf-8')
            (root/'recover.sh').write_bytes(script.replace('/run/lock/update-sites.lock','fixture.lock').encode())
            if uploaded:(root/'os-tutorial-release.py').write_text('# uploaded publisher')
            result=subprocess.run([BASH,'-c','export PATH="$PWD/commands:$PATH"; exec bash recover.sh'],
                cwd=root,capture_output=True,encoding='utf-8',timeout=15)
            return result,((root/'runner-args').read_text() if (root/'runner-args').exists() else ''), \
                ((root/'runner-input').read_text() if (root/'runner-input').exists() else '')

    def test_runs_uploaded_publisher_as_service_user_without_editing_active_source(self):
        result,args,source=self.run_script()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('-u os-tutorial -- /usr/bin/python3 -u -',args)
        self.assertIn('current/frontend',source);self.assertIn('current/deploy',source)
        self.assertIn('runpy.run_path',source)
        self.assertNotIn('write_text',source)

    def test_failure_propagates_and_cannot_claim_recovery_succeeded(self):
        result,args,_=self.run_script(exit_code=7)
        self.assertEqual(result.returncode,7,result.stderr)
        self.assertTrue(args);self.assertNotIn('恢复完成',result.stdout)

    def test_active_publisher_or_other_manual_update_is_never_interrupted(self):
        for kwargs in ({'active':'activating'},{'active':'active'},{'locked':True}):
            with self.subTest(kwargs=kwargs):
                result,args,_=self.run_script(**kwargs)
                self.assertNotEqual(result.returncode,0);self.assertFalse(args)

    def test_missing_upload_stops_before_starting_publisher(self):
        result,args,_=self.run_script(uploaded=False)
        self.assertNotEqual(result.returncode,0);self.assertFalse(args)


if __name__=='__main__':unittest.main()
