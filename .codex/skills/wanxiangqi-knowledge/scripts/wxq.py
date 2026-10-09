"""Evidence-backed store and command entry point for wanxiangqi-knowledge."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
CATEGORIES = ['players', 'heroes', 'equipment', 'talents', 'derivatives', 'effect-cards', 'player-skills']
FOLDERS = {'lineup': 'lineups', 'player': 'players', 'other': 'other'}
SECTIONS = {
    'lineup': ['阵容组成', '核心机制', '前期运营及应变', '中期运营及应变', '后期运营及应变',
               '成型后提升思路', '第一轮拍卖', '第二轮拍卖', '第三轮拍卖', '推荐天赋及原因',
               '站位技巧', '推荐装备', '终局技巧', '克制手段'],
    'player': ['技能', '使用技巧', '适配阵容'], 'other': ['知识内容']}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).exists() else default


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return False
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     delete=False, suffix='.tmp', newline='\n') as f:
        f.write(text)
        temporary = Path(f.name)
    try:
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + '.bak'))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def atomic_json(path, value):
    return atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[\w-]+', value) or len(value) > 120:
        raise ValueError('Invalid local ID: ' + str(value))
    return value


def source_dir(root, sid):
    return Path(root) / 'knowledge/sources' / safe_id(sid.replace(':', '_'))


def init_store(root):
    root = Path(root)
    for folder in ['knowledge/sources', 'knowledge/reports', 'knowledge/lineups',
                   'knowledge/players', 'knowledge/other', 'entities/raw']:
        (root / folder).mkdir(parents=True, exist_ok=True)
    for c in CATEGORIES:
        p = root / 'entities' / (c + '.json')
        if not p.exists():
            atomic_json(p, [])
    if not (root / 'knowledge/index.json').exists():
        atomic_json(root / 'knowledge/index.json', {'schema_version': 1, 'notes': []})


def entities(root):
    return [e for c in CATEGORIES for e in read_json(Path(root) / 'entities' / (c + '.json'), [])]


def correct_text(text, records):
    aliases = defaultdict(list)
    canonical = {e['name'] for e in records}
    for e in records:
        for alias in e.get('aliases', []):
            if isinstance(alias, str) and alias and alias != e['name']:
                aliases[alias].append(e)
    changes = []
    if not aliases:
        return text, changes
    pattern = re.compile('|'.join(re.escape(x) for x in sorted(set(aliases) | canonical, key=len, reverse=True)))
    def replace(match):
        token = match.group()
        if token in canonical:
            return token
        matches = {e['id']: e for e in aliases[token]}
        if len(matches) == 1:
            entity = next(iter(matches.values()))
            changes.append({'original': token, 'replacement': entity['name'], 'entity': entity['id'],
                            'status': 'confirmed_alias'})
            return entity['name']
        changes.append({'original': token, 'candidates': list(matches), 'status': 'ambiguous'})
        return token
    return pattern.sub(replace, text), changes


def run_batch(urls, worker):
    result = []
    for url in urls:
        try:
            result.append({'url': url, 'status': 'ok', 'result': worker(url)})
        except Exception as exc:
            result.append({'url': url, 'status': 'failed', 'error': str(exc)})
    return result


KNOWLEDGE_KINDS = {'mechanic', 'general_strategy', 'conditional_strategy'}


def merge_claims(old, incoming):
    merged = {}
    for claim in old + incoming:
        key = json.dumps({k: claim.get(k) for k in ['section', 'text', 'version', 'condition', 'inference', 'kind']},
                         sort_keys=True, ensure_ascii=False)
        item = merged.setdefault(key, {**claim, 'evidence': []})
        seen = {json.dumps(e, sort_keys=True) for e in item['evidence']}
        for evidence in claim.get('evidence', []):
            if json.dumps(evidence, sort_keys=True) not in seen:
                item['evidence'].append(evidence)
                seen.add(json.dumps(evidence, sort_keys=True))
    return list(merged.values())


def related(root, entity_ids, core=None, topic=None):
    index = read_json(Path(root) / 'knowledge/index.json', {'notes': []})
    return [n for n in index['notes'] if set(entity_ids) & set(n.get('entities', []))
            or (core and set(core) & set(n.get('core', []))) or (topic and topic == n.get('topic'))]


def render_note(note, sources):
    lines = ['# ' + note['title'], '']
    claims = [c for c in note.get('claims', []) if c.get('kind') in KNOWLEDGE_KINDS]
    sections = SECTIONS[note['type']] + sorted({c['section'] for c in claims} - set(SECTIONS[note['type']]))
    if note['type'] == 'other' and claims:
        sections = list(dict.fromkeys(c['section'] for c in claims))
    for section in sections:
        lines += ['## ' + section, '']
        selected = [c for c in claims if c['section'] == section]
        if not selected:
            lines += ['暂无已确认的通用策略', '']
        for c in selected:
            text = c['text']
            condition = c.get('condition', '').strip()
            if condition and condition not in text:
                text = f'当{condition}时，{text}'
            if c.get('inference'):
                text = '推测：' + text
            lines += ['- ' + text]
            lines += ['']
    lines += ['## 关联知识', '']
    for link in note.get('related', []):
        lines.append(f"- [{link['title']}](../{FOLDERS[link['type']]}/{link['id']}.md)")
    if not note.get('related'):
        lines.append('暂无')
    return '\n'.join(lines) + '\n'


def commit_notes(root, incoming):
    root = Path(root)
    init_store(root)
    sources = {}
    for p in (root / 'knowledge/sources').glob('*/metadata.json'):
        data = read_json(p)
        sources[data['id']] = data
    index_path = root / 'knowledge/index.json'
    notes = {n['id']: n for n in read_json(index_path)['notes']}
    known_entities = {e['id'] for e in entities(root)}
    for note in incoming:
        safe_id(note['id'])
        if note['type'] not in FOLDERS or not note.get('title'):
            raise ValueError('Invalid note type or title')
        target = root / 'knowledge' / FOLDERS[note['type']] / (note['id'] + '.md')
        pending_ids = {n['id'] for n in read_json(root / 'knowledge/pending-commit.json', {'notes': []})['notes']}
        if target.exists() and note['id'] not in notes and note['id'] not in pending_ids:
            raise ValueError('Unmanaged Markdown exists; migrate it before committing')
        if (set(note.get('entities', [])) | set(note.get('core', []))) - known_entities:
            raise ValueError('Unknown entity reference; register pending entity first')
        for claim in note.get('claims', []):
            if claim.get('kind') not in KNOWLEDGE_KINDS:
                raise ValueError('Knowledge requires mechanic/general_strategy/conditional_strategy kind; match_action belongs in internal reports')
            if not claim.get('section') or not claim.get('text') or not claim.get('evidence'):
                raise ValueError('Every claim requires section, text and evidence')
            for e in claim['evidence']:
                if e['source'] not in sources or not 0 <= e['start'] <= e['end']:
                    raise ValueError('Unknown source or invalid timestamp')
                folder = source_dir(root, e['source'])
                if not read_json(folder / 'asr.raw.json', {}).get('segments') or not read_json(folder / 'asr.corrected.json', {}).get('segments'):
                    raise ValueError('Source requires real ASR artifacts before knowledge commit')
                duration = sources[e['source']].get('duration')
                if duration and e['end'] > duration + 1:
                    raise ValueError('Evidence exceeds source duration')
                if e.get('frame'):
                    frame = (source_dir(root, e['source']) / e['frame']).resolve()
                    if not frame.is_relative_to(source_dir(root, e['source']).resolve()) or not frame.exists():
                        raise ValueError('Invalid frame reference')
        if note['id'] in notes and notes[note['id']]['type'] != note['type']:
            raise ValueError('Cannot change existing note type')
    for note in incoming:
        previous = notes.get(note['id'], {})
        notes[note['id']] = {**previous, **note,
                             'entities': sorted(set(previous.get('entities', []) + note.get('entities', []))),
                             'core': sorted(set(previous.get('core', []) + note.get('core', []))),
                             'claims': merge_claims(previous.get('claims', []), note.get('claims', []))}
    for note in notes.values():
        linked = [n for n in notes.values() if n['id'] != note['id'] and (
            set(note.get('entities', [])) & set(n.get('entities', [])) or
            set(note.get('core', [])) & set(n.get('core', [])) or
            note.get('topic') and note.get('topic') == n.get('topic'))]
        note['related'] = [{'id': n['id'], 'type': n['type'], 'title': n['title']} for n in linked]
    atomic_json(root / 'knowledge/pending-commit.json', {'notes': incoming})
    for note in notes.values():
        atomic_text(root / 'knowledge' / FOLDERS[note['type']] / (note['id'] + '.md'), render_note(note, sources))
    atomic_json(index_path, {'schema_version': 1, 'notes': list(notes.values())})
    (root / 'knowledge/pending-commit.json').unlink(missing_ok=True)
    return {'notes': len(notes), 'updated_input': len(incoming)}


def validate_store(root):
    root = Path(root)
    errors = []
    seen = set()
    counts = {}
    for c in CATEGORIES:
        records = read_json(root / 'entities' / (c + '.json'), [])
        counts[c] = len(records)
        for e in records:
            if e.get('id') in seen:
                errors.append('Duplicate entity ID: ' + e['id'])
            seen.add(e.get('id'))
            if e.get('category') != c or not e.get('name'):
                errors.append('Invalid entity category/name: ' + str(e.get('id')))
    index = read_json(root / 'knowledge/index.json', {'notes': []})
    note_ids = set()
    for n in index['notes']:
        if n['id'] in note_ids:
            errors.append('Duplicate note: ' + n['id'])
        note_ids.add(n['id'])
        target = root / 'knowledge' / FOLDERS[n['type']] / (safe_id(n['id']) + '.md')
        if not target.exists():
            errors.append('Missing note file: ' + str(target))
        for eid in n.get('entities', []) + n.get('core', []):
            if eid not in seen:
                errors.append('Unknown entity: ' + eid)
        for claim in n.get('claims', []):
            if claim.get('kind') not in KNOWLEDGE_KINDS:
                errors.append('Unclassified or match-specific claim: ' + n['id'])
            for evidence in claim.get('evidence', []):
                folder = source_dir(root, evidence['source'])
                if not (folder / 'asr.raw.json').exists():
                    errors.append('Missing ASR: ' + evidence['source'])
                if not (folder / 'metadata.json').exists():
                    errors.append('Missing metadata: ' + evidence['source'])
                if evidence.get('frame') and not (folder / evidence['frame']).exists():
                    errors.append('Missing cited frame: ' + evidence['frame'])
    return {'entities': counts, 'notes': len(index['notes']), 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('sync-entities')
    sub.add_parser('validate')
    p = sub.add_parser('prepare')
    p.add_argument('urls', nargs='+')
    p.add_argument('--model', default='large-v3')
    p.add_argument('--cookies', help='User-provided Netscape cookies; never discover credentials automatically')
    p = sub.add_parser('frames')
    p.add_argument('source')
    p.add_argument('times', nargs='+', type=float)
    p = sub.add_parser('related')
    p.add_argument('ids', nargs='*')
    p.add_argument('--core', nargs='*')
    p.add_argument('--topic')
    p = sub.add_parser('commit')
    p.add_argument('file', type=Path)
    p = sub.add_parser('finish')
    p.add_argument('source')
    p = sub.add_parser('process-local')
    p.add_argument('source')
    p.add_argument('--model', default='large-v3')
    p = sub.add_parser('fetch-stream')
    p.add_argument('source')
    p.add_argument('kind', choices=['audio', 'video'])
    p.add_argument('url', help='Exact public media URL observed in the browser')
    args = parser.parse_args()
    if args.command == 'init':
        init_store(args.root)
        result = {'root': str(args.root)}
    elif args.command == 'sync-entities':
        from official import sync_official
        result = sync_official(args.root)
    elif args.command == 'validate':
        result = validate_store(args.root)
    elif args.command == 'prepare':
        from media import prepare
        init_store(args.root)
        result = run_batch(args.urls, lambda u: prepare(args.root, u, args.model, args.cookies))
        atomic_json(args.root / 'knowledge/reports/last-prepare.json', {'at': now(), 'results': result})
    elif args.command == 'frames':
        from media import extract_frames
        result = extract_frames(args.root, args.source, source_dir(args.root, args.source) / 'media.mp4', args.times)
    elif args.command == 'related':
        result = related(args.root, args.ids, args.core, args.topic)
    elif args.command == 'commit':
        result = commit_notes(args.root, read_json(args.file)['notes'])
    elif args.command == 'process-local':
        from media import process_local
        result = process_local(args.root, args.source, args.model)
    elif args.command == 'fetch-stream':
        from media import download_observed
        folder = source_dir(args.root, args.source)
        result = download_observed(args.url, folder / (args.kind + '.m4s'))
    else:
        from media import finish
        result = finish(args.root, args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failed = isinstance(result, dict) and result.get('errors')
    if isinstance(result, list):
        failed = any(row.get('status') == 'failed' or any(p.get('stage') == 'failed'
                     for p in row.get('result', []) if isinstance(p, dict)) for row in result)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
