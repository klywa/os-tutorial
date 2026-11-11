"""Disposable source-navigation data; no Git or real services."""
from pathlib import Path
from types import SimpleNamespace
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store,server,website_data
from proposals import ProposalStore

def entry(nid,key,value):return {'id':nid,'type':'entry','key':key,'show_key':True,'value':value}
def heading(nid,title,level=2):return {'id':nid,'type':'heading','level':level,'title':title}

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='proposal-browser-',dir=ROOT/'temp') as folder:
  root=Path(folder);json_store.initialize(root)
  notes=[('one','当前笔记',[heading('title-one','当前笔记',1),heading('chapter-one','核心机制'),entry('one-a','当前条目','当前正式正文'),
      *[entry('long-'+str(i),'运营'+str(i),'保留原文上下文。'*35) for i in range(16)]]),
      ('two','原文定位样例',[heading('title-two','原文定位样例',1),heading('chapter-two','运营节奏'),entry('deleted','将删除','删除前的正式内容'),
      *[entry('second-long-'+str(i),'阶段'+str(i),'原文连续阅读。'*35) for i in range(12)],
      heading('final-chapter','终局技巧'),entry('source:target','目标原文','应该定位并高亮的正式内容'),
      heading('archived-section','旧章节'),entry('archived-entry','旧条目','旧内容')])]
  for nid,title,nodes in notes:
   json_store.save(root,[{'body':{'schema_version':6,'nodes':nodes},'metadata':{
    'id':nid,'type':'other','title':title,'path':'knowledge/other/'+nid+'.json'}}],partial=True)
  store=ProposalStore(root,root/'state/proposals.sqlite3');author={'username':'alice','role':'annotator'};admin={'username':'reviewer','role':'admin'}
  def submit(nid,scope,nodes):
   return store.submit(author,{'note_id':nid,'scope_id':scope,'revision':store._note(nid)['metadata']['revision'],'nodes':nodes})['items'][0]
  first=submit('one','one-a',[entry('one-a','当前条目','提案修改内容')])
  for i in range(1,16):submit('one','long-'+str(i),[entry('long-'+str(i),'运营'+str(i),'待审建议 '+str(i))])
  from edit_locks import EditLocks
  record=store._note('one')
  record['metadata']['claim_annotations']=[{'id':'fixture-claim','text_ref':'long-0',
      'kind':'conditional_strategy','origin':'manual','evidence':[]}]
  json_store.save(root,[record],partial=True)
  source=root/'raw/sources/BV1cZpA66E98_p1'
  source.mkdir(parents=True)
  (source/'metadata.json').write_text(json.dumps({'duration':30}),encoding='utf-8')
  (source/'asr.raw.json').write_text(json.dumps({'segments':[{'text':'browser evidence fixture'}]}),encoding='utf-8')
  store.edit_locks=EditLocks(store)
  lease=store.edit_locks.acquire(author,{'note_id':'one','client_id':'fixture-tab',
      'resource':{'kind':'entry','id':'long-0'}})
  evidence=store.submit_delta(author,{'note_id':'one','client_id':'fixture-tab','request_id':'fixture-evidence',
      'changes':[{'kind':'update','node':entry('long-0','运营0','带证据的原始提案'),
                  'lease':{k:lease[k] for k in ('id','token')},
                  'evidence_changes':[{'claim_id':'fixture-claim','inference':True,
                      'evidence':[{'source':'BV1cZpA66E98:p1','start':10,'end':20}]}]}]})['items'][0]
  changed=submit('two','source:target',[entry('source:target','目标原文','尚未确认的改动')])
  approved=submit('two','final-chapter',[*store._note('two')['body']['nodes'][-4:-2],entry('fresh','已确认新增','新增正式内容')])
  store.action(admin,approved['id'],'approve',{'revision':1})
  # Submit after the approved insertion: its node is a real canonical anchor.
  all_nodes=store._note('two')['body']['nodes'];start=next(i for i,n in enumerate(all_nodes) if n['id']=='final-chapter');end=next(i for i,n in enumerate(all_nodes) if n['id']=='archived-section')
  inserted=submit('two','final-chapter',[*all_nodes[start:end],entry('next','待审插入','只定位插入位置')])
  removed=submit('two','deleted',[]);store.action(admin,removed['id'],'approve',{'revision':1})
  orphan=submit('two','archived-entry',[entry('archived-entry','旧条目','将被拒绝')]);store.action(admin,orphan['id'],'reject',{'revision':1})
  record=store._note('two');body={**record['body'],'nodes':[n for n in record['body']['nodes'] if n['id'] not in ('archived-section','archived-entry')]}
  json_store.edit(root,'two',{'revision':record['metadata']['revision'],'document':body})
  website_data.export(root)
  config=root/'accounts.json';config.write_text(json.dumps({'schema_version':2,'sessionSecret':'s'*48,'accounts':[
   {'username':'reviewer','password':'fixture','role':'admin'},{'username':'alice','password':'fixture','role':'annotator'}]}),encoding='utf-8')
  http=server.create_server(root,0,start_worker=False) if '--local' in sys.argv else server.create_server(root,0,public=True,base_path='',auth_config=config,state_dir=root/'state')
  http.auth.secure=False
  http.sync=SimpleNamespace(status=lambda **kw:{'state':'synced'},enqueue=lambda:{'state':'synced'})
  print(json.dumps({'port':http.server_port,'root':str(root),'ids':{k:v['id'] for k,v in [('first',first),('evidence',evidence),('changed',changed),('approved',approved),('inserted',inserted),('removed',removed),('orphan',orphan)]},'approvedNode':approved['node_id']}),flush=True)
  try:http.serve_forever()
  finally:http.server_close()
