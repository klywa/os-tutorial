"""Explicit video/part demands share BV workers and registered transcript artifacts."""
import re,json
from urllib.parse import urlsplit,parse_qs

def schema(db):
 db.executescript("""CREATE TABLE IF NOT EXISTS link_demands(job TEXT,bvid TEXT,parts TEXT,PRIMARY KEY(job,bvid));
 CREATE TABLE IF NOT EXISTS part_discoveries(bvid TEXT PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS video_parts(bvid TEXT,part INTEGER,PRIMARY KEY(bvid,part));
 CREATE TABLE IF NOT EXISTS part_results(bvid TEXT,part INTEGER,state TEXT,error TEXT DEFAULT '',PRIMARY KEY(bvid,part));""")

def resolve_short(url):
 import urllib.request
 class Redirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,req,fp,code,msg,headers,newurl):
   parsed=urlsplit(newurl)
   if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in [None,443] or parsed.hostname not in ['b23.tv','www.bilibili.com','bilibili.com','m.bilibili.com']:raise ValueError('短链接跳转到了不支持的地址')
   return super().redirect_request(req,fp,code,msg,headers,newurl)
 with urllib.request.build_opener(Redirect()).open(url,timeout=15) as response:return response.url

def parse_links(text):
 if not isinstance(text,str) or len(text)>200000:raise ValueError('链接输入过长或格式无效')
 videos={};invalid=[];duplicates=0;lines=[]
 for number,raw in enumerate(text.splitlines(),1):
  raw=raw.strip()
  if not raw:continue
  try:
   value=raw
   if re.fullmatch(r'BV[a-zA-Z0-9]{10}(?:\?p=\d+)?',value):value='https://www.bilibili.com/video/'+value
   parsed=urlsplit(value)
   if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in [None,443]:raise ValueError('仅支持HTTPS的B站视频链接')
   if parsed.hostname=='b23.tv':value=resolve_short(value);parsed=urlsplit(value)
   match=re.fullmatch(r'/video/(BV[a-zA-Z0-9]{10})/?',parsed.path)
   if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in [None,443] or parsed.hostname not in ['www.bilibili.com','bilibili.com','m.bilibili.com'] or not match:raise ValueError('不是B站视频链接')
   params=parse_qs(parsed.query,keep_blank_values=True);part=params.get('p',[None])[0]
   if part is not None and (not part.isdigit() or int(part)<1 or int(part)>10000):raise ValueError('分P编号无效')
   bvid=match[1];parts=[int(part)] if part else None;old=videos.get(bvid)
   if old:
    duplicates+=1
    old['parts']=None if old['parts'] is None or parts is None else sorted(set(old['parts']+parts))
   else:videos[bvid]={'bvid':bvid,'url':'https://www.bilibili.com/video/'+bvid,'title':'','parts':parts}
   lines.append({'line':number,'input':raw,'bvid':bvid,'parts':parts,'valid':True})
  except (ValueError,OSError) as exc:
   item={'line':number,'input':raw,'error':str(exc),'valid':False};invalid.append(item);lines.append(item)
 return {'videos':list(videos.values()),'invalid':invalid,'duplicates':duplicates,'lines':lines}

def scope_for(store,bvid,db=None):
 if db is None:
  with store.db() as connection:return scope_for(store,bvid,connection)
 rows=db.execute("SELECT l.parts FROM dispatch d JOIN jobs j ON j.id=d.job LEFT JOIN link_demands l ON l.job=d.job AND l.bvid=d.bvid WHERE d.bvid=? AND j.state NOT IN ('stopped','deleted')",(bvid,)).fetchall()
 if not rows:return []
 if any(r['parts'] is None or json.loads(r['parts']) is None for r in rows):return None
 return sorted({p for r in rows for p in json.loads(r['parts'])})

def record_parts(store,bvid,entries):
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  db.executemany('INSERT OR IGNORE INTO video_parts VALUES(?,?)',[(bvid,int(r.get('playlist_index') or i)) for i,r in enumerate(entries,1)])
  db.execute('INSERT OR IGNORE INTO part_discoveries VALUES(?)',(bvid,))

def mark_part(store,bvid,part,state,error='',generation=None):
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT generation,state FROM tasks WHERE bvid=?',(bvid,)).fetchone()
  if generation is not None and (not row or row['generation']!=generation or row['state'] in ['paused','cancelled']):return
  db.execute('INSERT OR REPLACE INTO part_results VALUES(?,?,?,?)',(bvid,part,state,error))

def demand_done(store,bvid,parts,db):
 if parts is None and not db.execute('SELECT 1 FROM part_discoveries WHERE bvid=?',(bvid,)).fetchone():return False
 wanted=parts if parts is not None else [r[0] for r in db.execute('SELECT part FROM video_parts WHERE bvid=?',(bvid,))]
 if not wanted:return False
 completed={r[0] for r in db.execute("SELECT part FROM part_results WHERE bvid=? AND state='succeeded'",(bvid,))}
 return set(wanted)<=completed

