import json
import os
from pathlib import Path
import tempfile
import unittest
import configure_roles as roles

class RoleMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parents[1] / 'temp')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'admins.json'
        self.legacy = {'sessionSecret':'original-secret', 'sessionTtlHours':168,
                       'users':[{'username':'owner','password':'old-password'}]}
        self.path.write_text(json.dumps(self.legacy))
    def test_migration_preserves_credentials_removes_legacy_and_is_idempotent(self):
        self.assertTrue(roles.migrate(self.path, {'account_role': 'guest'}))
        value = json.loads(self.path.read_text())
        self.assertEqual(value, {'schema_version':2,'sessionSecret':'original-secret','sessionTtlHours':168,
            'accounts':[{'username':'owner','password':'old-password','role':'admin'},
                        {'username':'test1','password':'aa2025','role':'annotator'}]})
        backups = list(self.path.parent.glob('admins.json.backup-*'))
        self.assertEqual(json.loads(backups[0].read_text()), self.legacy)
        self.assertFalse(roles.migrate(self.path, {'allowed_roles':['guest']}))
        self.assertEqual(list(self.path.parent.glob('admins.json.backup-*')), backups)
    def test_old_server_cannot_trigger_migration(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '角色'):
            roles.migrate(self.path, {'role':'guest'})
        self.assertEqual(self.path.read_bytes(), before)
    def test_existing_test1_admin_is_never_silently_downgraded(self):
        self.legacy['users'].append({'username':'test1','password':'existing'})
        self.path.write_text(json.dumps(self.legacy))
        with self.assertRaisesRegex(ValueError, 'test1'):
            roles.migrate(self.path, {'account_role':'guest'})
        self.assertEqual(json.loads(self.path.read_text()), self.legacy)

if __name__ == '__main__': unittest.main()
