from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import json_store as store
import reader_store
from note_seasons import SEASONS, membership


def selected(url):
    values = parse_qs(urlsplit(url).query, keep_blank_values=True).get('season', ['S1'])
    if len(values) != 1 or values[0] not in SEASONS:
        raise ValueError('未知赛季')
    return values[0]


def matches(row, season):
    return season in membership(row)


def catalog(value, season):
    rows = [r for r in value['notes'] if matches(r, season)]
    return {**value, 'notes': rows, 'revision': store.digest([value['revision'], season])}


def members(root, season):
    index = reader_store.index(root)
    return {r['id']: r for r in index.get('notes', []) if matches(r, season)}


def ids(root, season):
    index = reader_store.index(root)
    current = {r['id'] for r in index.get('notes', []) if matches(r, season)}
    return current | {key for key, target in index.get('aliases', {}).items() if target in current}


def filter_links(value, allowed):
    result = dict(value)
    for field, key in (('related', 'id'), ('guide_related', 'note')):
        if field in result:
            result[field] = [item for item in result[field]
                             if (item.get(key) if isinstance(item, dict) else item) in allowed]
    return result


def note(root, nid, season, player=None):
    value = store.resolve_note(root, nid, player)
    if not value or not matches(value, season):
        return None
    result = filter_links(value, ids(root, season))
    current = members(root, season)
    result['related'] = [current[item] if isinstance(item, str) else item for item in result['related']
                         if not isinstance(item, str) or item in current]
    return result


def rows(root, values, season):
    allowed = ids(root, season) if store.enabled(root) else {r['id'] for r in values}
    return [filter_links(r, allowed) for r in values if matches(r, season)]


def dataset(root, season, resource, default):
    return store.read(Path(root) / 'website-data' / 'seasons' / season / (resource + '.json'), default)


def cards(root, season, path):
    values = dataset(root, season, 'cards', [])
    if path == '/api/cards':
        return values
    if path == '/api/cards/status':
        return {'version': store.digest(values), 'state': 'ready' if values else 'empty'}
    target = next((row for row in values if row['id'] == path.removeprefix('/api/cards/')), None)
    if target is None:
        raise KeyError('卡牌不存在')
    return target


def options(root, season, sections):
    entities = dataset(root, season, 'entities', [])
    players = [{k: row.get(k) for k in ('id', 'name', 'category', 'aliases')}
               for row in reader_store.entities(root) if row['category'] == 'players']
    return {'entities': entities, 'authoring_players': players,
            'factions': dataset(root, season, 'factions', []), 'sections': sections}


def search(root, query, season, cat):
    wanted = query.lower().split()
    entities = reader_store.entities(root) if season == 'S1' else dataset(root, season, 'entities', [])
    labels = {e['id']: ' '.join([e.get('name') or '', *(e.get('aliases') or [])]).lower() for e in entities}
    found = []
    for row in cat['notes']:
        projection = reader_store.cached(root, row)
        if projection and all(term in projection['text'] + ' ' + ' '.join(labels.get(ref, '') for ref in projection['refs']) for term in wanted):
            found.append(row['id'])
    return {'ready': cat['ready'], 'revision': cat['revision'], 'ids': found}


def template_read(root, season, path):
    if path == '/api/templates':
        value = dataset(root, season, 'templates', {'schema_version': 1, 'groups': [], 'events': []})
        return {**value, 'revision': store.digest(value)}
    if path == '/api/templates/warnings':
        return {'items': [], 'unseen_items': [], 'notification_revision': store.digest([]), 'unseen': False}
    raise KeyError('模板接口不存在')


def protected_write(path):
    return path.startswith(('/api/dashboard/usage/', '/api/templates/', '/api/cards/')) or path in ('/api/templates', '/api/cards')


def scoped_note_id(path):
    match = re.match(r'^/api/notes/([^/]+)(?:/|$)', path)
    return match[1] if match and match[1] not in ('catalog', 'search') else None
