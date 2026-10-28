"""Single-writer knowledge workspace shared by the CLI and local web UI."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
import wxq

FACTIONS = [
    {'id': 'faction:dahe', 'name': '大河'}, {'id': 'faction:sanfen', 'name': '三分'},
    {'id': 'faction:zhulu', 'name': '逐鹿'}, {'id': 'faction:heluo', 'name': '河洛'},
    {'id': 'faction:riluohai', 'name': '日落海'}]


class Conflict(ValueError):
    pass


class Busy(ValueError):
    pass


@contextmanager
def store_lock(root, wait=False):
    # OS byte-range locks release on process exit, including abnormal exits.
    path = Path(root) / 'raw/knowledge/.write.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = wxq.retry_file_access(lambda: open(path, 'a+b'), crt_access=True)
    # Byte-range locks may extend past EOF. Initializing a byte before taking
    # the lock races the first writer and can leak a handle on Windows.
    handle.seek(0)
    try:
        deadline = time.monotonic() + (2 if wait else 0)
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise Busy('知识库正在保存，请稍后重试') from exc
                time.sleep(.01)
        yield
    finally:
        handle.close()


def notes(root):
    import json_store
    if json_store.enabled(root):
        return json_store.notes(root)
    return wxq.read_json(Path(root) / 'knowledge/index.json', {'notes': []})['notes']


def note_link_event(root, recovery=False):
    # Standalone copies of this skill need not have the optional web catalog.
    import sys
    frontend = Path(__file__).resolve().parents[4] / 'frontend'
    if not (frontend / 'note_links.py').is_file() or not (Path(root) / 'raw/crawler/topics.sqlite3').is_file():
        return
    if str(frontend) not in sys.path: sys.path.insert(0, str(frontend))
    from note_links import recover_links_locked, after_knowledge_save
    if recovery:
        recover_links_locked(root)
    else:
        after_knowledge_save(root)


def default_meta(note):
    return {'required_factions': [], 'players': [], 'core_heroes': list(note.get('core', [])),
            'compositions': {'early': [], 'middle': [], 'late': []},
            'ban_conditions': [], 'matchups': []}


def factions(root):
    result = {f['id']: dict(f) for f in FACTIONS}
    for note in notes(root):
        meta = note.get('meta', {})
        from tactics import faction_references
        refs = faction_references(meta)
        for ref in refs:
            if ref.startswith('pending:'):
                result[ref] = {'id': ref, 'name': ref.removeprefix('pending:') + '（待确认）'}
    return list(result.values())


def chinese_number(n):
    digits = '零一二三四五六七八九'
    if n < 10:
        return digits[n]
    if n < 100:
        return (digits[n // 10] if n >= 20 else '') + '十' + (digits[n % 10] if n % 10 else '')
    return ''.join(digits[int(c)] for c in str(n))


def filename(title):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f：]', '－', title).strip(' .')[:90]
    if not re.search(r'[\u3400-\u9fff]', stem):
        raise ValueError('笔记标题必须包含中文，才能生成中文文件名')
    return stem


def revision(note):
    data = {k: v for k, v in note.items() if k != 'revision'}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def assign_paths(root, items):
    used = set()
    for note in items:
        old = note.get('path')
        if old:
            expected = f"knowledge/{wxq.FOLDERS[note['type']]}/"
            if not old.startswith(expected) or Path(old).name != old[len(expected):] or not old.endswith('.md'):
                raise ValueError('非法笔记路径')
            if old.casefold() in used:
                raise ValueError('重复笔记路径')
            used.add(old.casefold())
    for note in items:
        if note.get('path'):
            continue
        base = f"knowledge/{wxq.FOLDERS[note['type']]}/{filename(note['title'])}"
        candidate, num = base + '.md', 2
        while candidate.casefold() in used or (Path(root) / candidate).exists():
            candidate = base + '（' + chinese_number(num) + '）.md'
            num += 1
        note['path'] = candidate
        used.add(candidate.casefold())


def prepare(root, items):
    from player_identity import normalize
    normalize(root,items)
    assign_paths(root, items)
    names = {e['id']: e['name'] for e in wxq.entities(root)}
    known_entities = set(names)
    names.update({f['id']: f['name'] for f in FACTIONS})
    names.update({n['id']: n['title'] for n in items})
    for note in items:
        wxq.safe_id(note['id'])
        note.setdefault('aliases', [])
        if note['type'] == 'lineup':
            note['meta'] = {**default_meta(note), **note.get('meta', {})}
            refs = list(note['meta']['required_factions']) + list(note['meta']['players']) + list(note['meta']['core_heroes'])
            for members in note['meta']['compositions'].values():
                for member in members:
                    refs += [member['hero'], member.get('replaces', '')]
            refs += [m['target'] for m in note['meta']['matchups']]
            from tactics import references, claim_id
            refs += references(note['meta'])
            if (note['meta'].get('late_variants') or note['meta'].get('overview')) and 'entities' not in note.get('manual_fields', []):
                note['entities'] = sorted(set(note.get('entities', [])) | {r for r in refs if r in known_entities})
            for claim in note.get('claims', []):
                claim.setdefault('id', claim_id(claim))
            if note.get('reading_layout', {}).get('entity_paragraphs'):
                refs += note.get('entities', [])
            note['entity_names'] = {r: names.get(r, r.removeprefix('pending:')) for r in refs if r}
            from player_branches import validate as validate_branches
            validate_branches(note)
            if note['meta'].get('player_branches') and not note.get('reading_layout'):
                from lineup_layout import _render_generic,_render_markdown,PROFILE_ID
                markdown=_render_markdown(note) if note['id']==PROFILE_ID else _render_generic(note)
                note['reading_layout']={'preserve_original':True,'sections':re.findall(r'^## (.+)$',markdown,re.M)}
        note.setdefault('manual_sections', [])
        note.setdefault('history', [])
        note.setdefault('conflicts', [])
    from player_branches import update_player_adaptations
    update_player_adaptations(items)
    by_id = {n['id']: n for n in items}
    for note in items:
        existing_links = {link['id'] for link in note.get('related', [])}
        for target in items:
            if note.get('explicit_relationships'):continue
            if target.get('explicit_relationships'):continue
            if target['type']=='player' and target['id'] not in existing_links:continue
            if target['id'] != note['id'] and target['id'] not in existing_links and (note.get('meta', {}).get('late_variants') or target.get('meta', {}).get('late_variants')) and set(note.get('entities', [])) & set(target.get('entities', [])):
                note.setdefault('related', []).append({'id': target['id'], 'type': target['type'], 'title': target['title']})
        for link in note.get('related', []):
            if link['id'] in by_id:
                link['path'] = by_id[link['id']]['path']
                link['title'] = by_id[link['id']]['title']
        for link in note.get('guide_related',[]):
            target=by_id.get(link.get('note'))
            if target and target['type']=='player':
                link.update(title=target['title'],href='../players/'+Path(target['path']).name)
        note['revision'] = revision(note)
    return items


def make_transaction(root, items, obsolete=None, ignore_issues=(), expected_markdown=None):
    root = Path(root)
    old_paths={n['id']:n.get('path') for n in notes(root) if n['type']=='player'}
    prepare(root, items)
    obsolete=list(dict.fromkeys([*(obsolete or []),*(old_paths[n['id']] for n in items if n['type']=='player' and old_paths.get(n['id']) and old_paths[n['id']]!=n['path'])]))
    from markdown_sync import outputs
    from player_branches import enabled,document_path
    from markdown_sync import status
    before_sync=status(root)
    occupied={n['path'].casefold() for n in items}
    for note in items:
        if not enabled(note):continue
        for branch in note['meta']['player_branches']:
            path=document_path(note,branch).casefold()
            if path in occupied:raise Conflict('棋手文件名与其他笔记冲突，请使用其他标题')
            occupied.add(path)
    files, sync_state, blocked = outputs(root, items, ignore_issues)
    retired=[p for p,base in before_sync['files'].items() if p not in files and base['note'] not in blocked]
    for path in files:
        if path not in before_sync['files'] and (root/path).exists():
            raise Conflict('改名后的棋手文件已存在，请使用其他笔记标题')
    obsolete=list(dict.fromkeys([*obsolete,*retired]))
    expected={p:before_sync['files'].get(p,{}).get('hash') for p in files}
    expected.update({p:before_sync['files'][p]['hash'] for p in retired})
    expected.update(expected_markdown or {})
    return {'index': {'schema_version': 5 if any(enabled(n) for n in items) else 4, 'notes': items},
            'obsolete': obsolete or [], 'branch_files': files, 'sync_state': sync_state, 'blocked_notes': sorted(blocked),
            'expected_markdown':expected,'before_sync_state':before_sync}


def persist(root, items, obsolete=None, _sync=True, _ignore_issues=(), _expected_markdown=None, _replay_updates=None):
    import json_store
    if json_store.enabled(root):
        return json_store.persist_views(root, items)
    root = Path(root)
    if _sync:
        from markdown_sync import assert_clean
        assert_clean(root)
    transaction = make_transaction(root, items, obsolete, _ignore_issues, _expected_markdown)
    if _replay_updates:transaction['replay_updates']=deepcopy(_replay_updates)
    wxq.atomic_json(root / 'knowledge/pending-save.json', transaction)
    apply_transaction(root, transaction)


def apply_transaction(root, transaction):
    root = Path(root)
    for path in transaction.get('replay_updates',{}):
        target=(root/path).resolve()
        if not target.is_relative_to((root/'knowledge/replays').resolve()) or target.suffix!='.json':
            raise ValueError('非法重放路径')
    items = transaction['index']['notes']
    from markdown_sync import digest
    skip_files=set()
    preserved_obsolete=set()
    for path in transaction.get('obsolete',[]):
        base=transaction.get('before_sync_state',{}).get('files',{}).get(path)
        if not base or not (root/path).exists():continue
        external=(root/path).read_text('utf-8-sig')
        if digest(external)==transaction.get('expected_markdown',{}).get(path):continue
        preserved_obsolete.add(path)
        state=transaction['sync_state'];state['files'][path]=base
        issue={'note':base['note'],'path':path,'kind':'conflict','message':'改名期间旧Markdown被外部修改，已保留文件，请合并或恢复已保存内容',
               'base':base['document'],'saved':base['document'],'external':external}
        issue['id']=digest(str(issue))[:20]
        if not any(i.get('id')==issue['id'] for i in state['issues']):state['issues'].append(issue)
    for path,text in transaction.get('branch_files',{}).items():
        actual=digest((root/path).read_text('utf-8-sig')) if (root/path).exists() else None
        if path in transaction.get('expected_markdown',{}) and actual not in (transaction['expected_markdown'][path],digest(text)):
            state=transaction['sync_state'];base=state['files'][path];nid=base['note']
            skip_files.update(p for p,b in state['files'].items() if b['note']==nid)
            issue={'note':nid,'path':path,'kind':'conflict','message':'保存事务期间Markdown被外部修改，已保留文件','base':transaction.get('before_sync_state',{}).get('files',{}).get(path,{}).get('document',''),'saved':text,'external':(root/path).read_text('utf-8-sig') if actual else None}
            issue['id']=digest(str(issue))[:20];state['issues'].append(issue)
    for path in skip_files:
        prior=transaction.get('before_sync_state',{}).get('files',{}).get(path)
        if prior:transaction['sync_state']['files'][path]=prior
    # Validate paths before replaying a recovery record.
    assign_paths(root, items)
    for note in items:
        if note['id'] in transaction.get('blocked_notes', []):continue
        wxq.atomic_text(root / note['path'], wxq.render_note(note, {}))
        if note['type'] == 'lineup':
            wxq.atomic_json((root / note['path']).with_suffix('.json'), note)
    for path, text in transaction.get('branch_files', {}).items():
        if path in skip_files:continue
        target = (root / path).resolve()
        if not target.is_relative_to((root / 'knowledge/lineups').resolve()) or target.suffix != '.md':
            raise ValueError('非法棋手笔记路径')
        wxq.atomic_text(target, text)
    wxq.atomic_json(root / 'knowledge/index.json', transaction['index'])
    if transaction['index'].get('schema_version')==5:
        from player_branches import enabled
        wxq.atomic_json(root/'knowledge/replays/schema5-player-branches.json',{'schema_version':5,'notes':[n for n in items if enabled(n) or n.get('lineup_adaptations')]})
    if 'sync_state' in transaction:
        wxq.atomic_json(root / 'knowledge/markdown-sync.json', transaction['sync_state'])
    active = {n['path'] for n in items}
    for path in transaction.get('obsolete', []):
        if path in preserved_obsolete:continue
        target = (root / path).resolve()
        if not target.is_relative_to((root / 'knowledge').resolve()):
            raise ValueError('非法迁移路径')
        if path not in active and target.exists():
            # Keep the complete original for recovery before removing the old filename.
            wxq.retry_file_access(lambda: wxq.backup_file(target), crt_access=True)
            target.unlink()
    for path,data in transaction.get('replay_updates',{}).items():wxq.atomic_json(root/path,data)
    (root / 'knowledge/pending-save.json').unlink(missing_ok=True)
    note_link_event(root)


def recover(root):
    from official_sync import recover as recover_official
    recover_official(root)
    import json_store
    if json_store.enabled(root):
        json_store.recover(root)
        from reference_store import recover_cards, recover_transcript_edits
        recover_transcript_edits(root)
        recover_cards(root)
        return
    from reference_store import recover_cards, recover_transcript_edits
    recover_transcript_edits(root)
    recover_cards(root)
    transaction = wxq.read_json(Path(root) / 'knowledge/pending-save.json')
    if transaction:
        apply_transaction(root, transaction)
    if (Path(root) / 'knowledge/pending-note-link.json').is_file():
        note_link_event(root, recovery=True)


def migrate(root):
    import json_store
    if json_store.enabled(root):
        json_store.recover(root)
        return {'notes': len(json_store.notes(root)), 'schema_version': 6}
    with store_lock(root):
        recover(root)
        pending = wxq.read_json(Path(root) / 'knowledge/pending-commit.json')
        if pending:
            wxq._commit_notes(root, pending['notes'])
        items = deepcopy(notes(root))
        obsolete = []
        for note in items:
            if note.get('path'):
                continue
            legacy = f"knowledge/{wxq.FOLDERS[note['type']]}/{note['id']}.md"
            target = Path(root) / legacy
            if target.exists():
                original = target.read_text(encoding='utf-8')
                if original != wxq.render_note(note, {}):
                    original_claims = deepcopy(note.get('claims', []))
                    # Preserve unmanaged prose exactly in the authoritative record.
                    sections = re.split(r'^## (.+)\s*$', original, flags=re.M)
                    for i in range(1, len(sections), 2):
                        section, text = sections[i].strip(), sections[i + 1].strip()
                        if section in ['关联知识', '阵容信息']:
                            continue
                        existing = [c for c in note['claims'] if c['section'] == section]
                        expected = '\n\n'.join('- ' + c['text'] for c in existing)
                        if text == expected or not existing and text == '暂无已确认的通用策略':
                            continue
                        note['claims'] = [c for c in note['claims'] if c['section'] != section]
                        if text and text != '暂无已确认的通用策略':
                            note['claims'].append(manual_claim(section, text))
                        note.setdefault('manual_sections', []).append(section)
                    if len(sections) == 1:
                        note['claims'] = [manual_claim('知识内容', original)]
                        note['manual_sections'] = ['知识内容']
                    note.setdefault('history', []).append({'at': wxq.now(), 'origin': 'migration', 'markdown': original,
                                                          'previous': {'claims': original_claims}})
                obsolete.append(legacy)
        persist(root, items, obsolete)
        return {'notes': len(items), 'migrated': len(obsolete)}


def manual_claim(section, text):
    return {'section': section, 'text': text, 'kind': 'general_strategy', 'origin': 'manual',
            'condition': '', 'inference': False, 'version': None, 'evidence': []}


def create_note(root, payload):
    import json_store
    if json_store.enabled(root):
        return json_store.create(root, payload)
    """Create an empty, retry-safe knowledge note through the shared transaction."""
    if not isinstance(payload,dict) or set(payload)-{'type','title','aliases','request_id','player_id'}:
        raise ValueError('新建笔记字段无效')
    kind=payload.get('type');title=payload.get('title');aliases=payload.get('aliases',[]);request=payload.get('request_id')
    if kind not in wxq.FOLDERS:raise ValueError('请选择有效的笔记类型')
    if not isinstance(title,str) or not title.strip():raise ValueError('请填写笔记名称')
    title=title.strip();filename(title)
    if not isinstance(aliases,list) or not all(isinstance(a,str) for a in aliases):raise ValueError('别名须为文字列表')
    aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip()))
    if not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',request):raise ValueError('新建请求标识无效')
    normalized={'type':kind,'title':title,'aliases':aliases}
    if kind=='player':
        from player_identity import bind,catalog
        if not payload.get('player_id'):raise ValueError('请选择棋手')
        normalized['player_id']=payload['player_id']
        bind(normalized,catalog(root))
        title=normalized['title'];aliases=normalized['aliases']
    elif payload.get('player_id'):raise ValueError('只有棋手笔记可绑定棋手身份')
    fingerprint=hashlib.sha256(json.dumps(normalized,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    root=Path(root)
    with store_lock(root,wait=True):
        recover(root)
        items=deepcopy(notes(root))
        prior=next((n for n in items if n.get('creation',{}).get('request_id')==request),None)
        if prior:
            if prior['creation']['payload_hash']!=fingerprint:raise Conflict('请求标识已用于其他新建内容，草稿已保留')
            return prior
        if kind=='player':
            from player_identity import bind,catalog
            players=catalog(root)
            for existing in items:
                if existing['type']=='player' and bind(deepcopy(existing),players)==normalized['player_id']:
                    raise Conflict('该棋手已有笔记，请打开已有笔记：'+existing['title'])
        if any(n['type']==kind and n['title'].strip().casefold()==title.casefold() for n in items):
            raise Conflict('已有同类型同名笔记，请打开已有笔记或修改名称；草稿已保留')
        from markdown_sync import scan
        scan(root,_locked=True)
        # Reconcile external edits before adding a record, rather than persisting
        # an index captured before scan imported them.
        items=deepcopy(notes(root))
        nid='note-'+hashlib.sha256(request.encode()).hexdigest()[:24]
        if any(n['id']==nid for n in items):raise Conflict('笔记标识已存在，请重新发起新建')
        note={'id':nid,**normalized,'entities':[normalized['player_id']] if kind=='player' else [],'core':[],'claims':[],'related':[],
              'creation':{'request_id':request,'payload_hash':fingerprint}}
        items.append(note);persist(root,items)
        return note


def merge_note(previous, incoming):
    from player_branches import enabled
    if enabled(previous):
        protected_ids=set()
        for scope,sections in previous.get('manual_scopes',{}).items():
            owner=previous['meta'] if scope=='common' else next(b for b in previous['meta']['player_branches'] if b['id']==scope)
            ids=owner.get('common_claim_refs',owner.get('claim_refs',[]))
            protected_ids.update(c['id'] for c in previous['claims'] if c['id'] in ids and c['section'] in sections)
        old={c['id']:c for c in previous['claims']}
        protected_meta=False
        for scope,sections in previous.get('manual_scopes',{}).items():
            prior=previous['meta'] if scope=='common' else next(b for b in previous['meta']['player_branches'] if b['id']==scope)
            supplied=incoming.get('meta',{}) if scope=='common' else next((b for b in incoming.get('meta',{}).get('player_branches',[]) if b['id']==scope),{})
            fields=set()
            if '采用与转向信号' in sections:fields.add('selection')
            if '打法评价' in sections:fields.add('assessment')
            if '成员配置' in sections:fields.update(('compositions','required_factions','core_heroes','ban_conditions','matchups') if scope=='common' else ('overrides',))
            if any(s.startswith(('运营路线：','后期组合：')) for s in sections):
                if incoming.get('meta',{}).get('operation_routes')!=previous['meta'].get('operation_routes') or incoming.get('meta',{}).get('late_variants')!=previous['meta'].get('late_variants'):protected_meta=True
            if any(prior.get(f)!=supplied.get(f) for f in fields):protected_meta=True
        if not enabled(incoming) or protected_meta or not protected_ids<={c.get('id') for c in incoming.get('claims',[])} or any(c.get('id') in protected_ids and c!=old[c['id']] for c in incoming.get('claims',[])):
            result=deepcopy(previous)
            conflict={'kind':'player_scope','incoming':deepcopy(incoming)}
            if conflict not in result.setdefault('conflicts',[]):result['conflicts'].append(conflict)
            return result
    result = {**deepcopy(previous), **deepcopy(incoming)}
    if isinstance(incoming.get('meta'),dict) and 'major_variants' not in incoming['meta'] and 'major_variants' in previous.get('meta',{}):
        result['meta']['major_variants']=deepcopy(previous['meta']['major_variants'])
    for key in ['path', 'history', 'manual_sections', 'manual_scopes', 'manual_meta', 'manual_fields', 'conflicts']:
        if key in previous:
            result[key] = deepcopy(previous[key])
    for key in previous.get('manual_fields', []):
        result[key] = deepcopy(previous[key])
    protected = set(previous.get('manual_sections', []))
    accepted = []
    for claim in incoming.get('claims', []):
        if claim['section'] in protected:
            existing = [c for c in previous.get('claims', []) if c['section'] == claim['section']]
            if not any(c['text'] == claim['text'] for c in existing):
                conflict = {'kind': 'section', 'section': claim['section'], 'incoming': claim}
                if conflict not in result.setdefault('conflicts', []):
                    result['conflicts'].append(conflict)
        else:
            accepted.append(claim)
    # An explicit stable ID identifies a corrected conclusion. Its old evidence
    # describes the old wording; retain it only for a semantic duplicate.
    fields = ('section', 'text', 'version', 'condition', 'inference', 'kind')
    revised = {c['id']: c for c in accepted if c.get('id')}
    prior_by_id = {c.get('id'): c for c in previous.get('claims', []) if c.get('id')}
    corrections = []
    for cid, claim in revised.items():
        old = prior_by_id.get(cid)
        if not old or old['section'] in protected or all(old.get(k) == claim.get(k) for k in fields):
            continue
        if any(old.get(k) != claim.get(k) for k in fields if k != 'text') or not (
                {e['source'] for e in old.get('evidence', [])} & {e['source'] for e in claim.get('evidence', [])}):
            raise ValueError('新版本、条件或新来源策略需要独立结论 ID，不能覆盖旧结论')
        corrections.append(old)
    if corrections:
        result.setdefault('history', []).append({'at': wxq.now(), 'origin': 'import_correction',
                                                'previous': {'claims': deepcopy(corrections)}})
    old_claims = [c for c in previous.get('claims', [])
                  if c['section'] in protected or c.get('id') not in revised
                  or all(c.get(k) == revised[c['id']].get(k) for k in fields)]
    result['claims'] = wxq.merge_claims(old_claims, accepted)
    if previous.get('manual_meta'):
        result['meta'] = deepcopy(previous['meta'])
        if 'meta' in incoming and incoming['meta'] != previous['meta']:
            conflict = {'kind': 'meta', 'incoming': incoming['meta']}
            if conflict not in result.setdefault('conflicts', []):
                result['conflicts'].append(conflict)
    if not previous.get('manual_meta'):
        from tactics import claim_id, remap_claims
        fields = ('section', 'text', 'version', 'condition', 'inference', 'kind')
        retained = {tuple(c.get(k) for k in fields): claim_id(c) for c in result['claims']}
        for claim in accepted:
            target = retained[tuple(claim.get(k) for k in fields)]
            if claim_id(claim) != target:
                remap_claims(result.get('meta', {}), {claim_id(claim)}, target)
    return result


def validate_meta(root, meta):
    if not isinstance(meta, dict):
        raise ValueError('阵容信息必须为对象')
    expected = {'required_factions', 'players', 'core_heroes', 'compositions', 'ban_conditions', 'matchups'}
    if not expected.issubset(meta) or set(meta) - expected - {'operation_routes', 'late_variants', 'overview', 'major_variants','common_claim_refs','player_branches','assessment'} or not isinstance(meta['compositions'], dict) or set(meta['compositions']) != {'early', 'middle', 'late'}:
        raise ValueError('阵容信息缺失必需字段或阶段')
    if not isinstance(meta['ban_conditions'], list) or not isinstance(meta['matchups'], list):
        raise ValueError('适用条件和针对策略须为列表')
    known = {e['id'] for e in wxq.entities(root)}
    def reference(value):
        if not isinstance(value, str) or not value or len(value) > 160:
            raise ValueError('实体引用无效')
        if value not in known and not value.startswith('pending:') and value not in {f['id'] for f in FACTIONS}:
            raise ValueError('未知实体，请选择已有实体或以 pending: 标记待确认名称')
    from tactics import validate as validate_tactics
    from overview import validate as validate_overview
    validate_overview(meta, wxq.entities(root))
    validate_tactics(meta, reference)
    for b in meta.get('player_branches',[]):
        local={k:deepcopy(meta[k]) for k in expected};local['players']=[b['player']]
        if 'late_variants' in meta:local['late_variants']=[deepcopy(v) for v in meta['late_variants'] if v['id'] in b.get('late_variant_ids',[])]
        for key,value in b.get('overrides',{}).items():
            if key=='compositions':local[key].update(deepcopy(value))
            else:local[key]=deepcopy(value)
        validate_meta(root,local)
    for field in ['required_factions', 'players', 'core_heroes']:
        if not isinstance(meta.get(field, []), list):
            raise ValueError('实体选择应为列表')
        for value in meta.get(field, []):
            reference(value)
    for stage, members in meta.get('compositions', {}).items():
        if stage not in ['early', 'middle', 'late'] or not isinstance(members, list):
            raise ValueError('阶段组成无效')
        for member in members:
            if not isinstance(member, dict) or not member.get('hero'):
                raise ValueError('请选择阶段英雄，或移除空成员')
            reference(member['hero'])
            if member.get('necessity') not in ['required', 'optional']:
                raise ValueError('成员须标记必需或可选')
            if member.get('replaces'):
                reference(member['replaces'])
    for condition in meta.get('ban_conditions', []):
        if not isinstance(condition, dict) or not condition.get('faction'):
            raise ValueError('禁用条件缺少阵营')
        reference(condition['faction'])
        if condition.get('status') not in ['playable', 'unplayable', 'unknown']:
            raise ValueError('禁用适用状态无效')
    note_ids = set()
    if meta.get('matchups'):
        import json_store
        if json_store.enabled(root):
            pending = json_store.read(Path(root) / json_store.JOURNAL)
            index = pending['index'] if pending else json_store.read(Path(root) / json_store.INDEX, {'notes':[]})
            note_ids = {n['id'] for n in index['notes']}
        else:
            note_ids = {n['id'] for n in notes(root)}
    for matchup in meta.get('matchups', []):
        if not isinstance(matchup, dict):
            raise ValueError('针对策略无效')
        target = matchup.get('target', '')
        if target not in note_ids:
            reference(target)
        if not isinstance(matchup.get('text'), str) or not matchup['text'].strip():
            raise ValueError('针对策略需要正文')


def edit_locked(root, nid, payload, recover_first=True):
    return edit(root, nid, payload, _locked=True, _recover_first=recover_first)


def edit(root, nid, payload, _locked=False, _recover_first=True, _dry_run=False):
    import json_store
    if json_store.enabled(root):
        return json_store.edit(root, nid, payload, public=True)
    with nullcontext() if _locked else store_lock(root):
        if _recover_first: recover(root)
        from markdown_sync import scan
        scan(root, _locked=True)
        items = deepcopy(notes(root))
        note = next((n for n in items if n['id'] == nid), None)
        if note is None:
            raise KeyError('笔记不存在')
        if payload.get('revision') != note.get('revision'):
            raise Conflict('笔记已被其他操作更新，请重新载入后合并你的草稿')
        before = deepcopy(note)
        if 'title' in payload:
            title=payload['title']
            if not isinstance(title,str) or not title.strip():raise ValueError('请填写笔记标题')
            title=title.strip();filename(title)
            if any(n['id']!=nid and n['type']==note['type'] and n['title'].strip().casefold()==title.casefold() for n in items):
                raise ValueError('同类型笔记标题已存在，请使用其他标题')
            payload={**payload,'title':title}
        if note['type']=='player':
            from player_identity import bind,catalog
            bind(note,catalog(root))
            if payload.get('player_id',note['player_id'])!=note['player_id']:
                raise ValueError('棋手笔记不能改绑其他棋手')
            if payload.get('title',note['title'])!=note['title']:
                raise ValueError('棋手笔记只能以棋手名命名')
        sections = payload.get('sections', {})
        if not isinstance(sections, dict):
            raise ValueError('章节格式无效')
        from player_branches import enabled, apply_sections, validate as validate_branches
        if enabled(note):
            note['entity_names'].update({e['id']:e['name'] for e in wxq.entities(root)})
            updates=payload.get('scopes',[{'scope':payload.get('scope','common'),'sections':sections}])
            if not isinstance(updates,list) or (not updates and 'title' not in payload):raise ValueError('缺少编辑范围')
            for update in updates:
                if not isinstance(update,dict) or not isinstance(update.get('sections'),dict):raise ValueError('编辑范围格式无效')
                apply_sections(note,update['scope'],update['sections'])
            note['entity_names']=deepcopy(before.get('entity_names',{}))
            if 'meta' in payload and payload['meta'] != note['meta']:
                validate_meta(root,payload['meta']);note['meta'] = deepcopy(payload['meta']);note['manual_meta'] = True
            validate_branches(note)
            validate_meta(root,note['meta'])
            from tactics import validate as validate_tactics
            validate_tactics(note['meta'],lambda value:None,note['claims'])
            if 'title' in payload and payload['title']!=note['title']:
                note['title']=payload['title']
                note['manual_fields']=sorted(set(note.get('manual_fields',[])+['title']))
            if 'aliases' in payload:
                if not isinstance(payload['aliases'],list) or not all(isinstance(v,str) for v in payload['aliases']):raise ValueError('别名格式无效')
                note['aliases'] = payload['aliases']
            if note != before:
                note.setdefault('history',[]).append({'at':wxq.now(),'origin':'manual','previous':{k:before.get(k) for k in ['title','aliases','claims','meta','revision']}})
                if not _dry_run:persist(root,items)
                else:prepare(root,items)
            return note
        canonical=lambda section:wxq.PLAYER_SECTION_ALIASES.get(section,section) if note['type']=='player' else section
        normalized={}
        for section,text in sections.items():
            if not isinstance(section,str):raise ValueError('章节名称无效')
            key=canonical(section)
            if key in normalized and normalized[key]!=text:raise ValueError('新旧章节名的内容冲突，请刷新后合并；草稿已保留')
            normalized[key]=text
        for section, text in normalized.items():
            if not isinstance(text, str) or not isinstance(section, str) or not section.strip() or section == '关联知识':
                raise ValueError('章节名称或正文无效')
            current = '\n\n'.join(c['text'] for c in note['claims'] if canonical(c['section']) == section)
            if current == text.strip():
                continue
            from tactics import claim_id, remap_claims
            old_ids = {claim_id(c) for c in note['claims'] if canonical(c['section']) == section}
            note['claims'] = [c for c in note['claims'] if canonical(c['section']) != section]
            new_claim = manual_claim(section, text.strip()) if text.strip() else None
            if new_claim:
                new_claim['id'] = claim_id(new_claim)
                note['claims'].append(new_claim)
            if note.get('meta'):
                prior_meta = deepcopy(note['meta'])
                remap_claims(note['meta'], old_ids, new_claim['id'] if new_claim else None)
                if note['meta'] != prior_meta:
                    note['manual_meta'] = True
            note['manual_sections'] = sorted(set(note.get('manual_sections', []) + [section]))
        if note['type'] == 'lineup' and 'meta' in payload and payload['meta'] != note['meta']:
            validate_meta(root, payload['meta'])
            note['meta'] = deepcopy(payload['meta'])
            from tactics import claim_id, remap_claims
            for section, text in sections.items():
                old_claims = [c for c in before['claims'] if c['section'] == section]
                if '\n\n'.join(c['text'] for c in old_claims) != text.strip():
                    new_claim = next((c for c in note['claims'] if c['section'] == section), None)
                    remap_claims(note['meta'], {claim_id(c) for c in old_claims}, claim_id(new_claim) if new_claim else None)
            note['manual_meta'] = True
        if note.get('meta'):
            from tactics import validate as validate_tactics
            validate_tactics(note['meta'], lambda value: None, note['claims'])
        for key in ['title', 'aliases']:
            if key in payload:
                if key == 'title':
                    filename(payload[key])
                elif not isinstance(payload[key], list) or not all(isinstance(v, str) for v in payload[key]):
                    raise ValueError('别名格式无效')
                note[key] = payload[key]
                if before.get(key) != payload[key]:
                    note['manual_fields'] = sorted(set(note.get('manual_fields', []) + [key]))
        if before == note:
            return note
        note['history'].append({'at': wxq.now(), 'origin': 'manual', 'previous': {
            k: before.get(k) for k in ['title', 'aliases', 'claims', 'meta', 'revision']}})
        if _dry_run:
            prepare(root, items)
            return note
        persist(root, items)
        return note


def availability(note, banned):
    if not banned:
        return 'playable'
    meta = note.get('meta', {})
    if meta.get('late_variants'):
        from tactics import availability as flexible_availability
        return flexible_availability(meta, banned)
    if set(banned) & set(meta.get('required_factions', [])):
        return 'unplayable'
    states = {c['faction']: c['status'] for c in meta.get('ban_conditions', [])}
    selected = [states.get(f, 'unknown') for f in banned]
    return 'unplayable' if 'unplayable' in selected else 'unknown' if 'unknown' in selected else 'playable'


def canonical_url(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in ['http', 'https'] or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('请输入有效的 HTTP 或 HTTPS 内容链接')
    match = re.search(r'/video/(BV[\w]+)', parsed.path)
    if parsed.hostname in ['www.bilibili.com', 'bilibili.com', 'm.bilibili.com'] and match:
        part = parse_qs(parsed.query).get('p', ['1'])[0]
        if not part.isdigit() or int(part) < 1:
            raise ValueError('分 P 编号无效')
        return f'https://www.bilibili.com/video/{match[1]}?p={int(part)}', f'{match[1]}:p{int(part)}'
    params = {k: v for k, v in parse_qs(parsed.query).items() if not k.startswith('utm_') and k not in ['spm_id_from', 'vd_source']}
    normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or '/', urlencode(sorted(params.items()), doseq=True), ''))
    return normalized, 'link-' + hashlib.sha256(normalized.encode()).hexdigest()[:20]


def register_source(root, payload, sid=None, preserve_annotations=False, wait=False, cancelled=None, _metadata=None):
    url, canonical_id = canonical_url(payload.get('url', ''))
    with store_lock(root, wait=wait):
        path = Path(root) / 'knowledge/source-registry.json'
        rows = wxq.read_json(path, [])
        original_rows = deepcopy(rows)
        if _metadata is not None:
            if _metadata and canonical_url(_metadata.get('url',''))[0]!=url:raise ValueError('元数据与来源链接不一致')
            imported=_metadata or None
        else:imported = next((r for r in sources(root) if canonical_url(r['url'])[0] == url), None)
        if imported:
            canonical_id = imported['id']
        if sid:
            row = next((r for r in rows if r['id'] == sid), None)
            if row is None:
                # Existing imported sources can receive a registry annotation.
                original = next((r for r in sources(root) if r['id'] == sid), None)
                if original is None:
                    raise KeyError('来源不存在')
                row = {k: original.get(k, '') for k in ['id', 'url', 'title', 'notes']}
                rows.append(row)
            if canonical_url(row['url'])[0] != url:
                raise ValueError('编辑时不能改变来源链接身份；请另行添加')
        else:
            row = next((r for r in rows if r['id'] == canonical_id), None)
            if row is None:
                row = {'id': canonical_id, 'created_at': wxq.now()}
                rows.append(row)
        for key in ['title', 'notes']:
            if not isinstance(payload.get(key, ''), str):
                raise ValueError('标题和备注须为文字')
        title=payload.get('title','')
        if preserve_annotations:
            bvid=canonical_id.split(':p')[0]
            missing=lambda t:not t or (isinstance(t,str) and t.strip() in (bvid,bvid+':p1'))
            previous=row.get('title','')
            if row.get('title_origin')=='manual' or 'title' in row.get('manual_values',{}) or not missing(previous):title=previous
            else:
                title=next((t for t in [(imported or {}).get('title'),title] if not missing(t)),'')
                if title:row['title_origin']='metadata'
        else:row['title_origin']='manual' if title else 'unset'
        row.update({'url': url,
                    'title': title,
                    'notes': (row.get('notes') or (imported or {}).get('notes') or payload.get('notes', '')) if preserve_annotations else payload.get('notes', '')})
        if rows == original_rows:
            if cancelled and cancelled():
                raise InterruptedError('保存已取消')
            return row
        row['updated_at'] = wxq.now()
        wxq.atomic_json(path, rows, cancelled=cancelled)
        return row


def sources(root, source_ids=None):
    root = Path(root)
    selected = set(source_ids) if source_ids is not None else None
    if selected == set():
        return []
    if selected is not None and any(sid.startswith('link-') for sid in selected):
        # Generic URL IDs may have been replaced by an imported platform ID.
        return [row for row in sources(root) if row['id'] in selected]
    rows = {r['id']: dict(r) for r in wxq.read_json(root / 'knowledge/source-registry.json', [])}
    selected_folders = {sid.replace(':', '_') for sid in selected} if selected is not None else None
    linked = {}
    references = {}
    for note in notes(root):
        for claim in note.get('claims', []):
            for evidence in claim.get('evidence', []):
                linked.setdefault(evidence['source'], {})[note['id']] = {'id': note['id'], 'title': note['title']}
                references.setdefault(evidence['source'], []).append(evidence)
        for history in note.get('history', []):
            for claim in history.get('previous', {}).get('claims', []):
                for evidence in claim.get('evidence', []):
                    linked.setdefault(evidence['source'], {})[note['id']] = {'id': note['id'], 'title': note['title']}
                    references.setdefault(evidence['source'], []).append(evidence)
    for path in (root / 'raw/sources').glob('*/metadata.json'):
        if selected_folders is not None and path.parent.name not in selected_folders:
            continue
        metadata = wxq.read_json(path)
        sid = metadata['id']
        url, registry_id = canonical_url(metadata['url'])
        annotation = rows.pop(registry_id, {}) if registry_id != sid else rows.get(sid, {})
        row = {**metadata, **annotation, **rows.get(sid, {}), 'id': sid, 'url': url}
        state = wxq.read_json(path.parent / 'state.json', {})
        review = wxq.read_json(path.parent / 'review.json', {})
        row['stage'] = state.get('stage', 'registered')
        row['error'] = state.get('error', '')
        row['processing_warning'] = '；'.join(state.get('warnings', []))
        referenced = references.get(sid, [])
        intervals = review.get('checked_intervals', [])
        row['reviewed'] = review.get('approved') is True and bool(intervals) and all(
            any(a <= e['start'] and b >= e['end'] for a, b in intervals) for e in referenced)
        rows[sid] = row
    # Acquisition failures that happened before metadata existed remain visible.
    for result in wxq.read_json(root / 'raw/reports/last-prepare.json', {}).get('results', []):
        if result.get('status') != 'failed' or not result.get('url'):
            continue
        try:
            url, sid = canonical_url(result['url'])
        except ValueError:
            continue
        if selected is not None and sid not in selected:
            continue
        if sid not in rows or rows[sid].get('stage', 'registered') == 'registered':
            rows[sid] = {**rows.get(sid, {}), 'id': sid, 'url': url, 'stage': 'failed', 'error': result.get('error', '')}
    if selected is not None:
        rows = {sid: row for sid, row in rows.items() if sid in selected}
    for sid, row in rows.items():
        row.setdefault('stage', 'registered')
        row['linked_notes'] = list(linked.get(sid, {}).values())
        row['knowledge_status'] = 'deposited' if row['linked_notes'] and row['stage'] == 'complete' and row.get('reviewed') else 'submitted' if row['linked_notes'] else 'unprocessed'
    return sorted(rows.values(), key=lambda r: r.get('updated_at', r.get('collected_at', '')), reverse=True)
