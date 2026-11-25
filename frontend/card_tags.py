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
TAG_SEPARATOR = re.compile(r'[、，,\r\n]')
TAXONOMY_VERSION = 2
TAG_SUGGESTIONS = {
    '英雄': ('功能性', '快速施法', '控制', '治疗', '临时等级', '压制'),
    '天赋': ('经济类', '战力类', '回血类', '商店类', '阵容类'),
    '装备': ('吸血', '控制', '治疗', '反伤', '输出', '回蓝', '物理系', '法系', '护盾', '防御', '攻速'),
    '效果牌': ('等级转移',),
}
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
        created TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT, reviewed TEXT,
        taxonomy_version INTEGER NOT NULL DEFAULT 1)""")
    # Legacy reviews belong to the original tag vocabulary even after a release upgrade.
    if 'taxonomy_version' not in {row['name'] for row in conn.execute('PRAGMA table_info(tag_reviews)')}:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            if 'taxonomy_version' not in {row['name'] for row in conn.execute('PRAGMA table_info(tag_reviews)')}:
                conn.execute('ALTER TABLE tag_reviews ADD COLUMN taxonomy_version INTEGER NOT NULL DEFAULT 1')
    if conn.execute("SELECT 1 FROM tag_reviews WHERE status='pending' AND taxonomy_version<? LIMIT 1", (TAXONOMY_VERSION,)).fetchone():
        with conn:
            conn.execute("UPDATE tag_reviews SET status='expired' WHERE status='pending' AND taxonomy_version<?", (TAXONOMY_VERSION,))
    return conn


def apply_approved_tags(conn, cards):
    for row in conn.execute("""SELECT card_id, after_tags FROM tag_reviews
        WHERE status='approved' AND taxonomy_version=? ORDER BY reviewed,rowid""", (TAXONOMY_VERSION,)):
        if row['card_id'] in cards:
            cards[row['card_id']]['tags'] = json.loads(row['after_tags'])
    return cards


def effective_tags(root):
    cards = presets(root)
    if database(root).exists():
        with closing(connect(root)) as conn:
            return apply_approved_tags(conn, cards)
    return cards


def current(conn, cards, card_id):
    if card_id not in cards:
        raise KeyError('该卡牌没有标签目录')
    row = conn.execute("""SELECT id, after_tags FROM tag_reviews WHERE card_id=?
        AND status='approved' AND taxonomy_version=? ORDER BY reviewed DESC,rowid DESC LIMIT 1""",
        (card_id, TAXONOMY_VERSION)).fetchone()
    tags = json.loads(row['after_tags']) if row else cards[card_id]['tags']
    revision = row['id'] if row else hashlib.sha256(json.dumps([TAXONOMY_VERSION, tags], ensure_ascii=False).encode()).hexdigest()
    return tags, revision


def public_row(row):
    historical = row['taxonomy_version'] != TAXONOMY_VERSION
    return {**dict(row), 'historical': historical, 'before_tags': json.loads(row['before_tags']), 'after_tags': json.loads(row['after_tags'])}


def read(root, identity, path):
    if not identity:
        raise PermissionError('请先登录')
    editor = identity['role'] in ('admin', 'annotator')
    with closing(connect(root)) as conn:
        if path == '/api/cards/tag-reviews':
            if not editor:
                raise PermissionError('需要编写权限')
            rows = conn.execute("SELECT * FROM tag_reviews WHERE status='pending' AND taxonomy_version=? ORDER BY rowid", (TAXONOMY_VERSION,))
            return {'items': [public_row(row) for row in rows]}
        match = CARD_PATH.fullmatch(path)
        if not match:
            raise KeyError('接口不存在')
        card_id = match[1]
        cards = presets(root)
        tags, revision = current(conn, cards, card_id)
        rows = conn.execute('SELECT * FROM tag_reviews WHERE card_id=? ORDER BY rowid DESC', (card_id,)) if editor else []
        result = {'tags': tags, 'revision': revision, 'items': [public_row(row) for row in rows]}
        if editor:
            category = cards[card_id]['type']
            suggestions = set(TAG_SUGGESTIONS.get(category, ()))
            for card in apply_approved_tags(conn, cards).values():
                if card['type'] == category:
                    suggestions.update(card['tags'])
            result['suggestions'] = sorted(suggestions)
        return result


def mutate(root, identity, path, data):
    if not identity or identity['role'] not in ('admin', 'annotator'):
        raise PermissionError('需要编写权限')
    cards = presets(root)
    with closing(connect(root)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        now = datetime.now(timezone.utc).isoformat()
        match = CARD_PATH.fullmatch(path)
        if match:
            card_id = match[1]
            before, base = current(conn, cards, card_id)
            if data.get('revision') != base:
                raise Conflict('卡牌标签已更新，请刷新后核对')
            values = data.get('tags')
            if not isinstance(values, list) or any(not isinstance(v, str) or not 0 < len(v.strip()) <= 40
                                                   or TAG_SEPARATOR.search(v) for v in values):
                raise ValueError('每个标签须为 1 至 40 字的文本，且不能包含标签分隔符')
            after = sorted({v.strip() for v in values})
            if after == sorted(before):
                raise ValueError('标签没有变化')
            encoded_after = json.dumps(after)
            direct = identity['role'] == 'admin'
            if not direct:
                duplicate = conn.execute("""SELECT * FROM tag_reviews WHERE card_id=? AND author=? AND base=?
                    AND after_tags=? AND status='pending' AND taxonomy_version=?""",
                    (card_id, identity['username'], base, encoded_after, TAXONOMY_VERSION)).fetchone()
                if duplicate:
                    return public_row(duplicate)
            key = uuid.uuid4().hex
            conn.execute("""INSERT INTO tag_reviews
                (id,card_id,card_name,base,before_tags,after_tags,author,created,status,reviewer,reviewed,taxonomy_version)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, card_id, cards[card_id]['name'] + ('（觉醒）' if cards[card_id].get('awakened') else ''),
                 base, json.dumps(before), encoded_after, identity['username'], now,
                 'approved' if direct else 'pending', identity['username'] if direct else None,
                 now if direct else None, TAXONOMY_VERSION))
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
            if row['taxonomy_version'] != TAXONOMY_VERSION:
                raise Conflict('旧标签体系的提案已失效')
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
