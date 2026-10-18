"""Local, source-scoped topic queue. Model output never changes knowledge notes."""
import hashlib,json,sqlite3,time,uuid,sys
from pathlib import Path
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.codex/skills/wanxiangqi-knowledge/scripts'))
import wxq,workspace

TOPIC_FIELDS=('topic_players','topic_lineups','topic_heroes','topic_cards')
PROMPT_VERSION='major-topics-v7-two-pass'
MODEL='Qwen3-1.7B-Q8_0'

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)
def lineup_names(row):return [x for x in [row.get('common_name',''),row['name'],*row.get('aliases',[])] if x]
def fingerprint(row):
 path=Path(row['transcript_path']) if row.get('transcript_path') else None
 stat=path.stat() if path and path.is_file() else None
 return hashlib.sha256(encode([row.get('title',''),hashlib.sha256(path.read_bytes()).hexdigest() if stat else None,MODEL,PROMPT_VERSION]).encode()).hexdigest()

def catalog(root):
 result={key:[] for key in TOPIC_FIELDS}
 for kind,key in [('players','topic_players'),('heroes','topic_heroes'),('equipment','topic_cards'),('talents','topic_cards'),('effect-cards','topic_cards'),('player-skills','topic_cards'),('derivatives','topic_cards')]:
  for e in wxq.read_json(Path(root)/'entities'/f'{kind}.json',[]):
   result[key].append({'id':e['id'],'name':e['name']+('（觉醒）' if e.get('properties',{}).get('type')==9 else ''),'aliases':e.get('aliases',[])})
 result['topic_lineups']=TopicStore(root).roster()
 return result

def validate_result(data,text,players):
 if not isinstance(data,dict) or set(data)-{'players','lineups'}:raise ValueError('主题输出格式无效')
 ids={p['id'] for p in players};result={'players':[],'lineups':[]}
 for key in result:
  rows=data.get(key,[])
  if not isinstance(rows,list):raise ValueError('主题结果必须为列表')
  for item in rows:
   if not isinstance(item,dict):raise ValueError('主题条目无效')
   evidence=item.get('evidence','')
   if not isinstance(evidence,str) or not 4<=len(evidence.strip())<=80 or evidence not in text:raise ValueError('主题引文无法核验或超出80字')
   value=item.get('id' if key=='players' else 'name')
   if not isinstance(value,str) or not value.strip() or (key=='players' and value not in ids):raise ValueError('主题实体无效')
   if key=='players' and not any(n and n in text for p in players if p['id']==value for n in [p['name'],*p.get('aliases',[])]):continue
   if key=='players' and not any(n and n in evidence for p in players if p['id']==value for n in [p['name'],*p.get('aliases',[])]):raise ValueError('棋手引文没有指出对应名称')
   if key=='lineups':
    if value in {p['name'] for p in players}:continue
   normalized={'id' if key=='players' else 'name':value.strip(),'evidence':evidence}
   if key=='lineups':normalized['grounded']=value.strip() in evidence
   if key=='lineups':
    members=item.get('members',[]);complete=item.get('complete',False)
    if not isinstance(members,list) or not isinstance(complete,bool):raise ValueError('阵容组成证据无效')
    for member in members:
     if not isinstance(member,dict) or not isinstance(member.get('name'),str) or not isinstance(member.get('evidence'),str) or not 4<=len(member['evidence'])<=80 or member['evidence'] not in text or member['name'] not in member['evidence']:raise ValueError('阵容成员引文无法核验')
    normalized.update(members=members,complete=complete)
   if normalized not in result[key]:result[key].append(normalized)
 return result

