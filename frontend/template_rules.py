"""Bridge the portable text rules, legacy selectors and the editor's tree."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE = ROOT / 'src/condition/catalog.json'
RULE_FIELDS = {'expression', 'condition_tree', 'editor_mode', 'priority'}
EXPLANATION_PREFIX = '解释为何'
REMINDER_CATEGORY = '针对与提醒'
REMINDER_EVENT_IDS = {
    'lineup_ready', 'health_crisis', 'player_streak', 'opponent_streak',
    'dangerous_opponent', 'opponent_equipment', 'key_card_acquired',
    'key_card_shop', 'auction_start',
}
CATEGORY_TYPES = {'heroes':'英雄', 'equipment':'装备', 'effect-cards':'效果牌',
                  'players':'棋手', 'talents':'天赋', 'player-skills':'棋手技能', 'derivatives':'衍生物'}


def catalog():
    return json.loads(SOURCE.read_text(encoding='utf-8'))


def explanation_event(event):
    if event['id'] in REMINDER_EVENT_IDS:
        name = event['name'].removeprefix(EXPLANATION_PREFIX)
        return {**event, 'name': name, 'category': REMINDER_CATEGORY}
    if event.get('category') == REMINDER_CATEGORY:
        return event
    name = EXPLANATION_PREFIX + event['name'].removeprefix(EXPLANATION_PREFIX)
    return {**event, 'name': name, 'category': '解释类'}


def resolve_event(events, name, event_id=None):
    """Resolve an old portable name without guessing between competing events."""
    unprefixed = name.removeprefix(EXPLANATION_PREFIX)
    exact = [e for e in events if e['name'] == name]
    candidates = exact or [e for e in events if e['name'].removeprefix(EXPLANATION_PREFIX) == unprefixed]
    if event_id:
        by_id = next((e for e in events if e['id'] == event_id), None)
        if by_id and by_id in candidates:
            return by_id
    if len(candidates) > 1:
        raise ValueError('事件名称有歧义：'+name)
    return candidates[0] if candidates else None


def parameter_type(p):
    if 'dsl_type' in p:
        return p['dsl_type']
    if p['type'] == 'entity':
        return '|'.join(CATEGORY_TYPES[c] for c in p.get('entity_categories',CATEGORY_TYPES))
    return {'number':'number','boolean':'bool','text':'string'}[p['type']]


def definition(event):
    if not isinstance(event,dict) or not isinstance(event.get('parameters'),list):
        raise ValueError('事件参数必须为列表')
    for p in event['parameters']:
        if not isinstance(p,dict) or not isinstance(p.get('key'),str) or p.get('type') not in ('text','number','boolean','entity'):
            raise ValueError('事件参数缺少参数键或有效类型')
    return {'category':event.get('category','未分类'),
            'parameters':{p['key']:parameter_type(p) for p in event['parameters']}}


def library_catalog(events, *, root=None):
    result = catalog()
    result.pop('card_tags_file', None)
    if root is not None:
        from card_tags import effective_tags
        result['card_tags'] = effective_tags(root)
    result['events'] = {event['name']:definition(event) for event in events}
    return result


def disambiguate_existing(events, defaults):
    """Keep workbook names and all existing group-to-event bindings on upgrade."""
    reserved={e['name'] for e in events}
    used=set()
    changed={}
    def rank(event):
        default=defaults.get(event['id'])
        return (not (default and event['name']==default['name']),event['id'])
    for event in sorted(events,key=rank):
        name=event['name']
        if name in used:
            suffix=1
            while f'{name}（兼容 {suffix}）' in reserved:suffix+=1
            event['name']=f'{name}（兼容 {suffix}）'
            reserved.add(event['name'])
            changed[event['id']]=event
        used.add(event['name'])
    return changed


def check_type(value, source):
    def known(t):
        return t in {'string','int','number','bool'} or t in source['types'] or t in source['aliases']
    if not isinstance(value,str):
        raise ValueError('参数类型须为文本')
    members = (value[6:-1] if value.startswith('Array<') and value.endswith('>') else value).split('|')
    if not all(known(t) for t in members):
        raise ValueError('未知参数类型：'+value)
    if len(members)>1 and any(t in {'string','int','number','bool'} for t in members):
        raise ValueError('联合类型只允许命名实体：'+value)


def parameter(key, typ):
    category = next((c for c,t in CATEGORY_TYPES.items() if t == typ), None)
    kind = 'entity' if category or typ == '单位' else {'int':'number','number':'number','bool':'boolean'}.get(typ,'text')
    result = {'key':key,'name':key,'type':kind,'dsl_type':typ}
    if category: result['entity_categories'] = [category]
    return result


def parse_signature(signature):
    if not isinstance(signature,str):raise ValueError('事件签名必须为文本')
    name,opening,tail=signature.strip().rpartition('(')
    if not opening or not name.strip() or not tail.endswith(')'):
        raise ValueError('事件签名格式应为 事件名(参数: 类型)')
    params={}
    source=catalog()
    body=tail[:-1].strip()
    for entry in body.split(',') if body else []:
        key,colon,typ=entry.partition(':')
        key=key.strip()
        typ=re.sub(r'\s*([|<>])\s*',r'\1',typ.strip())
        if not colon or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',key) or key in params:
            raise ValueError('签名中的参数键无效或重复：'+key)
        check_type(typ,source)
        params[key]=typ
    return name.strip(),params


def workbook_events():
    events = []
    for name, data in catalog()['events'].items():
        eid = 'os_' + hashlib.sha256(name.removeprefix(EXPLANATION_PREFIX).encode()).hexdigest()[:16]
        params=[{**parameter(k,t),'id':'p_'+k} for k,t in data['parameters'].items()]
        events.append({'id':eid,'name':name,'category':data['category'],'parameters':params})
    return events


def operand(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def legacy_tree(conditions, event, entities=None):
    params = {p['key']:p for p in event['parameters']}
    def leaf(key, op, value):
        return {'kind':'leaf','left':key,'operator':op,'right':operand(value)}
    children = []
    for condition in conditions:
        key, op, value = (condition[k] for k in ('parameter_key','operator','value'))
        if op == 'between':
            children.extend([leaf(key, '>=', value[0]), leaf(key, '<=', value[1])])
            continue
        kind = params[key]['type']
        if kind == 'entity':
            row=(entities or {}).get(value['id'],{})
            name=row.get('name') or value['name']
            typ=parameter_type(params[key])
            if '|' in typ:
                category=CATEGORY_TYPES.get(row.get('category'))
                if not category:raise ValueError('缺少旧实体的类别：'+name)
                value={'类型':category,'名称':name}
            else:
                key += '.名称'
                value=name
        operator = {'gt':'>','gte':'>=','lt':'<','lte':'<='}.get(op, 'is' if kind in ('text','entity') else '==')
        node = leaf(key, operator, value)
        children.append({'kind':'not','children':[node]} if op == 'ne' else node)
    return {'kind':'all','children':children}


def tree_text(node, depth=0):
    if depth > 64 or not isinstance(node,dict):
        raise ValueError('条件树层级或节点格式无效')
    kind = node.get('kind')
    if kind == 'leaf':
        if set(node) != {'kind','left','operator','right'} or any(not isinstance(node[k],str) for k in ('left','operator','right')):
            raise ValueError('条件树叶节点格式无效')
        if not node['left'] or bool(node['operator']) != bool(node['right']):
            raise ValueError('请补全条件树叶节点')
        return ' '.join(s for s in (node['left'],node['operator'],node['right']) if s)
    if set(node) != {'kind','children'} or kind not in ('not','all','any') or not isinstance(node['children'],list):
        raise ValueError('条件树节点格式无效')
    children = [tree_text(child,depth+1) for child in node['children']]
    if kind == 'not':
        if len(children)!=1: raise ValueError('取反需要一个子条件')
        return 'not ('+children[0]+')'
    if not children:
        if depth or kind != 'all': raise ValueError('条件分组不能为空')
        return ''
    if len(children)==1: return children[0]
    return '('+(' and ' if kind=='all' else ' or ').join(children)+')'


def editor_rule(group, event, entities=None):
    if 'expression' in group:
        return {k:deepcopy(group[k]) for k in RULE_FIELDS if k in group}
    tree = legacy_tree(group['conditions'],event,entities)
    return {'condition_tree':tree,'expression':tree_text(tree),'priority':0,'editor_mode':'tree'}


def validate_rule(group, event):
    if not RULE_FIELDS.intersection(group):
        return
    from src.python.condition import validate_expression
    expr = group.get('expression')
    if not isinstance(expr,str) or len(expr)>100000 or type(group.get('priority',0)) is not int:
        raise ValueError('条件文本或优先级无效')
    mode = group.get('editor_mode','text')
    if mode not in ('tree','text'): raise ValueError('条件编辑模式无效')
    if 'condition_tree' in group and group['condition_tree'] is not None:
        generated = tree_text(group['condition_tree'])
        if mode=='tree' and generated!=expr: raise ValueError('条件树与正式文本不一致')
    elif mode=='tree':
        raise ValueError('条件树缺失')
    validate_expression(event['name'],expr,library_catalog([event]))

