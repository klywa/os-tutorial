"""Local note versions and anchored review requests, shared by HTTP and CLI."""
from copy import deepcopy
from pathlib import Path
import uuid
from datetime import datetime, timezone
import json_store as store

COMMENTS = 'raw/knowledge/annotations.json'


def version_folder(root, nid):
    return Path(root) / 'raw/knowledge/versions' / store.digest(nid)[:32]


def _version_rows(root, nid):
    folder = version_folder(root, nid)
    index = folder / 'index.meta.json'
    pending = store.pending_save(root)
    relative = index.relative_to(Path(root)).as_posix()
    if pending:
        overlay = next((e['value'] for e in pending.get('versions', []) if e['path']==relative), None)
        if overlay is not None: return overlay['versions']
    saved = store.read(index)
    if saved is not None: return saved['versions']
    rows = []
    for path in folder.glob('*.json'):
        if path.name == 'index.meta.json': continue
        row = store.read(path)
        rows.append({**{k:row[k] for k in ('id','note_id','at','origin','body_sha256','review_refs')},
                     'snapshot_sha256':store.digest(row['record'])})
    rows.sort(key=lambda r:(r['at'],r['id']), reverse=True)
    if rows: store.write_file(index, {'versions':rows})
    return rows


def versions(root, nid, *, _locked=False):
    if _locked or (version_folder(root,nid) / 'index.meta.json').exists():
        return _version_rows(root,nid)
    from workspace import store_lock
    with store_lock(root, wait=True):
        store.recover(root)
        return _version_rows(root,nid)


def version(root, nid, vid):
    if not isinstance(vid, str) or len(vid) != 32 or any(c not in '0123456789abcdef' for c in vid):
        raise ValueError('版本标识无效')
    path = version_folder(root, nid) / (vid + '.json')
    pending = store.pending_save(root)
    relative = path.relative_to(Path(root)).as_posix()
    row = next((entry['value'] for entry in pending.get('versions',[]) if entry['path']==relative),None) if pending else None
    if row is None: row = store.read(path)
    if not row or row['note_id'] != nid:
        raise KeyError('历史版本不存在')
    return row


def version_writes(root, old, new, origin='save', review_refs=None):
    import wxq
    result = []
    previous = {r['metadata']['id']: r for r in old}
    for record in new:
        nid = record['metadata']['id']; before = previous.get(nid)
        if before and before['body'] == record['body']:
            continue
        existing = versions(root, nid, _locked=True)
        candidates = []
        if before and (not existing or existing[0]['snapshot_sha256'] != store.digest(store.snapshot(before))):
            candidates.append((before, 'baseline', []))
        candidates.append((record, origin, review_refs or []))
        for item, source, refs in candidates:
            vid = uuid.uuid4().hex
            snap = store.snapshot(item)
            value = {'id': vid, 'note_id': nid, 'at': datetime.now(timezone.utc).isoformat(), 'origin': source,
                     'body_sha256': store.digest(item['body']), 'review_refs': refs, 'record':snap}
            result.append({'path': str((version_folder(root, nid) / (vid + '.json')).relative_to(Path(root))).replace('\\', '/'),
                           'value': value})
            existing.insert(0, {**{k:v for k,v in value.items() if k!='record'}, 'snapshot_sha256':store.digest(snap)})
        result.append({'path':(version_folder(root,nid) / 'index.meta.json').relative_to(Path(root)).as_posix(),
                       'value':{'versions':existing}})
    return result


def restore_evidence(root, nid, vid, before, record):
    historical = version(root, nid, vid)['record']
    old = {n['id']: n for n in [*before['body']['nodes'], *before['body'].get('supporting_nodes', [])]}
    current = {n['id']: n for n in [*record['body']['nodes'], *record['body'].get('supporting_nodes', [])]}
    original = {n['id']: n for n in [*historical['body']['nodes'], *historical['body'].get('supporting_nodes', [])]}
    eligible = {nid for nid, n in current.items() if n == original.get(nid) and n != old.get(nid)}
    restored = []
    for claim in historical['metadata'].get('claim_annotations', []):
        if claim['text_ref'] not in eligible:
            continue
        try:
            for evidence in claim.get('evidence', []):
                store.check_evidence(root, evidence)
        except (ValueError, KeyError, OSError):
            continue  # Changed or unavailable sources must not regain authority.
        restored.append(deepcopy(claim))
    refs = {c['text_ref'] for c in restored}; ids = {c['id'] for c in restored}
    active = [c for c in record['metadata'].get('claim_annotations', []) if c['text_ref'] not in refs and c.get('id') not in ids]
    record['metadata']['claim_annotations'] = active + restored


def scope(body, node_id):
    nodes = body['nodes']; start = next((i for i, n in enumerate(nodes) if n['id'] == node_id), None)
    if start is None:
        return []
    node = nodes[start]; end = start + 1
    if node['type'] == 'heading':
        while end < len(nodes) and not (nodes[end]['type'] == 'heading' and nodes[end]['level'] <= node['level']):
            end += 1
    return deepcopy(nodes[start:end])


def _rows(root):
    return store.read(Path(root) / COMMENTS, {'annotations': []})['annotations']


