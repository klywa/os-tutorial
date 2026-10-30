"""Versioned lineup roster and website provenance; never writes knowledge bodies."""
import hashlib,json,time,uuid,urllib.request
from pathlib import Path
from topics import TopicStore,encode
import wxq,workspace

SITE='https://www.datawxq.com'

def normalize_records(records,heroes):
 names={}
 for h in heroes:
  names.setdefault(h['name'],set()).add(h['id'])
  names.setdefault(h['id'],set()).add(h['id'])
 groups={};errors=[]
 for index,r in enumerate(records):
  try:
   ids=[]
   for name in r.get('heroes',[]):
    hits=names.get(name,set())
    if len(hits)!=1:raise ValueError('英雄无法唯一识别：'+str(name))
    ids.extend(hits)
   if not ids or not r.get('name','').strip():raise ValueError('缺少名称或完整组成')
   key=tuple(sorted(set(ids)));groups.setdefault(key,[]).append(r)
  except (ValueError,TypeError) as e:errors.append({'index':index,'record':r,'error':str(e)})
 items=[]
 for key,rows in groups.items():
  rows.sort(key=lambda r:(-float(r.get('usage',0)),-int(r.get('games',0)),r['name']))
  items.append({'name':rows[0]['name'],'heroes':list(key),'aliases':list(dict.fromkeys(r['name'] for r in rows[1:] if r['name']!=rows[0]['name'])),'sources':rows})
 return {'items':items,'errors':errors,'scanned':len(records),'merged':sum(len(r)-1 for r in groups.values())}

