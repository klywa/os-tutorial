"""Reviewed, per-card overrides of the condition catalog's effect tags."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

from workspace import Conflict

CARD_PATH = re.compile(r'/api/cards/([^/]+)/tags')
REVIEW_PATH = re.compile(r'/api/cards/tag-reviews/([^/]+)/(approve|reject)')
_public_databases = {}


def matches(path):
    return path == '/api/cards/tag-reviews' or CARD_PATH.fullmatch(path) or REVIEW_PATH.fullmatch(path)


def presets(root):
    path = Path(root) / 'src/condition/card-tags.json'
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}


def database(root):
    root = Path(root).resolve()
    return _public_databases.get(root, root / 'raw/card-tag-reviews.sqlite3')


def configure_public_database(root, state_dir):
    """Keep the review history available to every checkout serving this site."""
    root = Path(root).resolve()
    target = Path(state_dir).resolve() / 'card-tag-reviews.sqlite3'
    legacy = root / 'raw/card-tag-reviews.sqlite3'
    if legacy.exists() and not target.exists() and legacy != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as folder:
            copy = Path(folder) / target.name
            with closing(sqlite3.connect(legacy)) as source, closing(sqlite3.connect(copy)) as dest:
                source.backup(dest)
            try:
                if os.name == 'nt':
                    copy.rename(target)  # Windows rename refuses an existing target.
                else:
                    target.hardlink_to(copy)
            except FileExistsError:
                pass
    _public_databases[root] = target


def connect(root):
    path = database(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS tag_reviews (
        id TEXT PRIMARY KEY, card_id TEXT NOT NULL, card_name TEXT NOT NULL, base TEXT NOT NULL,
        before_tags TEXT NOT NULL, after_tags TEXT NOT NULL, author TEXT NOT NULL,
        created TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT, reviewed TEXT)""")
    return conn


def effective_tags(root):
    cards = presets(root)
    if database(root).exists():
        with closing(connect(root)) as conn:
            for row in conn.execute("SELECT card_id, after_tags FROM tag_reviews WHERE status='approved' ORDER BY reviewed,rowid"):
                if row['card_id'] in cards:
                    cards[row['card_id']]['tags'] = json.loads(row['after_tags'])
    return cards


def current(conn, cards, card_id):
    if card_id not in cards:
        raise KeyError('该卡牌没有标签目录')
    row = conn.execute("SELECT id, after_tags FROM tag_reviews WHERE card_id=? AND status='approved' ORDER BY reviewed DESC,rowid DESC LIMIT 1", (card_id,)).fetchone()
    tags = json.loads(row['after_tags']) if row else cards[card_id]['tags']
    revision = row['id'] if row else hashlib.sha256(json.dumps(tags, ensure_ascii=False).encode()).hexdigest()
    return tags, revision


def public_row(row):
    return {**dict(row), 'before_tags': json.loads(row['before_tags']), 'after_tags': json.loads(row['after_tags'])}


def read(root, identity, path):
    if not identity:
        raise PermissionError('请先登录')
    editor = identity['role'] in ('admin', 'annotator')
    with closing(connect(root)) as conn:
        if path == '/api/cards/tag-reviews':
            if not editor:
                raise PermissionError('需要编写权限')
            rows = conn.execute("SELECT * FROM tag_reviews WHERE status='pending' ORDER BY rowid")
            return {'items': [public_row(row) for row in rows]}
        match = CARD_PATH.fullmatch(path)
        if not match:
            raise KeyError('接口不存在')
        card_id = match[1]
        tags, revision = current(conn, presets(root), card_id)
        rows = conn.execute('SELECT * FROM tag_reviews WHERE card_id=? ORDER BY rowid DESC', (card_id,)) if editor else []
        return {'tags': tags, 'revision': revision, 'items': [public_row(row) for row in rows]}


def mutate(root, identity, path, data):
    if not identity or identity['role'] not in ('admin', 'annotator'):
        raise PermissionError('需要编写权限')
    cards = presets(root)
    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(root)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        match = CARD_PATH.fullmatch(path)
        if match:
            card_id = match[1]
            before, base = current(conn, cards, card_id)
            if data.get('revision') != base:
                raise Conflict('卡牌标签已更新，请刷新后核对')
            values = data.get('tags')
            if not isinstance(values, list) or any(not isinstance(v, str) or not 0 < len(v.strip()) <= 40 for v in values):
                raise ValueError('每个标签须为 1 至 40 字的文本')
            after = sorted({v.strip() for v in values})
            if after == sorted(before):
                raise ValueError('标签没有变化')
            key = uuid.uuid4().hex
            conn.execute("INSERT INTO tag_reviews VALUES(?,?,?,?,?,?,?,?,'pending',NULL,NULL)",
                         (key, card_id, cards[card_id]['name'] + ('（觉醒）' if cards[card_id].get('awakened') else ''), base, json.dumps(before), json.dumps(after), identity['username'], now))
        else:
            match = REVIEW_PATH.fullmatch(path)
            if not match:
                raise KeyError('接口不存在')
            if identity['role'] != 'admin':
                raise PermissionError('只有管理员能审核标签')
            key, action = match.groups()
            row = conn.execute('SELECT * FROM tag_reviews WHERE id=?', (key,)).fetchone()
            if not row:
                raise KeyError('标签提案不存在')
            if row['status'] != 'pending':
                raise Conflict('提案已经处理')
            if action == 'approve' and current(conn, cards, row['card_id'])[1] != row['base']:
                raise Conflict('该卡标签已变更，请核对后重新提案')
            conn.execute('UPDATE tag_reviews SET status=?,reviewer=?,reviewed=? WHERE id=?',
                         ('approved' if action == 'approve' else 'rejected', identity['username'], now, key))
        return public_row(conn.execute('SELECT * FROM tag_reviews WHERE id=?', (key,)).fetchone())


def submit(server, identity, path, data):
    result = mutate(server.root, identity, path, data)
    if result['status'] == 'approved':
        import templates_http
        import templates_store
        templates_store.refresh_published(server.root, entities=templates_http.effective_entities(server))
    return result