def start_links(store,text,tags=None):
 from crawler import now,encode
 report=parse_links(text)
 if not report['videos']:raise ValueError('没有有效的视频链接')
 import uuid
 from crawler import config
 jid=uuid.uuid4().hex[:12]
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  db.execute('INSERT INTO jobs(id,config,state,created,scanned,matched,duplicates) VALUES(?,?,?,?,?,?,?)',(jid,encode(config({'kind':'links','keywords':[],'process_limit':10000,'tags':tags if tags is not None else []})),'scanned',now(),len(report['lines']),len(report['videos']),report['duplicates']))
  for video in report['videos']:
   db.execute('INSERT INTO link_demands VALUES(?,?,?)',(jid,video['bvid'],json.dumps(video['parts'])))
   db.execute('INSERT OR IGNORE INTO videos VALUES(?,?)',(video['bvid'],encode({**video,'collected_at':now()})))
   db.execute("INSERT INTO hits VALUES(?,?,'')",(jid,video['bvid']))
   store.queue_job_tags(jid,video['bvid'],db)
 from video_titles import sync_cached
 import workspace
 for video in report['videos']:
  sync_cached(store.root,store,video['bvid'],video['parts'])
  for part in video['parts'] or [1]:
   url=video['url']+'?p='+str(part)
   workspace.register_source(store.root,{'url':url,'title':'','notes':''},preserve_annotations=True,wait=True,_metadata={})
 store.enqueue(jid,[v['bvid'] for v in report['videos']])
 result=store.job(jid);done=result['counts']['succeeded']
 titles={r['bvid']:r.get('title','') for r in result.get('items',[])}
 for row in report['videos']:row['title']=titles.get(row['bvid'],'')
 return {**report,'job':result, 'accepted':len(report['videos']),'completed':done,'added':len(report['videos'])-done}

def inspect_artifacts(store,bvid):
 """Read/hash transcript files before taking the queue's write lock."""
 import wxq
 from reference_store import transcript_errors
 artifacts=[]
 for folder in (store.root/'raw/sources').glob(bvid+'_p*'):
  meta=wxq.read_json(folder/'metadata.json',{});part=meta.get('part');sid=meta.get('id')
  if not isinstance(part,int) or not sid:continue
  count=meta.get('part_count')
  valid=not any(not e.startswith('Transcript was manually edited') for e in transcript_errors(store.root,sid))
  artifacts.append((part,count,valid))
 return artifacts

def refresh_artifacts(db,bvid,artifacts):
 """Apply a previously inspected snapshot using SQL only."""
 for part,count,valid in artifacts:
  if isinstance(count,int) and 0<count<=10000:db.executemany('INSERT OR IGNORE INTO video_parts VALUES(?,?)',[(bvid,i) for i in range(1,count+1)])
  if not valid:
   db.execute('DELETE FROM part_results WHERE bvid=? AND part=?',(bvid,part));continue
  db.execute("INSERT OR REPLACE INTO part_results VALUES(?,?,'succeeded','')",(bvid,part))

def state_for(store,jid,bvid,state):
 with store.db() as db:
  demand=db.execute('SELECT parts FROM link_demands WHERE job=? AND bvid=?',(jid,bvid)).fetchone()
  if demand:
   if demand_done(store,bvid,json.loads(demand['parts']),db):return 'succeeded'
   if state=='succeeded':return 'queued'
 return state


def part_requested(store,bvid,part,generation=None):
 if generation is not None and (store.halted(bvid) or not store.requested(bvid,generation)):return False
 scope=scope_for(store,bvid)
 return scope is None or part in scope

def reconcile(store):
 """Older surviving workers may finish without writing the new per-part records."""
 with store.db() as db:
  pending=db.execute("SELECT l.job,l.bvid FROM link_demands l JOIN jobs j ON j.id=l.job LEFT JOIN dispatch d ON d.job=l.job AND d.bvid=l.bvid WHERE d.job IS NULL AND j.state NOT IN ('stopped','deleted')").fetchall()
 for row in pending:store.enqueue(row['job'],[row['bvid']])
 with store.db() as db:
  completed=db.execute("SELECT DISTINCT t.bvid,t.generation FROM tasks t JOIN link_demands l ON l.bvid=t.bvid WHERE t.state='succeeded'").fetchall()
 for row in completed:
  artifacts=inspect_artifacts(store,row['bvid'])
  with store.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if not db.execute("SELECT 1 FROM tasks WHERE bvid=? AND generation=? AND state='succeeded'",(row['bvid'],row['generation'])).fetchone():continue
   bvid=row['bvid'];scope=scope_for(store,bvid,db)
   if scope==[]:continue
   refresh_artifacts(db,bvid,artifacts)
   if not demand_done(store,bvid,scope,db):db.execute("UPDATE tasks SET state='queued',progress='{}',error='',error_data='{}' WHERE bvid=? AND state='succeeded'",(bvid,))
