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
    def test_static_preview_remains_available_during_knowledge_save(self):
        with workspace.store_lock(self.root,wait=True):
            with urlopen(self.url.removesuffix('api/'),timeout=5) as response:
                self.assertEqual(response.status,200)
                self.assertIn(b'<html',response.read())

    def test_lineup_batch_delete_restore_api(self):
        def send(path,payload,method='POST'):
            with urlopen(Request(self.url+path,json.dumps(payload).encode(),{'Content-Type':'application/json'},method=method)) as response:return json.load(response)
        rows=send('topics/lineups',{'name':'测试阵容','heroes':[]});row=rows[0]
        saved=send('topics/lineups/batch',{'items':[{'id':row['id'],'revision':row['revision'],'common_name':'常用名','aliases':['别名']}]},'PUT')[0]
        with self.assertRaises(HTTPError) as conflict:send('topics/lineups/batch',{'items':[{'id':row['id'],'revision':row['revision'],'common_name':'旧修改'}]},'PUT')
        self.assertEqual(conflict.exception.code,409);self.assertEqual(json.load(conflict.exception)['lineup_ids'],[row['id']])
        deleted=send('topics/lineups/'+row['id'],{'revision':saved['revision']},'DELETE')[0];self.assertTrue(deleted['deleted_at'])
        restored=send('topics/lineups/'+row['id']+'/restore',{'revision':deleted['revision']})[0];self.assertFalse(restored['deleted_at']);self.assertEqual(restored['common_name'],'常用名')
    def test_source_edit_revision_and_transcript_api(self):
        def send(path,payload,method='POST'):
            with urlopen(Request(self.url+path,json.dumps(payload).encode(),{'Content-Type':'application/json'},method=method)) as response:return json.load(response)
        source=send('sources',{'url':'https://example.com/edit','title':'原标题'})
        with urlopen(self.url+'sources') as response:row=json.load(response)[0]
        sid=source['id']
        saved=send('sources/'+sid,{'revision':row['revision'],'title':'人工题','author':'','keywords':['标签']},'PUT')
        self.assertEqual(saved['title'],'人工题')
        with self.assertRaises(HTTPError) as stale:send('sources/'+sid,{'revision':row['revision'],'title':'过期'},'PUT')
        self.assertEqual(stale.exception.code,409)
        wxq.atomic_text(self.root/'raw/api-transcript.md','原文')
        wxq.atomic_json(self.root/'raw/index.json',{'sources':{sid:{'path':'raw/api-transcript.md'}}})
        with urlopen(self.url+'sources/'+sid+'/transcript') as response:before=json.load(response)
        text=send('sources/'+sid+'/transcript',{'revision':before['revision'],'text':'人工文字稿'},'PUT')
        self.assertTrue(text['manual_edit'])
        with self.assertRaises(HTTPError) as conflict:send('sources/'+sid+'/transcript',{'revision':before['revision'],'text':'过期'},'PUT')
        self.assertEqual(conflict.exception.code,409)

    def test_creator_edit_delete_and_late_save(self):
        def request(path, data=None, method='POST'):
            return urlopen(Request(self.url+path, json.dumps(data or {}).encode(), {'Content-Type':'application/json'},method=method))
        with request('crawler/creators',{'url':'https://space.bilibili.com/123','name':'test','date_from':'2026-09-10'}) as response:
            creator=json.load(response)
        with request('crawler/creators/123',{**creator,'name':'edited'},'PUT') as response:
            self.assertEqual(json.load(response)['name'],'edited')
        with request('crawler/creators/123',method='DELETE') as response:
            self.assertEqual(json.load(response)['deleted'],'123')
        with self.assertRaises(HTTPError) as caught:
            request('crawler/creators/123',creator,'PUT')
        self.assertEqual(caught.exception.code,404)

    def test_creator_create_is_unique_and_does_not_overwrite(self):
        def send(payload, method='POST', suffix=''):
            req=Request(self.url+'crawler/creators'+suffix,json.dumps(payload).encode(),{'Content-Type':'application/json'},method=method)
            with urlopen(req) as response:
                return json.load(response)
        original={'url':'https://space.bilibili.com/3632302133348552','name':'同名','date_from':'2026-09-10','keywords':['李信'],'enabled':False}
        creator=send(original)
        self.assertIsInstance(creator['uid'],str)
        with self.assertRaises(HTTPError) as caught:
            send({**creator,'name':'不能覆盖','enabled':True})
        self.assertEqual(caught.exception.code,409)
        self.assertEqual(json.load(caught.exception)['uid'],creator['uid'])
        send({**original,'url':'https://space.bilibili.com/456'})
        with urlopen(self.url+'crawler/creators') as response:
            rows=json.load(response)
        self.assertEqual(len(rows),2)
        self.assertEqual(len(server_module.crawler.Store(self.root).creators()),2)
        self.assertEqual(next(r for r in rows if r['uid']==creator['uid'])['name'],'同名')
        self.assertFalse(next(r for r in rows if r['uid']==creator['uid'])['enabled'])
        with self.assertRaises(HTTPError) as changed:
            send({**creator,'url':'https://space.bilibili.com/456'},'PUT','/'+creator['uid'])
        self.assertEqual(changed.exception.code,400)

    def test_concurrent_creator_create_has_one_winner(self):
        def create(_):
            req=Request(self.url+'crawler/creators',json.dumps({'url':'https://space.bilibili.com/123','name':'并发','date_from':'2026-09-10'}).encode(),{'Content-Type':'application/json'})
            try:
                with urlopen(req) as response:return response.status
            except HTTPError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(create,range(2))),[200,409])

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

    def test_crawler_search_preview_stop_resume_and_creators(self):
        def send(path,payload,method='POST'):
            request=Request(self.url+path,json.dumps(payload).encode(),{'Content-Type':'application/json'},method=method)
            with urlopen(request) as response:
                return json.load(response)
        job=send('crawler/searches',{'keywords':['李信'],'mode':'preview','min_views':10})
        self.assertEqual(job['config']['mode'],'preview')
        self.server.crawler.store.discover(job['id'],{'bvid':'BV1234567890'},'李信',False)
        result=send('crawler/jobs/'+job['id']+'/start',{'bvids':['BV1234567890']})
        self.assertEqual(result['counts']['queued'],1)
        self.assertEqual(send('crawler/jobs/'+job['id']+'/stop',{})['state'],'stopped')
        self.assertEqual(send('crawler/jobs/'+job['id']+'/resume',{})['state'],'pending')
        creator=send('crawler/creators',{'name':'UP主','url':'https://space.bilibili.com/123','date_from':'2026-10-01'})
        self.assertEqual(creator['uid'],'123')
        one=send('crawler/creators/123/check',{})
        two=send('crawler/creators/123/check',{})
        self.assertEqual(one['id'],two['id'])
        with urlopen(self.url+'crawler/settings') as response:
            self.assertEqual(json.load(response)['search']['keywords'],['李信'])

    def test_transcript_api_missing_files_and_escape_are_rejected(self):
        wxq.atomic_text(self.root/'raw/valid.md','完整文字稿')
        wxq.atomic_json(self.root/'raw/index.json',{'sources':{'good':{'path':'raw/valid.md'},'escape':{'path':'../secret.txt'}}})
        with urlopen(self.url+'sources/good/transcript') as response:
            self.assertEqual(json.load(response)['text'],'完整文字稿')
        for sid in ['missing','escape']:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url+'sources/'+sid+'/transcript')
            self.assertEqual(error.exception.code,404)
        request=Request(self.url+'sources/paths',json.dumps({'ids':['good','good','missing']}).encode(),{'Content-Type':'application/json'})
        with urlopen(request) as response:
            result=json.load(response)
        self.assertEqual(len(result['paths']),1)
        self.assertEqual(result['skipped'],1)

    def test_delete_crawler_job_preserves_content_and_validates_parallelism(self):
        job=self.server.crawler.store.new_job({'keywords':['delete']})
        self.server.crawler.store.discover(job['id'],{'bvid':'BV1234567890'},'delete',True)
        path='crawler/jobs/'+job['id']
        with urlopen(Request(self.url+path,b'{}',{'Content-Type':'application/json'},method='DELETE')) as response:
            self.assertTrue(json.load(response)['deleted'])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+path)
        self.assertEqual(error.exception.code,404)
        with urlopen(self.url+'crawler/jobs') as response:
            self.assertNotIn(job['id'],[j['id'] for j in json.load(response)])
        self.assertIn('BV1234567890',self.server.crawler.store.projections())
        with urlopen(Request(self.url+'crawler/settings',b'{"parallelism":3}',{'Content-Type':'application/json'},method='PUT')) as response:
            self.assertEqual(json.load(response)['parallelism'],3)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url+'crawler/settings',b'{"parallelism":0}',{'Content-Type':'application/json'},method='PUT'))
        self.assertEqual(error.exception.code,400)

    def test_card_image_route_reads_only_registered_assets(self):
        from card_images import sync_images
        from reference_store import export_cards
        from unittest.mock import patch
        wxq.atomic_json(self.root/'entities/equipment.json', [{'id':'card:10','name':'装备','category':'equipment','description':'测试','properties':{'thumb':'https://game.gtimg.cn/a.png'},'sources':[]}])
        export_cards(self.root)
        with patch('card_images.fetch_image',return_value=b'\x89PNG\r\n\x1a\nfixture'):
            sync_images(self.root)
        with urlopen(self.url+'cards') as response:
            card=json.load(response)[0]
        self.assertEqual(card['image_status'],'ready')
        with urlopen(self.url.removesuffix('api/')+card['thumb_url'].lstrip('/')) as response:
            self.assertEqual(response.headers['Content-Type'],'image/png')
            self.assertTrue(response.read().startswith(b'\x89PNG'))
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+'cards/card%3A10/images/../../secrets')
        self.assertEqual(error.exception.code,404)

    def test_global_activity_and_phase_stop_routes(self):
        store = self.server.crawler.store
        job = store.new_job({'keywords': ['control']})
        store.discover(job['id'], {'bvid': 'BV1234567890', 'title': 'control'}, '', True)
        store.claim()
        store.finish_task('BV1234567890', 'running', progress={'phase': 'downloading', 'downloaded_bytes': 12})
        with urlopen(self.url+'crawler/activity') as response:
            self.assertEqual(json.load(response)[0]['progress']['downloaded_bytes'], 12)
        def post(path):
            with urlopen(Request(self.url+path, b'{}', {'Content-Type':'application/json'}, method='POST')) as response:
                return json.load(response)
        self.assertEqual(post('crawler/tasks/BV1234567890/stop-download')['state'], 'paused')
        self.assertEqual(post('crawler/tasks/BV1234567890/resume')['state'], 'queued')
        store.claim()
        store.finish_task('BV1234567890', 'running', progress={'phase': 'transcribing'})
        result = post('crawler/jobs/'+job['id']+'/stop-transcribe')
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['items'][0]['state'], 'paused')
        self.assertEqual(post('crawler/tasks/BV1234567890/delete')['state'], 'cancelled')
        with urlopen(self.url+'crawler/activity') as response:
            self.assertEqual(json.load(response), [])

    def test_reading_endpoint_uses_current_revision_and_preserves_legacy_notes(self):
        wxq.commit_notes(self.root, [{'id':'yaomei-sacrifice-lixin','type':'lineup','title':'李信','claims':[],'entities':[]},
                                     {'id':'legacy','type':'other','title':'旧笔记','claims':[],'entities':[]}])
        with urlopen(self.url + 'notes/yaomei-sacrifice-lixin/reading') as response:
            reading = json.load(response)
        note = next(n for n in workspace.notes(self.root) if n['id']=='yaomei-sacrifice-lixin')
        self.assertEqual(reading['revision'],note['revision'])
        self.assertEqual(len(reading['sections']),11)
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
