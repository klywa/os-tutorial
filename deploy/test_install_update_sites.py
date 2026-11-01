"""Exercise bootstrap failure recovery with fake system commands only."""
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
class InstallerRecoveryTests(unittest.TestCase):
    def run_installer(self,*args):
        base=ROOT/'temp'; base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory); commands=root/'commands'; commands.mkdir()
            mocks={
                'id':'printf "0\\n"',
                'install':'exit 0',
                'flock':'exit 0',
                'sleep':'printf "sleep %s\\n" "$*" >> events',
                'systemctl':'printf "systemctl %s\\n" "$*" >> events\n'
                            'if [ "$*" = "start os-tutorial-update.service" ]; then exit 7; fi',
            }
            for name,body in mocks.items():
                path=commands/name
                path.write_bytes(('#!/usr/bin/env bash\n'+body+'\n').encode())
                path.chmod(0o755)
            script=(ROOT/'deploy/install-update-sites.sh').read_text(encoding='utf-8')
            # Redirect the only pre-bootstrap file write into this fixture.
            (root/'installer.sh').write_bytes(script.replace('/run/lock/update-sites.lock','fixture.lock').encode())
            result=subprocess.run([BASH,'-c','export PATH="$PWD/commands:$PATH"; exec bash installer.sh "$@"',
                                   'fixture',*args],cwd=root,env=os.environ.copy(),
                                  capture_output=True,text=True,encoding='utf-8',timeout=15)
            events=(root/'events').read_text() if (root/'events').exists() else ''
            return result,events.splitlines()

    def test_recovery_restarts_website_on_bootstrap_failure_and_keeps_exit_status(self):
        result,events=self.run_installer('--recover-port')
        self.assertEqual(result.returncode,7,result.stdout+result.stderr)
        self.assertEqual(events,['systemctl stop os-tutorial.service','sleep 70',
                                 'systemctl start os-tutorial-update.service',
                                 'systemctl start os-tutorial.service'])

    def test_normal_install_failure_does_not_stop_website(self):
        result,events=self.run_installer()
        self.assertEqual(result.returncode,7,result.stdout+result.stderr)
        self.assertEqual(events,['systemctl start os-tutorial-update.service'])

    def test_unknown_option_does_not_touch_services(self):
        result,events=self.run_installer('--unknown')
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        self.assertEqual(events,[])


if __name__=='__main__':
    unittest.main()