class LineupCatalog:
 def __init__(self,root):
  self.root=Path(root);self.topics=TopicStore(root)
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE')
   sql=db.execute("SELECT sql FROM sqlite_master WHERE name='topic_lineups'").fetchone()[0]
   if 'name TEXT UNIQUE' in sql:
    db.execute('ALTER TABLE topic_lineups RENAME TO topic_lineups_unique_old')
    db.execute(sql.replace('name TEXT UNIQUE','name TEXT'))
    db.execute('INSERT INTO topic_lineups SELECT * FROM topic_lineups_unique_old');db.execute('DROP TABLE topic_lineups_unique_old')
   columns={r['name'] for r in db.execute('PRAGMA table_info(topic_lineups)')}
   for name,kind in [('deleted_at',"TEXT DEFAULT ''"),('restore_enabled','INTEGER DEFAULT 1')]:
    if name not in columns:db.execute(f'ALTER TABLE topic_lineups ADD COLUMN {name} {kind}')
   for name,kind in [('heroes',"TEXT DEFAULT '[]'"),('sort_order','INTEGER DEFAULT 0'),('revision','INTEGER DEFAULT 1'),('manual_fields',"TEXT DEFAULT '[]'"),('sources',"TEXT DEFAULT '[]'"),('merged_into',"TEXT DEFAULT ''"),('common_name',"TEXT DEFAULT ''"),('naming_sources',"TEXT DEFAULT '[]'")]:
    if name not in columns:db.execute(f'ALTER TABLE topic_lineups ADD COLUMN {name} {kind}')
   db.executescript('CREATE TABLE IF NOT EXISTS lineup_imports(token TEXT PRIMARY KEY,revision INTEGER,payload TEXT); CREATE TABLE IF NOT EXISTS lineup_notes(lineup TEXT,note TEXT,PRIMARY KEY(lineup,note));')
   db.executescript("CREATE TABLE IF NOT EXISTS lineup_variants(id TEXT PRIMARY KEY,heroes TEXT); CREATE TABLE IF NOT EXISTS lineup_variant_links(lineup TEXT,variant TEXT,sources TEXT DEFAULT '[]',manual INTEGER DEFAULT 0,PRIMARY KEY(lineup,variant)); CREATE TABLE IF NOT EXISTS lineup_naming(id TEXT PRIMARY KEY,lineup TEXT,payload TEXT,state TEXT DEFAULT 'pending',revision INTEGER DEFAULT 1);")
   from note_links import schema
   schema(db)
 def revision(self,db=None):
  if db is None:return int(self.topics.setting('catalog_revision') or 0)
  r=db.execute("SELECT value FROM topic_settings WHERE key='catalog_revision'").fetchone();return int(json.loads(r[0])) if r else 0
 def bump(self,db,reanalyze=False):
  value=self.revision(db)+1;db.execute('INSERT OR REPLACE INTO topic_settings VALUES(?,?)',('catalog_revision',str(value)))
  self.topics.reconcile(db)
  # Evidence that can already be resolved is reused; only unresolved records lacking
  # complete composition require another model pass. Old valid projections remain.
  for task in list(db.execute("SELECT source,fingerprint,result FROM topic_tasks WHERE state='succeeded'")) if reanalyze else []:
   data=json.loads(task['result']);names={c['name'] for c in data.get('lineups',[]) if not c.get('complete')}
   if names and any(c['name'] in names for c in db.execute("SELECT name FROM topic_candidates WHERE source=? AND fingerprint=? AND state='pending'",(task['source'],task['fingerprint']))):
    db.execute("UPDATE topic_tasks SET state='queued',generation=generation+1 WHERE source=?",(task['source'],))
  return value
 def roster(self,db=None):
  if db is None:
   with self.topics.db() as conn:return self.roster(conn)
  rows=[]
  hero_names={h['id']:h['name'] for h in wxq.read_json(self.root/'entities/heroes.json',[])}
  for r in db.execute('SELECT * FROM topic_lineups ORDER BY sort_order,rowid'):
   r=dict(r)
   for k in ['heroes','aliases','sources','manual_fields','naming_sources']:r[k]=json.loads(r[k])
   r['display_name']=r['common_name'] or r['name'];r['variants']=self.variants(r['id'],db)
   from note_links import links
   r['note_links']=links(db,r['id']);r['primary_note_id']=next((x['note'] for x in r['note_links'] if x['role']=='primary'),None)
   r['enabled']=bool(r['enabled']);r['description']='、'.join(hero_names.get(h,h) for h in r['heroes']);r['note_ids']=[x[0] for x in db.execute('SELECT note FROM lineup_notes WHERE lineup=?',(r['id'],))];rows.append(r)
  return rows
 def variants(self,uid,db=None):
  if db is None:
   with self.topics.db() as conn:return self.variants(uid,conn)
  return [{**dict(r),'heroes':json.loads(r['heroes']),'sources':json.loads(r['sources']),'manual':bool(r['manual'])} for r in db.execute('SELECT v.*,l.sources,l.manual FROM lineup_variants v JOIN lineup_variant_links l ON v.id=l.variant WHERE l.lineup=? ORDER BY v.id',(uid,))]
 def save_variants(self,payload):
  uid=payload.get('lineup');items=payload.get('variants',[])
  if not isinstance(items,list) or any(not isinstance(v,dict) or not isinstance(v.get('heroes'),list) or not v['heroes'] or any(h not in self.hero_ids() for h in v['heroes']) or len(set(v['heroes']))!=len(v['heroes']) for v in items):raise ValueError('变阵英雄组成无效')
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM topic_lineups WHERE id=?',(uid,)).fetchone()
   if not row or row['merged_into'] or row['deleted_at']:raise KeyError('主阵容不存在')
   if payload.get('revision')!=row['revision']:raise workspace.Conflict('主阵容已更新，请刷新后重试')
   db.execute('DELETE FROM lineup_variant_links WHERE lineup=?',(uid,))
   for v in items:self.put_variant(db,uid,v,True)
   db.execute('UPDATE topic_lineups SET revision=revision+1,manual_fields=? WHERE id=?',(encode(list(set(json.loads(row['manual_fields']))|{'variants'})),uid));self.bump(db,True)
  return self.roster()
 def put_variant(self,db,uid,item,manual=False):
  heroes=sorted(set(item['heroes']));vid='variant:'+hashlib.sha256(encode(heroes).encode()).hexdigest()[:24]
  db.execute('INSERT OR IGNORE INTO lineup_variants VALUES(?,?)',(vid,encode(heroes)))
  db.execute('INSERT OR REPLACE INTO lineup_variant_links VALUES(?,?,?,?)',(uid,vid,encode(item.get('sources',[])),int(manual)))
 def hero_ids(self):return {r['id'] for r in wxq.read_json(self.root/'entities/heroes.json',[])}
 def add_naming(self,uid,item):
  if not isinstance(item.get('name'),str) or not item['name'].strip() or not isinstance(item.get('evidence',[]),list):raise ValueError('命名候选格式无效')
  for e in item.get('evidence',[]):
   if not isinstance(e,dict) or not isinstance(e.get('url'),str) or not e['url'].startswith(('https://','http://')) or not isinstance(e.get('quote'),str):raise ValueError('命名证据无效')
  cid=hashlib.sha256(encode([uid,item['name']]).encode()).hexdigest()[:24]
  with self.topics.db() as db:
   if not db.execute('SELECT 1 FROM topic_lineups WHERE id=? AND merged_into=\'\' AND deleted_at=\'\'',(uid,)).fetchone():raise KeyError('主阵容不存在')
   db.execute('INSERT OR IGNORE INTO lineup_naming(id,lineup,payload) VALUES(?,?,?)',(cid,uid,encode(item)))
   db.execute("UPDATE lineup_naming SET payload=?,revision=revision+1 WHERE id=? AND state='pending' AND payload!=?",(encode(item),cid,encode(item)))
  return cid
 def naming(self):
  with self.topics.db() as db:return [{**json.loads(r['payload']),**dict(r)} for r in db.execute("SELECT n.* FROM lineup_naming n JOIN topic_lineups l ON l.id=n.lineup WHERE n.state='pending' AND l.merged_into='' AND l.deleted_at='' ORDER BY n.rowid")]
 def resolve_naming(self,cid,payload):
  action=payload.get('action')
  if action not in ['common','alias','reject']:raise ValueError('未知命名操作')
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');candidate=db.execute('SELECT * FROM lineup_naming WHERE id=?',(cid,)).fetchone()
   if not candidate:raise KeyError('命名候选不存在')
   if candidate['state']!='pending' or candidate['revision']!=payload.get('candidate_revision'):raise workspace.Conflict('候选已处理，请刷新')
   if action!='reject':
    target=payload.get('target',candidate['lineup']);row=db.execute('SELECT * FROM topic_lineups WHERE id=?',(target,)).fetchone()
    if not row or row['merged_into'] or row['deleted_at']:raise KeyError('主阵容不存在')
    if row['revision']!=payload.get('revision'):raise workspace.Conflict('主阵容已更新，草稿保留')
    data=json.loads(candidate['payload']);name=payload.get('name',data['name'])
    if not isinstance(name,str) or not name.strip():raise ValueError('请输入名称')
    name=name.strip();fields=set(json.loads(row['manual_fields']))
    if action=='common':
     fields.add('common_name');db.execute('UPDATE topic_lineups SET common_name=?,naming_sources=? WHERE id=?',(name,encode(data.get('evidence',[])),target))
    else:
     fields.add('aliases');db.execute('UPDATE topic_lineups SET aliases=? WHERE id=?',(encode(list(dict.fromkeys([*json.loads(row['aliases']),name]))),target))
    db.execute('UPDATE topic_lineups SET manual_fields=?,revision=revision+1 WHERE id=?',(encode(sorted(fields)),target))
    self.bump(db)
   db.execute('UPDATE lineup_naming SET state=?,revision=revision+1 WHERE id=?',('rejected' if action=='reject' else 'accepted',cid))
  return self.naming()
 def save(self,payload):
  raw_name=payload.get('name','')
  if not isinstance(raw_name,str):raise ValueError('阵容名称无效')
  name=raw_name.strip();heroes=payload.get('heroes',[]);aliases=payload.get('aliases',[])
  if 'common_name' in payload and not isinstance(payload['common_name'],str):raise ValueError('常用名必须为文字')
  if not name or not isinstance(heroes,list) or any(not isinstance(h,str) or h not in self.hero_ids() for h in heroes):raise ValueError('阵容名称或英雄成员无效')
  if len(set(heroes))!=len(heroes) or not isinstance(aliases,list) or any(not isinstance(a,str) for a in aliases):raise ValueError('成员重复或别称无效')
  if not isinstance(payload.get('enabled',True),bool) or not isinstance(payload.get('sort_order',0),int) or payload.get('sort_order',0)<0:raise ValueError('启用状态或排序无效')
  aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip() and a.strip()!=name))
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');rows=self.roster(db);old=next((r for r in rows if r['id']==payload.get('id')),None)
   if payload.get('id') and not old:raise KeyError('阵容不存在')
   if old and payload.get('revision')!=old['revision']:raise workspace.Conflict('阵容已更新，请刷新后重试；草稿保留')
   if old and old['merged_into']:raise ValueError('该阵容已合并')
   if old and old['deleted_at']:raise ValueError('阵容已删除，请先恢复')
   for r in rows:
    if old and r['id']==old['id'] or r['merged_into']:continue
    unchanged_name=old and name==old['name']
    if not unchanged_name and name==r['name']:raise ValueError('原名重复，请编辑原项或明确合并')
    if heroes and set(heroes)==set(r['heroes']):raise ValueError('相同英雄组成已存在，请使用合并')
   uid=old['id'] if old else 'lineup:'+uuid.uuid4().hex
   values=[name,encode(aliases),int(payload.get('enabled',True)),encode(heroes),payload.get('sort_order',0),encode(sorted(set(['name','aliases','heroes','sort_order','enabled'])|set(old['manual_fields'] if old else [])))]
   if old:db.execute('UPDATE topic_lineups SET name=?,aliases=?,enabled=?,heroes=?,sort_order=?,manual_fields=?,revision=revision+1 WHERE id=?',(*values,uid))
   else:db.execute('INSERT INTO topic_lineups(id,name,aliases,enabled,heroes,sort_order,manual_fields) VALUES(?,?,?,?,?,?,?)',(uid,*values))
   if 'common_name' in payload:
    fields=set(values[-1] and json.loads(values[-1]))|{'common_name'}
    if old:fields.update(old['manual_fields'])
    db.execute('UPDATE topic_lineups SET common_name=?,manual_fields=? WHERE id=?',(payload['common_name'].strip(),encode(sorted(fields)),uid))
   if old and set(old['heroes'])!=set(heroes):db.execute("UPDATE topic_candidates SET state='pending',target=NULL WHERE target=? AND resolution='auto'",(uid,))
   self.bump(db,bool(old and set(old['heroes'])!=set(heroes)))
  return self.roster()
 def save_quick_batch(self,payload):
  items=payload.get('items');request=payload.get('request_id')
  if not isinstance(request,str) or not request.strip() or len(request)>150:raise ValueError('缺少批量请求标识')
  if not isinstance(items,list) or not 0<len(items)<=1000:raise ValueError('请提交1至1000行')
  fingerprint=hashlib.sha256(encode(items).encode()).hexdigest()
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE')
   db.execute('CREATE TABLE IF NOT EXISTS lineup_batch_requests(id TEXT PRIMARY KEY,fingerprint TEXT,result TEXT)')
   prior=db.execute('SELECT * FROM lineup_batch_requests WHERE id=?',(request,)).fetchone()
   if prior:
    if prior['fingerprint']!=fingerprint:raise workspace.Conflict('同一请求标识的内容已变化')
    return json.loads(prior['result'])
   rows={r['id']:r for r in self.roster(db)};seen=set();names={n.strip() for r in rows.values() if not r['deleted_at'] and not r['merged_into'] for n in (r['name'],r['common_name']) if n.strip()};prepared=[];errors=[];stale=[];warnings=[]
   for index,item in enumerate(items):
    try:
     if not isinstance(item,dict) or set(item)-{'id','client_id','revision','common_name','aliases'}:raise ValueError('只允许常用命名和别名')
     uid=item.get('id');key=uid or item.get('client_id')
     if not isinstance(key,str) or not key or key in seen:raise ValueError('行标识缺失或重复')
     seen.add(key);name=item.get('common_name','');aliases=item.get('aliases',[])
     if not isinstance(name,str) or not isinstance(aliases,list) or any(not isinstance(a,str) for a in aliases):raise ValueError('名称与别名格式无效')
     name=name.strip();aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip()))
     if uid:
      old=rows.get(uid)
      if not old or old['deleted_at'] or old['merged_into']:raise ValueError('阵容不存在或已删除')
      if item.get('revision')!=old['revision']:stale.append(uid)
     else:
      if not name and not aliases:continue
      if not name:raise ValueError('请补齐常用命名')
      if name in names:warnings.append({'client_id':key,'name':name,'message':'同名阵容已存在，保留为独立条目'})
      names.add(name)
     prepared.append((uid,key,name,aliases))
    except ValueError as e:errors.append({'index':index,'client_id':item.get('client_id') if isinstance(item,dict) else None,'error':str(e)})
   if errors:
    e=ValueError('整批未保存，请检查标记行');e.row_errors=errors;raise e
   if stale:
    e=workspace.Conflict('阵容已更新，草稿保留');e.lineup_ids=stale;raise e
   created={}
   for uid,key,name,aliases in prepared:
    if uid:
     fields=encode(sorted(set(rows[uid]['manual_fields'])|{'common_name','aliases'}))
     db.execute('UPDATE topic_lineups SET common_name=?,aliases=?,manual_fields=?,revision=revision+1 WHERE id=?',(name,encode(aliases),fields,uid))
    else:
     uid='lineup:'+uuid.uuid4().hex;created[key]=uid
     db.execute('INSERT INTO topic_lineups(id,name,common_name,aliases,heroes,enabled,sort_order,manual_fields) VALUES(?,?,?,?,?,1,?,?)',(uid,name,name,encode(aliases),encode([]),len(rows)+len(created),encode(['name','common_name','aliases'])))
   if prepared:self.bump(db)
   result={'roster':self.roster(db),'created':created,'warnings':warnings}
   db.execute('INSERT INTO lineup_batch_requests VALUES(?,?,?)',(request,fingerprint,encode(result)))
  return result
 def save_batch(self,payload):
  items=payload.get('items')
  if not isinstance(items,list) or not items or len(items)>1000:raise ValueError('请提交1至1000条名称修改')
  seen=set()
  for item in items:
   if not isinstance(item,dict) or set(item)-{'id','revision','common_name','aliases'} or not isinstance(item.get('id'),str) or item['id'] in seen:raise ValueError('批量修改只允许唯一阵容的名称字段')
   seen.add(item['id'])
   if 'common_name' in item and not isinstance(item['common_name'],str):raise ValueError('常用名必须为文字')
   if 'aliases' in item and (not isinstance(item['aliases'],list) or any(not isinstance(a,str) for a in item['aliases'])):raise ValueError('别名须为文字列表')
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');rows={r['id']:r for r in self.roster(db)}
   missing=seen-set(rows)
   if missing:raise KeyError('阵容不存在：'+next(iter(missing)))
   stale=[item['id'] for item in items if item.get('revision')!=rows[item['id']]['revision']]
   if stale:
    error=workspace.Conflict('阵容已更新，整批未保存；请处理冲突后重试');error.lineup_ids=stale;raise error
   for item in items:
    old=rows[item['id']]
    if old['merged_into'] or old['deleted_at']:raise ValueError('已合并或已删除阵容不能编辑：'+old['name'])
    fields=set(old['manual_fields'])
    for key in ('common_name','aliases'):
     if key not in item:continue
     value=item[key].strip() if key=='common_name' else encode(list(dict.fromkeys(a.strip() for a in item[key] if a.strip() and a.strip()!=old['name'])))
     db.execute(f'UPDATE topic_lineups SET {key}=? WHERE id=?',(value,item['id']));fields.add(key)
    db.execute('UPDATE topic_lineups SET manual_fields=?,revision=revision+1 WHERE id=?',(encode(sorted(fields)),item['id']))
   self.bump(db)
  return self.roster()
 def delete(self,uid,payload):
  return self.set_deleted(uid,payload,True)
 def restore(self,uid,payload):
  return self.set_deleted(uid,payload,False)
 def set_deleted(self,uid,payload,deleting):
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM topic_lineups WHERE id=?',(uid,)).fetchone()
   if not row:raise KeyError('阵容不存在')
   if payload.get('revision')!=row['revision']:
    error=workspace.Conflict('阵容已更新，请刷新后重试');error.lineup_ids=[uid];raise error
   if row['merged_into']:raise ValueError('已合并阵容不能删除或恢复')
   if bool(row['deleted_at'])==deleting:raise ValueError('阵容已删除' if deleting else '阵容尚未删除')
   fields=encode(sorted(set(json.loads(row['manual_fields']))|{'enabled','deleted_at'}))
   if deleting:db.execute('UPDATE topic_lineups SET deleted_at=?,restore_enabled=enabled,enabled=0,manual_fields=?,revision=revision+1 WHERE id=?',(wxq.now(),fields,uid))
   else:db.execute("UPDATE topic_lineups SET deleted_at='',enabled=restore_enabled,manual_fields=?,revision=revision+1 WHERE id=?",(fields,uid))
   self.bump(db)
  return self.roster()
 def preview(self,report=None):
  if report is None:report=fetch_website(self.root)
  if report.get('errors'):raise ValueError('采集存在异常，未应用不完整结果；原名单保留')
  if not report.get('items'):raise ValueError('未获取到有效阵容，原名单保留')
  token=uuid.uuid4().hex;changes=[]
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');existing=self.roster(db)
   for item in report['items']:
    old=next((r for r in existing if r['heroes'] and set(r['heroes'])==set(item['heroes'])),None)
    changes.append({'name':item['name'],'id':old['id'] if old else None,'action':'保留人工合并' if old and old['merged_into'] else '保留人工值／更新来源' if old and old['manual_fields'] else '更新' if old else '新增'})
   db.execute('INSERT INTO lineup_imports VALUES(?,?,?)',(token,self.revision(db),encode(report)))
  return {**report,'token':token,'changes':changes,'current_count':len(existing)}
 def apply(self,token):
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');preview=db.execute('SELECT * FROM lineup_imports WHERE token=?',(token,)).fetchone()
   if not preview:raise KeyError('导入预览已失效')
   if preview['revision']!=self.revision(db):raise workspace.Conflict('名单已变化，请重新预览')
   report=json.loads(preview['payload'])
   if report.get('errors') or not report.get('items'):raise ValueError('采集存在异常，未应用不完整结果；原名单保留')
   rows=self.roster(db)
   for index,item in enumerate(report['items']):
    old=next((r for r in rows if r['heroes'] and set(r['heroes'])==set(item['heroes'])),None)
    if old:
     uid=old['id']
     if old['manual_fields']:db.execute('UPDATE topic_lineups SET sources=?,revision=revision+1 WHERE id=?',(encode(item['sources']),old['id']))
     else:db.execute('UPDATE topic_lineups SET name=?,aliases=?,sources=?,revision=revision+1 WHERE id=?',(item['name'],encode(item['aliases']),encode(item['sources']),old['id']))
    else:
     uid='lineup:'+uuid.uuid4().hex
     db.execute('INSERT INTO topic_lineups(id,name,aliases,enabled,heroes,sort_order,sources) VALUES(?,?,?,1,?,?,?)',(uid,item['name'],encode(item['aliases']),encode(item['heroes']),index,encode(item['sources'])))
     rows.append({'id':uid,**item,'manual_fields':[],'merged_into':''})
    if not old or 'variants' not in old['manual_fields']:
     db.execute('DELETE FROM lineup_variant_links WHERE lineup=? AND manual=0',(uid,))
     for variant in item.get('variants',[]):
      if not variant.get('heroes') or any(h not in self.hero_ids() for h in variant['heroes']):raise ValueError('导入变阵身份无效，原名单保留')
      self.put_variant(db,uid,variant)
   self.bump(db,True);db.execute('DELETE FROM lineup_imports WHERE token=?',(token,))
   db.execute('INSERT OR REPLACE INTO topic_settings VALUES(?,?)',('last_lineup_import',encode({k:v for k,v in report.items() if k!='items'})))
  return {'roster':self.roster(),'report':report}
 def links(self):
  return {r['id']:r['note_ids'] for r in self.roster()}
 def suggestions(self):
  notes=workspace.notes(self.root);result=[]
  for r in self.roster():
   if not r['enabled']:continue
   for n in notes:
    if n['type']!='lineup' or n['id'] in r['note_ids']:continue
    names=[r['name'],r['common_name'],*r['aliases']];names=[x for x in names if x];members={m['hero'] for m in n.get('meta',{}).get('compositions',{}).get('late',[])}
    core=set(n.get('meta',{}).get('core_heroes',[]));same_name=any(s in n['title'] or n['title'] in s for s in names)
    if same_name or members and members==set(r['heroes']) or core and core.issubset(set(r['heroes'])):result.append({'lineup':r['id'],'note':n['id'],'title':n['title'],'reason':'名称或成员相符，仅为关联建议，待人工确认'})
  return result
 def bind(self,payload):
  uid=payload.get('lineup');ids=payload.get('note_ids',[])
  valid={n['id'] for n in workspace.notes(self.root) if n['type']=='lineup'}
  if not isinstance(ids,list) or any(i not in valid for i in ids):raise ValueError('只能关联现有阵容笔记')
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM topic_lineups WHERE id=?',(uid,)).fetchone()
   if not row:raise KeyError('阵容不存在')
   if payload.get('revision')!=row['revision']:raise workspace.Conflict('阵容已更新，请刷新后重试')
   if row['merged_into'] or row['deleted_at']:raise ValueError('阵容已合并或删除')
   previous=set(x['note'] for x in __import__('note_links').links(db,uid))
   if previous and set(ids)-previous:raise workspace.Conflict('请通过关联弹窗选择主笔记或变体，不能批量覆盖')
   for old in previous-set(ids):db.execute('INSERT OR IGNORE INTO lineup_note_exclusions VALUES(?,?)',(uid,old))
   db.execute('DELETE FROM lineup_note_roles WHERE lineup=? AND note NOT IN ('+','.join('?' for _ in ids)+')',(uid,*ids)) if ids else db.execute('DELETE FROM lineup_note_roles WHERE lineup=?',(uid,))
   db.execute('DELETE FROM lineup_notes WHERE lineup=?',(uid,));db.executemany('INSERT INTO lineup_notes VALUES(?,?)',[(uid,i) for i in set(ids)])
   db.execute('UPDATE topic_lineups SET revision=revision+1 WHERE id=?',(uid,));self.bump(db)
  return self.roster()
 def merge(self,payload):
  source=payload.get('source');target=payload.get('target')
  with self.topics.db() as db:
   db.execute('BEGIN IMMEDIATE');rows={r['id']:r for r in self.roster(db)}
   if source==target or source not in rows or target not in rows:raise ValueError('请选择两个不同阵容')
   a,b=rows[source],rows[target]
   if payload.get('source_revision')!=a['revision'] or payload.get('target_revision')!=b['revision']:raise workspace.Conflict('阵容已变化，请刷新后合并')
   if a['merged_into'] or b['merged_into'] or a['deleted_at'] or b['deleted_at'] or not b['enabled']:raise ValueError('不能合并到已合并或停用阵容')
   # Resolve legacy single-note primaries before moving rows; losing this
   # projection would turn a known primary + variant into ambiguous legacy links.
   primary_ids={link['note'] for r in (a,b) for link in r['note_links'] if link['role']=='primary'}
   if len(primary_ids)>1:raise workspace.Conflict('两个阵容已有不同主笔记，请先通过关联弹窗解除其中一个主笔记关联，再合并')
   roles={}
   priority={'legacy':0,'variant':1,'primary':2}
   for r in (b,a):
    for link in r['note_links']:
     old=roles.get(link['note'])
     if old is None or priority[link['role']]>priority[old]:roles[link['note']]=link['role']
   db.execute('UPDATE topic_lineups SET enabled=0,merged_into=?,revision=revision+1 WHERE id=?',(target,source))
   db.execute('UPDATE topic_lineups SET merged_into=? WHERE merged_into=?',(target,source))
   db.execute('UPDATE topic_candidates SET target=? WHERE target=?',(target,source))
   db.execute('INSERT OR IGNORE INTO lineup_variant_links SELECT ?,variant,sources,manual FROM lineup_variant_links WHERE lineup=?',(target,source));db.execute('DELETE FROM lineup_variant_links WHERE lineup=?',(source,))
   db.execute('INSERT OR IGNORE INTO lineup_notes SELECT ?,note FROM lineup_notes WHERE lineup=?',(target,source));db.execute('DELETE FROM lineup_notes WHERE lineup=?',(source,))
   db.execute('DELETE FROM lineup_note_roles WHERE lineup IN (?,?)',(source,target))
   db.executemany('INSERT INTO lineup_note_roles VALUES(?,?,?)',[(target,note,role) for note,role in roles.items()])
   db.execute('INSERT OR IGNORE INTO lineup_note_exclusions SELECT ?,note FROM lineup_note_exclusions WHERE lineup=?',(target,source))
   db.execute('DELETE FROM lineup_note_exclusions WHERE lineup=?',(source,))
   db.execute('UPDATE topic_lineups SET revision=revision+1 WHERE id=?',(target,));self.bump(db)
  return self.roster()

