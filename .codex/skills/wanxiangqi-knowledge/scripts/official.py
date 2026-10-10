"""Import public data actually referenced by the official website."""
import html
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
from wxq import CATEGORIES, atomic_json, atomic_text, init_store, now, read_json

OFFICIAL = 'https://wxq.qq.com/cp/a20260707sfgw/index.html'


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': OFFICIAL})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8-sig')


def plain(value):
    return html.unescape(re.sub('<[^>]+>', '', str(value or ''))).strip()


def walk_cards(value):
    if isinstance(value, dict):
        if 'id' in value and 'name' in value and 'type' in value:
            yield value
        for child in value.values():
            yield from walk_cards(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_cards(child)


def normalize(data, url, at):
    buckets = {c: {} for c in CATEGORIES}
    for card in walk_cards(data):
        category = {1: 'heroes', 9: 'heroes', 2: 'effect-cards', 5: 'equipment', 6: 'talents'}.get(card['type'], 'derivatives')
        hero = card.get('heroCard') or {}
        if hero.get('actorType') not in (None, 1) or hero.get('isNotShowInAtlas'):
            category = 'derivatives'
        eid = 'card:' + str(card['id'])
        record = {'id': eid, 'category': category, 'name': card['name'], 'aliases': [],
                  'description': plain(card.get('desc')), 'properties': card,
                  'relations': [{'kind': 'previews', 'id': 'card:' + str(i)} for i in card.get('previewCardIDs', [])],
                  'sources': [url], 'version': None, 'status': 'official', 'retrieved_at': at}
        old = buckets[category].get(eid)
        if old is None or len(json.dumps(record)) > len(json.dumps(old)):
            buckets[category][eid] = record
    for lord in data.get('lords', []):
        lid = str(lord.get('lordId', lord.get('id', '')))
        name = lord.get('name') or lord.get('lordName') or lord.get('title')
        buckets['players']['player:' + lid] = {
            'id': 'player:' + lid, 'category': 'players', 'name': name or ('棋手-' + lid),
            'aliases': [], 'description': plain(lord.get('desc')), 'properties': lord,
            'relations': [], 'sources': [url], 'version': None, 'status': 'official', 'retrieved_at': at}
        for card in walk_cards(lord):
            # Only type 7 is a lord skill; related heroes/equipment/talents retain their categories.
            if card['type'] != 7:
                continue
            eid = 'card:' + str(card['id'])
            for b in buckets.values():
                b.pop(eid, None)
            previous_skill = buckets['player-skills'].get(eid)
            record = {
                'id': eid, 'category': 'player-skills', 'name': card['name'], 'aliases': [],
                'description': plain(card.get('desc')), 'properties': card,
                'relations': [{'kind': 'owner', 'id': 'player:' + lid}], 'sources': [url],
                'version': None, 'status': 'official', 'retrieved_at': at}
            if previous_skill:
                record['relations'] = previous_skill['relations'] + [r for r in record['relations'] if r not in previous_skill['relations']]
            buckets['player-skills'][eid] = record
    for player in data.get('data', []):
        if not isinstance(player, dict) or 'uid' not in player or 'title' not in player:
            continue
        eid = 'player:' + str(player['uid'])
        buckets['players'][eid] = {'id': eid, 'category': 'players', 'name': player['title'],
                                 'aliases': [], 'description': '', 'properties': {'cms': player},
                                 'relations': [], 'sources': [url], 'version': None,
                                 'status': 'official', 'retrieved_at': at}
    return buckets


def sync_official(root):
    root = Path(root)
    init_store(root)
    report = {'at': now(), 'page': OFFICIAL, 'counts': {}, 'errors': [], 'missing': [], 'unknown_types': []}
    buckets = {c: {} for c in CATEGORIES}
    try:
        page = fetch(OFFICIAL)
        atomic_text(root / 'entities/raw/index.html', page)
        scripts = re.findall(r'<script[^>]+src=[\"\']([^\"\']+)', page)
        endpoints = set()
        for src in sorted(set(scripts)):
            if not re.search(r'/(cards|role)\.js$', src):
                continue
            url = urllib.parse.urljoin(OFFICIAL, src)
            body = fetch(url)
            atomic_text(root / 'entities/raw' / Path(urllib.parse.urlparse(url).path).name, body)
            endpoints.update(re.findall(r'[\"\']((?:https?:)?//[^\"\'\s]+(?:\.js|\.json))(?:\?[^\"\']*)?[\"\']', body))
        endpoints = {('https:' + u if u.startswith('//') else u) for u in endpoints
                     if ('oscard_new_' in u or ('info_article_' in u and '/prod/' in u))}
        if not endpoints:
            raise ValueError('Official schema changed: no data endpoints discovered')
        for url in sorted(endpoints):
            try:
                body = fetch(url)
                data = json.loads(body)
                report['unknown_types'] += [{'id': c['id'], 'type': c['type'], 'name': c['name']}
                                           for c in walk_cards(data) if c['type'] not in [1, 2, 5, 6, 7, 9]]
                atomic_text(root / 'entities/raw' / Path(urllib.parse.urlparse(url).path).name, body)
                parsed = normalize(data, url, report['at'])
                for category, records in parsed.items():
                    for eid, record in records.items():
                        previous = buckets[category].get(eid)
                        if previous:
                            record['properties'] = {**previous['properties'], **record['properties']}
                            record['sources'] = sorted(set(previous['sources'] + record['sources']))
                            if not record['description']:
                                record['description'] = previous['description']
                        buckets[category][eid] = record
            except Exception as exc:
                report['errors'].append({'url': url, 'error': str(exc)})
    except Exception as exc:
        report['errors'].append({'url': OFFICIAL, 'error': str(exc)})
    # A lord-owned card is a player skill, even when also present in generic card lists.
    for eid in buckets['player-skills']:
        for c in CATEGORIES:
            if c != 'player-skills':
                buckets[c].pop(eid, None)
    for skill in buckets['player-skills'].values():
        for relation in skill['relations']:
            if relation['kind'] == 'owner' and relation['id'] in buckets['players']:
                owner = buckets['players'][relation['id']]
                link = {'kind': 'skill', 'id': skill['id']}
                if link not in owner['relations']:
                    owner['relations'].append(link)
    prior = {e['id']: e for c in CATEGORIES for e in read_json(root / 'entities' / (c + '.json'), [])}
    for category, records in buckets.items():
        path = root / 'entities' / (category + '.json')
        old = {e['id']: e for e in read_json(path, [])}
        # Move IDs whose newly confirmed category differs; do not delete absent IDs.
        moved_ids = {eid for c, b in buckets.items() if c != category for eid in b}
        old = {eid: e for eid, e in old.items() if eid not in moved_ids}
        for eid, record in records.items():
            previous = prior.get(eid, {})
            record['aliases'] = previous.get('aliases', [])
            history = previous.get('history', [])
            if previous and previous.get('properties') != record['properties']:
                history = history + [{'retrieved_at': previous.get('retrieved_at'),
                                      'properties': previous.get('properties'), 'version': previous.get('version')}]
            if history:
                record['history'] = history
            old[eid] = record
        atomic_json(path, sorted(old.values(), key=lambda e: e['id']))
        report['counts'][category] = len(records)
        if not records:
            report['missing'].append(category)
    atomic_json(root / 'entities/sync-report.json', report)
    from reference_store import export_cards
    report['card_reference'] = export_cards(root)
    atomic_json(root / 'entities/sync-report.json', report)
    return report
