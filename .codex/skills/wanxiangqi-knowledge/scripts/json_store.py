"""Canonical JSON knowledge pairs, lightweight index and recoverable transactions.

Legacy dictionaries returned by notes() are transient projections for existing
source tracking and filters, never an additional persisted source of text.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import uuid
from functools import lru_cache
import json_document as document

INDEX = 'knowledge/index.meta.json'
JOURNAL = 'raw/knowledge/pending-json-save.json'


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text('utf-8-sig')) if path.exists() else default


@lru_cache(maxsize=128)
def _cached_read(path, modified, size):
    return read(path)


def cached_read(path):
    path = Path(path)
    stat = path.stat()
    return _cached_read(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def snapshot(record):
    return {'body':deepcopy(record['body']),
            'metadata':deepcopy({k:v for k,v in record['metadata'].items() if k not in ('history','conflicts')})}


def editable_record(record):
    """History entries are append-only; copy the list, not every old snapshot."""
    meta = deepcopy({k:v for k,v in record['metadata'].items() if k!='history'})
    if 'history' in record['metadata']:
        meta['history'] = list(record['metadata']['history'])
    return {'body':deepcopy(record['body']), 'metadata':meta}


def manual_nodes(record):
    meta = record['metadata']
    ids = {nid for nid, info in meta.get('node_annotations', {}).items() if info.get('origin') == 'manual'}
    ids.update(c['text_ref'] for c in meta.get('claim_annotations', []) if c.get('origin') == 'manual')
    values = {n['id']:n.get('value','') for n in [*record['body']['nodes'],*record['body'].get('supporting_nodes',[])]}
    manual_texts = [values.get(c['text_ref'],'').strip() for c in meta.get('claim_annotations',[]) if c.get('origin')=='manual']
    section = None
    for node in record['body']['nodes']:
        if node['type'] == 'heading' and node['level'] == 2:
            section = node['title']
        if section in meta.get('manual_sections', []):
            ids.add(node['id'])
        if node['type']=='entry' and any(text and (text in document.render_node(node) or node['value'].strip() in text) for text in manual_texts):
            ids.add(node['id'])
    return ids


def enabled(root):
    return (Path(root) / INDEX).is_file()


def initialize(root):
    """Initialize an empty directory only. Never migrate or remove material."""
    import wxq
    from workspace import store_lock
    root = Path(root)
    with store_lock(root,wait=True):
        if enabled(root):return
        if any(p.is_file() for p in (root/'knowledge').rglob('*')):
            raise ValueError('知识目录已有材料，请显式迁移；初始化不会转换或清理文件')
        for folder in ('raw/sources','raw/reports','entities/raw','knowledge/lineups','knowledge/players','knowledge/other'):
            (root/folder).mkdir(parents=True,exist_ok=True)
        for category in wxq.CATEGORIES:
            path=root/'entities'/(category+'.json')
            if not path.exists():write_file(path,[])
        save(root,[])


def write_file(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (json.dumps(value, ensure_ascii=False, separators=(',', ':')) if path.name == Path(JOURNAL).name
            else json.dumps(value, ensure_ascii=False, indent=2)) + '\n'
    if path.exists() and path.read_text('utf-8') == text:
        return
    import wxq
    wxq.atomic_text(path, text)


def target(root, path, metadata=False):
    root = Path(root).resolve()
    result = (root / path).resolve()
    if not result.is_relative_to(root / 'knowledge') or result.suffix != '.json' or (not metadata and result.name.endswith('.meta.json')):
        raise ValueError('非法JSON知识路径')
    return result


def meta_path(path):
    return str(Path(path).with_suffix('.meta.json')).replace('\\', '/')


def check_record(record):
    body, meta = record['body'], record['metadata']
    document.validate(body)
    document.validate({'schema_version':6,'nodes':[*body['nodes'],*body.get('supporting_nodes',[])]})
    if meta.get('type') not in ('lineup', 'player', 'other') or not re.fullmatch(r'[a-zA-Z0-9_-]+', meta.get('id', '')):
        raise ValueError('笔记身份无效')
    if not isinstance(meta.get('title'), str) or not meta['title'].strip():
        raise ValueError('笔记标题无效')
    if meta['type']=='lineup' and (not isinstance(meta.get('aliases',[]),list)
            or any(not isinstance(value,str) for value in meta.get('aliases',[]))):
        raise ValueError('阵容别名必须是字符串列表')
    folders={'lineup':'lineups','player':'players','other':'other'}
    if Path(meta.get('path','')).parent.as_posix() != 'knowledge/'+folders[meta['type']]:
        raise ValueError('正文路径必须位于对应知识目录')
    if meta['type'] in ('player', 'lineup') and not meta.get('player_id'):
        raise ValueError('棋手及阵容笔记必须绑定棋手')
    headings = [n for n in body['nodes'] if n['type'] == 'heading' and n['level'] == 1]
    if len(headings) != 1 or headings[0]['title'] != meta['title']:
        raise ValueError('正文必须包含唯一且与笔记名称一致的一级标题')
    texts = {n['id'] for n in [*body['nodes'], *body.get('supporting_nodes', [])]}
    def check_refs(value):
        if isinstance(value, dict):
            if '$text' in value and value['$text'] not in texts:
                raise ValueError('知识引用不存在：' + str(value['$text']))
            for v in value.values():check_refs(v)
        elif isinstance(value, list):
            for v in value:check_refs(v)
    check_refs(body.get('semantics', {}))
    for c in meta.get('claim_annotations', []):
        if c.get('text_ref') not in texts:
            raise ValueError('证据关联的知识节点不存在')
    if meta['type'] == 'lineup' and body.get('semantics', {}).get('players') != [meta['player_id']]:
        raise ValueError('阵容适用棋手必须与笔记绑定一致')


def save(root, items, aliases=None, origin='save', review_refs=None, *, partial=False, prepare_only=False):
    """Caller holds store_lock. Publish changed pairs and a complete light index."""
    root = Path(root)
    previous = read(root / INDEX, {'notes': []})
    old_rows = {row['id']: row for row in previous['notes']}
    changed, before, rows = [], [], []
    ids, paths = set(), set()
    for incoming in items:
        nid = incoming['metadata']['id']
        if nid in ids:
            raise ValueError('重复笔记身份或文件名')
        ids.add(nid)
        old = _disk_record(root, old_rows[nid]) if nid in old_rows else None
        if old is not None and incoming == old:
            rows.append(old_rows[nid])
            continue
        record = editable_record(incoming)
        if record['metadata']['type']=='lineup':record['metadata'].setdefault('aliases',[])
        check_record(record)
        m = record['metadata']; target(root, m['path'])
        m['body_sha256'] = digest(record['body'])
        m['revision'] = digest({'body': record['body'], 'metadata': {k:v for k,v in m.items() if k != 'revision'}})[:20]
        rows.append({k:m.get(k) for k in ('id','type','title','path','player_id','revision')})
        changed.append(record)
        if old is not None: before.append(old)
    if partial:
        replacements = {r['id']:r for r in rows}
        rows = [replacements.pop(r['id'], r) for r in previous['notes']] + list(replacements.values())
    for row in rows:
        target(root, row['path'])
        if row['path'].casefold() in paths:
            raise ValueError('重复笔记身份或文件名')
        paths.add(row['path'].casefold())
    index = {'schema_version':6, 'notes':rows,
             'aliases':deepcopy(aliases if aliases is not None else previous.get('aliases', {}))}
    retired = [r['path'] for r in previous['notes'] if r['path'] not in {x['path'] for x in rows}]
    if not changed and not retired and index == previous:
        return []
    from note_review import version_writes
    journal = {'schema_version':6, 'origin':origin, 'delta':True, 'records':changed, 'index':index,
               'versions':version_writes(root, before, changed, origin, review_refs), 'retired':retired}
    if prepare_only:return journal
    write_file(root / JOURNAL, journal)
    recover(root)
    return changed


def automatic_journal(journal):
    if not journal:return False
    origin = journal.get('origin')
    if origin is not None:return origin in ('official', 'usage_aliases')
    # Old metadata-only saves have no provenance (including automatic aliases).
    # Preserve ambiguous pre-upgrade writes for explicit review as well.
    if journal.get('versions') == []:return True
    return any(entry.get('value', {}).get('origin') in ('official', 'usage_aliases')
               for entry in journal.get('versions', []))


def pending_save(root):
    journal = read(Path(root)/JOURNAL)
    return None if automatic_journal(journal) else journal


def recover(root, *, official=True, apply_official_notes=False):
    if official and (Path(root)/'raw/knowledge/pending-official-sync.json').exists():
        from official_sync import recover as recover_official
        recover_official(root)
    root = Path(root)
    journal = read(root / JOURNAL)
    if not journal:
        return
    if automatic_journal(journal) and not apply_official_notes:
        from official_sync import defer_notes
        defer_notes(root, journal)
        (root/JOURNAL).unlink()
        return
    for entry in journal.get('versions', []):
        write_file(root / entry['path'], entry['value'])
    for record in journal['records']:
        check_record(record)
        path = record['metadata']['path']
        write_file(target(root, path), record['body'])
        write_file(target(root, meta_path(path), True), record['metadata'])
        # Rebuildable projections never make canonical saves depend on cache availability.
        try:
            from reader_store import write_record
            write_record(root,record)
        except (OSError,ValueError,KeyError):pass
    write_file(root / INDEX, journal['index'])
    for path in journal.get('retired', []):
        for name in (path, meta_path(path)):
            p = target(root, name, True)
            if p.exists():
                import wxq
                wxq.backup_file(p)
                p.unlink()
    import wxq
    wxq.retry_file_access(lambda:(root / JOURNAL).unlink(missing_ok=True))


def _disk_record(root, row):
    try:
        body = cached_read(target(root, row['path']))
        meta = cached_read(target(root, meta_path(row['path']), True))
    except FileNotFoundError:
        body = meta = None
    if body is None or meta is None or digest(body) != meta.get('body_sha256') or meta.get('revision') != row.get('revision'):
        baseline = read(deferred_baseline_path(root, row))
        if baseline and baseline['metadata'].get('revision') == row.get('revision'):
            check_record(baseline)
            if digest(baseline['body']) == baseline['metadata'].get('body_sha256'):return baseline
        raise ValueError('正文与附件不一致：' + row['path'])
    return {'body':body, 'metadata':meta}


def deferred_baseline_path(root, row):
    return Path(root)/'raw/official-sync/deferred-baselines'/f'{digest([row["id"], row.get("revision")])}.json'


def preserve_deferred_baselines(root, journal):
    """Read an interrupted save's last consistent pairs without restoring tracked files."""
    root = Path(root)
    affected = {record['metadata']['id'] for record in journal.get('records', [])}
    def candidates(relative):
        path = root/relative
        value = read(path)
        if value is not None:yield value
        folder = root/'raw/backups/knowledge'/Path(relative).relative_to('knowledge').parent
        if folder.exists():
            for backup in sorted(folder.iterdir(), reverse=True):
                if backup.name.startswith(path.name+'.') and backup.name.endswith('.bak'):
                    yield read(backup)
    for row in read(root/INDEX, {'notes':[]})['notes']:
        if row['id'] not in affected:continue
        try:
            _disk_record(root, row)
            continue
        except ValueError:pass
        meta = next((m for m in candidates(meta_path(row['path'])) if m.get('revision') == row.get('revision')), None)
        body = next((b for b in candidates(row['path']) if meta and digest(b) == meta.get('body_sha256')), None)
        if meta is None or body is None:
            raise ValueError('旧自动事务已保留，但缺少一致的旧版备份，请人工恢复：'+row['path'])
        baseline = {'body':body, 'metadata':meta}
        check_record(baseline)
        write_file(deferred_baseline_path(root, row), baseline)


