"""Stable creator tasks with preserved historical batch identities."""
import json,uuid
from datetime import datetime,timedelta
from bilibili import BJ

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS monitor_members(job TEXT PRIMARY KEY,monitor TEXT NOT NULL)')

class MonitorMixin:
    def job_is_monitor(self,jid,db):
        return bool(db.execute('SELECT 1 FROM jobs WHERE id=? AND creator IS NOT NULL',(jid,)).fetchone())
    def ensure_monitor(self,uid):
        from crawler import config,encode,now
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            found=db.execute('SELECT data FROM creators WHERE uid=?',(uid,)).fetchone()
            if not found:raise KeyError('UP主不存在')
            row=json.loads(found['data'])
            migrated=not row.get('monitor_version')
            jobs=db.execute("SELECT id,state FROM jobs WHERE creator=? AND state!='deleted' ORDER BY CASE state WHEN 'scanning' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,created,id",(uid,)).fetchall()
            jid=row.get('job_id')
            if jid not in {j['id'] for j in jobs}:jid=jobs[0]['id'] if jobs else uuid.uuid4().hex[:12]
            filters=config({'date_from':row['date_from'],'keywords':row.get('keywords',[]),'tags':row.get('tags',[]),'mode':'auto','scan_limit':10000,'process_limit':10000})
            db.execute("INSERT OR IGNORE INTO jobs(id,config,state,created,creator) VALUES(?,?,'scanned',?,?)",(jid,encode(filters),now(),uid))
            # A running scan keeps its immutable filter snapshot until the next round.
            db.execute("UPDATE jobs SET config=? WHERE id=? AND state!='scanning'",(encode(filters),jid))
            for job in jobs:db.execute('INSERT OR REPLACE INTO monitor_members VALUES(?,?)',(job['id'],jid))
            db.execute("UPDATE jobs SET state='scanned',scan_cancelled=1 WHERE creator=? AND id!=? AND state IN ('pending','scanning')",(uid,jid))
            db.execute('INSERT OR REPLACE INTO monitor_members VALUES(?,?)',(jid,jid))
            cooldown=db.execute("SELECT r.* FROM risk_retries r JOIN jobs j ON j.id=r.target WHERE r.kind='job' AND j.creator=? AND r.next_retry_at>? ORDER BY r.next_retry_at DESC LIMIT 1",(uid,now())).fetchone()
            if cooldown:
                db.execute("INSERT OR REPLACE INTO risk_retries VALUES('job',?,?,?,?)",(jid,cooldown['attempt'],cooldown['next_retry_at'],cooldown['error']))
            row.update(job_id=jid,monitor_version=1);db.execute('UPDATE creators SET data=? WHERE uid=?',(encode(row),uid))
        if migrated:self.queue_creator_tags(uid)
        return jid

    def check_creator(self,uid):
        jid=self.ensure_monitor(uid)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=json.loads(db.execute('SELECT data FROM creators WHERE uid=?',(uid,)).fetchone()['data'])
            if row.get('enabled',True):
                # Paused tasks require explicit resume; ordinary scheduler checks never undo pause.
                db.execute("UPDATE jobs SET state='pending',scan_cancelled=0,error='',limited=0 WHERE id=? AND state NOT IN ('pending','scanning','stopped')",(jid,))
        return self.job(jid)

    def resume_creators(self):
        from crawler import now
        for creator in self.creators():
            if not creator.get('enabled',True):continue
            jid=self.ensure_monitor(creator['uid'])
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                # Two clients arriving together share one persisted request window, even if scan completes quickly.
                row=json.loads(db.execute('SELECT data FROM creators WHERE uid=?',(creator['uid'],)).fetchone()['data'])
                last=row.get('last_frontend_resume')
                state=db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()['state']
                if state!='stopped' and last and datetime.now(BJ)-datetime.fromisoformat(last)<timedelta(seconds=5):continue
                db.execute("UPDATE jobs SET state='scanned' WHERE id IN (SELECT job FROM monitor_members WHERE monitor=?) AND id!=? AND state='stopped'",(jid,jid))
                db.execute("UPDATE jobs SET state='pending',scan_cancelled=0,error='',limited=0 WHERE id=? AND state NOT IN ('pending','scanning')",(jid,))
                row['last_frontend_resume']=now();db.execute('UPDATE creators SET data=? WHERE uid=?',(json.dumps(row,ensure_ascii=False),creator['uid']))
        return self.creators()

    def monitor_info(self,row,db):
        jid=row.get('job_id');job=db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone() if jid else None
        retry=db.execute("SELECT attempt,next_retry_at FROM risk_retries WHERE kind='job' AND target=?",(jid,)).fetchone() if jid else None
        state='disabled' if not row.get('enabled',True) else 'paused' if job and job['state']=='stopped' else 'retry_wait' if retry else 'scanning' if job and job['state']=='scanning' else 'pending' if job and job['state']=='pending' else 'failed' if row.get('error') else 'waiting'
        row.update(monitor_state=state,checking=state=='scanning',retry=dict(retry) if retry else None)
        pending=db.execute("SELECT state,COUNT(*) n FROM acquisition_tags WHERE owner=? GROUP BY state",('creator:'+row['uid'],)).fetchall()
        row['tag_progress']={r['state']:r['n'] for r in pending}
        error=db.execute("SELECT error FROM acquisition_tags WHERE owner=? AND state='failed' LIMIT 1",('creator:'+row['uid'],)).fetchone()
        row['tag_error']=error['error'] if error else ''
        clock=self.settings()['clock'];hour,minute=map(int,clock.split(':'));current=datetime.now(BJ);target=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if target<=current:target+=timedelta(days=1)
        row['next_check']=target.isoformat(timespec='seconds') if row.get('enabled',True) else None
        return row
