"""Private content and viewer boundaries, including conditional/image reads."""
import json
import http.client
import test_website as fixtures


class PrivateAccessTests(fixtures.PublicHttpTests):
    def test_only_hashed_static_assets_are_cached_long_term(self):
        dist=self.root/'dist';(dist/'assets').mkdir(parents=True)
        for name in ('index-Ab12Cd34.js','index-Ab12Cd34.css','unhashed.js'):
            (dist/'assets'/name).write_text('/* fixture */')
        (dist/'index.html').write_text('<html>login</html>')
        self.http.dist=dist
        for path,expected in [('assets/index-Ab12Cd34.js','public, max-age=31536000, immutable'),
                ('assets/index-Ab12Cd34.css','public, max-age=31536000, immutable'),
                ('assets/unhashed.js','no-cache'),('','no-cache')]:
            connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
            connection.request('GET','/os-tutorial/'+path,headers={'Host':'klywa.xyz'})
            response=connection.getresponse();response.read();connection.close()
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers['Cache-Control'],expected)

    def setUp(self):
        super().setUp()
        self.config.write_text(json.dumps({'schema_version': 2, 'sessionSecret': 's'*48,
            'accounts': [{'username': 'klywa', 'password': 'aa2025', 'role': 'admin'},
                         {'username': 'reader', 'password': 'test-password', 'role': 'viewer'}]}))

    def test_every_content_route_requires_login(self):
        for path in ('notes/catalog', 'notes/search?q=x', 'notes/n', 'notes/n/reading',
                     'notes/n/revision', 'options', 'dashboard', 'cards', 'cards/n',
                     'cards/n/images/thumb'):
            with self.subTest(path=path):
                self.assertEqual(self.call('/os-tutorial/api/'+path)[0], 401)
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        conn.request('GET', '/os-tutorial/api/notes/catalog', headers={
            'Host': 'klywa.xyz', 'If-None-Match': '"cached"'})
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        response.read(); conn.close()

    def test_viewer_reads_but_cannot_access_editing_or_elevate(self):
        status, _, headers = self.call('/os-tutorial/api/auth/login', 'POST',
                                      {'username': 'reader', 'password': 'test-password'})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        me = self.call('/os-tutorial/api/auth/me')[1]
        self.assertEqual((me['role'], me['allowed_roles']), ('viewer', ['viewer']))
        for path in ('notes/catalog', 'notes/search?q=x', 'options', 'cards'):
            self.assertEqual(self.call('/os-tutorial/api/'+path)[0], 200)
        for path in ('proposals', 'edit-locks?note_id=n', 'dashboard/usage/matches', 'admin/sync'):
            self.assertEqual(self.call('/os-tutorial/api/'+path)[0], 403)
        for path, method, data in [('notes/n', 'PUT', {}), ('notes', 'POST', {}),
                ('proposals', 'POST', {}), ('edit-locks/acquire', 'POST', {}),
                ('auth/role', 'POST', {'role': 'admin'}), ('auth/role', 'POST', {'role': 'annotator'})]:
            self.assertEqual(self.call('/os-tutorial/api/'+path, method, data)[0], 403)

    def test_admin_can_simulate_viewer_and_restore(self):
        self.login()
        status, data, headers = self.call('/os-tutorial/api/auth/role', 'POST', {'role': 'viewer'})
        self.assertEqual(status, 200)
        self.assertEqual(data['account_role'], 'admin')
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/os-tutorial/api/notes/n', 'PUT', {})[0], 403)
        self.assertEqual(self.call('/os-tutorial/api/auth/role', 'POST', {'role': 'admin'})[0], 200)
