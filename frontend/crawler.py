"""Durable local acquisition queue, shared source projection, and scheduler."""
import json
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / '.codex/skills/wanxiangqi-knowledge/scripts'
sys.path.insert(0, str(SCRIPTS))
import wxq
import workspace
from bilibili import Bilibili, BJ, creator_uid


def now():
    return datetime.now(BJ).isoformat(timespec='seconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def matches_filters(row, filters):
    date = row.get('published')
    for field, operator in [('date_from', lambda a, b: a >= b), ('date_to', lambda a, b: a <= b)]:
        if filters.get(field) and (not date or not operator(date, filters[field])):
            return False
    for field, source, operator in [('min_views', 'view_count', lambda a, b: a >= b),
                                    ('max_views', 'view_count', lambda a, b: a <= b),
                                    ('min_duration', 'duration', lambda a, b: a >= b),
                                    ('max_duration', 'duration', lambda a, b: a <= b)]:
        if filters.get(field) not in (None, ''):
            if row.get(source) is None or not operator(float(row[source]), float(filters[field])):
                return False
    return True


def config(payload):
    result = {**payload}
    keywords = payload.get('keywords', [])
    if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
        raise ValueError('关键词须为文字列表')
    result['keywords'] = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))
    for key, default in [('scan_limit', 100), ('process_limit', 50)]:
        result[key] = int(payload.get(key, default))
        if not 1 <= result[key] <= 10000:
            raise ValueError('采集和处理上限须在1至10000之间')
    for key in ['date_from', 'date_to']:
        if result.get(key):
            datetime.strptime(result[key], '%Y-%m-%d')
    if result.get('date_from') and result.get('date_to') and result['date_from'] > result['date_to']:
        raise ValueError('起始日期不能晚于结束日期')
    for low, high in [('min_views', 'max_views'), ('min_duration', 'max_duration')]:
        for key in [low, high]:
            result[key] = None if result.get(key) in ('', None) else float(result[key])
            if result[key] is not None and (not 0 <= result[key] <= 1e15):
                raise ValueError('筛选数值须为非负有限数')
        if result[low] is not None and result[high] is not None and result[low] > result[high]:
            raise ValueError('最小值不能大于最大值')
    result.setdefault('mode', 'auto')
    result.setdefault('order', 'totalrank')
    if result['mode'] not in ['auto', 'preview'] or result['order'] not in ['totalrank', 'pubdate', 'click']:
        raise ValueError('模式或排序无效')
    return result


