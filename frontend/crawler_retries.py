"""Persistent retries: no sleeps, network calls or knowledge locks in transactions."""
import json
from datetime import datetime, timedelta
from acquisition_errors import describe_error

DELAYS = {'busy': (5, 15, 30, 60), 'crash': (60, 300, 900, 3600)}
TRANSIENT = {'busy', 'crash', 'network', 'extractor', 'formats'}


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS acquisition_retries(
        kind TEXT,target TEXT,attempt INTEGER NOT NULL,category TEXT NOT NULL,
        next_retry_at TEXT NOT NULL,error TEXT NOT NULL,marker INTEGER NOT NULL,
        detail TEXT NOT NULL,PRIMARY KEY(kind,target))''')
    # Preserve existing deadlines and attempts during upgrade, including exhausted retries.
    db.execute('''INSERT OR IGNORE INTO acquisition_retries
        SELECT 'task',n.bvid,n.attempt,'network',n.next_retry_at,n.error,t.generation,'{}'
        FROM network_retries n JOIN tasks t ON t.bvid=n.bvid''')


def tag_target(owner, bvid):
    return json.dumps([owner, bvid], separators=(',', ':'))


class RetryMixin:
    def retry_status(self, kind, target, db=None):
        if db is None:
            with self.db() as connection:
                return self.retry_status(kind, target, connection)
        row = db.execute('SELECT * FROM acquisition_retries WHERE kind=? AND target=?', (kind, target)).fetchone()
        if not row:
            return None
        return {k: row[k] for k in ('attempt', 'category', 'next_retry_at', 'error')}

    def schedule_retry(self, db, kind, target, error, marker, phase=None):
        from crawler import now, encode
        detail = describe_error(error, phase)
        if detail['category'] not in TRANSIENT:
            db.execute('DELETE FROM acquisition_retries WHERE kind=? AND target=?', (kind, target))
            return None
        old = db.execute('SELECT * FROM acquisition_retries WHERE kind=? AND target=?', (kind, target)).fetchone()
        attempt = old['attempt'] + 1 if old else 1
        delays = DELAYS.get(detail['category'], (60, 300, 900, 1800))
        when = (datetime.fromisoformat(now()) + timedelta(seconds=delays[min(attempt - 1, len(delays) - 1)])).isoformat(timespec='seconds')
        db.execute('INSERT OR REPLACE INTO acquisition_retries VALUES(?,?,?,?,?,?,?,?)',
                   (kind, target, attempt, detail['category'], when, str(error), marker, encode(detail)))
        return self.retry_status(kind, target, db)

    def adopt_transient_failures(self):
        from crawler import now, encode
        restored = []
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            tasks = db.execute('''SELECT * FROM tasks t WHERE state='failed' AND EXISTS(
                SELECT 1 FROM dispatch d JOIN jobs j ON j.id=d.job
                WHERE d.bvid=t.bvid AND j.state NOT IN ('stopped','deleted'))''').fetchall()
            for task in tasks:
                progress = json.loads(task['progress'] or '{}')
                phase = progress.get('last_phase') or progress.get('phase')
                retry = self.schedule_retry(db, 'task', task['bvid'], task['error'], task['generation'], phase)
                if not retry:
                    continue
                detail = describe_error(task['error'], phase, f'raw/crawler/{task["bvid"]}.log')
                progress.update(phase='retry_wait', last_phase=phase, next_retry_at=retry['next_retry_at'], attempt=retry['attempt'])
                db.execute("UPDATE tasks SET state='queued',error_data=?,progress=?,updated=?,generation=generation+1 WHERE bvid=? AND generation=?",
                           (encode(detail), encode(progress), now(), task['bvid'], task['generation']))
                db.execute('INSERT INTO task_diagnostics VALUES(?,?,?,?)', (task['bvid'], task['generation'], encode(detail), now()))
                # Keep legacy readers and older API callers working.
                if retry['category'] == 'network':
                    db.execute('INSERT OR REPLACE INTO network_retries VALUES(?,?,?,?)',
                               (task['bvid'], retry['attempt'], retry['next_retry_at'], task['error']))
                restored.append(task['bvid'])
            for job in db.execute("SELECT * FROM jobs WHERE state='failed' AND scan_cancelled=0").fetchall():
                if self.schedule_retry(db, 'job', job['id'], job['error'], 0, 'discovery'):
                    db.execute("UPDATE jobs SET state='pending' WHERE id=? AND state='failed'", (job['id'],))
            # Historical tag failures are adopted without overwriting their version.
            for item in db.execute("SELECT * FROM acquisition_tags WHERE state='failed'").fetchall():
                if self.schedule_retry(db, 'tag', tag_target(item['owner'], item['bvid']), item['error'], item['version'], 'tagging'):
                    db.execute("UPDATE acquisition_tags SET state='pending' WHERE owner=? AND bvid=? AND version=?",
                               (item['owner'], item['bvid'], item['version']))
        return restored
