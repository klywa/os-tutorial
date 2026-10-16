import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import sys

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
import wxq
import workspace
spec = importlib.util.spec_from_file_location('frontend_server', ROOT / 'frontend/server.py')
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.wxq-runtime/test-temp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        wxq.init_store(self.root)
        workspace.migrate(self.root)
        self.server = server_module.create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/'

    def test_registration_and_read(self):
        request = Request(self.url + 'sources', json.dumps({'url':'https://example.com/video','title':'人工来源','notes':'提取后期策略'}).encode(), {'Content-Type':'application/json'})
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
        with urlopen(self.url + 'sources') as response:
            source = json.load(response)[0]
            self.assertEqual(source['knowledge_status'], 'unprocessed')
            self.assertEqual(source['notes'], '提取后期策略')

    def test_reading_endpoint_uses_current_revision_and_preserves_legacy_notes(self):
        wxq.commit_notes(self.root, [{'id':'yaomei-sacrifice-lixin','type':'lineup','title':'李信','claims':[],'entities':[]},
                                     {'id':'legacy','type':'other','title':'旧笔记','claims':[],'entities':[]}])
        with urlopen(self.url + 'notes/yaomei-sacrifice-lixin/reading') as response:
            reading = json.load(response)
        note = next(n for n in workspace.notes(self.root) if n['id']=='yaomei-sacrifice-lixin')
        self.assertEqual(reading['revision'],note['revision'])
        self.assertEqual(len(reading['sections']),10)
        workspace.edit(self.root,note['id'],{'revision':note['revision'],'sections':{'新修订':'新的人工建议'}})
        with urlopen(self.url + 'notes/yaomei-sacrifice-lixin/reading') as response:
            updated=json.load(response)
        self.assertNotEqual(updated['revision'],reading['revision'])
        self.assertIn('新的人工建议',''.join(s['markdown'] for s in updated['sections']))
        with urlopen(self.url + 'notes/legacy/reading') as response:
            self.assertIsNone(json.load(response)['profile'])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + 'notes/missing/reading')
        self.assertEqual(error.exception.code,404)

    def test_cards_summary_detail_and_unknown_id(self):
        from reference_store import export_cards
        wxq.atomic_json(self.root / 'entities/equipment.json', [{
            'id': 'card:10', 'name': '装备', 'category': 'equipment',
            'description': '回复生命', 'properties': {'type': 5}, 'sources': []}])
        export_cards(self.root)
        with urlopen(self.url + 'cards') as response:
            summaries = json.load(response)
            self.assertEqual(summaries[0]['effect'], '回复生命')
            self.assertNotIn('raw_attributes', summaries[0])
        with urlopen(self.url + 'cards/card%3A10') as response:
            self.assertEqual(json.load(response)['stats'], {})
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + 'cards/card%3Amissing')
        self.assertEqual(error.exception.code, 404)

    def test_parallel_reads_do_not_compete_for_write_lock(self):
        def read(path):
            with urlopen(self.url + path) as response:
                return response.status
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(list(pool.map(read, ['notes', 'sources', 'options'])), [200, 200, 200])

    def test_reject_cross_origin_and_invalid_body(self):
        request = Request(self.url + 'sources', b'{}', {'Content-Type':'application/json','Origin':'https://evil.example'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)
        request = Request(self.url + 'sources', b'{}', {'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)

    def test_edit_conflict_http(self):
        wxq.commit_notes(self.root, [{'id':'manual','type':'other','title':'手工笔记','claims':[],'entities':[]}])
        note = workspace.notes(self.root)[0]
        body = {'revision':note['revision'],'sections':{'知识内容':'自己的操作心得'}}
        request = Request(self.url + 'notes/manual', json.dumps(body).encode(), {'Content-Type':'application/json'}, method='PUT')
        with urlopen(request) as response:
            self.assertEqual(json.load(response)['claims'][0]['origin'], 'manual')
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 409)