class TopicStore:
 def __init__(self,root):
  self.root=Path(root);self.path=self.root/'raw/crawler/topics.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.db() as db:db.executescript('''
   CREATE TABLE IF NOT EXISTS topic_tasks(source TEXT PRIMARY KEY,fingerprint TEXT,state TEXT,generation INTEGER DEFAULT 0,result TEXT DEFAULT '{}',progress TEXT DEFAULT '{}',error TEXT DEFAULT '',updated TEXT);
   CREATE TABLE IF NOT EXISTS topic_lineups(id TEXT PRIMARY KEY,name TEXT UNIQUE,aliases TEXT,enabled INTEGER);
   CREATE TABLE IF NOT EXISTS topic_candidates(id TEXT PRIMARY KEY,source TEXT,name TEXT,evidence TEXT,fingerprint TEXT,state TEXT DEFAULT 'pending',target TEXT,grounded INTEGER DEFAULT 1);
   CREATE TABLE IF NOT EXISTS topic_settings(key TEXT PRIMARY KEY,value TEXT);
  ''')
  # Existing queued candidates predate the explicit new-mapping review flag.
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if 'grounded' not in {r['name'] for r in db.execute('PRAGMA table_info(topic_candidates)')}:
    db.execute('ALTER TABLE topic_candidates ADD COLUMN grounded INTEGER DEFAULT 1')
    db.execute('UPDATE topic_candidates SET grounded=instr(evidence,name)>0')
   for table,name,kind in [('topic_tasks','roster_revision','INTEGER DEFAULT 0'),('topic_tasks','batch',"TEXT DEFAULT ''"),('topic_candidates','members',"TEXT DEFAULT '[]'"),('topic_candidates','complete','INTEGER DEFAULT 0'),('topic_candidates','resolution',"TEXT DEFAULT 'auto'")]:
    if name not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
  try:
   yield db;db.commit()
  except BaseException:db.rollback();raise
  finally:db.close()
 def setting(self,key,value=None):
  with self.db() as db:
   if value is not None:db.execute('INSERT OR REPLACE INTO topic_settings VALUES(?,?)',(key,encode(value)))
   row=db.execute('SELECT value FROM topic_settings WHERE key=?',(key,)).fetchone()
   return json.loads(row[0]) if row else False
 def roster(self):
  from lineup_catalog import LineupCatalog
  return LineupCatalog(self.root).roster()
 def validated(self):
  value=self.setting('validated')
  return value is True or isinstance(value,dict) and value.get('model')==MODEL and value.get('prompt_version')==PROMPT_VERSION and value.get('passed') is True
 def save_roster(self,payload):
  from lineup_catalog import LineupCatalog
  roster_store=LineupCatalog(self.root)
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if 'names' in payload:
    names=payload['names']
    if not isinstance(names,list) or any(not isinstance(n,str) for n in names):raise ValueError('阵容名单须为文字列表')
    existing=[dict(r) for r in db.execute('SELECT * FROM topic_lineups')]
    for name in names:
     name=name.strip()
     if any(name in json.loads(r['aliases']) and name!=r['name'] for r in existing):raise ValueError('该名称已是其他阵容的确认别称')
     if name and not db.execute('SELECT 1 FROM topic_lineups WHERE name=?',(name,)).fetchone():db.execute('INSERT INTO topic_lineups(id,name,aliases,enabled) VALUES(?,?,?,1)',('lineup:'+uuid.uuid4().hex,name,'[]'))
   else:
    uid=payload.get('id');name=payload.get('name','').strip();aliases=payload.get('aliases',[])
    if not name or not isinstance(aliases,list) or any(not isinstance(a,str) for a in aliases):raise ValueError('阵容名称或别称无效')
    if not isinstance(payload.get('enabled',True),bool):raise ValueError('启用状态无效')
    current=db.execute('SELECT * FROM topic_lineups WHERE id=?',(uid,)).fetchone()
    if not current:raise KeyError('阵容不存在')
    if dict(current).get('deleted_at') or dict(current).get('merged_into'):raise ValueError('阵容已删除或合并，不能编辑')
    aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip() and a.strip()!=name))
    occupied={x for r in db.execute('SELECT * FROM topic_lineups WHERE id!=?',(uid,)) for x in [r['name'],*json.loads(r['aliases'])]}
    if any(x in occupied for x in [name,*aliases]):raise ValueError('名称或别称与其他阵容重复')
    previous=json.loads(db.execute('SELECT manual_fields FROM topic_lineups WHERE id=?',(uid,)).fetchone()[0])
    db.execute('UPDATE topic_lineups SET name=?,aliases=?,enabled=?,revision=revision+1,manual_fields=? WHERE id=?',(name,encode(list(dict.fromkeys(a.strip() for a in aliases if a.strip()))),int(payload.get('enabled',True)),encode(sorted(set(previous)|{'name','aliases','enabled'})),uid))
   roster_store.bump(db)
  return self.roster()
 def reconcile(self,db):
  db.execute("UPDATE topic_candidates SET state='pending',target=NULL WHERE state='resolved' AND resolution='auto' AND target IN (SELECT id FROM topic_lineups WHERE enabled=1)")
  roster=[{**dict(r),'aliases':json.loads(r['aliases']),'heroes':json.loads(dict(r).get('heroes','[]'))} for r in db.execute('SELECT * FROM topic_lineups WHERE enabled=1')]
  if db.execute("SELECT 1 FROM sqlite_master WHERE name='lineup_variant_links'").fetchone():
   for r in roster:r['variants']=[{'heroes':json.loads(v[0])} for v in db.execute('SELECT v.heroes FROM lineup_variants v JOIN lineup_variant_links l ON v.id=l.variant WHERE l.lineup=?',(r['id'],))]
  for c in list(db.execute("SELECT * FROM topic_candidates WHERE state='pending'")):
   target=self.candidate_target(c,roster)
   if target:db.execute("UPDATE topic_candidates SET state='resolved',target=? WHERE id=?",(target,c['id']))
 def candidate_target(self,c,roster):
  c=dict(c)
  if 'heroes' not in c:
   c['heroes']=[m.get('id') for m in json.loads(c.get('members','[]'))] if isinstance(c.get('members','[]'),str) else [m.get('id') for m in c.get('members',[])]
  hits=[r['id'] for r in roster if r['enabled'] and c['name'] in lineup_names(r) and (c.get('grounded',False) or any(n in c['evidence'] for n in lineup_names(r)))]
  if len(hits)==1:return hits[0]
  if c.get('complete') and c.get('heroes'):
   hits=[r['id'] for r in roster if r['enabled'] and (not hits or r['id'] in hits) and any(set(h)==set(c['heroes']) for h in [r.get('heroes',[]),*[v['heroes'] for v in r.get('variants',[])]])]
   if len(hits)==1:return hits[0]
  return None
 def map_lineup(self,name):
  hits=[r['id'] for r in self.roster() if r['enabled'] and name in lineup_names(r)]
  return hits[0] if len(hits)==1 else None
 def sync(self,rows):
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   for r in rows:
    fp=fingerprint(r);state='ignored' if r.get('ignored') else 'waiting' if not r.get('transcript_path') else 'no_speech' if r.get('transcript_status')=='no_speech' else 'queued'
    old=db.execute('SELECT * FROM topic_tasks WHERE source=?',(r['id'],)).fetchone()
    if not old:db.execute('INSERT INTO topic_tasks(source,fingerprint,state,updated) VALUES(?,?,?,?)',(r['id'],fp,state,wxq.now()))
    elif old['fingerprint']!=fp or (old['state'] in ['ignored','waiting','no_speech'] and old['state']!=state) or state!='queued' and old['state']!=state:
     db.execute("UPDATE topic_tasks SET fingerprint=?,state=?,generation=generation+1,error='',progress='{}',updated=? WHERE source=?",(fp,state,wxq.now(),r['id']))
 def project(self,rows):
  with self.db() as db:
   tasks={r['source']:dict(r) for r in db.execute('SELECT * FROM topic_tasks')}
   candidates=[dict(r) for r in db.execute('SELECT * FROM topic_candidates')]
  roster=self.roster()
  redirects={x['id']:x.get('merged_into') for x in roster if x.get('merged_into')}
  for r in rows:
   task=tasks.get(r['id'],{});data=json.loads(task.get('result','{}'))
   r.update({k:[] for k in TOPIC_FIELDS});r['ignored']=False
   r['topic_players']=list(dict.fromkeys(p['id'] for p in data.get('players',[])))
   for c in candidates:
    if c['source']!=r['id'] or c['fingerprint']!=data.get('_fingerprint',task.get('fingerprint')) or c['state']=='rejected' or c['name'] not in {x['name'] for x in data.get('lineups',[])}:continue
    target=c['target'] if c['state']=='resolved' else self.candidate_target(c,roster)
    if target and target not in r['topic_lineups']:r['topic_lineups'].append(target)
   r['topic_state']=task.get('state','waiting');r['topic_error']=task.get('error','')
   r['topic_manual']=[k for k in TOPIC_FIELDS if k in r.get('manual_values',{})]
   r.update(r.get('manual_values',{}))
   r['topic_lineups']=list(dict.fromkeys(redirects.get(x,x) for x in r['topic_lineups']))
  return rows
 def snapshot(self):
  with self.db() as db:
   counts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM topic_tasks GROUP BY state')}
   active=[{**dict(r),'progress':json.loads(r['progress'])} for r in db.execute("SELECT source,state,progress,error FROM topic_tasks WHERE state IN ('running','failed') ORDER BY updated DESC LIMIT 20")]
  return {'counts':counts,'active':active,'paused':self.setting('paused'),'validated':self.validated(),'model':MODEL,'roster_count':len(self.roster()),'roster_revision':self.setting('catalog_revision') or 0,'batch':self.setting('topic_batch')}
 def control(self,action,source=None):
  if action in ['pause','resume']:self.setting('paused',action=='pause')
  elif action=='reextract':
   batch=wxq.now()+'-'+uuid.uuid4().hex[:8];self.setting('topic_batch',{'id':batch,'roster_revision':self.setting('catalog_revision') or 0,'model':MODEL,'prompt_version':PROMPT_VERSION})
   with self.db() as db:db.execute("UPDATE topic_tasks SET state='queued',generation=generation+1,error='',progress='{}',batch=? WHERE state NOT IN ('ignored','waiting','no_speech')",(batch,))
  elif action in ['retry','extract']:
   with self.db() as db:
    if source:db.execute("UPDATE topic_tasks SET state='queued',generation=generation+1,error='' WHERE source=? AND state NOT IN ('ignored','waiting','no_speech')",(source,))
    else:db.execute("UPDATE topic_tasks SET state='queued',generation=generation+1,error='' WHERE state='failed'")
  else:raise ValueError('未知主题任务操作')
  return self.snapshot()
 def pending(self):
  with self.db() as db:rows=[dict(r) for r in db.execute("SELECT c.*,t.fingerprint current,t.result current_result FROM topic_candidates c JOIN topic_tasks t ON t.source=c.source WHERE c.state='pending' AND t.state!='ignored'")]
  roster=self.roster()
  rows=[r for r in rows if r['fingerprint']==r['current'] and r['name'] in {x['name'] for x in json.loads(r['current_result']).get('lineups',[])} and not self.candidate_target(r,roster)]
  index=wxq.read_json(self.root/'raw/index.json',{}).get('sources',{})
  for r in rows:
   r['members']=json.loads(r['members']);r['reason']='名称或完整组成未唯一匹配名单'
   path=index.get(r['source'],{}).get('path')
   try:
    target=(self.root/path).resolve() if path else None
    text=target.read_text('utf-8') if target and target.is_relative_to((self.root/'raw').resolve()) else '';pos=text.find(r['evidence']);r['context']=text[max(0,pos-250):pos+len(r['evidence'])+250] if pos>=0 else r['evidence']
   except OSError:r['context']=r['evidence']
  return rows
 def resolve(self,cid,payload):
  from lineup_catalog import LineupCatalog
  roster_store=LineupCatalog(self.root)
  target=payload.get('target');reject=payload.get('reject',False)
  if not reject and target not in {r['id'] for r in self.roster() if r['enabled']}:raise ValueError('请选择名单内阵容')
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   candidate=db.execute('SELECT * FROM topic_candidates WHERE id=?',(cid,)).fetchone()
   if not candidate:raise KeyError('候选不存在')
   task=db.execute('SELECT * FROM topic_tasks WHERE source=?',(candidate['source'],)).fetchone()
   if not task or task['state']=='ignored' or task['fingerprint']!=candidate['fingerprint'] or candidate['name'] not in {r['name'] for r in json.loads(task['result']).get('lineups',[])}:raise workspace.Conflict('候选已过期或内容已忽略，请刷新待确认列表')
   if not reject:
    row=db.execute('SELECT * FROM topic_lineups WHERE id=? AND enabled=1',(target,)).fetchone()
    if not row:raise ValueError('阵容已停用')
   if not reject and payload.get('remember_alias'):
    name=candidate['name']
    aliases=json.loads(row['aliases'])
    if name!=row['name'] and name not in aliases:aliases.append(name)
    db.execute('UPDATE topic_lineups SET aliases=?,revision=revision+1,manual_fields=? WHERE id=?',(encode(aliases),encode(list(set(json.loads(row['manual_fields']))|{'aliases'})),target))
   if not db.execute("UPDATE topic_candidates SET state=?,target=?,resolution='manual' WHERE id=?",('rejected' if reject else 'resolved',target,cid)).rowcount:raise KeyError('候选不存在')
   if payload.get('remember_alias') and not reject:roster_store.bump(db)
   else:self.reconcile(db)
  return self.pending()
 def claim(self):
  if self.setting('paused') or not self.validated():return None
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT * FROM topic_tasks WHERE state='queued' ORDER BY updated,source LIMIT 1").fetchone()
   if row:
    revision=self.setting('catalog_revision') or 0
    db.execute("UPDATE topic_tasks SET state='running',generation=generation+1,progress='{}',roster_revision=? WHERE source=?",(revision,row['source']))
    return {**dict(row),'generation':row['generation']+1,'roster_revision':revision}
 def finish(self,task,data,error=''):
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if not db.execute("SELECT 1 FROM topic_tasks WHERE source=? AND generation=? AND fingerprint=? AND state='running'",(task['source'],task['generation'],task['fingerprint'])).fetchone():return False
   revision=db.execute("SELECT value FROM topic_settings WHERE key='catalog_revision'").fetchone()
   if task.get('roster_revision',0)!=(json.loads(revision[0]) if revision else 0):
    db.execute("UPDATE topic_tasks SET state='queued',generation=generation+1 WHERE source=?",(task['source'],));return False
   if not error:data={**data,'_fingerprint':task['fingerprint']}
   db.execute('UPDATE topic_tasks SET state=?,result=CASE WHEN ? THEN result ELSE ? END,error=?,updated=? WHERE source=?',('failed' if error else 'succeeded',bool(error),encode(data),error,wxq.now(),task['source']))
   if not error:
    for c in data.get('lineups',[]):
     cid=hashlib.sha256(encode([task['source'],task['fingerprint'],c['name']]).encode()).hexdigest()[:24]
     db.execute('INSERT OR IGNORE INTO topic_candidates(id,source,name,evidence,fingerprint,grounded) VALUES(?,?,?,?,?,?)',(cid,task['source'],c['name'],c['evidence'],task['fingerprint'],int(c.get('grounded',True))))
     db.execute("UPDATE topic_candidates SET evidence=?,grounded=?,members=?,complete=? WHERE id=? AND state='pending'",(c['evidence'],int(c.get('grounded',True)),encode(c.get('members',[])),int(c.get('complete',False)),cid))
    self.reconcile(db)
   return True
