"""Read-only coverage of the current canonical note bodies."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import threading

import json_store as store
from reader_store import signature
from workspace import Busy, store_lock


FIELDS = (
    ('rhythm', '运营节奏'), ('heroes', '英雄'), ('auction', '拍卖'),
    ('equipment', '关键装备'), ('talents', '推荐天赋'),
    ('counter', '克制方法'), ('operations', '关键操作'),
)
_cache = {}
_guard = threading.Lock()


def field_for(title, parents=()):
    title = re.sub(r'[【】\[\]*\s]', '', title)
    title = re.split(r'[：:]', title)[-1]
    if title in {'运营节奏', '阵容组成与运营节奏', '运营路线比较', '运营路线选择',
                 '运营路线与后期组合', '前中后期共通流程', '成型后提升思路', '后期提升思路'}:
        return 'rhythm'
    if title in {'前期', '中期', '后期'} and any('路线' in p for p in parents):
        return 'rhythm'
    if (re.match(r'^(前期|中期|后期)(英雄组成与运营|运营)', title)
            or title == '三分控的运营与补充成员'):
        return 'rhythm'
    if title == '英雄':
        return 'heroes'
    if (title in {'拍卖', '三轮拍卖', '拍卖选择', '拍卖补充'}
            or re.match(r'^第[一二三123]轮拍卖', title) or title.endswith('分支拍卖')):
        return 'auction'
    if title in {'关键装备', '推荐装备', '装备选择', '其他装备选择'} or title.endswith('分支装备'):
        return 'equipment'
    if title in {'推荐天赋', '推荐天赋及原因', '天赋选择', '条件天赋与后期资源', '天赋与后期提升'}:
        return 'talents'
    if title in {'克制手段', '克制方法', '克制与风险'}:
        return 'counter'
    if title in {'关键操作', '关键操作顺序'}:
        return 'operations'
    return None


def substantive(text):
    """Discard gap-only clauses, not paragraphs that also contain advice.

    These deterministic rules measure presence, not correctness/completeness.
    Entry labels and table identity cells alone never establish coverage.
    """
    text = re.sub(r'!?\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'<[^>]*>', '', text)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if '|' in line:
            # Header and separator rows do not contain recommendations.
            if re.fullmatch(r'[\s|:\-]+', line):
                continue
            if i + 1 < len(lines) and re.fullmatch(r'[\s|:\-]+', lines[i + 1]):
                continue
            cells = line.strip().strip('|').split('|')
            line = '；'.join(cells[1:]) if len(cells) > 1 else ''
        line = re.sub(r'[*_`#>【】\[\]]', '', line)
        for clause in re.split(r'[。！？；;\n，,]', line):
            clause = re.sub(r'^\s*(?:[-+•]|\d+[.)、])\s*', '', clause).strip(' \t：:。.、-—')
            if not re.search(r'[\w\u4e00-\u9fff]{2}', clause):
                continue
            if re.match(r'^(?:不要|不必|无需|不用|没有必要|不需要).{2}', clause):
                return True
            if re.search(r'待(?:补充|完善|整理|核对|确认|验证|收集|研究|考证|裁决)', clause):
                continue
            if re.search(r'(?:尚未|未|尚缺|缺少|暂无|暂缺|没有).{0,12}(?:整理|确认|核对|统计|收录|提供|覆盖|结论|策略|建议|资料|证据|来源|内容|信息|数据|说明|补充)', clause):
                continue
            if re.search(r'(?:^|[：:])(?:暂无|暂缺|未知|无|不详|待定|待续|待补|未整理|未确认|未覆盖|N/?A|TBD|TODO)$', clause, re.I):
                continue
            if re.match(r'^(?:详见|参见|参考|来源|见下文|见上文|同上|关联知识)(?:$|[：:\s])', clause):
                continue
            return True
    return False


def coverage(body):
    results = {key: {'covered': False, 'section': None, 'node_id': None} for key, _ in FIELDS}
    stack = []
    for node in body['nodes']:
        if node['type'] == 'heading':
            while stack and stack[-1]['level'] >= node['level']:
                stack.pop()
            stack.append(node)
            # Only chapters, never opening metadata, establish a field.
            if node['level'] >= 2:
                key = field_for(node['title'], [h['title'] for h in stack[:-1]])
                if key and results[key]['node_id'] is None:
                    results[key].update(section=node['title'], node_id=node['id'])
        elif node['type'] == 'entry':
            if re.match(r'^(?:来源|视频来源|参考资料|参考来源|参考链接|引用|证据|关联知识|相关链接)', node.get('key', '').strip('*【】[]：: ')):
                continue
            matches = [(h, field_for(h['title'], [p['title'] for p in stack[:i]])) for i, h in enumerate(stack) if h['level'] >= 2]
            matches = [(h, key) for h, key in matches if key]
            if matches and substantive(node.get('value', '')):
                h, key = matches[-1]
                if h['title'] == '克制与风险' and not any(
                    substantive(sentence) and re.search(
                        r'可用|可以用|优先用|通过|利用|针对|集火|打断|限制|切断|阻止|绕过|破解|克制|压制其|控制其|控制对手', sentence)
                    for sentence in re.split(r'[。！？；;\n]', node.get('value', ''))
                ):
                    continue
                if not results[key]['covered']:
                    results[key].update(covered=True, section=h['title'], node_id=h['id'])
    return results


def fingerprint(root, rows):
    return (tuple(signature(root / store.INDEX) or ()),
            tuple(signature(root / store.JOURNAL) or ()),
            tuple((row['id'], tuple(signature(store.target(root, row['path'])) or ()))
                  for row in rows))


def _read(path, label):
    try:
        value = store.read(path)
        if not isinstance(value, dict):
            raise ValueError('不是JSON对象')
        return value
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f'看板读取失败：{label}（{exc}）') from exc


def _all_snapshot(root):
    root = Path(root).resolve()
    with store_lock(root):
        if (root / store.JOURNAL).exists():
            raise Busy('知识库正在更新，请稍后刷新看板')
        for _ in range(3):
            index_stamp = signature(root / store.INDEX)
            index = _read(root / store.INDEX, store.INDEX)
            if not isinstance(index.get('notes'), list):
                raise ValueError('看板读取失败：知识索引缺少笔记列表')
            rows = list({r['id']: r for r in index['notes'] if r['type'] in ('player', 'lineup')}.values())
            try:
                stamp = fingerprint(root, rows)
                if signature(root / store.INDEX) != index_stamp:
                    continue
                cache_key = str(root)
                with _guard:
                    cached = _cache.get(cache_key)
                if cached and cached[0] == stamp and fingerprint(root, rows) == stamp:
                    return deepcopy(cached[1])
                notes = []
                for row in rows:
                    body = _read(store.target(root, row['path']), row['path'])
                    if not isinstance(body.get('nodes'), list) or any(
                        not isinstance(n, dict) or n.get('type') not in ('heading', 'entry')
                        or not isinstance(n.get('id'), str)
                        or (n['type'] == 'heading' and (not isinstance(n.get('title'), str) or not isinstance(n.get('level'), int)))
                        or (n['type'] == 'entry' and not isinstance(n.get('value'), str))
                        for n in body['nodes']
                    ):
                        raise ValueError(f'看板读取失败：{row["path"]} 正文节点无效')
                    if row['type'] != 'lineup':
                        continue
                    fields = coverage(body)
                    count = sum(f['covered'] for f in fields.values())
                    notes.append({'id': row['id'], 'title': row['title'], 'player_id':row.get('player_id'), 'covered': count,
                                  'rate': count / len(FIELDS), 'fields': fields})
                if fingerprint(root, rows) != stamp:
                    continue
            except (OSError, ValueError) as exc:
                if signature(root / store.INDEX) != index_stamp:
                    continue
                raise ValueError(str(exc)) from exc
            n = len(notes)
            count = sum(note['covered'] for note in notes)
            result = {
                'revision': store.digest(stamp),
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'counts': {'player': sum(r['type'] == 'player' for r in rows), 'lineup': n},
                'summary': {'covered': count, 'total': n * len(FIELDS), 'rate': count / (n * len(FIELDS)) if n else None},
                'fields': [{'id': key, 'label': label,
                            'covered': sum(note['fields'][key]['covered'] for note in notes),
                            'total': n,
                            'rate': sum(note['fields'][key]['covered'] for note in notes) / n if n else None}
                           for key, label in FIELDS],
                'notes': notes,
            }
            with _guard:
                if len(_cache) >= 8:
                    _cache.pop(next(iter(_cache)))
                _cache[cache_key] = (stamp, result)
            return deepcopy(result)
    raise Busy('知识库正在更新，请稍后刷新看板')


def snapshot(root,scope='all'):
    if scope not in ('all','usage_top10','usage_top20','usage_top50'):raise ValueError('未知看板筛选范围')
    result=_all_snapshot(root)
    if scope!='all':
        from lineup_usage import project
        return project(root,result,scope)
    return result