def _link_mutation(method):
 def run(self,*args,**kwargs):
  from note_links import recover_links,auto_link
  recover_links(self.root)
  result=method(self,*args,**kwargs)
  auto_link(self.root)
  if isinstance(result,list):return self.roster()
  if isinstance(result,dict) and 'roster' in result:result['roster']=self.roster()
  return result
 return run
for _method in ['save','save_batch','resolve_naming','apply','restore','delete','save_variants','bind','merge']:
 setattr(LineupCatalog,_method,_link_mutation(getattr(LineupCatalog,_method)))

def fetch_variants(read,scope,row):
 pages=[];items=[];seen=set();key=row.get('lineupKey')
 if not key:raise ValueError('主阵容缺少详情身份，导入不完整')
 for page in range(1,501):
  payload={**scope,'operator':'AND','advancedMode':False,'filters':[],'exclusions':[],'page':page,'pageSize':12,'lineupKey':key}
  data=json.loads(read('https://api.datatft.com/wzwxq/lineups/detail',payload))
  if data.get('code') not in [None,0,1,200]:raise ValueError('阵容详情请求失败')
  data=data.get('data',data);values=data.get('variants')
  if not isinstance(values,list):raise ValueError('阵容详情缺少变阵列表')
  marker=encode(values)
  if values and marker in seen:raise ValueError('变阵重复分页，导入不完整')
  seen.add(marker);pages.append(data);items.extend(values)
  total=data.get('variantCount')
  if not isinstance(total,int) or total<0:raise ValueError('变阵总数无效')
  if len(items)==total:break
  if not values or len(items)>total:raise ValueError('变阵数量不符，导入不完整')
  time.sleep(.4)
 else:raise ValueError('变阵分页超过安全上限')
 if any(not isinstance(v.get('count'),int) or not isinstance(v.get('heroes'),list) or not v['heroes'] for v in items):raise ValueError('变阵组成或场次缺失')
 return {'pages':pages,'scanned':len(items),'items':[v for v in items if v['count']>=scope['minimumCount']]}

