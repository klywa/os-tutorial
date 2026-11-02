"""Durable annotation work; never write knowledge files inside a queue transaction."""
import json,uuid
from pathlib import Path
import wxq,workspace
from crawler_retries import tag_target

def normalize_tags(value):
    if not isinstance(value,list) or any(not isinstance(x,str) for x in value):
        raise ValueError('标签须为文字列表')
    return list(dict.fromkeys(x.strip() for x in value if x.strip()))

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS acquisition_tags(
        owner TEXT,bvid TEXT,parts TEXT,tags TEXT,state TEXT DEFAULT 'pending',
        error TEXT DEFAULT '',version INTEGER DEFAULT 1,PRIMARY KEY(owner,bvid))''')

class TagMixin:
    def tag_requested(self,item,db):
        owner=item['owner']
        if owner.startswith('creator:'):
            row=db.execute("SELECT c.data,j.state FROM creators c LEFT JOIN jobs j ON j.id=json_extract(c.data,'$.job_id') WHERE c.uid=?",(owner.split(':',1)[1],)).fetchone()
            return bool(row and json.loads(row['data']).get('enabled',True) and row['state'] not in ('stopped','deleted'))
        row=db.execute('SELECT state FROM jobs WHERE id=?',(owner,)).fetchone()
        return not row or row['state'] not in ('stopped','deleted')

    def queue_tags(self,owner,bvid,tags,parts=None,db=None):
        tags=normalize_tags(tags)
        if not tags:return
        if db is None:
            with self.db() as connection:
                connection.execute('BEGIN IMMEDIATE')
                return self.queue_tags(owner,bvid,tags,parts,connection)
        old=db.execute('SELECT tags,parts FROM acquisition_tags WHERE owner=? AND bvid=?',(owner,bvid)).fetchone()
        if old:
            tags=normalize_tags(json.loads(old['tags'])+tags)
            previous=json.loads(old['parts'])
            parts=None if previous is None or parts is None else sorted(set(previous+parts))
        db.execute('''INSERT INTO acquisition_tags(owner,bvid,parts,tags) VALUES(?,?,?,?)
            ON CONFLICT(owner,bvid) DO UPDATE SET tags=excluded.tags,parts=excluded.parts,
            state='pending',error='',version=acquisition_tags.version+1''',(owner,bvid,json.dumps(parts),json.dumps(tags,ensure_ascii=False)))
        db.execute("DELETE FROM acquisition_retries WHERE kind='tag' AND target=?",(tag_target(owner,bvid),))

    def queue_job_tags(self,jid,bvid,db=None):
        if db is None:
            with self.db() as connection:
                connection.execute('BEGIN IMMEDIATE')
                return self.queue_job_tags(jid,bvid,connection)
        job=db.execute('SELECT config,creator FROM jobs WHERE id=?',(jid,)).fetchone()
        if not job:return
        tags=json.loads(job['config']).get('tags',[]);owner=jid
        if job['creator']:
            creator=db.execute('SELECT data FROM creators WHERE uid=?',(job['creator'],)).fetchone()
            if creator:
                row=json.loads(creator['data']);video=db.execute('SELECT data FROM videos WHERE bvid=?',(bvid,)).fetchone()
                author=(json.loads(video['data']).get('author') or '') if video else ''
                tags=row.get('tags',[])+[row.get('name','').strip() or author.strip() or 'UP主'+job['creator']]
                owner='creator:'+job['creator']
        demand=db.execute('SELECT parts FROM link_demands WHERE job=? AND bvid=?',(jid,bvid)).fetchone()
        self.queue_tags(owner,bvid,tags,json.loads(demand['parts']) if demand else None,db)

    def queue_creator_tags(self,uid):
        # Expand historical associations in the background, not in the configuration request.
        with self.db() as db:
            creator=db.execute('SELECT data FROM creators WHERE uid=?',(uid,)).fetchone()
            if creator:
                row=json.loads(creator['data'])
                self.queue_tags('creator:'+uid,'@registry',row.get('tags',[])+[row.get('name','').strip() or 'UP主'+uid],db=db)

    def retry_tags(self,uid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("DELETE FROM acquisition_retries WHERE kind='tag' AND json_extract(target,'$[0]')=?",('creator:'+uid,))
            db.execute("UPDATE acquisition_tags SET state='pending',error='',version=version+1 WHERE owner=? AND state IN ('failed','pending')",('creator:'+uid,))
        return self.creators()

    def process_tags(self,limit=10):
        from crawler import now
        from processing_lock import file_lock
        import hashlib
        with self.db() as db:work=db.execute("""SELECT t.* FROM acquisition_tags t WHERE state='pending'
            AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.id=t.owner AND j.state IN ('stopped','deleted'))
            AND (t.owner NOT LIKE 'creator:%' OR EXISTS(SELECT 1 FROM creators c
                JOIN jobs j ON j.id=json_extract(c.data,'$.job_id') WHERE t.owner='creator:'||c.uid
                AND json_extract(c.data,'$.enabled')!=0 AND j.state NOT IN ('stopped','deleted')))
            AND NOT EXISTS(SELECT 1 FROM acquisition_retries a WHERE a.kind='tag'
                AND a.target=json_array(t.owner,t.bvid) AND a.next_retry_at>?)
            ORDER BY t.rowid LIMIT ?""",(now(),limit)).fetchall()
        for item in work:
            key=tag_target(item['owner'],item['bvid'])
            try:
                with file_lock(self.root/'raw/crawler/tag-locks'/(hashlib.sha256(key.encode()).hexdigest()+'.lock')):
                    with self.db() as db:
                        current=db.execute('SELECT state,version FROM acquisition_tags WHERE owner=? AND bvid=?',(item['owner'],item['bvid'])).fetchone()
                        retry=self.retry_status('tag',key,db)
                        requested=self.tag_requested(item,db)
                    if not requested or not current or current['state']!='pending' or current['version']!=item['version']:continue
                    if retry and retry['next_retry_at']>now():continue
                    try:
                        self._process_tag_item(item)
                        state,error='done',''
                    except Exception as exc:state,error='failed',exc
                    with self.db() as db:
                        db.execute('BEGIN IMMEDIATE')
                        current=db.execute('SELECT version FROM acquisition_tags WHERE owner=? AND bvid=?',(item['owner'],item['bvid'])).fetchone()
                        if not current or current['version']!=item['version']:continue
                        if state=='failed':
                            retry=self.schedule_retry(db,'tag',key,error,item['version'],'tagging')
                            if retry:state='pending'
                        else:db.execute("DELETE FROM acquisition_retries WHERE kind='tag' AND target=?",(key,))
                        db.execute('UPDATE acquisition_tags SET state=?,error=? WHERE owner=? AND bvid=? AND version=?',(state,str(error),item['owner'],item['bvid'],item['version']))
            except workspace.Busy:
                pass  # Another processor owns this exact tag item.
        return len(work)

    def _process_tag_item(self,item):
        if item['bvid']=='@registry':
            uid=item['owner'].split(':',1)[1]
            with self.db() as db:
                hits=db.execute('SELECT DISTINCT h.bvid,h.job FROM hits h JOIN jobs j ON j.id=h.job WHERE j.creator=?',(uid,)).fetchall()
                found=db.execute('SELECT data FROM creators WHERE uid=?',(uid,)).fetchone()
            if not found:
                with self.db() as db:db.execute("UPDATE acquisition_tags SET state='done' WHERE owner=? AND bvid=? AND version=?",(item['owner'],item['bvid'],item['version']))
                return
            creator=json.loads(found['data'])
            for hit in hits:self.queue_job_tags(hit['job'],hit['bvid'])
            rows=workspace.sources(self.root)
            for row in rows:
                if str(row.get('manual_values',{}).get('uid',row.get('uid','')))==uid:
                    bvid=row.get('bvid') or row['id'].split(':')[0]
                    name=creator.get('name','').strip() or (row.get('author') or '').strip() or 'UP主'+uid
                    if bvid.startswith('BV'):self.queue_tags(item['owner'],bvid,creator.get('tags',[])+[name])
        else:self.apply_acquisition_tags(item)

    def apply_acquisition_tags(self,item):
        bvid=item['bvid'];parts=json.loads(item['parts']);tags=json.loads(item['tags'])
        # Ensure discovery placeholders exist. Full part registrations are re-enqueued on worker completion.
        registered={row['id'] for row in wxq.read_json(self.root/'knowledge/source-registry.json',[])}
        for part in parts or [1]:
            if f'{bvid}:p{part}' in registered:continue
            workspace.register_source(self.root,{'url':f'https://www.bilibili.com/video/{bvid}?p={part}','title':'','notes':''},preserve_annotations=True,wait=True,_metadata={})
        with workspace.store_lock(self.root,wait=True):
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                current=db.execute('SELECT version FROM acquisition_tags WHERE owner=? AND bvid=?',(item['owner'],item['bvid'])).fetchone()
                if not current or current['version']!=item['version'] or not self.tag_requested(item,db):return
                path=self.root/'knowledge/source-registry.json';rows=wxq.read_json(path,[]);changed=False
                for row in rows:
                    if not (row['id']==bvid+':p1' or row['id'].startswith(bvid+':p')):continue
                    if parts is not None and row['id'] not in {f'{bvid}:p{p}' for p in parts}:continue
                    values=row.get('manual_values',{});old=values.get('tags',row.get('tags',[]));merged=normalize_tags(old+tags)
                    if old==merged:continue
                    row['manual_values']={**values,'tags':merged};row['manual_revision']=uuid.uuid4().hex;row['manual_updated_at']=wxq.now();changed=True
                if changed:wxq.atomic_json(path,rows)
