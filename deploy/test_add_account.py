import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import add_account


class AddAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / 'temp')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'admins.json'
        self.original = {'schema_version': 2, 'sessionSecret': 'x' * 40,
                         'sessionTtlHours': 48, 'accounts': [
                             {'username': 'owner', 'password': 'original', 'role': 'admin'}]}
        self.path.write_text(json.dumps(self.original), encoding='utf-8')

    def test_add_roles_preserves_config_and_backup(self):
        for role in ('admin', 'annotator'):
            before = self.path.read_bytes()
            backup = add_account.add_account(self.path, role, role, '中文 $ password')
            self.assertEqual(backup.read_bytes(), before)
        value = json.loads(self.path.read_text('utf-8'))
        self.assertEqual(value['accounts'][0], self.original['accounts'][0])
        self.assertEqual(value['sessionSecret'], self.original['sessionSecret'])
        self.assertEqual(value['sessionTtlHours'], 48)
        self.assertEqual([a['role'] for a in value['accounts']], ['admin', 'admin', 'annotator'])
        if os.name != 'nt':
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_invalid_and_duplicate_leave_original_untouched(self):
        before = self.path.read_bytes()
        for args in [('guest', 'new', 'pass'), ('admin', '', 'pass'),
                     ('admin', 'new', ''), ('annotator', 'owner', 'new')]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                add_account.add_account(self.path, *args)
            self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob('*.backup-*')))

    def test_invalid_config_is_not_replaced(self):
        for value in ({'users': []}, {**self.original, 'sessionSecret': 'short'}):
            self.path.write_text(json.dumps(value), encoding='utf-8')
            before = self.path.read_bytes()
            with self.assertRaises(ValueError):
                add_account.add_account(self.path, 'admin', 'new', 'pass')
            self.assertEqual(self.path.read_bytes(), before)

    def test_replace_failure_preserves_original_and_backup(self):
        before = self.path.read_bytes()
        with patch.object(add_account.os, 'replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                add_account.add_account(self.path, 'admin', 'new', 'pass')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(next(self.path.parent.glob('*.backup-*')).read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_concurrent_account_operation_is_rejected(self):
        before = self.path.read_bytes()
        with add_account.account_lock(self.path):
            with self.assertRaisesRegex(ValueError, '操作正在运行'):
                add_account.add_account(self.path, 'admin', 'new', 'pass')
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_three_arguments_and_no_password_output(self):
        with patch.object(add_account, 'CONFIG', self.path), patch('builtins.print') as output:
            self.assertEqual(add_account.main(['annotator', 'writer', 'private-password']), 0)
            self.assertNotIn('private-password', str(output.call_args_list))
            self.assertEqual(add_account.main(['admin', 'writer', 'other-private']), 1)
            self.assertNotIn('other-private', str(output.call_args_list))


if __name__ == '__main__':
    unittest.main()
