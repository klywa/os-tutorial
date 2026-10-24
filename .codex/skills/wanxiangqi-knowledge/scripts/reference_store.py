"""Readable official card reference and faithful, protected transcript exports."""
from copy import deepcopy
import difflib
import hashlib
from pathlib import Path
import re
import wxq

FACTION_IDS = {321: 'dahe', 309: 'sanfen', 320: 'zhulu', 319: 'heluo', 314: 'riluohai'}
FACTION_NAMES = {321: '大河', 309: '三分', 320: '逐鹿', 319: '河洛', 314: '日落海', 307: '无阵营'}
CATEGORY_NAMES = {'heroes': '英雄', 'players': '棋手', 'equipment': '装备', 'talents': '天赋',
                  'derivatives': '衍生物', 'effect-cards': '效果牌', 'player-skills': '棋手技能'}


def plain(value):
    from official import plain as clean
    return clean(value)


def faction(properties):
    rid = properties.get('relationID')
    name = FACTION_NAMES.get(rid, properties.get('relationName') or '未提供')
    return {'id': 'faction:' + FACTION_IDS[rid] if rid in FACTION_IDS else ('faction:none' if rid == 307 else ''),
            'name': name, 'official_id': rid}


def normalize_cards(rows):
    from acquisition import build
    acquisition = build(rows)
    base = {}; counterparts = {}
    for row in rows:
        p = row.get('properties', {})
        if row['category'] == 'heroes' and p.get('type') == 1:
            key = (row['name'], p.get('relationID'), p.get('quality'))
            counterparts.setdefault(key, []).append(row)
        awake = (row.get('properties', {}).get('heroCard') or {}).get('awakeingCard') or {}
        if awake.get('id'):
            base['card:' + str(awake['id'])] = row
    result = []
    for row in rows:
        p = row.get('properties', {}); hero = p.get('heroCard') or {}
        skill_owner = row
        if p.get('type') == 9 and row['id'] not in base:
            matches = counterparts.get((row['name'], p.get('relationID'), p.get('quality')), [])
            if len(matches) == 1: base[row['id']] = matches[0]
        if not hero.get('skillList') and row['id'] in base:
            skill_owner = base[row['id']]
        skills = []
        for skill in (skill_owner.get('properties', {}).get('heroCard') or {}).get('skillList', []):
            skills.append({'id': skill.get('id'), 'name': skill.get('name') or '未提供',
                           'effect': plain(skill.get('desc')),
                           'enhancements': [{'level': item.get('level'), 'effect': plain(item.get('desc'))}
                                            for item in (skill.get('enhanceSkill') or {}).get('params', [])]})
        stat = hero.get('properties') or {}; stats = {}
        for field, label in [('HP', '最大生命值'), ('phyAttack', '物理攻击力'), ('magAttack', '法术攻击力'),
                             ('phyDefense', '物理防御'), ('magDefense', '法术防御'), ('attackDistance', '攻击距离')]:
            if field in stat: stats[label] = stat[field]
        if 'initEnergy' in stat and 'energy' in stat:
            stats['法力值（初始／最大）'] = f"{stat['initEnergy']}/{stat['energy']}"
        if 'attackSpeed' in stat: stats['攻击速度'] = stat['attackSpeed'] / 10000
        if 'criticalRate' in stat: stats['暴击率'] = f"{stat['criticalRate'] / 100:g}%"
        if 'criticalEffect' in stat: stats['暴击效果'] = f"{100 + stat['criticalEffect'] / 100:g}%"
        extra = {}; raw_attributes = {}
        for container in ['equipCard', 'talentCard', 'effectCard']:
            for key, value in (p.get(container) or {}).items():
                if value is not None: raw_attributes[key] = value
        for key, label in [('atlasSubTypeName', '装备分类'), ('equipTypeName', '装备类型'),
                           ('grpName', '所属分组'), ('grpDesc', '解锁条件')]:
            if raw_attributes.get(key): extra[label] = plain(raw_attributes[key])
        if p.get('talentStageDesc'): extra['拍卖轮次（官网原文）'] = p['talentStageDesc']
        if p.get('cardGetDesc') and row['category'] != 'heroes': extra['获得途径'] = plain(p['cardGetDesc'])
        result.append({'id': row['id'], 'name': row['name'], 'category': row['category'],
                       'aliases': row.get('aliases', []), 'effect': row.get('description') or '未提供',
                       'faction': faction(p), 'tier': p.get('quality') if row['category'] == 'heroes' else None,
                       'quality': p.get('quality'), 'awakened': p.get('type') == 9,
                       'skills': skills, 'skills_source': skill_owner['id'] if skills else None,
                       'stats': stats, 'attributes': extra, 'raw_attributes': raw_attributes,
                       'relations': row.get('relations', []),
                       'sources': row.get('sources', []), 'retrieved_at': row.get('retrieved_at'),
                       'version': row.get('version'), 'status': row.get('status', 'official'),
                       **acquisition.get(row['id'], {})})
    return result