def load_record(root, nid, *, clone=True):
    """Read one logical record, including the published transaction overlay."""
    root = Path(root)
    for attempt in range(2):
        pending = pending_save(root)
        index = pending['index'] if pending else read(root / INDEX, {'notes':[]})
        row = next((r for r in index['notes'] if r['id']==nid), None)
        if row is None: return None
        overlay = next((r for r in pending['records'] if r['metadata']['id']==nid), None) if pending else None
        try:
            record = overlay if overlay is not None else _disk_record(root, row)
            return deepcopy(record) if clone else record
        except (ValueError, FileNotFoundError):
            if attempt: raise
    return None


def records(root, clone=True):
    root = Path(root)
    for attempt in range(2):
        pending = pending_save(root)
        if pending and not pending.get('delta'):
            return deepcopy(pending['records'])
        index = pending['index'] if pending else read(root / INDEX, {'notes':[]})
        overlay = {r['metadata']['id']:r for r in pending['records']} if pending else {}
        try:
            result = [overlay[row['id']] if row['id'] in overlay else _disk_record(root,row) for row in index['notes']]
            return deepcopy(result) if clone else result
        except (ValueError, FileNotFoundError):
            if attempt: raise
    return []


def resolve_value(value, texts):
    if isinstance(value, dict):
        if '$text' in value and set(value) <= {'$text', '$format'}:
            return texts[value['$text'] + (':markdown' if value.get('$format') == 'markdown' else '')]
        return {k: resolve_value(v, texts) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, texts) for v in value]
    return value


