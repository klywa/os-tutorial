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
        if p.get('cardGetDesc'): extra['获取途径'] = plain(p['cardGetDesc'])
        result.append({'id': row['id'], 'name': row['name'], 'category': row['category'],
                       'aliases': row.get('aliases', []), 'effect': row.get('description') or '未提供',
                       'faction': faction(p), 'tier': p.get('quality') if row['category'] == 'heroes' else None,
                       'quality': p.get('quality'), 'awakened': p.get('type') == 9,
                       'skills': skills, 'skills_source': skill_owner['id'] if skills else None,
                       'stats': stats, 'attributes': extra, 'raw_attributes': raw_attributes,
                       'relations': row.get('relations', []),
                       'sources': row.get('sources', []), 'retrieved_at': row.get('retrieved_at'),
                       'version': row.get('version'), 'status': row.get('status', 'official')})
    return result


def render_card(card):
    import json
    lines = [f"# {card['name']}{'（觉醒）' if card['awakened'] else ''}", '',
             f"类别：{CATEGORY_NAMES[card['category']]}", '', f"阵营：{card['faction']['name']}", '',
             f"资料状态：{'待核实' if card['status'] == 'pending' else '官网资料'}", '',
             f"英雄品阶：{card['tier'] if card['tier'] is not None else '未提供'}", '',
             '## 卡牌效果', '', card['effect'], '', '## 技能', '']
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
    lines += ['', '## 官网资料', '', f"同步日期：{card['retrieved_at'] or '未提供'}", '',
              f"游戏版本：{card['version'] or '官网未标明'}", '']
    lines += [f'- [官网数据 {i+1}]({url})' for i, url in enumerate(card['sources'])]
    return '\n'.join(lines) + '\n'


def _save_cards(root, cards):
    for card in cards:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '－', card['name'])[:90]
        ident = card['id'].replace(':', '-')
        card['path'] = f"knowledge/cards/{card['category']}/{name}－{ident}.md"
        wxq.atomic_text(root / card['path'], render_card(card))
    wxq.atomic_json(root / 'knowledge/cards/index.json', {'schema_version': 1, 'cards': cards})


def recover_cards(root):
    root = Path(root); pending = root / 'knowledge/pending-cards.json'
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


def render_transcript(metadata, asr, corrections):
    segments = asr.get('segments', [])
    if not segments: raise ValueError('Missing corrected ASR segments')
    lines = [f"# {metadata['title']}", '', f"来源：{metadata['url']}", '',
             f"分 P：{metadata.get('part', 1)}", '',
             '全文按纠正后的转写顺序保留讲解和实战；待核实词不替换为猜测，转写间隔不补写内容。', '']
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
    with store_lock(root):
        recover(root)
        manifest = wxq.read_json(root / 'raw/index.json', {'schema_version': 1, 'sources': {}})
        folders = [wxq.source_dir(root, sid) for sid in ids] if ids else [
            f for f in (root / 'raw/sources').iterdir()
            if wxq.read_json(f / 'state.json', {}).get('stage') == 'complete']
        for folder in folders:
            try:
                metadata = wxq.read_json(folder / 'metadata.json'); sid = metadata['id']
                raw = folder / 'asr.raw.json'; corrected = folder / 'asr.corrected.json'
                if not raw.exists(): raise ValueError('Missing original ASR')
                text = render_transcript(metadata, wxq.read_json(corrected, {}), wxq.read_json(folder / 'corrections.json', []))
                path = f'raw/{folder.name}.md'; target = root / path
                previous = manifest['sources'].get(sid, {})
                if target.exists() and digest(target.read_bytes()) != previous.get('output_sha256') and target.read_text('utf8') != text:
                    difference = ''.join(difflib.unified_diff(target.read_text('utf8').splitlines(True),
                                        text.splitlines(True), fromfile='现有文字稿', tofile='新生成文字稿'))
                    wxq.atomic_text(root / f'raw/reports/transcript-conflicts/{folder.name}.diff', difference)
                    raise ValueError('文字稿含人工修改，保留原文；差异见transcript-conflicts')
                wxq.atomic_text(target, text)
                manifest['sources'][sid] = {'path': path, 'raw_sha256': digest(raw.read_bytes()),
                    'corrected_sha256': digest(corrected.read_bytes()), 'output_sha256': digest(target.read_bytes())}
                results.append({'source': sid, 'path': path, 'segments': len(wxq.read_json(corrected)['segments'])})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                errors.append({'source': folder.name, 'error': str(exc)})
        wxq.atomic_json(root / 'raw/index.json', manifest)
        report = {'results': results, 'errors': errors}
        wxq.atomic_json(root / 'raw/reports/transcript-export.json', report)
    return report


def transcript_errors(root, sid):
    root = Path(root); row = wxq.read_json(root / 'raw/index.json', {}).get('sources', {}).get(sid)
    if not row: return ['Missing exported transcript: ' + sid]
    target = (root / row['path']).resolve()
    if not target.is_relative_to((root / 'raw').resolve()) or not target.exists():
        return ['Invalid/missing transcript file: ' + sid]
    folder = wxq.source_dir(root, sid)
    for filename, key in [('asr.raw.json', 'raw_sha256'), ('asr.corrected.json', 'corrected_sha256')]:
        if not (folder / filename).exists() or digest((folder / filename).read_bytes()) != row[key]:
            return ['Transcript is stale: ' + sid]
    if digest(target.read_bytes()) != row['output_sha256']: return ['Transcript was manually edited: ' + sid]
    try:
        expected = render_transcript(wxq.read_json(folder / 'metadata.json'),
            wxq.read_json(folder / 'asr.corrected.json'), wxq.read_json(folder / 'corrections.json', []))
        if target.read_text('utf8') != expected: return ['Transcript is stale: ' + sid]
    except (ValueError, KeyError, TypeError, OSError):
        return ['Invalid transcript rendering inputs: ' + sid]
    return []
