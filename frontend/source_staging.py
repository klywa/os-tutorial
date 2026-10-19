"""One persistent source basket per project. Stores IDs, never client paths."""
import hashlib,json
from crawler import Store,batch_paths
import workspace

class Staging:
 def __init__(self,root):
  self.store=Store(root);self.root=self.store.root
  with self.store.db() as db:
   db.execute('CREATE TABLE IF NOT EXISTS source_staging(id TEXT PRIMARY KEY,position INTEGER)')
   db.execute('CREATE TABLE IF NOT EXISTS staging_revision(id INTEGER PRIMARY KEY,value INTEGER)')
   db.execute('INSERT OR IGNORE INTO staging_revision VALUES(1,0)')
 def sources(self):
  return {r['id']:r for r in workspace.sources(self.root) if not r.get('manual_values',{}).get('ignored')}
 def get(self):
  valid=self.sources()
  with self.store.db() as db:
   ids=[r['id'] for r in db.execute('SELECT id FROM source_staging ORDER BY position,id') if r['id'] in valid]
   revision=db.execute('SELECT value FROM staging_revision WHERE id=1').fetchone()[0]
  return {'ids':ids,'items':[{'id':sid,'title':valid[sid].get('manual_values',{}).get('title',valid[sid].get('title',''))} for sid in ids],
    'revision':revision,'project_key':hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:16]}
 def prune(self):
  valid=self.sources()
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE');changed=0
   for row in db.execute('SELECT id FROM source_staging').fetchall():
    if row['id'] not in valid:changed+=db.execute('DELETE FROM source_staging WHERE id=?',(row['id'],)).rowcount
   if changed:db.execute('UPDATE staging_revision SET value=value+1 WHERE id=1')
 def add(self,ids):
  if not isinstance(ids,list) or len(ids)>10000 or any(not isinstance(v,str) for v in ids):raise ValueError('请选择最多10000个来源ID')
  valid=self.sources()
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE');pos=db.execute('SELECT COALESCE(MAX(position),0) FROM source_staging').fetchone()[0];changed=0
   for sid in dict.fromkeys(ids):
    if sid in valid:pos+=1;changed+=db.execute('INSERT OR IGNORE INTO source_staging VALUES(?,?)',(sid,pos)).rowcount
   if changed:db.execute('UPDATE staging_revision SET value=value+1 WHERE id=1')
  self.prune();return self.get()
 def remove(self,sid):
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('DELETE FROM source_staging WHERE id=?',(sid,)).rowcount:db.execute('UPDATE staging_revision SET value=value+1 WHERE id=1')
  return self.get()
 def clear(self,revision):
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT value FROM staging_revision WHERE id=1').fetchone()[0]!=revision:raise workspace.Conflict('暂存区已更新，请刷新后清空')
   db.execute('DELETE FROM source_staging');db.execute('UPDATE staging_revision SET value=value+1 WHERE id=1')
  return self.get()
 def paths(self):
  import wxq
  from reference_store import transcript_target
  data=self.get();paths=[];skipped=[]
  with workspace.store_lock(self.root,wait=True):
   manifest=wxq.read_json(self.root/'raw/index.json',{})
   for item in data['items']:
    try:
     _,target=transcript_target(self.root,item['id'],manifest);path=str(target)
     if path not in paths:paths.append(path)
    except (KeyError,OSError):skipped.append({**item,'reason':'文字稿文件已缺失' if item['id'] in manifest.get('sources',{}) else '等待生成文字稿'})
  return {'paths':paths,'skipped':len(skipped),'revision':data['revision'],'ids':data['ids'],'details':skipped,
          'fingerprint':hashlib.sha256(json.dumps([data['ids'],paths],ensure_ascii=False).encode()).hexdigest()}