def render_card(card):
    import json
    lines = [f"# {card['name']}{'（觉醒）' if card['awakened'] else ''}", '',
             f"类别：{CATEGORY_NAMES[card['category']]}", '', f"阵营：{card['faction']['name']}", '',
             f"资料状态：{'待核实' if card['status'] == 'pending' else '官网资料'}", '',
             f"英雄品阶：{card['tier'] if card['tier'] is not None else '未提供'}", '',
             '## 卡牌效果', '', card['effect'], '', '## 技能', '']
    if card.get('routes'):
        lines[12:12] = ['获得途径：'+' '.join(r['text'] for r in card['routes']), '']
    if card.get('other_uses'):
        lines[12:12] = ['其他作用：'+card['other_uses'], '']
    if card['skills_source'] and card['skills_source'] != card['id']:
        lines += [f"官网未单独提供本觉醒卡技能；以下为对应普通英雄（{card['skills_source']}）技能，不代表额外觉醒强化。", '']
    for s in card['skills']:
        lines += [f"### {s['name']}", '', s['effect'] or '未提供', '']
        lines += [f"- {e['level']}级：{e['effect']}" for e in s['enhancements']] + ['']
    if not card['skills']: lines += ['未提供', '']
    lines += ['## 基础属性', ''] + ([f'- {k}：{v}' for k, v in card['stats'].items()] or ['未提供'])
    lines += ['', '## 其他官方属性', '']
    lines += ([f'- {k}：{json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}'
               for k, v in card['attributes'].items()] or ['未提供'])
    return '\n'.join(lines) + '\n'


def save_json_cards(root, cards, evidence_refs=None):
    import json_document, json_store
    root = Path(root); rows = []
    for card in cards:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '－', card['name'])[:90]
        path = f"knowledge/cards/{card['category']}/{name}－{card['id'].replace(':', '-')}.json"
        body = json_document.parse(render_card(card))
        old_body=json_store.read(root/path,{})
        previous={}
        for node in old_body.get('nodes',[]):
            signature=(node['type'],node.get('title'),node.get('key'),node.get('value'))
            previous.setdefault(signature,[]).append(node['id'])
        used=set()
        reused=set()
        for node in body['nodes']:
            signature=(node['type'],node.get('title'),node.get('key'),node.get('value'))
            candidates=previous.get(signature,[])
            if candidates:
                node['id']=candidates.pop(0);reused.add(node['id'])
            if node['id'] in used:
                node['id']='n-'+hashlib.sha256((card['id']+repr(signature)).encode()).hexdigest()[:20]
            used.add(node['id'])
        # Reviewed acquisition prose can change while the field keeps its identity.
        enrichment_ids={n.get('key'):n['id'] for n in old_body.get('nodes',[])
                        if n.get('key') in ('获得途径','其他作用') and n['id'] not in reused}
        for node in body['nodes']:
            previous_id=enrichment_ids.get(node.get('key'))
            if previous_id and node['id'] not in reused:
                used.discard(node['id']);node['id']=previous_id
                used.add(previous_id);reused.add(previous_id)
        # An official effect can change wording or even parse as a different
        # key. Its card/section position still identifies the same field.
        def locations(nodes):
            headings=[];count={};located=[]
            for n in nodes:
                if n['type']=='heading':
                    while headings and headings[-1][0]>=n['level']:headings.pop()
                    headings.append((n['level'],n['title']))
                elif n.get('key') not in ('获得途径','其他作用'):
                    section=tuple(headings);position=count.get(section,0);count[section]=position+1
                    located.append((section,position,n))
            return located
        available={(s,p):n['id'] for s,p,n in locations(old_body.get('nodes',[])) if n['id'] not in reused}
        for section,position,node in locations(body['nodes']):
            previous_id=available.get((section,position))
            if node['id'] not in reused and previous_id:
                used.discard(node['id']);node['id']=previous_id;used.add(previous_id);reused.add(previous_id)
        texts = {n['value']: n['id'] for n in body['nodes'] if n['type'] == 'entry'}
        def intern(value):
            if isinstance(value, str) and value in texts:return {'$text': texts[value]}
            if isinstance(value, dict):return {k: intern(v) for k, v in value.items()}
            if isinstance(value, list):return [intern(v) for v in value]
            return value
        body['semantics'] = intern({k: v for k, v in card.items() if k not in ('sources', 'retrieved_at', 'version', 'path')})
        meta = {k: card.get(k) for k in ('id', 'sources', 'retrieved_at', 'version')}
        previous_meta=json_store.read(root/json_store.meta_path(path),{})
        if old_body and old_body!=body:
            meta['history']=[*previous_meta.get('history',[]),{'body':old_body,'sources':previous_meta.get('sources',[])}]
        elif previous_meta.get('history'):meta['history']=previous_meta['history']
        if evidence_refs:
            meta['acquisition_evidence']={r['text']:[evidence_refs[i] for i in r['evidence_ids'] if i in evidence_refs] for r in card.get('routes',[])}
            if card.get('other_uses'):
                meta['other_uses_evidence']=[evidence_refs[card['id']]] if card['id'] in evidence_refs else []
        meta.update(path=path, body_sha256=json_store.digest(body))
        json_store.write_file(root / path, body)
        json_store.write_file(root / json_store.meta_path(path), meta)
        rows.append({'id': card['id'], 'path': path})
    json_store.write_file(root / 'knowledge/cards/index.meta.json', {'schema_version': 6, 'cards': rows})


