import importlib.util
import os
from pathlib import Path
import tempfile
import socket
import subprocess
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LaunchTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'PowerShell wrapper smoke test runs on Windows')
    def test_powershell_entry_from_another_directory(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(HERE.parent / 'start.ps1'), '-Port', str(sock.getsockname()[1]), '-NoBrowser', '-SkipTopicModel'], cwd=HERE, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('occupied', result.stderr)

    def test_port_in_use_does_not_install_or_start(self):
        launcher = load('launch')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            with patch('sys.argv', ['launch', '--port', str(sock.getsockname()[1])]), patch.object(launcher.shutil, 'which', return_value='tool'), patch.object(launcher, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'occupied'):
                    launcher.main()
                self.assertEqual(run.call_count, 1)  # Only the Node version check.

    def test_fresh_install_then_reuse_and_no_browser(self):
        launcher = load('launch')
        with tempfile.TemporaryDirectory(dir=HERE.parent / 'raw') as folder:
            root = Path(folder)
            frontend = root / 'frontend'
            frontend.mkdir()
            (frontend / 'package-lock.json').write_text('{}')
            requirements = root / '.codex/skills/wanxiangqi-knowledge/scripts/requirements.txt'
            requirements.parent.mkdir(parents=True)
            requirements.write_text('example==1')
            commands = []

            def fake_run(command, cwd=None):
                command = list(map(str, command))
                commands.append(command)
                if 'venv' in command:
                    python = root / '.wxq-runtime/Scripts/python.exe'
                    python.parent.mkdir(parents=True)
                    python.touch()
                if 'ci' in command:
                    (frontend / 'node_modules').mkdir()

            with patch('sys.argv', ['launch', '--port', '0']), patch.object(launcher, 'ROOT', root), patch.object(launcher, 'FRONTEND', frontend), patch.object(launcher.shutil, 'which', return_value='tool'), patch.object(launcher, 'run', side_effect=fake_run), patch.object(launcher.subprocess, 'check_output', return_value='win32/x64/24'), patch.object(launcher.os, 'name', 'nt'):
                # Choose a free port without starting the actual service.
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    port = sock.getsockname()[1]
                with patch('sys.argv', ['launch', '--port', str(port), '--no-browser', '--skip-topic-model']):
                    launcher.main()
                    self.assertTrue(any('venv' in command for command in commands))
                    self.assertTrue(any('pip' in command for command in commands))
                    self.assertTrue(any('ci' in command for command in commands))
                    self.assertNotIn('--open-browser', commands[-1])
                    commands.clear()
                    launcher.main()
                    self.assertFalse(any('venv' in command or 'pip' in command or 'ci' in command for command in commands))
                    self.assertTrue(any('build' in command for command in commands))

    def test_mac_model_uses_native_server_and_checks_model(self):
        installer = load('install_topic_model')
        with tempfile.TemporaryDirectory(dir=HERE.parent / 'raw') as folder:
            with patch.object(installer, 'ROOT', Path(folder)), patch.object(installer.sys, 'platform', 'darwin'), patch.object(installer.shutil, 'which', return_value='/opt/homebrew/bin/llama-server'), patch.object(installer, 'download') as download:
                result = installer.install()
                self.assertEqual(result['runtime_executable'], '/opt/homebrew/bin/llama-server')
                self.assertEqual(download.call_count, 1)
                self.assertEqual(download.call_args.args[2], installer.MODEL_SHA)

    def test_mac_missing_runtime_fails_before_download(self):
        installer = load('install_topic_model')
        with patch.object(installer.sys, 'platform', 'darwin'), patch.object(installer.shutil, 'which', return_value=None), patch.object(installer, 'download') as download:
            with self.assertRaisesRegex(RuntimeError, 'llama.cpp'):
                installer.install()
            download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