def project(record, public=False):
    body = deepcopy(record['body'])
    source = record['metadata']
    meta = deepcopy({k:v for k,v in source.items() if not public or k not in ('history','legacy_layout','retired_claim_annotations','claim_annotations','entity_names','conflicts')})
    if public:
        meta['history_count'] = len(source.get('history', []))
        meta['conflicts'] = [{'reason':x.get('reason', '待核对的知识冲突')} for x in source.get('conflicts', [])]
    texts = {n['id']: n.get('value', n.get('title', '')) for n in [*body['nodes'], *body.get('supporting_nodes', [])]}
    texts.update({n['id']+':markdown':document.render_node(n).rstrip('\r\n') for n in [*body['nodes'], *body.get('supporting_nodes', [])]})
    semantics = resolve_value(body.get('semantics', {}), texts)
    claims = []
    annotations = [{k:v for k,v in c.items() if k != 'evidence'} for c in source.get('claim_annotations', [])] if public else meta.pop('claim_annotations', [])
    for c in deepcopy(annotations):
        ref = c['text_ref']
        formatted = c.pop('text_format',None)=='markdown'
        claims.append({**c, 'text': texts[ref+(':markdown' if formatted else '')]})
    meta.pop('body_sha256', None)
    meta.pop('claims', None)
    result = {**meta, 'schema_version': 6, 'document': body, 'claims': claims, 'meta': semantics,
            'lineup_adaptations': deepcopy(body.get('adaptations', [])), 'topic': body.get('topic', ''),
            'aliases': meta.get('aliases', []), 'entities': meta.get('entities', []), 'core': semantics.get('core_heroes', []),
            'related': meta.get('related', []), 'history': meta.get('history', []), 'conflicts': meta.get('conflicts', []),
            'manual_sections': meta.get('manual_sections', [])}
    if meta['type'] != 'lineup':result.pop('meta', None)
    return result