def json_cards(root):
    import json_store
    root = Path(root); result = []
    pending = json_store.read(root / 'raw/knowledge/pending-cards.json')
    if pending:return pending['cards']
    for row in json_store.read(root / 'knowledge/cards/index.meta.json', {'cards': []})['cards']:
        path = json_store.target(root, row['path'])
        body = json_store.read(path)
        meta = json_store.read(root / json_store.meta_path(row['path']))
        if not body or not meta or json_store.digest(body) != meta['body_sha256']:
            raise ValueError('卡牌正文与附件不一致：' + row['id'])
        texts = {n['id']: n.get('value', n.get('title', '')) for n in body['nodes']}
        card = json_store.resolve_value(body['semantics'], texts)
        card.update({k: v for k, v in meta.items() if k != 'body_sha256'})
        result.append(card)
    return result


def _save_cards(root, cards):
    import json_store
    if json_store.enabled(root):
        from acquisition import register_snapshot
        return save_json_cards(root, cards, register_snapshot(root, wxq.entities(root), locked=True))
    for card in cards:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '－', card['name'])[:90]
        ident = card['id'].replace(':', '-')
        card['path'] = f"knowledge/cards/{card['category']}/{name}－{ident}.md"
        wxq.atomic_text(root / card['path'], render_card(card))
    wxq.atomic_json(root / 'knowledge/cards/index.json', {'schema_version': 1, 'cards': cards})


def recover_cards(root):
    root = Path(root); pending = wxq.storage_path(root / 'knowledge/pending-cards.json')
    data = wxq.read_json(pending)
    if data:
        validate_cards(data['cards'])
        _save_cards(root, data['cards']); pending.unlink()


def export_cards(root):
    from workspace import store_lock
    root = Path(root)
    with store_lock(root):
        recover_cards(root)
        cards = normalize_cards(wxq.entities(root))
        validate_cards(cards)
        wxq.atomic_json(root / 'knowledge/pending-cards.json', {'cards': cards})
        recover_cards(root)
    return {'cards': len(cards)}


def validate_cards(cards):
    for card in cards:
        if card['category'] not in wxq.CATEGORIES or not re.fullmatch(r'(card|player|pending):[\w:-]+', card['id']):
            raise ValueError('Invalid card transaction')