def fetch_website(root):
 from lineup_website import read_website as read,website_scope
 scope=website_scope(read)
 pages=[];records=[];seen=set()
 for page in range(1,501):
  data=json.loads(read('https://api.datatft.com/wzwxq/lineups/search',{**scope,'operator':'AND','advancedMode':False,'filters':[],'exclusions':[],'page':page,'pageSize':12}))
  if data.get('code') not in [None,0,1,200]:raise ValueError('网站请求失败：'+str(data.get('message',data.get('msg','未知原因'))))
  data=data.get('data',data);items=data.get('lineups')
  if not isinstance(items,list):raise ValueError('网站阵容响应无效，原名单保留')
  marker=encode(items)
  if items and marker in seen:raise ValueError('网站重复返回相同分页，已停止导入')
  seen.add(marker);pages.append(data);records.extend(items)
  total=data.get('total')
  if not isinstance(total,int) or total<0 or len(records)>total:raise ValueError('主列表总数无效')
  if len(records)==total:break
  if not items:raise ValueError('网站提前返回空页，导入不完整')
  time.sleep(.4)
 else:raise ValueError('分页超过安全上限，未应用不完整名单')
 folder=Path(root)/'raw/crawler/lineup-imports';folder.mkdir(parents=True,exist_ok=True)
 details={}
 for row in records:
  details[row['lineupKey']]=fetch_variants(read,scope,row);time.sleep(.4)
 stamp=uuid.uuid4().hex;wxq.atomic_json(folder/(stamp+'.json'),{'scope':scope,'pages':pages,'details':details})
 # Normalization follows the public response shape; original rows remain in the snapshot.
 normalized=[];local=wxq.read_json(Path(root)/'entities/heroes.json',[])
 for r in records:
  try:normalized.append({'name':website_name(r,local),'heroes':['card:'+str(h['id']) for h in r.get('heroes',[])],'usage':r.get('appearanceRate',0),'games':r.get('count',0),'raw':r})
  except (KeyError,TypeError,ValueError):normalized.append({'name':'网站记录结构异常','heroes':[],'raw':r})
 report=normalize_records(normalized,local)
 unique=set();links=0
 valid={h['id'] for h in local}
 for item in report['items']:
  variants={}
  for source in item['sources']:
   for v in details[source['raw']['lineupKey']]['items']:
    ids=tuple(sorted({'card:'+str(h['id']) for h in v['heroes']}))
    if not ids or any(h not in valid for h in ids):raise ValueError('变阵英雄身份未知，原名单保留')
    if set(ids)==set(item['heroes']):continue
    entry=variants.setdefault(ids,{'heroes':list(ids),'sources':[]});entry['sources'].append({'parent_key':source['raw']['lineupKey'],'games':v['count'],'usage':v.get('appearanceRate'),'raw':v})
  item['variants']=list(variants.values());links+=len(variants);unique.update(variants)
 return {**report,'variant_scanned':sum(d['scanned'] for d in details.values()),'variant_links':links,'variant_unique':len(unique),'scope':scope,'url':SITE+'/lineups','fetched_at':wxq.now(),'pages':len(pages),'snapshot':str(folder/(stamp+'.json'))}

def website_name(row,heroes):
 """Mirror the website's public lineupPresentation title rule, not an LLM name."""
 by_id={r['id'].replace('card:',''):r for r in heroes};factions={};core={h['id'] for h in row.get('coreHeroes',[])}
 for i,h in enumerate(row['heroes']):
  faction=by_id.get(h['id'],{}).get('properties',{}).get('relationName')
  if not faction or faction=='无阵营':continue
  count,cores,order=factions.get(faction,(0,0,i));factions[faction]=(count+1,cores+int(h['id'] in core),order)
 faction=sorted(factions,key=lambda f:(-factions[f][0],-factions[f][1],factions[f][2]))[0] if factions else None
 units={u['heroId']:u for u in row.get('recommendedUnits',[])}
 equipped=[(i,h,units[h['id']]) for i,h in enumerate(row['heroes']) if len(units.get(h['id'],{}).get('itemIds',[]))==3]
 equipped.sort(key=lambda x:(-x[2].get('appearanceRate',0),-x[2].get('count',0),x[0]))
 return ' · '.join(([faction] if faction else [])+[h['name'] for _,h,_ in equipped[:2]]) or str(row.get('lineupSize',len(row['heroes'])))+' 人阵容'