def notes(root, public=False):
    return [project(r, public=public) for r in records(root, clone=False)]


def resolve_note(root, nid, player=None):
    root = Path(root)
    index = read(root / INDEX, {})
    aliases = index.get('aliases', {})
    mapped = aliases.get(nid + ('|' + player if player else '')) or aliases.get(nid)
    key = mapped or nid
    record = load_record(root, key, clone=False)
    return project(record, public=True) if record else None


def from_legacy(note, markdown):
    body = document.parse(markdown)
    metadata = {k: deepcopy(v) for k, v in note.items() if k not in ('claims', 'meta', 'reading_layout', 'revision', 'document', 'core', 'lineup_adaptations', 'topic')}
    if note.get('reading_layout'):metadata['legacy_layout'] = deepcopy(note['reading_layout'])
    if note.get('lineup_adaptations'):body['adaptations'] = deepcopy(note['lineup_adaptations'])
    if note.get('topic'):body['topic'] = note['topic']
    body['supporting_nodes'] = []
    metadata['claim_annotations'] = []
    texts = {}
    for node in body['nodes']:
        if node['type'] == 'entry':
            texts.setdefault(node['value'], node['id'])
    for number, claim in enumerate(note.get('claims', [])):
        text = claim['text']
        ref = texts.get(text)
        if ref is None:
            ref = 'support-' + str(claim.get('id') or number)
            body['supporting_nodes'].append({'id': ref, 'type': 'entry', 'key': '正文', 'show_key': False, 'value': text, 'separator': ''})
            texts[text] = ref
        metadata['claim_annotations'].append({**{k: deepcopy(v) for k, v in claim.items() if k != 'text'}, 'text_ref': ref})

    def intern(value):
        if isinstance(value, str) and value in texts:
            return {'$text': texts[value]}
        if isinstance(value, dict):
            return {k: intern(v) for k, v in value.items()}
        if isinstance(value, list):
            return [intern(v) for v in value]
        return deepcopy(value)
    semantic = deepcopy(note.get('meta', {}))
    if note['type'] == 'lineup':
        from workspace import default_meta
        semantic = {**default_meta(note), **semantic}
    for field in ('player_branches', 'common_claim_refs'):
        semantic.pop(field, None)
    if note['type'] == 'lineup':
        semantic['players'] = [note['player_id']]
    body['semantics'] = intern(semantic)
    return {'body': body, 'metadata': metadata}