def enrich_meta(meta, rows):
    result = deepcopy(meta); heroes = {r['id']: r for r in rows if r.get('category') == 'heroes'}
    members = {i: '核心英雄' for i in result.get('core_heroes', [])}
    for stage in ['middle', 'late']:
        for member in result.get('compositions', {}).get(stage, []):
            if member['necessity'] == 'required': members[member['hero']] = member.get('role') or '必需英雄'
    dependencies = {}
    for eid, role in members.items():
        if eid not in heroes: continue
        row = heroes[eid]; f = faction(row.get('properties', {}))
        if f['official_id'] in FACTION_IDS: dependencies.setdefault(f['id'], []).append(f"{row['name']}（{role}）")
    required = set(result.get('required_factions', []))
    conditions = {}
    for condition in result.get('ban_conditions', []):
        f = condition['faction']
        if condition.get('derived_dependency'):
            if not condition.get('explicit_required'): required.discard(f)
            if condition.get('explicit_condition') is not None:
                conditions[f] = deepcopy(condition['explicit_condition'])
        elif condition.get('reason', '').startswith('完整阵容无法获取：'):
            # Migrate exports from before derivation provenance was recorded.
            required.discard(f)
            original = condition['reason'].partition(' 原条件说明：')[2]
            if original:
                conditions[f] = {'faction': f, 'status': 'unknown', 'reason': original}
        else:
            conditions[f] = deepcopy(condition)
    explicit_required = set(required)
    result['required_factions'] = sorted(required | set(dependencies))
    for f, members in dependencies.items():
        previous = conditions.get(f, {})
        reason = '完整阵容无法获取：' + '、'.join(members) + '。'
        if previous.get('reason') and previous['reason'] != reason:
            reason += ' 原条件说明：' + previous['reason']
        conditions[f] = {'faction': f, 'status': 'unplayable', 'reason': reason,
                         'derived_dependency': True, 'explicit_required': f in explicit_required,
                         'explicit_condition': previous or None}
    result['ban_conditions'] = list(conditions.values())
    if result.get('late_variants'):
        from tactics import enrich
        result = enrich(result, rows)
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stamp(seconds):
    seconds = round(seconds, 2); minutes = int(seconds // 60)
    return f'{minutes:02d}:{seconds % 60:05.2f}'


def transcript_artifacts(folder):
    folder = Path(folder)
    subtitle = wxq.read_json(folder / 'metadata.json', {}).get('transcript_origin') == 'bilibili_subtitle'
    prefix = 'subtitle' if subtitle else 'asr'
    return folder / (prefix + '.raw.json'), folder / (prefix + '.corrected.json')


def transcript_has_evidence(folder):
    raw, corrected = transcript_artifacts(folder)
    original = wxq.read_json(raw, {})
    return bool(original.get('body' if raw.name == 'subtitle.raw.json' else 'segments') and
                wxq.read_json(corrected, {}).get('segments'))


def render_transcript(metadata, asr, corrections):
    segments = asr.get('segments', [])
    if not segments:
        if 'segments' not in asr or not asr.get('model'):
            raise ValueError('Missing corrected ASR segments')
        return f"# {metadata['title']}\n\n来源：{metadata['url']}\n\n未检测到语音。\n"
    lines = [f"# {metadata['title']}", '', f"来源：{metadata['url']}", '',
             f"分 P：{metadata.get('part', 1)}", '',
             '全文按纠正后的转写顺序保留讲解和实战；待核实词不替换为猜测，转写间隔不补写内容。', '']
    if metadata.get('transcript_origin') == 'bilibili_subtitle':
        lines[6:6] = ['文字稿来源：B站字幕（' + ('自动生成' if asr.get('automatic') else '人工提供') + '，' + asr.get('language', '中文') + '），待核对。', '']
    previous = 0; previous_start = -1
    for s in segments:
        a, b = s['start'], s['end']
        if not 0 <= a <= b <= metadata.get('duration', b) + 1 or a < previous_start:
            raise ValueError('Invalid transcript time order/range')
        if a - previous > 20:
            lines += [f"> 转写间隔 {stamp(previous)}–{stamp(a)}：可能为静音或漏识别，未补写。", '']
        lines += [f"## {stamp(a)}–{stamp(b)}", '', s['text'], '']
        candidates = sorted({f"{c.get('original')} → {c.get('candidate')}" for c in corrections
                             if c.get('segment') == s.get('id') and c.get('status') in
                             ['needs_context_review', 'ambiguous']})
        if candidates: lines += ['> 待核实候选（未采用）：' + '；'.join(candidates), '']
        previous = max(previous, b); previous_start = a
    return '\n'.join(lines) + '\n'


def export_transcripts(root, ids=None):
    from workspace import store_lock, recover
    root = Path(root); results = []; errors = []
    with store_lock(root, wait=True):
        recover(root)
        manifest = wxq.read_json(root / 'raw/index.json', {'schema_version': 1, 'sources': {}})
        folders = [wxq.source_dir(root, sid) for sid in ids] if ids else [
            f for f in (root / 'raw/sources').iterdir()
            if wxq.read_json(f / 'state.json', {}).get('stage') == 'complete']
        for folder in folders:
            try:
                metadata = wxq.read_json(folder / 'metadata.json'); sid = metadata['id']
                raw, corrected = transcript_artifacts(folder)
                if not raw.exists(): raise ValueError('Missing original ASR')
                text = render_transcript(metadata, wxq.read_json(corrected, {}), wxq.read_json(folder / 'corrections.json', []))
                path = f'raw/{folder.name}.md'; target = root / path
                previous = manifest['sources'].get(sid, {})
                if previous.get('manual_edit'):
                    if not target.is_file():raise ValueError('人工文字稿文件缺失，保留索引等待恢复')
                    results.append({'source':sid,'path':previous['path'],'manual_edit':True})
                    continue
                if target.exists() and digest(target.read_bytes()) != previous.get('output_sha256') and target.read_text('utf8') != text:
                    difference = ''.join(difflib.unified_diff(target.read_text('utf8').splitlines(True),
                                        text.splitlines(True), fromfile='现有文字稿', tofile='新生成文字稿'))
                    wxq.atomic_text(root / f'raw/reports/transcript-conflicts/{folder.name}.diff', difference)
                    raise ValueError('文字稿含人工修改，保留原文；差异见transcript-conflicts')
                wxq.atomic_text(target, text)
                manifest['sources'][sid] = {'path': path, 'transcript_origin': metadata.get('transcript_origin', 'local_asr'), 'raw_sha256': digest(raw.read_bytes()),
                    'corrected_sha256': digest(corrected.read_bytes()), 'output_sha256': digest(target.read_bytes())}
                results.append({'source': sid, 'path': path, 'segments': len(wxq.read_json(corrected)['segments'])})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                errors.append({'source': folder.name, 'error': str(exc)})
        wxq.atomic_json(root / 'raw/index.json', manifest)
        report = {'results': results, 'errors': errors}
        wxq.atomic_json(root / 'raw/reports/transcript-export.json', report)
    return report


def repair_transcript_index(root, sid):
    """Upgrade legacy provenance only when the existing output can be verified."""
    from workspace import store_lock
    root = Path(root)
    with store_lock(root, wait=True):
        path = root / 'raw/index.json'
        manifest = wxq.read_json(path, {})
        row = manifest.get('sources', {}).get(sid)
        if not row:
            return False
        folder = wxq.source_dir(root, sid)
        target = (root / row.get('path', '')).resolve()
        if not target.is_relative_to((root / 'raw').resolve()) or not target.is_file():
            return False
        try:
            raw, corrected = transcript_artifacts(folder)
            hashes = {'raw_sha256': digest(raw.read_bytes()),
                      'output_sha256': digest(target.read_bytes())}
            legacy_raw = row.get('transcript_file') == 'asr.raw.json' and row.get('raw_sha256') == hashes['raw_sha256'] and row.get('output_sha256') == hashes['output_sha256']
            if not legacy_raw:
                hashes['corrected_sha256'] = digest(corrected.read_bytes())
            if any(row.get(k) and row[k] != v for k, v in hashes.items()):
                return False
            if not legacy_raw:
                expected = render_transcript(wxq.read_json(folder / 'metadata.json'),
                    wxq.read_json(corrected), wxq.read_json(folder / 'corrections.json', []))
                if target.read_text('utf8') != expected:
                    return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        backup = root / 'raw/reports/index-upgrades' / (folder.name + '.json')
        if not backup.exists():
            wxq.atomic_json(backup, row)
        row.update(hashes)
        if legacy_raw:
            row['export_format'] = 'legacy_raw'
        wxq.atomic_json(path, manifest)
        return True


def transcript_errors(root, sid):
    root = Path(root); row = wxq.read_json(root / 'raw/index.json', {}).get('sources', {}).get(sid)
    if not row: return ['Missing exported transcript: ' + sid]
    target = (root / row.get('path', '')).resolve()
    if not target.is_relative_to((root / 'raw').resolve()) or not target.exists():
        return ['Invalid/missing transcript file: ' + sid]
    folder = wxq.source_dir(root, sid)
    raw, corrected = transcript_artifacts(folder)
    for filename, key in [(raw.name, 'raw_sha256'), (corrected.name, 'corrected_sha256')]:
        if row.get('export_format') == 'legacy_raw' and filename == 'asr.corrected.json':
            continue  # This registered export explicitly uses original ASR, not corrected ASR.
        if not row.get(key):
            return ['Transcript index needs verification: ' + sid]
        if not (folder / filename).exists() or digest((folder / filename).read_bytes()) != row[key]:
            return ['Transcript is stale: ' + sid]
    if not row.get('output_sha256'): return ['Transcript index needs verification: ' + sid]
    if digest(target.read_bytes()) != row['output_sha256']: return ['Transcript was manually edited: ' + sid]
    if row.get('manual_edit'): return []
    if row.get('export_format') == 'legacy_raw': return []
    try:
        expected = render_transcript(wxq.read_json(folder / 'metadata.json'),
            wxq.read_json(corrected), wxq.read_json(folder / 'corrections.json', []))
        if target.read_text('utf8') != expected: return ['Transcript is stale: ' + sid]
    except (ValueError, KeyError, TypeError, OSError):
        return ['Invalid transcript rendering inputs: ' + sid]
    return []


def transcript_target(root, sid, manifest):
    row=manifest.get('sources',{}).get(sid)
    if not row:raise KeyError('文字稿尚未生成')
    path=(Path(root)/row.get('path','')).resolve()
    if not path.is_relative_to((Path(root)/'raw').resolve()) or not path.is_file():raise KeyError('文字稿文件不存在或路径无效')
    return row,path


def recover_transcript_edits(root):
    """Caller owns the workspace lock. Roll back an interrupted two-file save."""
    root=Path(root);journal=root/'raw/transcript-edit-pending.json'
    pending=wxq.read_json(journal)
    if not pending:return
    row,path=transcript_target(root,pending['source'],pending['manifest'])
    if str(path.relative_to(root.resolve()))!=pending['path']:raise ValueError('文字稿恢复路径不一致')
    wxq.atomic_text(path,pending['text'])
    wxq.atomic_json(root/'raw/index.json',pending['manifest'])
    journal.unlink()


def transcript_snapshot(root, sid):
    from workspace import store_lock
    root=Path(root)
    journal=root/'raw/transcript-edit-pending.json'
    index=root/'raw/index.json'
    # Unrelated source saves need not block an atomic, stable transcript read.
    for _ in range(3):
        if journal.is_file():break
        row,path=transcript_target(root,sid,wxq.read_json(index,{}))
        text=path.read_text('utf-8')
        if not journal.is_file() and wxq.read_json(index,{}).get('sources',{}).get(sid)==row:
            return {'source':sid,'path':str(path),'text':text,'revision':digest(text.encode('utf-8')),'manual_edit':bool(row.get('manual_edit'))}
    with store_lock(root,wait=True):
        recover_transcript_edits(root)
        row,path=transcript_target(root,sid,wxq.read_json(root/'raw/index.json',{}))
        text=path.read_text('utf-8')
        return {'source':sid,'path':str(path),'text':text,'revision':digest(text.encode('utf-8')),'manual_edit':bool(row.get('manual_edit'))}


def save_transcript(root, sid, payload):
    from workspace import store_lock, Conflict
    import copy
    import uuid
    root=Path(root).resolve()
    if set(payload)-{'text','revision'}:raise ValueError('文字稿仅允许通过来源ID编辑正文')
    if not isinstance(payload.get('text'),str) or not payload['text'].strip():raise ValueError('文字稿正文不能为空')
    with store_lock(root,wait=True):
        recover_transcript_edits(root)
        index=root/'raw/index.json';manifest=wxq.read_json(index,{})
        row,path=transcript_target(root,sid,manifest);old=path.read_text('utf-8')
        if payload.get('revision')!=digest(old.encode('utf-8')):raise Conflict('文字稿已被修改，请刷新后重新编辑；草稿仍保留')
        previous=copy.deepcopy(manifest)
        backup=root/'raw/reports/transcript-edits'/wxq.safe_id(sid.replace(':','_'))/(uuid.uuid4().hex+'.md')
        wxq.atomic_text(backup,old)
        journal=root/'raw/transcript-edit-pending.json'
        wxq.atomic_json(journal,{'source':sid,'path':str(path.relative_to(root)),'text':old,'manifest':previous})
        row.update(output_sha256=digest(payload['text'].encode('utf-8')),manual_edit={'at':wxq.now(),'backup':str(backup.relative_to(root))})
        try:
            wxq.atomic_text(path,payload['text'])
            wxq.atomic_json(index,manifest)
            journal.unlink()
        except Exception:
            recover_transcript_edits(root)
            raise
        return {'source':sid,'path':str(path),'text':payload['text'],'revision':row['output_sha256'],'manual_edit':True}
