"""Evidence-backed store and command entry point for wanxiangqi-knowledge."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
import errno
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
CATEGORIES = ['players', 'heroes', 'equipment', 'talents', 'derivatives', 'effect-cards', 'player-skills']
FOLDERS = {'lineup': 'lineups', 'player': 'players', 'other': 'other'}
SECTIONS = {
    'lineup': ['阵容组成', '禁用阵营适用情况', '核心机制', '前期运营及应变', '中期运营及应变', '后期运营及应变',
               '成型后提升思路', '第一轮拍卖', '第二轮拍卖', '第三轮拍卖', '推荐天赋及原因',
               '站位技巧', '推荐装备', '终局技巧', '克制手段'],
    'player': ['技能', '前期思路', '适用打法与选择', '适用技巧'], 'other': ['知识内容']}
PLAYER_SECTION_ALIASES = {'使用技巧':'适用技巧','适配阵容':'适用打法与选择'}


def now():
    return datetime.now(timezone.utc).isoformat()


def retry_file_access(operation, cancelled=None, crt_access=False):
    delays = [.05, .1, .2, .4, .8]
    for attempt in range(len(delays) + 1):
        if cancelled and cancelled():
            raise InterruptedError('保存已取消')
        try:
            return operation()
        except OSError as exc:
            # Windows CRT open() used by reads/backups can discard winerror and report EACCES.
            windows_crt_denied = crt_access and os.name == 'nt' and getattr(exc, 'winerror', None) is None and exc.errno == errno.EACCES
            if (getattr(exc, 'winerror', None) not in (5, 32, 33) and not windows_crt_denied) or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


def read_json(path, default=None):
    return json.loads(retry_file_access(lambda: Path(path).read_text(encoding='utf-8-sig'), crt_access=True)) if Path(path).exists() else default


def backup_file(path):
    """Keep knowledge recovery copies outside the live knowledge tree."""
    path = Path(path).resolve()
    knowledge = next((parent for parent in path.parents if parent.name == 'knowledge'), None)
    if knowledge is None:
        target = path.with_suffix(path.suffix + '.bak')
    else:
        relative = path.relative_to(knowledge)
        folder = knowledge.parent / 'raw/backups/knowledge' / relative.parent
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (relative.name + '.' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.' + uuid.uuid4().hex + '.bak')
    shutil.copy2(path, target)
    return target


def atomic_text(path, text, cancelled=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and retry_file_access(lambda: path.read_text(encoding='utf-8'), cancelled, crt_access=True) == text:
        return False
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     delete=False, suffix='.tmp', newline='\n') as f:
        f.write(text)
        temporary = Path(f.name)
    try:
        def replace():
            if path.exists():
                backup_file(path)
            temporary.replace(path)
        retry_file_access(replace, cancelled, crt_access=True)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def atomic_json(path, value, cancelled=None):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    return atomic_text(path, text, cancelled=cancelled) if cancelled is not None else atomic_text(path, text)


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[\w-]+', value) or len(value) > 120:
        raise ValueError('Invalid local ID: ' + str(value))
    return value


def source_dir(root, sid):
    return Path(root) / 'raw/sources' / safe_id(sid.replace(':', '_'))


def init_store(root):
    root = Path(root)
    for folder in ['raw/sources', 'raw/reports', 'knowledge/lineups',
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
    from player_branches import enabled, entry_markdown
    if enabled(note):return entry_markdown(note)
    from lineup_layout import PROFILE_ID, render as render_profile
    if note['type'] == 'lineup':
        return render_profile(note)
    lines = ['# ' + note['title'], '']
    if note.get('meta'):
        from workspace import FACTIONS
        names = {f['id']: f['name'] for f in FACTIONS}
        names.update(note.get('entity_names', {}))
        meta = note['meta']
        flexible = bool(meta.get('late_variants'))
        empty_dependency = '随组合查看，无全局共同要求' if flexible else '待确认'
        lines += ['## 阵容信息', '', '必须阵营：' + ('、'.join(names.get(x, x.removeprefix('pending:')) for x in meta.get('required_factions', [])) or empty_dependency), '']
        lines += ['适用棋手：' + ('、'.join(names.get(x, x) for x in meta.get('players', [])) or '待确认'), '',
                  '核心英雄：' + ('、'.join(names.get(x, x) for x in meta.get('core_heroes', [])) or empty_dependency), '']
        for stage, label in [('early', '前期'), ('middle', '中期'), ('late', '后期')]:
            members = meta.get('compositions', {}).get(stage, [])
            lines += [label + '英雄组成：', '']
            if not members:
                lines += [('按运营节奏及后期组合选择，见下文' if flexible else '待确认'), '']
            for member in members:
                necessity = '必需' if member['necessity'] == 'required' else '可选'
                text = f"- {names.get(member['hero'], member['hero'])}（{necessity}）：{member.get('role', '')}"
                if member.get('replaces'):
                    text += '；替换' + names.get(member['replaces'], member['replaces'])
                if member.get('replacement_note'):
                    text += '；' + member['replacement_note']
                lines += [text, '']
        for condition in meta.get('ban_conditions', []):
            status = {'playable': '可玩', 'unplayable': '不可玩', 'unknown': '待确认'}[condition['status']]
            lines += [f"- {names.get(condition['faction'], condition['faction'])}被禁：{status}。{condition.get('reason', '')}", '']
        for matchup in meta.get('matchups', []):
            lines += [f"- 针对{names.get(matchup['target'], matchup['target'])}：{matchup.get('condition', '')} {matchup['text']}", '']
    claims = [c for c in note.get('claims', []) if c.get('kind') in KNOWLEDGE_KINDS]
    if note['type']=='player':
        claims=[{**c,'section':PLAYER_SECTION_ALIASES.get(c['section'],c['section'])} for c in claims]
    sections = SECTIONS[note['type']] + sorted({c['section'] for c in claims} - set(SECTIONS[note['type']]))
    if note['type'] == 'other' and claims:
        sections = list(dict.fromkeys(c['section'] for c in claims))
    for section in sections:
        lines += ['## ' + section, '']
        selected = [c for c in claims if c['section'] == section]
        if note['type']=='player' and section=='适用打法与选择':
            from player_branches import render_adaptations
            lines += render_adaptations(note,heading=False)
            if selected:lines+=['### 其他选阵说明','']
        if not selected and not (note['type']=='player' and section=='适用打法与选择' and note.get('lineup_adaptations')):
            lines += [('未确定阵容时的通用开局尚待确认。' if note['type']=='player' and section=='前期思路' else '暂无已确认的通用策略'), '']
        for c in selected:
            text = c['text']
            condition = c.get('condition', '').strip()
            if condition and condition not in text:
                text = f"当{condition}{'' if condition.endswith('时') else '时'}，{text}"
            if c.get('inference') and not (note['type']=='player' and note.get('reading_layout',{}).get('version')==4):
                text = '推测：' + text
            lines += [text if note['type']=='player' and text.startswith('### ') else '- ' + text]
            lines += ['']
    if note.get('meta'):
        from tactics import render as render_tactics
        lines += render_tactics(note['meta'], claims, names)
    from player_branches import render_adaptations
    if note['type']!='player':lines += render_adaptations(note)
    lines += ['## 关联知识', '']
    for link in note.get('related', []):
        path = link.get('path', f"knowledge/{FOLDERS[link['type']]}/{link['id']}.md")
        lines.append(f"- [{link['title']}](../{Path(path).parent.name}/{Path(path).name})")
    if not note.get('related'):
        lines.append('暂无')
    return '\n'.join(lines) + '\n'


def commit_notes(root, incoming):
    from workspace import store_lock, recover
    with store_lock(root):
        recover(root)
        from markdown_sync import scan
        scan(root,_locked=True)
        return _commit_notes(root, incoming)


def _commit_notes(root, incoming):
    from workspace import merge_note, persist, validate_meta
    root = Path(root)
    init_store(root)
    sources = {}
    for p in (root / 'raw/sources').glob('*/metadata.json'):
        data = read_json(p)
        sources[data['id']] = data
    index_path = root / 'knowledge/index.json'
    notes = {n['id']: n for n in read_json(index_path)['notes']}
    from player_identity import import_notes
    incoming=import_notes(root,incoming,list(notes.values()))
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
        if 'meta' in note:
            validate_meta(root, note['meta'])
            from tactics import validate as validate_tactics
            validate_tactics(note['meta'], lambda value: None, note.get('claims', []))
        for claim in note.get('claims', []):
            if claim.get('origin') == 'manual':
                old = notes.get(note['id'], {})
                if claim in old.get('claims', []) and claim['section'] in old.get('manual_sections', []):
                    continue
                raise ValueError('Manual revisions must originate from the web editor; unchanged existing revisions may be replayed')
            if claim.get('kind') not in KNOWLEDGE_KINDS:
                raise ValueError('Knowledge requires mechanic/general_strategy/conditional_strategy kind; match_action belongs in internal reports')
            if not claim.get('section') or not claim.get('text') or not claim.get('evidence'):
                raise ValueError('Every claim requires section, text and evidence')
            for e in claim['evidence']:
                if e.get('type') == 'document':
                    from document_sources import validate_evidence
                    validate_evidence(root,e)
                    continue
                if e['source'] not in sources or not 0 <= e['start'] <= e['end']:
                    raise ValueError('Unknown source or invalid timestamp')
                folder = source_dir(root, e['source'])
                from reference_store import transcript_has_evidence
                if not transcript_has_evidence(folder):
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
        notes[note['id']] = {**merge_note(previous, note),
                             'entities': sorted(set(previous.get('entities', []) + note.get('entities', []))),
                             'core': sorted(set(previous.get('core', []) + note.get('core', []))),
                             }
        if note['type'] == 'lineup' and not notes[note['id']].get('manual_meta'):
            from reference_store import enrich_meta
            from workspace import default_meta
            notes[note['id']]['meta'] = enrich_meta(notes[note['id']].get('meta') or default_meta(notes[note['id']]), entities(root))
    from workspace import prepare as prepare_notes
    prepare_notes(root, list(notes.values()))
    for merged in notes.values():
        if merged['type'] == 'lineup':
            from workspace import validate_meta
            from tactics import validate as validate_tactics
            validate_meta(root, merged['meta'])
            validate_tactics(merged['meta'], lambda ref: None, merged.get('claims', []))
    for note in notes.values():
        linked = [n for n in notes.values() if n['id'] != note['id'] and (
            set(note.get('entities', [])) & set(n.get('entities', [])) or
            set(note.get('core', [])) & set(n.get('core', [])) or
            note.get('topic') and note.get('topic') == n.get('topic'))]
        note['related'] = [{'id': n['id'], 'type': n['type'], 'title': n['title']} for n in linked]
    atomic_json(root / 'knowledge/pending-commit.json', {'notes': incoming})
    obsolete = [f"knowledge/{FOLDERS[n['type']]}/{n['id']}.md" for n in notes.values() if not n.get('path')]
    persist(root, list(notes.values()), obsolete)
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
    try:
        from copy import deepcopy
        from player_identity import normalize
        normalized=normalize(root,deepcopy(index['notes']))
        for old,new in zip(index['notes'],normalized):
            if old['type']=='player' and any(old.get(k)!=new.get(k) for k in ('title','player_id')):
                errors.append('Player identity migration required: '+old['id'])
    except (ValueError,TypeError,KeyError) as exc:
        errors.append('Invalid player identity: '+str(exc))
    note_ids = set()
    for n in index['notes']:
        if n['id'] in note_ids:
            errors.append('Duplicate note: ' + n['id'])
        note_ids.add(n['id'])
        target = root / n.get('path', f"knowledge/{FOLDERS[n['type']]}/{safe_id(n['id'])}.md")
        if not target.exists():
            errors.append('Missing note file: ' + str(target))
        elif n.get('path') and target.read_text(encoding='utf-8') != render_note(n, {}):
            errors.append('Markdown differs from index: ' + n['id'])
        if n['type'] == 'lineup' and n.get('path'):
            if read_json(target.with_suffix('.json')) != n:
                errors.append('Lineup archive differs from index: ' + n['id'])
            try:
                from player_branches import validate as validate_branches, documents
                validate_branches(n)
                for path, expected in documents(n).items():
                    if not (root/path).exists() or (root/path).read_text('utf-8') != expected:
                        errors.append('Player Markdown differs: ' + path)
                from workspace import validate_meta
                validate_meta(root, n.get('meta', {}))
                from tactics import validate as validate_tactics
                validate_tactics(n.get('meta', {}), lambda value: None, n.get('claims', []))
            except (ValueError, KeyError, TypeError) as exc:
                errors.append('Invalid meta: ' + str(exc))
        for eid in n.get('entities', []) + n.get('core', []):
            if eid not in seen:
                errors.append('Unknown entity: ' + eid)
        for claim in n.get('claims', []):
            if claim.get('kind') not in KNOWLEDGE_KINDS:
                errors.append('Unclassified or match-specific claim: ' + n['id'])
            for evidence in claim.get('evidence', []):
                if evidence.get('type') == 'document':
                    from document_sources import validate_evidence
                    try:validate_evidence(root,evidence)
                    except (ValueError,OSError,KeyError,TypeError) as exc:errors.append(str(exc))
                    continue
                folder = source_dir(root, evidence['source'])
                from reference_store import transcript_artifacts
                if not transcript_artifacts(folder)[0].exists():
                    errors.append('Missing ASR: ' + evidence['source'])
                if not (folder / 'metadata.json').exists():
                    errors.append('Missing metadata: ' + evidence['source'])
                if evidence.get('frame') and not (folder / evidence['frame']).exists():
                    errors.append('Missing cited frame: ' + evidence['frame'])
    from reference_store import transcript_errors
    for folder in (root / 'raw/sources').glob('*'):
        if read_json(folder / 'state.json', {}).get('stage') == 'complete':
            metadata = read_json(folder / 'metadata.json', {})
            if metadata.get('id'): errors += transcript_errors(root, metadata['id'])
    cards = read_json(root / 'knowledge/cards/index.json', {}).get('cards', [])
    card_ids = set()
    for card in cards:
        if card['id'] in card_ids: errors.append('Duplicate reference card: ' + card['id'])
        card_ids.add(card['id'])
        from reference_store import render_card
        path = (root / card['path']).resolve()
        if not path.is_relative_to((root / 'knowledge/cards').resolve()) or not path.exists():
            errors.append('Missing card reference: ' + card['id'])
        elif path.read_text('utf8') != render_card(card): errors.append('Card Markdown differs: ' + card['id'])
    return {'entities': counts, 'notes': len(index['notes']), 'cards': len(cards), 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('sync-entities')
    sub.add_parser('sync-card-images')
    sub.add_parser('validate')
    sub.add_parser('sync-markdown')
    sub.add_parser('migrate')
    sub.add_parser('migrate-player-identities')
    p = sub.add_parser('export-transcripts')
    p.add_argument('sources', nargs='*')
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
    elif args.command == 'sync-card-images':
        from card_images import sync_images
        result = sync_images(args.root)
    elif args.command == 'sync-markdown':
        from markdown_sync import scan
        result = scan(args.root)
    elif args.command == 'validate':
        result = validate_store(args.root)
    elif args.command == 'migrate-player-identities':
        from player_identity import migrate
        result = migrate(args.root)
    elif args.command == 'migrate':
        from workspace import migrate
        result = migrate(args.root)
        from player_identity import migrate as migrate_players
        result['player_identity']=migrate_players(args.root)
    elif args.command == 'export-transcripts':
        from reference_store import export_transcripts
        result = export_transcripts(args.root, args.sources or None)
    elif args.command == 'prepare':
        from media import prepare
        init_store(args.root)
        result = run_batch(args.urls, lambda u: prepare(args.root, u, args.model, args.cookies))
        atomic_json(args.root / 'raw/reports/last-prepare.json', {'at': now(), 'results': result})
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
        from workspace import store_lock
        with store_lock(args.root):
            result = finish(args.root, args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failed = isinstance(result, dict) and result.get('errors')
    if isinstance(result, list):
        failed = any(row.get('status') == 'failed' or any(p.get('stage') == 'failed'
                     for p in row.get('result', []) if isinstance(p, dict)) for row in result)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