def structure_labels(record):
    """Expose legacy plain labels/list rows without changing text or evidence."""
    body, meta = record['body'], record['metadata']
    before = document.markdown(body)
    result = []
    redirects = {}
    for old in body['nodes']:
        if old['type'] != 'entry' or old['show_key']:
            result.append(old);continue
        parsed = document.parse(old['value'])['nodes']
        if not parsed or not all(n['type']=='entry' for n in parsed) or not any(n['show_key'] for n in parsed):
            result.append(old);continue
        parsed[-1]['separator'] = old.get('separator','')
        for i,n in enumerate(parsed):n['id'] = old['id'] if i==0 else old['id']+'-part-'+str(i)
        annotations = [c for c in meta.get('claim_annotations',[]) if c['text_ref']==old['id']]
        if len(parsed)==1:
            redirects[old['id']]={'$text':old['id'],'$format':'markdown'}
            for c in annotations:c['text_format']='markdown'
        else:
            source=deepcopy(old);source['id']=old['id']+'-source';source['separator']=''
            body.setdefault('supporting_nodes',[]).append(source)
            redirects[old['id']]={'$text':source['id']}
            for c in annotations:c['text_ref']=source['id']
        if any(c.get('origin')=='manual' for c in annotations) or meta.get('node_annotations',{}).get(old['id'],{}).get('origin')=='manual':
            for n in parsed:meta.setdefault('node_annotations',{})[n['id']]={'origin':'manual'}
        result.extend(parsed)
    def redirect(value):
        if isinstance(value,dict):
            if set(value)=={'$text'} and value['$text'] in redirects:return redirects[value['$text']]
            return {k:redirect(v) for k,v in value.items()}
        if isinstance(value,list):return [redirect(v) for v in value]
        return value
    body['nodes']=result
    if redirects:body['semantics']=redirect(body.get('semantics',{}))
    if document.markdown(body)!=before:raise ValueError('条目细化改变了原文格式')
    return record


def validate_semantics(root, record):
    if record['metadata']['type']!='lineup':return
    from workspace import validate_meta
    fields={'required_factions','players','core_heroes','compositions','ban_conditions','matchups','operation_routes','late_variants','overview','major_variants','assessment'}
    semantics=project(record,public=True)['meta']
    try:validate_meta(root,{k:v for k,v in semantics.items() if k in fields})
    except (TypeError,AttributeError,KeyError) as exc:raise ValueError('阵容结构格式无效，请检查阶段成员与运营条件') from exc


