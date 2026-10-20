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
 def sources(self,ids=None):
  return {r['id']:r for r in workspace.sources(self.root,source_ids=ids) if not r.get('manual_values',{}).get('ignored')}
 def get(self):
  with self.store.db() as db:
   ids=[r['id'] for r in db.execute('SELECT id FROM source_staging ORDER BY position,id')]
   revision=db.execute('SELECT value FROM staging_revision WHERE id=1').fetchone()[0]
  valid=self.sources(ids);ids=[sid for sid in ids if sid in valid]
  return {'ids':ids,'items':[{'id':sid,'title':valid[sid].get('manual_values',{}).get('title',valid[sid].get('title',''))} for sid in ids],
    'revision':revision,'project_key':hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:16]}
 def prune(self):
  with self.store.db() as db:ids=[r['id'] for r in db.execute('SELECT id FROM source_staging')]
  valid=self.sources(ids)
  with self.store.db() as db:
   db.execute('BEGIN IMMEDIATE');changed=0
   for sid in ids:
    if sid not in valid:changed+=db.execute('DELETE FROM source_staging WHERE id=?',(sid,)).rowcount
   if changed:db.execute('UPDATE staging_revision SET value=value+1 WHERE id=1')
 def add(self,ids):
  if not isinstance(ids,list) or len(ids)>10000 or any(not isinstance(v,str) for v in ids):raise ValueError('请选择最多10000个来源ID')
  valid=self.sources(ids)
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
 def prompt(self):
  import wxq
  from reference_store import transcript_target
  for attempt in range(3):
   registry=wxq.read_json(self.root/'knowledge/source-registry.json',[])
   with self.store.db() as db:
    ids=[r['id'] for r in db.execute('SELECT id FROM source_staging ORDER BY position,id')]
    revision=db.execute('SELECT value FROM staging_revision WHERE id=1').fetchone()[0]
   sources=self.sources(ids);manifest=wxq.read_json(self.root/'raw/index.json',{});items=[]
   for sid in ids:
    if sid not in sources:continue
    row=sources[sid];manual=row.get('manual_values',{})
    location=manual.get('url',row['url'])
    try:
     _,target=transcript_target(self.root,sid,manifest);location=str(target)
    except (KeyError,OSError):pass
    items.append({'id':sid,'title':manual.get('title',row.get('title','')),
      'location':location,'notes':manual.get('notes',row.get('notes',''))})
   with self.store.db() as db:
    current_ids=[r['id'] for r in db.execute('SELECT id FROM source_staging ORDER BY position,id')]
    current_revision=db.execute('SELECT value FROM staging_revision WHERE id=1').fetchone()[0]
   current_manifest=wxq.read_json(self.root/'raw/index.json',{})
   if ids==current_ids and revision==current_revision and registry==wxq.read_json(self.root/'knowledge/source-registry.json',[]) and all(manifest.get('sources',{}).get(sid)==current_manifest.get('sources',{}).get(sid) for sid in ids):
    return {'items':items,'revision':revision,
      'fingerprint':hashlib.sha256(json.dumps(items,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
  raise workspace.Conflict('暂存或内容资料正在变化，请稍后重试；编辑草稿已保留')