def _record(root, nid):
    record = store.load_record(root, nid, clone=False)
    if not record:
        raise KeyError('笔记不存在')
    return record


def annotations(root, note_id=None, status=None):
    records = {}
    result = []
    for row in _rows(root):
        if row.get('deleted') or (note_id and row['note_id'] != note_id) or (status and row['status'] != status):
            continue
        if row['note_id'] not in records:
            records[row['note_id']] = store.load_record(root, row['note_id'], clone=False)
        record = records.get(row['note_id'])
        current = scope(record['body'], row['node_id']) if record else []
        result.append({**row, 'anchor_state': 'missing' if not current else 'current' if current == row['target'] else 'changed',
                       'current_target': current, 'current_revision': record['metadata']['revision'] if record else None})
    return result


def mutate(root, payload):
    from workspace import store_lock, Conflict
    import wxq
    with store_lock(root, wait=True):
        store.recover(root)
        rows = _rows(root); aid = payload.get('id')
        row = next((r for r in rows if r['id'] == aid), None) if aid else None
        if aid and not row:
            raise KeyError('批注不存在')
        if row and payload.get('revision') != row['revision']:
            raise Conflict('批注已更新，请重新载入')
        if row:
            row.setdefault('history', []).append({k: deepcopy(v) for k, v in row.items() if k != 'history'})
            if 'text' in payload:
                if not isinstance(payload['text'], str) or not payload['text'].strip():
                    raise ValueError('请填写批注内容')
                row.update(text=payload['text'].strip(), status='open')
            if payload.get('action') == 'delete':
                row['deleted'] = True
            elif payload.get('action') == 'reopen':
                row['status'] = 'open'
            elif payload.get('action') == 'defer':
                row.update(status='open', result=str(payload.get('result', '')).strip())
        else:
            record = _record(root, payload.get('note_id'))
            if payload.get('note_revision') != record['metadata']['revision']:
                raise Conflict('笔记已更新，请重新载入后批注')
            target = scope(record['body'], payload.get('node_id'))
            if not target:
                raise ValueError('批注目标不存在')
            text = payload.get('text')
            if not isinstance(text, str) or not text.strip():
                raise ValueError('请填写批注内容')
            row = {'id': uuid.uuid4().hex, 'note_id': record['metadata']['id'], 'node_id': payload['node_id'],
                   'note_revision': record['metadata']['revision'], 'target': target, 'text': text.strip(),
                   'status': 'open', 'created_at': wxq.now(), 'history': []}
            rows.append(row)
        row.update(revision=uuid.uuid4().hex, updated_at=wxq.now())
        store.write_file(Path(root) / COMMENTS, {'annotations': rows})
        return deepcopy(row)


def authorize(root, record, refs):
    """Authorize only exact, current anchored scopes; never a generic bypass."""
    allowed = set(); rows = {r['id']: r for r in annotations(root)}
    for ref in refs:
        row = rows.get(ref.get('id'))
        if not row or row['status'] != 'open' or row['revision'] != ref.get('revision') or row['note_id'] != record['metadata']['id']:
            raise ValueError('批注授权无效或已更新')
        if row['anchor_state'] != 'current':
            raise ValueError('批注目标已变化，请重新确认目标后新建批注')
        allowed.update(n['id'] for n in row['target'])
    return allowed


def apply_editorial(root, payload):
    """Explicit annotated wording edits; same provenance handling as UI edits."""
    refs = payload.get('review_refs')
    if not isinstance(refs, list) or not refs:
        raise ValueError('措辞修改必须关联有效批注')
    return store.edit(root, payload.get('note_id'), {'revision': payload.get('revision'), 'document': payload.get('document')}, _review=refs)


def complete(root, aid, payload):
    from workspace import store_lock, Conflict
    import wxq
    with store_lock(root, wait=True):
        store.recover(root)
        rows = _rows(root); row = next((r for r in rows if r['id'] == aid and not r.get('deleted')), None)
        if not row:
            raise KeyError('批注不存在')
        if row['status'] == 'resolved' and row.get('result_revision') == payload.get('result_revision'):
            return row
        if row['revision'] != payload.get('revision'):
            raise Conflict('批注已更新')
        record = _record(root, row['note_id']); meta = record['metadata']
        if meta['revision'] != payload.get('result_revision'):
            raise ValueError('完成版本与当前正文不一致')
        receipt = {'id': aid, 'revision': row['revision']}
        if receipt not in meta.get('review_receipts', []):
            raise ValueError('当前正文未通过该批注授权提交')
        validation = wxq.validate_store(Path(root))
        if validation.get('errors'):
            raise ValueError('知识校验未通过，批注保持待处理')
        row.setdefault('history', []).append({k: deepcopy(v) for k, v in row.items() if k != 'history'})
        row.update(status='resolved', result=str(payload.get('result', '')).strip(), result_revision=meta['revision'],
                   result_version=versions(root, row['note_id'], _locked=True)[0]['id'], updated_at=wxq.now(), revision=uuid.uuid4().hex)
        store.write_file(Path(root) / COMMENTS, {'annotations': rows})
        return deepcopy(row)