def edit(root, nid, payload, *, _review=None, public=False):
    from workspace import Conflict, store_lock
    with store_lock(root, wait=True):
        recover(root)
        before = load_record(root, nid, clone=False)
        record = editable_record(before) if before is not None else None
        if record is None:
            raise KeyError('笔记不存在')
        meta, body = record['metadata'], record['body']
        if payload.get('revision') != meta['revision']:
            raise Conflict('笔记已更新，请重新载入后合并草稿')
        if set(payload) - {'revision', 'document', 'aliases', 'title', 'restore_version'}:
            raise ValueError('请通过结构化JSON正文编辑知识')
        incoming = document.clean_labels(payload.get('document', body))
        document.validate(incoming)
        # Supporting evidence and structured semantics are maintained by the
        # canonical document, not accepted as accidental editor omissions.
        for key in ('supporting_nodes', 'semantics'):
            incoming.setdefault(key, deepcopy(body.get(key, [] if key == 'supporting_nodes' else {})))
        if _review:
            from note_review import authorize
            allowed = authorize(root, before, _review)
            old_visible = {n['id']: n for n in body['nodes']}
            new_visible = {n['id']: n for n in incoming['nodes']}
            if list(old_visible) != list(new_visible):
                raise ValueError('措辞修改不能新增、删除或重排节点')
            for node_id, node in new_visible.items():
                old_node = old_visible[node_id]
                if old_node == node:
                    continue
                if node_id not in allowed or any(old_node.get(k) != node.get(k) for k in set(old_node) | set(node) if k not in ('key', 'value', 'title')):
                    raise ValueError('措辞修改超出批注授权范围')
            for key in set(body) | set(incoming):
                if key != 'nodes' and body.get(key, [] if key == 'supporting_nodes' else {} if key == 'semantics' else None) != incoming.get(key):
                    raise ValueError('措辞修改不能修改结构化知识或支撑节点')
        if incoming != body:
            # Keep display identity across text edits without rewriting evidence.
            display_refs = document.claim_display_refs(body, project(record, public=True)['claims'])
            for annotation in meta.get('claim_annotations', []):
                if annotation['id'] in display_refs:
                    annotation['display_ref'] = display_refs[annotation['id']]
        title = payload.get('title', meta['title'])
        if title != meta['title']:
            raise ValueError('笔记身份名称通过新建与迁移维护；正文编辑不能改绑棋手或阵容')
        old_nodes = {n['id']: n for n in [*body['nodes'], *body.get('supporting_nodes', [])]}
        new_nodes = {n['id']: n for n in [*incoming['nodes'], *incoming.get('supporting_nodes', [])]}
        deleted = old_nodes.keys() - new_nodes.keys()
        if deleted:
            active = []
            removed_claim_ids = set()
            for annotation in meta.get('claim_annotations', []):
                if annotation['text_ref'] in deleted:
                    if annotation.get('id'):removed_claim_ids.add(annotation['id'])
                    meta.setdefault('retired_claim_annotations', []).append({**annotation, 'history_index':len(meta.get('history', []))})
                else:active.append(annotation)
            meta['claim_annotations'] = active
            def detach(value):
                if isinstance(value,dict):
                    if value.get('$text') in deleted:return ''
                    return {k:detach(v) for k,v in value.items()}
                if isinstance(value,list):return [detach(v) for v in value if not isinstance(v,str) or v not in removed_claim_ids]
                return value
            incoming['semantics'] = detach(incoming.get('semantics',{}))
        for node_id in old_nodes.keys() | new_nodes.keys():
            if old_nodes.get(node_id) != new_nodes.get(node_id):
                meta.setdefault('node_annotations', {})[node_id] = {'origin': 'manual'}
                for annotation in meta.get('claim_annotations', []):
                    if annotation['text_ref'] == node_id:
                        annotation.update(origin='manual', evidence=[], inference=False)
        if incoming.get('semantics') != body.get('semantics'):
            meta['manual_semantics'] = True
        current_section = '知识内容'
        for n in incoming['nodes']:
            if n['type'] == 'heading':
                if n['level'] == 2:
                    current_section = n['title']
                continue
            if old_nodes.get(n['id']) != n:
                meta.setdefault('node_annotations', {})[n['id']] = {'origin': 'manual', 'section': current_section}
                for annotation in meta.get('claim_annotations', []):
                    if annotation['text_ref'] == n['id']:
                        annotation.update(origin='manual', evidence=[], inference=False)
        if incoming != body or payload.get('aliases', meta.get('aliases', [])) != meta.get('aliases', []):
            import wxq
            meta.setdefault('history', []).append({'at': wxq.now(), 'origin': 'manual', 'previous': snapshot(before)})
            meta['aliases'] = payload.get('aliases', meta.get('aliases', []))
            record['body'] = incoming
        if payload.get('restore_version'):
            from note_review import restore_evidence
            restore_evidence(root, nid, payload['restore_version'], before, record)
        if record['body'] != before['body']:
            meta['review_receipts'] = deepcopy(_review or [])
        validate_semantics(root,record)
        saved = save(root, [record], origin='review' if _review else 'history_merge' if payload.get('restore_version') else 'manual', review_refs=_review, partial=True)
        return project(saved[0] if saved else record, public=public)