def due_creators(creators, clock, current=None):
    current = current or datetime.now(BJ)
    hour, minute = map(int, clock.split(':'))
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # At service restart, catch up the latest scheduled occurrence (also before today's time).
    if current < target:
        target -= timedelta(days=1)
    return [c for c in creators if c.get('enabled', True) and
            (not c.get('last_success') or datetime.fromisoformat(c['last_success']) < target)]


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'raw/crawler/queue.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, config TEXT NOT NULL, state TEXT NOT NULL,
                    created TEXT NOT NULL, scanned INTEGER DEFAULT 0, matched INTEGER DEFAULT 0,
                    duplicates INTEGER DEFAULT 0, limited INTEGER DEFAULT 0, error TEXT DEFAULT '', creator TEXT);
                CREATE TABLE IF NOT EXISTS videos(bvid TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hits(job TEXT, bvid TEXT, keyword TEXT, PRIMARY KEY(job,bvid,keyword));
                CREATE TABLE IF NOT EXISTS tasks(bvid TEXT PRIMARY KEY, state TEXT NOT NULL,
                    error TEXT DEFAULT '', progress TEXT DEFAULT '{}', updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS dispatch(job TEXT, bvid TEXT, charged INTEGER DEFAULT 1, PRIMARY KEY(job,bvid));
                CREATE TABLE IF NOT EXISTS creators(uid TEXT PRIMARY KEY, data TEXT NOT NULL);
            ''')
            if 'charged' not in [r['name'] for r in db.execute('PRAGMA table_info(dispatch)')]:
                db.execute('ALTER TABLE dispatch ADD COLUMN charged INTEGER DEFAULT 1')
            if 'generation' not in [r['name'] for r in db.execute('PRAGMA table_info(tasks)')]:
                db.execute('ALTER TABLE tasks ADD COLUMN generation INTEGER NOT NULL DEFAULT 0')
            if 'last_dispatched' not in [r['name'] for r in db.execute('PRAGMA table_info(jobs)')]:
                db.execute("ALTER TABLE jobs ADD COLUMN last_dispatched TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self, value=None):
        with self.db() as db:
            if value is not None:
                if 'parallelism' in value and (type(value['parallelism']) is not int or not 1 <= value['parallelism'] <= 4):
                    raise ValueError('同时处理视频数须为1至4之间的整数')
                if 'clock' in value and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value['clock']):
                    raise ValueError('每日时间须为HH:mm')
                if value.get('cookies') and not Path(value['cookies']).is_file():
                    raise ValueError('cookies文件不存在')
                for k in ['clock', 'cookies', 'search', 'parallelism']:
                    if k in value:
                        v = config(value[k]) if k == 'search' else value[k]
                        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (k, encode(v)))
            return {'clock': '09:00', 'cookies': '', 'search': config({}), 'parallelism': 2,
                    **{r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}}

    def new_job(self, payload, creator=None):
        payload = config(payload)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if creator:
                existing = db.execute("SELECT id FROM jobs WHERE creator=? AND state IN ('pending','scanning')", (creator,)).fetchone()
                if existing:
                    job_id = existing['id']
                else:
                    job_id = None
            else:
                job_id = None
            if not job_id:
                job_id = uuid.uuid4().hex[:12]
                db.execute('INSERT INTO jobs(id,config,state,created,creator) VALUES(?,?,?,?,?)',
                           (job_id, encode(payload), 'pending', now(), creator))
        return self.job(job_id)

    def jobs(self):
        with self.db() as db:
            ids = [r['id'] for r in db.execute("SELECT id FROM jobs WHERE state!='deleted' ORDER BY created DESC LIMIT 100")]
        return [self.job(i, False) for i in ids]

    def next_pending(self, exclude=()):
        with self.db() as db:
            condition = ' AND id NOT IN (' + ','.join('?' for _ in exclude) + ')' if exclude else ''
            row = db.execute("SELECT id FROM jobs WHERE state='pending'" + condition + ' ORDER BY created,id LIMIT 1', tuple(exclude)).fetchone()
        return self.job(row['id'], False) if row else None

    def begin_scan(self, jid):
        with self.db() as db:
            return bool(db.execute("UPDATE jobs SET state='scanning',error='' WHERE id=? AND state='pending'", (jid,)).rowcount)

    def job(self, jid, items=True):
        with self.db() as db:
            r = db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
            if not r:
                raise KeyError('任务不存在')
            result = {**dict(r), 'config': json.loads(r['config'])}
            rows = db.execute('''SELECT v.bvid,v.data,t.state,t.error,t.progress,h.keyword,
                EXISTS(SELECT 1 FROM dispatch d WHERE d.bvid=v.bvid AND d.job=h.job) AS selected
                FROM hits h JOIN videos v ON v.bvid=h.bvid LEFT JOIN tasks t ON t.bvid=v.bvid
                WHERE h.job=? ORDER BY v.bvid''', (jid,)).fetchall()
        grouped = {}
        for row in rows:
            entry = grouped.setdefault(row['bvid'], {**json.loads(row['data']), 'keywords': [],
                'state': row['state'] if row['selected'] else 'preview', 'error': row['error'] or '',
                'progress': json.loads(row['progress'] or '{}')})
            if row['keyword']:
                entry['keywords'].append(row['keyword'])
        result['counts'] = {state: sum(v['state'] == state for v in grouped.values())
                            for state in ['preview', 'queued', 'running', 'paused', 'cancelled', 'succeeded', 'failed']}
        for phase in ['downloading', 'transcribing']:
            result['counts'][phase] = sum(v['state'] == 'running' and v['progress'].get('phase') == phase for v in grouped.values())
        if items:
            result['items'] = list(grouped.values())
        return result

    def update_job(self, jid, **values):
        allowed = {'state', 'scanned', 'matched', 'duplicates', 'limited', 'error'}
        if not set(values) <= allowed:
            raise ValueError('Invalid job update')
        with self.db() as db:
            condition = " AND state!='stopped'" if values.get('state') in ['scanning', 'scanned', 'failed'] else ''
            return bool(db.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in values) + " WHERE id=? AND state!='deleted'" + condition, (*values.values(), jid)).rowcount)

    def discover(self, jid, row, keyword, enqueue):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT state FROM jobs WHERE id=?', (jid,)).fetchone()
            if not job or job['state'] in ['deleted', 'stopped']:
                return False
            db.execute('INSERT OR REPLACE INTO videos VALUES(?,?)', (row['bvid'], encode({**row, 'collected_at': now()})))
            db.execute('INSERT OR IGNORE INTO hits VALUES(?,?,?)', (jid, row['bvid'], keyword))
        if enqueue:
            self.enqueue(jid, [row['bvid']])
        return True

    def enqueue(self, jid, bvids):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT config,state FROM jobs WHERE id=?', (jid,)).fetchone()
            if not job:
                raise KeyError('任务不存在')
            if job['state'] in ['stopped', 'deleted']:
                return
            limit = json.loads(job['config'])['process_limit']
            for bvid in bvids:
                if not db.execute('SELECT 1 FROM hits WHERE job=? AND bvid=?', (jid, bvid)).fetchone():
                    raise ValueError('视频不属于该任务')
                if db.execute('SELECT 1 FROM dispatch WHERE job=? AND bvid=?', (jid, bvid)).fetchone():
                    continue
                existing = db.execute('SELECT state FROM tasks WHERE bvid=?', (bvid,)).fetchone()
                cached = cached_video(self.root, bvid)
                charged = int(not existing and not cached)
                if charged and db.execute('SELECT COALESCE(SUM(charged),0) FROM dispatch WHERE job=?', (jid,)).fetchone()[0] >= limit:
                    db.execute('UPDATE jobs SET limited=1 WHERE id=?', (jid,))
                    continue
                db.execute('INSERT OR IGNORE INTO tasks(bvid,state,updated) VALUES(?,?,?)', (bvid, 'succeeded' if cached else 'queued', now()))
                db.execute("UPDATE tasks SET state='queued',error='' WHERE bvid=? AND state='cancelled'", (bvid,))
                db.execute('INSERT OR IGNORE INTO dispatch(job,bvid,charged) VALUES(?,?,?)', (jid, bvid, charged))

    def stop(self, jid):
        self.update_job(jid, state='stopped')

    def resume(self, jid):
        self.job(jid, False)
        self.update_job(jid, state='pending')

    def delete_job(self, jid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM jobs WHERE id=?', (jid,)).fetchone():
                raise KeyError('任务不存在')
            db.execute("UPDATE jobs SET state='deleted',error='' WHERE id=?", (jid,))
            # Keep hits/video metadata for external content and auditing. Only dispatch is retired.
            db.execute("""UPDATE tasks SET state='cancelled',error='' WHERE state='queued' AND NOT EXISTS(
                SELECT 1 FROM dispatch d JOIN jobs j ON j.id=d.job WHERE d.bvid=tasks.bvid AND j.state!='deleted')""")
        return {'id': jid, 'deleted': True}

    def requested(self, bvid, generation=None):
        with self.db() as db:
            return bool(db.execute("""SELECT 1 FROM dispatch d JOIN jobs j ON j.id=d.job
                JOIN tasks t ON t.bvid=d.bvid WHERE d.bvid=? AND j.state!='deleted'
                AND t.state NOT IN ('paused','cancelled') AND (? IS NULL OR t.generation=?) LIMIT 1""", (bvid, generation, generation)).fetchone())

    def halted(self, bvid):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM tasks WHERE bvid=? AND state IN ('paused','cancelled')", (bvid,)).fetchone())

    def activity(self):
        """Global video queue, with shared videos appearing only once."""
        with self.db() as db:
            rows = db.execute("""SELECT t.*,v.data FROM tasks t JOIN videos v ON v.bvid=t.bvid
                WHERE t.state IN ('running','queued','paused') AND EXISTS(
                SELECT 1 FROM dispatch d JOIN jobs j ON j.id=d.job
                WHERE d.bvid=t.bvid AND j.state!='deleted')
                ORDER BY CASE t.state WHEN 'running' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,t.updated,t.bvid""").fetchall()
            result = []
            for row in rows:
                jobs = db.execute("""SELECT j.id,j.config,j.creator FROM jobs j JOIN dispatch d ON d.job=j.id
                    WHERE d.bvid=? AND j.state!='deleted' ORDER BY j.created""", (row['bvid'],)).fetchall()
                result.append({**json.loads(row['data']), 'bvid': row['bvid'], 'state': row['state'],
                    'error': row['error'], 'progress': json.loads(row['progress']),
                    'jobs': [{'id': j['id'], 'name': j['creator'] or '、'.join(json.loads(j['config'])['keywords'])} for j in jobs]})
            return result

    def control_task(self, bvid, action):
        from processing_lock import file_lock
        if action not in ['stop-download', 'stop-transcribe', 'resume', 'delete']:
            raise ValueError('未知视频操作')
        if action == 'resume':
            # A process still releasing its lock must not race a new run.
            with file_lock(self.root / 'raw/crawler/locks' / (bvid + '.lock')):
                with self.db() as db:
                    if not db.execute("SELECT 1 FROM tasks WHERE bvid=? AND state='paused'", (bvid,)).fetchone():
                        raise ValueError('仅已停止的视频可以继续处理')
                    db.execute("UPDATE tasks SET state='queued',error='',progress='{}',updated=? WHERE bvid=?", (now(), bvid))
            return {'bvid': bvid, 'state': 'queued'}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tasks WHERE bvid=?', (bvid,)).fetchone()
            if not row:
                raise KeyError('视频任务不存在')
            if action != 'delete':
                phase = 'downloading' if action == 'stop-download' else 'transcribing'
                if row['state'] != 'running' or json.loads(row['progress']).get('phase') != phase:
                    raise ValueError('视频已不在对应阶段，请刷新任务状态')
            state = 'cancelled' if action == 'delete' else 'paused'
            db.execute('UPDATE tasks SET state=?,error=?,updated=?,generation=generation+1 WHERE bvid=?',
                       (state, '' if action == 'delete' else '已停止，保留已有文件和转写检查点', now(), bvid))
        return {'bvid': bvid, 'state': state}

    def stop_phase(self, jid, action):
        self.stop(jid)
        phase = 'downloading' if action == 'stop-download' else 'transcribing'
        for item in self.job(jid)['items']:
            if item['state'] == 'running' and item['progress'].get('phase') == phase:
                try:
                    self.control_task(item['bvid'], action)
                except ValueError:
                    pass  # The phase may have completed since the snapshot.

    def cancel_orphan(self, bvid):
        with self.db() as db:
            cursor = db.execute("""UPDATE tasks SET state='cancelled',error='',progress='{}',updated=?
                WHERE bvid=? AND state IN ('queued','running') AND NOT EXISTS(
                SELECT 1 FROM dispatch d JOIN jobs j ON j.id=d.job WHERE d.bvid=tasks.bvid AND j.state!='deleted')""", (now(), bvid))
            return bool(cursor.rowcount)

    def running_count(self):
        with self.db() as db:
            return db.execute("SELECT COUNT(*) FROM tasks WHERE state='running'").fetchone()[0]

    def tasks(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tasks')]

    def claim(self, exclude=()):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            condition = ' AND t.bvid NOT IN (' + ','.join('?' for _ in exclude) + ')' if exclude else ''
            row = db.execute('''SELECT t.*,j.id AS owner FROM tasks t JOIN dispatch d ON d.bvid=t.bvid
                JOIN jobs j ON j.id=d.job WHERE t.state='queued' AND j.state NOT IN ('stopped','deleted')''' + condition + '''
                ORDER BY (SELECT COUNT(*) FROM tasks r JOIN dispatch rd ON rd.bvid=r.bvid
                          WHERE rd.job=j.id AND r.state='running'),
                         j.last_dispatched,j.created,t.updated,t.bvid LIMIT 1''', tuple(exclude)).fetchone()
            if not row:
                return None
            db.execute("UPDATE tasks SET state='running',error='',updated=?,generation=generation+1 WHERE bvid=?", (now(), row['bvid']))
            db.execute('UPDATE jobs SET last_dispatched=? WHERE id=?', (datetime.now(BJ).isoformat(), row['owner']))
            return {**dict(row), 'state': 'running', 'generation': row['generation'] + 1}

    def finish_task(self, bvid, state, error='', progress=None, generation=None):
        with self.db() as db:
            db.execute("UPDATE tasks SET state=?,error=?,progress=?,updated=? WHERE bvid=? AND state NOT IN ('cancelled','paused') AND (? IS NULL OR generation=?)",
                       (state, error, encode(progress or {}), now(), bvid, generation, generation))

    def retry(self, jid, bvids=None):
        with self.db() as db:
            if not db.execute("SELECT 1 FROM jobs WHERE id=? AND state!='deleted'", (jid,)).fetchone():
                raise KeyError('任务已删除或不存在')
            db.execute("UPDATE tasks SET state='queued',error='',updated=? WHERE state='failed' AND bvid IN (SELECT bvid FROM dispatch WHERE job=?)" +
                       (' AND bvid IN (' + ','.join('?' for _ in bvids) + ')' if bvids else ''),
                       (now(), jid, *(bvids or [])))
            db.execute("UPDATE jobs SET state=CASE WHEN state IN ('failed','stopped') THEN 'pending' ELSE state END,error='' WHERE id=?", (jid,))

    def recover_tasks(self, exclude=()):
        from processing_lock import file_lock
        # A hard-killed HTTP process can leave its ASR child alive. Its source lock owns that work.
        for task in self.tasks():
            if task['state'] != 'running' or task['bvid'] in exclude:
                continue
            try:
                with file_lock(self.root / 'raw/crawler/locks' / (task['bvid'] + '.lock')):
                    with self.db() as db:
                        db.execute("UPDATE tasks SET state='queued' WHERE bvid=? AND state='running'", (task['bvid'],))
            except workspace.Busy:
                continue

    def recover(self):
        self.recover_tasks()
        with self.db() as db:
            db.execute("UPDATE jobs SET state='pending' WHERE state='scanning'")

    def save_creator(self, payload):
        uid = creator_uid(payload.get('url', ''))
        if not payload.get('date_from'):
            raise ValueError('请选择拉取起始日期')
        datetime.strptime(payload['date_from'], '%Y-%m-%d')
        if not isinstance(payload.get('name', ''), str) or not isinstance(payload.get('keywords', []), list):
            raise ValueError('UP主名称或关键词格式无效')
        if any(not isinstance(k, str) for k in payload.get('keywords', [])):
            raise ValueError('关键词须为文字')
        with self.db() as db:
            old = db.execute('SELECT data FROM creators WHERE uid=?', (uid,)).fetchone()
            row = {**(json.loads(old['data']) if old else {}), **{k: payload[k] for k in
                   ['name', 'date_from', 'enabled', 'keywords'] if k in payload},
                   'uid': uid, 'url': f'https://space.bilibili.com/{uid}'}
            row.setdefault('enabled', True)
            row.setdefault('keywords', [])
            row['keywords'] = list(dict.fromkeys(k.strip() for k in row['keywords'] if k.strip()))
            db.execute('INSERT OR REPLACE INTO creators VALUES(?,?)', (uid, encode(row)))
        return row

    def creators(self):
        with self.db() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT data FROM creators')]

    def creator_result(self, uid, error=''):
        with self.db() as db:
            found = db.execute('SELECT data FROM creators WHERE uid=?', (uid,)).fetchone()
            if not found:
                return
            row = json.loads(found['data'])
            row.update(last_checked=now(), error=error)
            if not error:
                row['last_success'] = now()
            db.execute('UPDATE creators SET data=? WHERE uid=?', (encode(row), uid))

    def check_creator(self, uid):
        row = next((r for r in self.creators() if r['uid'] == uid), None)
        if not row:
            raise KeyError('UP主不存在')
        return self.new_job({'date_from': row['date_from'], 'keywords': row['keywords'],
                             'mode': 'auto', 'scan_limit': 10000, 'process_limit': 10000}, uid)

    def projections(self):
        with self.db() as db:
            rows = db.execute('''SELECT v.bvid,v.data,h.keyword,h.job,t.state,t.error FROM videos v
                JOIN hits h ON h.bvid=v.bvid LEFT JOIN tasks t ON t.bvid=v.bvid''').fetchall()
        result = {}
        for r in rows:
            item = result.setdefault(r['bvid'], {**json.loads(r['data']), 'keywords': [], 'batches': [],
                'acquisition_state': r['state'] or 'preview', 'acquisition_error': r['error']})
            if r['keyword'] and r['keyword'] not in item['keywords']:
                item['keywords'].append(r['keyword'])
            if r['job'] not in item['batches']:
                item['batches'].append(r['job'])
        return result


def source_rows(root, store):
    projections = store.projections()
    rows = workspace.sources(root)
    manifest = wxq.read_json(Path(root) / 'raw/index.json', {}).get('sources', {})
    for row in rows:
        bv = row.get('bvid') or row['id'].split(':')[0]
        extra = projections.get(bv, {})
        for k in ['keywords', 'batches', 'uid', 'space_url', 'view_count', 'collected_at', 'acquisition_state', 'acquisition_error']:
            if k in extra:
                row[k] = extra[k]
        for k in ['author', 'title', 'published', 'duration']:
            if not row.get(k) and extra.get(k):
                row[k] = extra[k]
        if extra.get('published'):
            row['published'] = extra['published']
        if row.get('collected_at'):
            try:
                row['collected_at'] = datetime.fromisoformat(row['collected_at'].replace('Z', '+00:00')).astimezone(BJ).isoformat(timespec='seconds')
            except (ValueError, TypeError):
                pass
        published = row.get('published')
        if published and re.fullmatch(r'\d{8}', published):
            row['published'] = datetime.strptime(published, '%Y%m%d').date().isoformat()
        entry = manifest.get(row['id'], {})
        target = (Path(root) / entry.get('path', '__missing__')).resolve()
        valid = target.is_relative_to((Path(root) / 'raw').resolve()) and target.is_file()
        row['transcript_path'] = str(target) if valid else None
        row['transcript_status'] = 'ready' if valid else 'missing'
        if valid and not wxq.read_json(wxq.source_dir(root, row['id']) / 'asr.raw.json', {}).get('segments'):
            row['transcript_status'] = 'no_speech'
    return rows


def cached_video(root, bvid):
    from reference_store import transcript_errors
    root = Path(root)
    manifest = wxq.read_json(root / 'raw/index.json', {}).get('sources', {})
    folders = list((root / 'raw/sources').glob(bvid + '_p*'))
    if not folders:
        return False
    expected = wxq.read_json(folders[0] / 'metadata.json', {}).get('part_count')
    if not expected or len(folders) != expected:
        return False
    for folder in folders:
        sid = wxq.read_json(folder / 'metadata.json', {}).get('id')
        target = (root / manifest.get(sid, {}).get('path', '__missing__')).resolve()
        if not target.is_relative_to((root / 'raw').resolve()) or not target.is_file() or not (folder / 'asr.raw.json').is_file() or not (folder / 'asr.corrected.json').is_file():
            return False
        try:
            if any(not error.startswith('Transcript was manually edited') for error in transcript_errors(root, sid)):
                return False
        except (KeyError, ValueError, TypeError, OSError):
            return False
    return True


def transcript(root, sid):
    row = wxq.read_json(Path(root) / 'raw/index.json', {}).get('sources', {}).get(sid)
    if not row:
        raise KeyError('文字稿尚未生成')
    path = (Path(root) / row['path']).resolve()
    if not path.is_relative_to((Path(root) / 'raw').resolve()) or not path.is_file():
        raise KeyError('文字稿文件不存在')
    return {'source': sid, 'path': str(path), 'text': path.read_text('utf-8')}


def batch_paths(root, ids):
    if not isinstance(ids, list) or len(ids) > 10000 or any(not isinstance(s, str) for s in ids):
        raise ValueError('请选择最多10000条内容')
    paths, skipped = [], 0
    for sid in dict.fromkeys(ids):
        try:
            path = transcript(root, sid)['path']
            if path not in paths:
                paths.append(path)
        except (KeyError, OSError):
            skipped += 1
    return {'paths': paths, 'skipped': skipped}


class Runtime:
    def __init__(self, root):
        self.root = Path(root)
        self.store = Store(root)
        self.closed = threading.Event()
        self.thread = None
        self.scans = {}
        self.workers = {}
        self.processes = {}
        self.process_lock = threading.Lock()
        self.scan_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='crawler-search')
        self.media_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='crawler-media')
        self.last_recovery = time.monotonic()

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=5)
        with self.process_lock:
            processes = list(self.processes.values())
        for process in processes:
            terminate_worker(process)
        self.scan_pool.shutdown(wait=True, cancel_futures=True)
        self.media_pool.shutdown(wait=True, cancel_futures=True)

    def loop(self):
        from processing_lock import file_lock
        try:
            with file_lock(self.root / 'raw/crawler/runtime.lock'):
                self.store.recover()
                while not self.closed.is_set():
                    try:
                        self.tick()
                    except Exception as exc:
                        self.record_error(exc)
                    self.closed.wait(.5)
        except workspace.Busy:
            pass  # Another local service owns the worker for this project.

    def record_error(self, exc):
        wxq.atomic_json(self.root / 'raw/crawler/runtime-error.json', {'at': now(), 'error': str(exc)})

    def tick(self):
        if self.closed.is_set():
            return
        for pending in [self.scans, self.workers]:
            for key, future in list(pending.items()):
                if future.done():
                    try:
                        future.result()
                    except Exception as exc:
                        self.record_error(exc)
                    del pending[key]
        # Also reap a surviving worker that subsequently died after an HTTP-service restart.
        if time.monotonic() - self.last_recovery >= 30:
            self.store.recover_tasks(exclude=self.workers)
            self.last_recovery = time.monotonic()
        settings = self.store.settings()
        current = datetime.now(BJ)
        for creator in due_creators(self.store.creators(), settings['clock'], current):
            if creator.get('last_checked') and current - datetime.fromisoformat(creator['last_checked']) < timedelta(hours=1):
                continue
            self.store.check_creator(creator['uid'])
        while len(self.scans) < 2 and not self.closed.is_set():
            pending = self.store.next_pending(exclude=self.scans)
            if not pending:
                break
            if self.store.begin_scan(pending['id']):
                self.scans[pending['id']] = self.scan_pool.submit(self.scan, pending)
        # Count surviving child processes from the previous service as occupied slots too.
        while max(len(self.workers), self.store.running_count()) < settings['parallelism'] and not self.closed.is_set():
            task = self.store.claim(exclude=self.workers)
            if not task:
                break
            self.workers[task['bvid']] = self.media_pool.submit(self.process_task, task)

    def scan(self, job):
        jid, filters = job['id'], job['config']
        state = self.store.job(jid, False)['state']
        if state == 'pending':
            if not self.store.begin_scan(jid):
                return
        elif state != 'scanning':
            return
        scanned = matched = duplicates = 0
        seen = set()
        try:
            adapter = Bilibili(self.store.settings()['cookies'])
            for keyword in filters['keywords'] if not job['creator'] else ['']:
                page, count = 1, 0
                while count < filters['scan_limit'] and not self.closed.is_set():
                    if self.store.job(jid, False)['state'] in ['stopped', 'deleted']:
                        return
                    rows, more = adapter.creator_page(job['creator'], page) if job['creator'] else adapter.search_page(keyword, page, filters['order'])
                    older = bool(rows) and all(r.get('published') and filters.get('date_from') and r['published'] < filters['date_from'] for r in rows)
                    for row in rows:
                        if count >= filters['scan_limit'] or self.store.job(jid, False)['state'] in ['stopped', 'deleted'] or self.closed.is_set():
                            break
                        count += 1
                        scanned += 1
                        if any(row.get(k) is None for k in ['published', 'view_count', 'duration']):
                            row = {**row, **adapter.detail(row['bvid'])}
                        if not matches_filters(row, filters):
                            continue
                        if job['creator'] and filters['keywords'] and not any(k.casefold() in (row['title'] + ' ' + row['description']).casefold() for k in filters['keywords']):
                            continue
                        repeated = row['bvid'] in seen
                        duplicates += int(repeated or any(t['bvid'] == row['bvid'] for t in self.store.tasks()))
                        if not repeated:
                            matched += 1
                            seen.add(row['bvid'])
                        keywords = [keyword] if not job['creator'] else [k for k in filters['keywords'] if k.casefold() in (row['title'] + ' ' + row['description']).casefold()] or ['']
                        for k in keywords:
                            if not self.store.discover(jid, row, k, filters['mode'] == 'auto'):
                                return
                        # Discovery registration must preserve manual annotations.
                        self.store.update_job(jid, scanned=scanned, matched=matched, duplicates=duplicates)
                        register_discovered(self.root, row)
                    self.store.update_job(jid, scanned=scanned, matched=matched, duplicates=duplicates)
                    if count >= filters['scan_limit'] and (more or len(rows) > count):
                        self.store.update_job(jid, limited=1)
                    if not rows or not more or (job['creator'] and older):
                        break
                    page += 1
            if not self.closed.is_set() and self.store.update_job(jid, state='scanned'):
                if job['creator']:
                    self.store.creator_result(job['creator'])
        except Exception as exc:
            updated = self.store.update_job(jid, state='failed', error=str(exc))
            if updated and job['creator']:
                self.store.creator_result(job['creator'], str(exc))

    def process_task(self, task):
        bvid = task['bvid']
        generation = task['generation']
        def finish(state, error='', progress=None):
            self.store.finish_task(bvid, state, error, progress, generation=generation)
        output = self.root / 'raw/crawler' / (bvid + '.log')
        process = None
        try:
            if not self.store.requested(bvid, generation):
                self.store.cancel_orphan(bvid)
                return
            if self.closed.is_set():
                finish('queued')
                return
            with output.open('w', encoding='utf8') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('crawler_worker.py')),
                    '--root', str(self.root), '--bvid', bvid, '--generation', str(generation)], stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=sys.platform != 'win32')
                with self.process_lock:
                    self.processes[bvid] = process
                while process.poll() is None:
                    if self.closed.is_set() or not self.store.requested(bvid, generation):
                        terminate_worker(process)
                        if not self.store.cancel_orphan(bvid):
                            # A fresh batch may have attached while the process was being cancelled.
                            with self.store.db() as db:
                                db.execute("UPDATE tasks SET state='queued' WHERE bvid=? AND state='running' AND generation=?", (bvid,generation))
                        return
                    self.closed.wait(.25)
                if not self.store.requested(bvid, generation):
                    self.store.cancel_orphan(bvid)
                    return
                if process.returncode == 75:
                    finish('queued', '来源正在处理，稍后自动重试')
                    self.closed.wait(2)
                elif process.returncode:
                    finish('failed', '处理失败，可重试。' + output.read_text('utf8', errors='replace')[-1200:])
                else:
                    finish('succeeded', progress={'phase': 'ready'})
        except Exception as exc:
            if process is not None:
                terminate_worker(process)
            if self.store.requested(bvid, generation):
                finish('failed', str(exc))
            else:
                self.store.cancel_orphan(bvid)
        finally:
            with self.process_lock:
                self.processes.pop(bvid, None)


def terminate_worker(process):
    """Terminate only a worker owned by this runtime, including its FFmpeg children."""
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=10)
    else:
        import os
        import signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)



def register_discovered(root, row):
    # Existing CLI registry identity is p1 for an unqualified BV URL.
    workspace.register_source(root, {'url': row['url'], 'title': row.get('title', ''), 'notes': ''}, preserve_annotations=True, wait=True)
