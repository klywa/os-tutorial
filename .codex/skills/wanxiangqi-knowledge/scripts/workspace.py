"""Single-writer knowledge workspace shared by the CLI and local web UI."""
from contextlib import contextmanager
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
    path = Path(root) / 'knowledge/.write.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a+b')
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b'0')
        handle.flush()
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
    return wxq.read_json(Path(root) / 'knowledge/index.json', {'notes': []})['notes']


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
            note['entity_names'] = {r: names.get(r, r.removeprefix('pending:')) for r in refs if r}
        note.setdefault('manual_sections', [])
        note.setdefault('history', [])
        note.setdefault('conflicts', [])
    by_id = {n['id']: n for n in items}
    for note in items:
        existing_links = {link['id'] for link in note.get('related', [])}
        for target in items:
            if target['id'] != note['id'] and target['id'] not in existing_links and (note.get('meta', {}).get('late_variants') or target.get('meta', {}).get('late_variants')) and set(note.get('entities', [])) & set(target.get('entities', [])):
                note.setdefault('related', []).append({'id': target['id'], 'type': target['type'], 'title': target['title']})
        for link in note.get('related', []):
            if link['id'] in by_id:
                link['path'] = by_id[link['id']]['path']
                link['title'] = by_id[link['id']]['title']
        note['revision'] = revision(note)
    return items


def persist(root, items, obsolete=None):
    root = Path(root)
    prepare(root, items)
    transaction = {'index': {'schema_version': 4, 'notes': items}, 'obsolete': obsolete or []}
    wxq.atomic_json(root / 'knowledge/pending-save.json', transaction)
    apply_transaction(root, transaction)


def apply_transaction(root, transaction):
    root = Path(root)
    items = transaction['index']['notes']
    # Validate paths before replaying a recovery record.
    assign_paths(root, items)
    for note in items:
        wxq.atomic_text(root / note['path'], wxq.render_note(note, {}))
        if note['type'] == 'lineup':
            wxq.atomic_json((root / note['path']).with_suffix('.json'), note)
    wxq.atomic_json(root / 'knowledge/index.json', transaction['index'])
    active = {n['path'] for n in items}
    for path in transaction.get('obsolete', []):
        target = (root / path).resolve()
        if not target.is_relative_to((root / 'knowledge').resolve()):
            raise ValueError('非法迁移路径')
        if path not in active and target.exists():
            # Keep the complete original for recovery before removing the old filename.
            wxq.atomic_text(target.with_suffix('.md.bak'), target.read_text(encoding='utf-8'))
            target.unlink()
    (root / 'knowledge/pending-save.json').unlink(missing_ok=True)


def recover(root):
    from reference_store import recover_cards, recover_transcript_edits
    recover_transcript_edits(root)
    recover_cards(root)
    transaction = wxq.read_json(Path(root) / 'knowledge/pending-save.json')
    if transaction:
        apply_transaction(root, transaction)


def migrate(root):
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


def merge_note(previous, incoming):
    result = {**deepcopy(previous), **deepcopy(incoming)}
    if isinstance(incoming.get('meta'),dict) and 'major_variants' not in incoming['meta'] and 'major_variants' in previous.get('meta',{}):
        result['meta']['major_variants']=deepcopy(previous['meta']['major_variants'])
    for key in ['path', 'history', 'manual_sections', 'manual_meta', 'manual_fields', 'conflicts']:
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
    if not expected.issubset(meta) or set(meta) - expected - {'operation_routes', 'late_variants', 'overview', 'major_variants'} or not isinstance(meta['compositions'], dict) or set(meta['compositions']) != {'early', 'middle', 'late'}:
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
    for matchup in meta.get('matchups', []):
        if not isinstance(matchup, dict):
            raise ValueError('针对策略无效')
        target = matchup.get('target', '')
        if target not in {n['id'] for n in notes(root)}:
            reference(target)
        if not isinstance(matchup.get('text'), str) or not matchup['text'].strip():
            raise ValueError('针对策略需要正文')


def edit(root, nid, payload):
    with store_lock(root):
        recover(root)
        items = deepcopy(notes(root))
        note = next((n for n in items if n['id'] == nid), None)
        if note is None:
            raise KeyError('笔记不存在')
        if payload.get('revision') != note.get('revision'):
            raise Conflict('笔记已被其他操作更新，请重新载入后合并你的草稿')
        before = deepcopy(note)
        sections = payload.get('sections', {})
        if not isinstance(sections, dict):
            raise ValueError('章节格式无效')
        for section, text in sections.items():
            if not isinstance(text, str) or not isinstance(section, str) or not section.strip() or section == '关联知识':
                raise ValueError('章节名称或正文无效')
            current = '\n\n'.join(c['text'] for c in note['claims'] if c['section'] == section)
            if current == text.strip():
                continue
            from tactics import claim_id, remap_claims
            old_ids = {claim_id(c) for c in note['claims'] if c['section'] == section}
            note['claims'] = [c for c in note['claims'] if c['section'] != section]
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


def register_source(root, payload, sid=None, preserve_annotations=False, wait=False, cancelled=None):
    url, canonical_id = canonical_url(payload.get('url', ''))
    with store_lock(root, wait=wait):
        path = Path(root) / 'knowledge/source-registry.json'
        rows = wxq.read_json(path, [])
        imported = next((r for r in sources(root) if canonical_url(r['url'])[0] == url), None)
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
        row.update({'url': url,
                    'title': (row.get('title') or (imported or {}).get('title') or payload.get('title', '')) if preserve_annotations else payload.get('title', ''),
                    'notes': (row.get('notes') or (imported or {}).get('notes') or payload.get('notes', '')) if preserve_annotations else payload.get('notes', ''),
                    'updated_at': wxq.now()})
        wxq.atomic_json(path, rows, cancelled=cancelled)
        return row


def sources(root):
    root = Path(root)
    rows = {r['id']: dict(r) for r in wxq.read_json(root / 'knowledge/source-registry.json', [])}
    linked = {}
    for note in notes(root):
        for claim in note.get('claims', []):
            for evidence in claim.get('evidence', []):
                linked.setdefault(evidence['source'], {})[note['id']] = {'id': note['id'], 'title': note['title']}
        for history in note.get('history', []):
            for claim in history.get('previous', {}).get('claims', []):
                for evidence in claim.get('evidence', []):
                    linked.setdefault(evidence['source'], {})[note['id']] = {'id': note['id'], 'title': note['title']}
    for path in (root / 'raw/sources').glob('*/metadata.json'):
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
        all_claims = [c for n in notes(root) for c in n.get('claims', [])]
        all_claims += [c for n in notes(root) for h in n.get('history', []) for c in h.get('previous', {}).get('claims', [])]
        referenced = [e for c in all_claims for e in c.get('evidence', []) if e['source'] == sid]
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
        if sid not in rows or rows[sid].get('stage', 'registered') == 'registered':
            rows[sid] = {**rows.get(sid, {}), 'id': sid, 'url': url, 'stage': 'failed', 'error': result.get('error', '')}
    for sid, row in rows.items():
        row.setdefault('stage', 'registered')
        row['linked_notes'] = list(linked.get(sid, {}).values())
        row['knowledge_status'] = 'deposited' if row['linked_notes'] and row['stage'] == 'complete' and row.get('reviewed') else 'submitted' if row['linked_notes'] else 'unprocessed'
    return sorted(rows.values(), key=lambda r: r.get('updated_at', r.get('collected_at', '')), reverse=True)
