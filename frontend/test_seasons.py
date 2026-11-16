import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest
from pathlib import Path

import server
import json_store
import reader_store
import dashboard
import seasons
from migrate_note_seasons import migrate


class SeasonTests(unittest.TestCase):
    def test_membership_and_scoped_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            json_store.initialize(root)
            def create(title, values=None):
                payload = dict(type='other', title=title, request_id='request-'+str(sum(map(ord,title))))
                if values is not None:
                    payload['seasons'] = values
                return json_store.create(root, payload)
            a = create('甲笔记')
            b = create('乙笔记', ['S2'])
            c = create('丙笔记', ['S2', 'S1'])
            self.assertEqual(a['seasons'], ['S1'])
            self.assertEqual(c['seasons'], ['S1', 'S2'])
            self.assertEqual({n['id'] for n in seasons.catalog(reader_store.catalog(root), 'S2')['notes']}, {b['id'], c['id']})
            self.assertIsNone(seasons.note(root, a['id'], 'S2'))
            self.assertEqual(seasons.note(root, b['id'], 'S2')['id'], b['id'])
            with self.assertRaises(ValueError):
                create('无效笔记', [])
            saved = json_store.edit(root, b['id'], dict(revision=b['revision'], seasons=['S1', 'S2']))
            self.assertEqual(saved['seasons'], ['S1', 'S2'])
            self.assertEqual(dashboard.snapshot(root, season='S2')['counts']['lineup'], 0)


    def test_backfill_preserves_body_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            json_store.initialize(root)
            note = json_store.create(root, dict(type='other', title='旧笔记', request_id='legacy-test'))
            index = json_store.read(root / json_store.INDEX)
            index['notes'][0].pop('seasons')
            json_store.write_file(root / json_store.INDEX, index)
            body = root / note['path']
            before = body.read_bytes()
            path = root / json_store.meta_path(note['path'])
            metadata = json_store.read(path)
            metadata.pop('seasons')
            json_store.write_file(path, metadata)
            self.assertEqual(migrate(root), 1)
            self.assertEqual(migrate(root), 0)
            self.assertEqual(json_store.read(path)['seasons'], ['S1'])
            self.assertEqual(json_store.read(root / json_store.INDEX)['notes'][0]['id'], note['id'])
            self.assertEqual(body.read_bytes(), before)

    def test_local_http_scopes_reads_and_protects_s1_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            json_store.initialize(root)
            a = json_store.create(root, dict(type='other', title='甲攻略', request_id='season-aa'))
            b = json_store.create(root, dict(type='other', title='乙攻略', request_id='season-bb', seasons=['S2']))
            reader_store.rebuild(root)
            http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            http.root = root
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{http.server_port}/api/'
                def get(path):
                    with urlopen(base + path, timeout=5) as result:
                        return json.load(result)
                self.assertEqual([n['id'] for n in get('notes/catalog')['notes']], [a['id']])
                self.assertEqual([n['id'] for n in get('notes/catalog?season=S2')['notes']], [b['id']])
                self.assertEqual(get('notes/search?season=S2')['ids'], [b['id']])
                self.assertEqual(get(f"notes/{b['id']}/reading?season=S2")['note_id'], b['id'])
                self.assertEqual(get('cards?season=S2'), [])
                self.assertEqual(get('templates?season=S2')['groups'], [])
                self.assertFalse(get('dashboard?scope=usage_top10&season=S2')['usage']['ready'])
                for path, status in ((f"notes/{a['id']}?season=S2", 404),
                                     (f"notes/{b['id']}/revision", 404), ('notes/catalog?season=', 400)):
                    with self.assertRaises(HTTPError) as error:
                        get(path)
                    self.assertEqual(error.exception.code, status)
                for path in ('dashboard/usage/refresh', 'templates/changes'):
                    request = Request(base + path + '?season=S2', data=b'{}',
                                      headers={'Content-Type': 'application/json'})
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request, timeout=5)
                    self.assertEqual(error.exception.code, 400)
            finally:
                http.shutdown()
                http.server_close()