def create(root, payload):
    import wxq
    from workspace import filename, store_lock, Conflict
    from player_identity import catalog
    kind = payload.get('type')
    if kind not in wxq.FOLDERS:
        raise ValueError('笔记类型无效')
    player = payload.get('player_id')
    players = catalog(root)
    if kind in ('player', 'lineup') and player not in players:
        raise ValueError('请选择有效棋手')
    title = str(payload.get('title', '')).strip()
    if kind == 'player':
        title = players[player]['name']
    elif kind == 'lineup':
        suffix = '-' + players[player]['name']
        title = title if title.endswith(suffix) else title + suffix
    filename(title)
    request = payload.get('request_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request):
        raise ValueError('新建请求标识无效')
    with store_lock(root, wait=True):
        recover(root)
        items = records(root)
        fingerprint = digest({k: payload.get(k) for k in ('type', 'title', 'aliases', 'player_id')})
        old = next((r for r in items if r['metadata'].get('creation', {}).get('request_id') == request), None)
        if old:
            if old['metadata']['creation']['payload_hash'] != fingerprint:
                raise Conflict('请求标识已用于不同内容')
            return project(old)
        if any(r['metadata']['type'] == kind and (r['metadata']['title'] == title or (kind == 'player' and r['metadata'].get('player_id') == player)) for r in items):
            raise Conflict('该笔记已存在，请打开已有笔记')
        metadata = {'id': 'note-' + hashlib.sha256(request.encode()).hexdigest()[:24], 'type': kind, 'title': title,
                    'path': f'knowledge/{wxq.FOLDERS[kind]}/{filename(title)}.json', 'aliases': payload.get('aliases', []),
                    'player_id': player, 'creation': {'request_id': request, 'payload_hash': fingerprint}}
        item = from_legacy({**metadata, 'meta': {'players': [player]} if kind == 'lineup' else {}}, '# ' + title + '\n')
        items.append(item)
        save(root, items)
        return next(n for n in notes(root) if n['id'] == metadata['id'])


def validate(root):
    errors = []
    try:
        items = records(root)
        for record in items:
            check_record(record)
            project(record)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        errors.append(str(exc)); items = []
    for p in (Path(root) / 'knowledge').rglob('*'):
        if p.is_file() and p.suffix != '.json':
            errors.append('知识库含非JSON文件：' + str(p))
    return {'schema_version': 6, 'notes': len(items), 'errors': errors}


def persist_views(root, views):
    previous = {r['metadata']['id']: r for r in records(root)}
    items = []
    for view in views:
        if 'document' not in view:
            raise ValueError('旧结论提交不能写入JSON知识库；请使用版本6正文契约')
        old = previous.get(view['id'])
        if old and view.get('claims', []) != project(old)['claims']:
            raise ValueError('不能通过旧claims接口修改正文；请编辑结构化JSON')
        meta = deepcopy(old['metadata'] if old else {})
        for k, v in view.items():
            if k not in ('document', 'claims', 'meta', 'schema_version', 'revision', 'reading_layout'):
                meta[k] = deepcopy(v)
        items.append({'body': deepcopy(view['document']), 'metadata': meta})
    save(root, items)


def commit(root, incoming):
    import wxq
    from workspace import store_lock, Conflict
    with store_lock(root, wait=True):
        recover(root)
        current = {r['metadata']['id']: r for r in records(root)}
        changed = []
        batch_refs = []
        for item in incoming:
            if 'body' not in item or 'metadata' not in item:
                raise ValueError('版本6提交须包含body和metadata；旧schema只能显式迁移')
            record = deepcopy(item)
            record['body'] = document.clean_labels(record['body'])
            check_record(record)
            meta = record['metadata'];nid = meta['id'];previous = current.get(nid)
            if previous:
                if meta.get('revision') != previous['metadata']['revision']:
                    raise Conflict('知识已更新，请读取最新正文与附件后合并')
                if meta.get('player_id') != previous['metadata'].get('player_id'):
                    raise ValueError('既有笔记不能改绑棋手')
                protected = manual_nodes(previous)
                refs = record.pop('review_refs', [])
                from note_review import authorize
                allowed = authorize(root, previous, refs) if refs else set()
                batch_refs.extend(refs)
                old_nodes = {n['id']: n for n in [*previous['body']['nodes'], *previous['body'].get('supporting_nodes', [])]}
                new_nodes = {n['id']: n for n in [*record['body']['nodes'], *record['body'].get('supporting_nodes', [])]}
                protected_semantics = previous['metadata'].get('manual_semantics') or previous['metadata'].get('manual_meta')
                if any(new_nodes.get(node_id) != old_nodes.get(node_id) for node_id in protected - allowed) or (protected_semantics and previous['body'].get('semantics') != record['body'].get('semantics')):
                    previous['metadata'].setdefault('conflicts', []).append({'at': wxq.now(), 'incoming': snapshot(record), 'reason': '人工正文受到保护'})
                    changed.append(meta['id']);continue
                meta['review_receipts'] = refs
                for k in ('history', 'node_annotations', 'retired_claim_annotations', 'manual_sections', 'manual_semantics', 'conflicts', 'creation'):
                    if k in previous['metadata']:meta[k] = deepcopy(previous['metadata'][k])
                if record['body'] != previous['body']:
                    history=meta.setdefault('history',[])
                    history.append({'at':wxq.now(),'origin':'import','body':deepcopy(previous['body']),
                                    'claim_annotations':deepcopy(previous['metadata'].get('claim_annotations',[]))})
                    current_claim_ids={c.get('id') for c in meta.get('claim_annotations',[])}
                    retired=meta.setdefault('retired_claim_annotations',[])
                    known_retired={c.get('id') for c in retired}
                    retired.extend({**deepcopy(c),'history_index':len(history)-1} for c in previous['metadata'].get('claim_annotations',[])
                                   if c.get('id') not in current_claim_ids and c.get('id') not in known_retired)
            projected = project(record)
            validate_semantics(root,record)
            old_claims = project(previous)['claims'] if previous else []
            old_visible = {n['id']:n for n in previous['body']['nodes']} if previous else {}
            annotated = {c['text_ref'] for c in meta.get('claim_annotations',[]) if c.get('kind') in wxq.KNOWLEDGE_KINDS and c.get('evidence')}
            placeholders = {'暂无已确认的通用策略','暂无已确认结论','未提供','待确认'}
            for node in record['body']['nodes']:
                if node['type']!='entry':continue
                old_node=old_visible.get(node['id'],{})
                entry_changed=(node.get('key'),node.get('value'))!=(old_node.get('key'),old_node.get('value'))
                if entry_changed and node['value'].strip().rstrip('。') not in placeholders and node['value'].strip() and node['id'] not in annotated:
                    raise ValueError('新增或改义条目必须直接关联来源证据：'+node['key'])
            known = {e['id'] for e in wxq.entities(root)}
            if (set(meta.get('entities', [])) | set(meta.get('core', []))) - known:
                raise ValueError('存在未知实体')
            for claim in projected['claims']:
                if claim.get('kind') not in wxq.KNOWLEDGE_KINDS:
                    raise ValueError('结论类别无效')
                if claim.get('origin') == 'manual' and claim not in old_claims:
                    raise ValueError('人工知识只能由网页编辑产生，导入不能伪造人工来源')
                if claim.get('origin') != 'manual' and not claim.get('evidence') and claim not in old_claims:
                    raise ValueError('知识结论需要可追溯证据')
                for evidence in claim.get('evidence', []):
                    check_evidence(root, evidence)
            current[nid] = record;changed.append(nid)
        save(root, list(current.values()), origin='review' if batch_refs else 'import', review_refs=batch_refs)
        return {'notes': changed, 'schema_version': 6}


def check_evidence(root, evidence):
    import wxq
    if evidence.get('type') == 'document':
        from document_sources import validate_evidence
        validate_evidence(root, evidence)
        return
    folder = wxq.source_dir(root, evidence['source'])
    from reference_store import transcript_artifacts
    if not transcript_artifacts(folder)[0].exists() or not (folder / 'metadata.json').exists():
        raise ValueError('来源转写或档案不存在：' + evidence['source'])
    if evidence.get('frame') and not (folder / evidence['frame']).exists():
        raise ValueError('引用画面不存在：' + evidence['frame'])


def validate_evidence(root):
    import wxq
    from reference_store import json_cards, validate_cards, transcript_errors
    result = validate(root)
    result['entities'] = {c: len(wxq.read_json(Path(root) / 'entities' / (c + '.json'), [])) for c in wxq.CATEGORIES}
    for note in notes(root):
        for claim in note['claims']:
            if claim.get('kind') not in wxq.KNOWLEDGE_KINDS:
                result['errors'].append('结论类别无效：' + note['id'])
            for evidence in claim.get('evidence', []):
                try:check_evidence(root, evidence)
                except (ValueError, KeyError, OSError) as exc:result['errors'].append(str(exc))
    try:
        cards = json_cards(root);validate_cards(cards);result['cards'] = len(cards)
    except (ValueError, KeyError, OSError) as exc:
        result['errors'].append(str(exc));result['cards'] = 0
    for folder in (Path(root) / 'raw/sources').glob('*'):
        if read(folder / 'state.json', {}).get('stage') == 'complete':
            sid = read(folder / 'metadata.json', {}).get('id')
            if sid:result['errors'].extend(transcript_errors(root, sid))
    return result
