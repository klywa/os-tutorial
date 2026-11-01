"""Isolated public UI fixture. No real Git, server configuration or workers."""
from pathlib import Path
import json,sys,tempfile
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store,server,website_data
from proposals import ProposalStore

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='locks-browser-',dir=ROOT/'temp') as folder:
        root=Path(folder);json_store.initialize(root)
        nodes=[{'id':'title','type':'heading','level':1,'title':'协作阅读样例'},
            {'id':'chapter','type':'heading','level':2,'title':'核心机制'},
            *[{'id':key,'type':'entry','key':key.upper(),'show_key':True,'value':'原有正文 '+key} for key in ('a','b','c')],
            {'id':'chapter-two','type':'heading','level':2,'title':'运营节奏'},
            *[{'id':'long-'+str(i),'type':'entry','key':'运营'+str(i),'show_key':True,'value':'手机连续阅读测试。'*25} for i in range(12)],
            {'id':'chapter-three','type':'heading','level':2,'title':'终局技巧'},
            {'id':'end','type':'entry','key':'终局','show_key':True,'value':'保持连续阅读，章节只负责定位。'}]
        json_store.save(root,[{'body':{'schema_version':6,'nodes':nodes},'metadata':{'id':'browser-note',
            'type':'other','title':'协作阅读样例','path':'knowledge/other/协作阅读样例.json'}}],partial=True)
        website_data.export(root)
        config=root/'accounts.json';config.write_text(json.dumps({'schema_version':2,'sessionSecret':'s'*48,
            'accounts':[{'username':name,'password':'fixture','role':role} for name,role in
                [('reviewer','admin'),('alice','annotator'),('bob','annotator')]]}),encoding='utf-8')
        record=json_store.load_record(root,'browser-note')
        ProposalStore(root,root/'state/proposals.sqlite3').submit({'username':'alice','role':'annotator'},
            {'note_id':'browser-note','revision':record['metadata']['revision'],'scope_id':'a',
             'nodes':[{**nodes[2],'value':'管理员已确认的 A 正文'}]})
        http=server.create_server(root,0,public=True,base_path='',auth_config=config,state_dir=root/'state')
        http.auth.secure=False
        http.sync=SimpleNamespace(status=lambda **kw:{'state':'synced','phase':'synced'},enqueue=lambda:{'state':'synced','phase':'synced'})
        print(json.dumps({'port':http.server_port,'root':str(root)}),flush=True)
        try:http.serve_forever()
        finally:http.server_close()
