"""The dashboard HTTP surface must stay local, read-only and asynchronous."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
from server import Handler

class UsageHttpTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'temp/usage-http';folder.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        (root/'knowledge').mkdir();(root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
        class QuietHandler(Handler):
            def log_message(self,*args):pass
        self.calls=0
        def request():self.calls+=1;return {'state':'queued','ready':False}
        self.server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler);self.server.root=root
        self.server.crawler=SimpleNamespace(usage=SimpleNamespace(request=request))
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def call(self,path,method='GET',payload=None):
        req=urllib.request.Request(self.url+path,data=None if method=='GET' else json.dumps(payload or {}).encode(),method=method,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.load(r)

    def test_default_scope_is_compatible_and_usage_has_no_false_zero(self):
        status,data=self.call('/api/dashboard');self.assertEqual(status,200);self.assertEqual(data['counts']['lineup'],0)
        status,data=self.call('/api/dashboard?scope=usage_top10');self.assertEqual(status,200);self.assertFalse(data['usage']['ready']);self.assertIsNone(data['summary']['rate'])

    def test_manual_refresh_is_accepted_without_doing_network_in_handler(self):
        code,data=self.call('/api/dashboard/usage/refresh','POST');self.assertEqual(code,202);self.assertEqual(data['state'],'queued');self.assertEqual(self.calls,1)

    def test_unknown_scope_and_wrong_mutation_method_are_rejected(self):
        for path,method in [('/api/dashboard?scope=invalid','GET'),('/api/dashboard/usage/refresh','PUT')]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.call(path,method)
            self.assertEqual(error.exception.code,400)

    def test_mapping_editor_saves_and_conflicts_through_local_http(self):
        import lineup_usage as usage
        root=self.server.root
        (root/'knowledge/lineups').mkdir()
        row={'id':'note','title':'测试阵容','type':'lineup','player_id':'player:1','path':'knowledge/lineups/note.json','revision':'one'}
        import json_store as store
        from workspace import store_lock
        body={'schema_version':6,'nodes':[{'id':'title','type':'heading','level':1,'title':row['title']}],'semantics':{'players':['player:1']}}
        with store_lock(root):store.save(root,[{'body':body,'metadata':{**row,'aliases':[]}}],partial=True)
        path=root/usage.SNAPSHOT;path.parent.mkdir(parents=True,exist_ok=True)
        pair={'id':'g@player:1','source_id':'g','source_name':'外网阵容','heroes':['card:1'],'player_id':'player:1','player_name':'棋手','rank':1,'usage':.2}
        path.write_text(json.dumps({'id':'test','window':usage.window(),'fetched_at':usage.now().isoformat(),'scope':{},'pairs':[pair]}),encoding='utf-8')
        _,data=self.call('/api/dashboard/usage/matches')
        payload={'revision':data['revision'],'pair_id':pair['id'],'pair_revision':data['pairs'][0]['pair_revision'],'note_id':'note'}
        code,saved=self.call('/api/dashboard/usage/matches','PUT',payload)
        self.assertEqual(code,200);self.assertEqual(saved['assignment']['note_id'],'note')
        with self.assertRaises(urllib.error.HTTPError) as error:self.call('/api/dashboard/usage/matches','PUT',payload)
        self.assertEqual(error.exception.code,409)
        _,dashboard=self.call('/api/dashboard?scope=usage_top10');self.assertEqual(dashboard['notes'][0]['match_basis'],'manual')

if __name__=='__main__':unittest.main()
