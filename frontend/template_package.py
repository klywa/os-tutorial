"""Name-based v3 interchange, also consumed directly by the game matcher."""
from collections import Counter
from copy import deepcopy
import uuid

import template_rules as rules
import templates_schema as schema


def _find(rows, field, name, what):
    matched = [row for row in rows if row.get(field)==name]
    if len(matched)>1:
        raise ValueError(what+'名称有歧义：'+str(name))
    return matched[0] if matched else None


def _scope_name(identity, rows, key):
    if identity is None:
        return None
    row = rows.get(identity)
    if not row or not row.get(key):
        raise ValueError('找不到适用范围的名称：'+str(identity))
    return row[key]


def effective_expression(scope, expression):
    """Include binding clauses for display and standalone DSL consumers."""
    clauses = ['玩家.' + field + ' is ' + rules.operand(scope[key])
               for key, field in (('player', '使用棋手'), ('lineup', '使用阵容'))
               if scope.get(key) is not None]
    if not clauses:
        return expression
    if expression.strip():
        clauses.append('(' + expression + ')')
    return ' and '.join(clauses)


def _related_key(row):
    return row['name'], rules.CATEGORY_TYPES[row['category']]


def _restore_related(associations, previous, entities, retired):
    """Preserve the selected versions when resolving a previously exported name."""
    if not isinstance(associations, list):
        raise ValueError('关联实体必须为列表')
    known = {**retired, **entities}
    anchors = {}
    original = previous.get('related_entities', [])
    for ref in original:
        row = known.get(ref['id'])
        if row:
            name, kind = _related_key(row)
            for spelling in {name, ref['name'], retired.get(ref['id'], {}).get('name', name)}:
                anchors.setdefault((spelling, kind), []).append(ref)
    result = {}
    for association in associations:
        schema.fields(association, {'名称', '类型'}, {'名称', '类型'})
        key = (schema.text(association['名称']), schema.text(association['类型']))
        matched = anchors.get(key)
        if not matched:
            matched = [{'id': row['id'], 'name': row['name']} for row in entities.values()
                       if _related_key(row) == key]
        if not matched:
            raise ValueError('未知关联实体：'+str(association))
        for ref in matched:
            result[ref['id']] = deepcopy(ref)
    if result.keys() == {r['id'] for r in original}:
        return deepcopy(original)
    return list(result.values())


def _scope_match(rows, previous_id, field, name, label):
    if name is None:
        return None
    schema.text(name, label)
    previous = rows.get(previous_id)
    if previous and previous.get(field) == name:
        return previous_id
    matched = _find(rows.values(), field, name, label)
    if matched is None:
        raise ValueError('未知'+label+'：'+name)
    return matched['id']


def encode(public, entities, notes, metadata=None, *, all_groups=None, root=None):
    from templates_portable import encode as old_encode
    runtime_catalog = rules.library_catalog(public['events'],root=root or rules.ROOT)
    if len(runtime_catalog['events'])!=len(public['events']):
        raise ValueError('事件名称重复，请为事件使用唯一名称')
    data = old_encode(public)
    event_by_id = {e['id']:e for e in public['events']}
    for event in data['events']:
        event.pop('id')
        params = runtime_catalog['events'][event['name']]['parameters']
        event['signature'] = event['name']+'('+', '.join(k+': '+t for k,t in params.items())+')'
    counts = Counter((g['event_id'],g['name']) for g in (public['groups'] if all_groups is None else all_groups))
    for group, original in zip(data['groups'],public['groups']):
        if counts[(original['event_id'],group['name'])]==1:
            group.pop('id')
        event = event_by_id[group.pop('event_id')]
        group['event_name'] = event['name']
        archived = {**(metadata or {}).get('baselines',{}).get(original['id'],{}),
                    **(metadata or {}).get('entity_archive',{}).get(original['id'],{})}
        refs = {**archived,**entities}
        group['scope'] = {'player':_scope_name(original['scope']['player_id'],refs,'name'),
                          'lineup':_scope_name(original['scope']['lineup_note_id'],notes,'title')}
        group.update(rules.editor_rule(original,event,refs))
        group['effective_expression'] = effective_expression(group['scope'], group['expression'])
        group.setdefault('priority',0)
        if not group['conditions']: group.pop('conditions')
        if original.get('related_entities'):
            keys = dict.fromkeys(_related_key(refs[r['id']]) for r in original['related_entities'])
            group['related_entities'] = [{'名称':name,'类型':kind} for name,kind in keys]
    data['schema_version'] = 3
    data['condition_catalog'] = runtime_catalog
    return data


def decode(document, public, entities, notes, **kwargs):
    from templates_portable import decode as old_decode
    schema.fields(document,{'kind','schema_version','condition_catalog','events','groups'},
                  {'kind','schema_version','events','groups'})
    doc = deepcopy(document)
    imported_catalog = doc.pop('condition_catalog', None)
    if imported_catalog is not None:
        current = rules.catalog()
        # Previous v3 catalogs may lack fields introduced in later releases.
        if not isinstance(imported_catalog,dict) or not isinstance(imported_catalog.get('events'),dict):
            raise ValueError('配置的类型目录与当前项目不一致')
        types = imported_catalog.get('types')
        expected = deepcopy(current['types'])
        previous_lineups = isinstance(types,dict) and '阵容' not in types
        operations = dict(current['operations'])
        aliases = current['aliases']
        unit_types = current['unit_types']
        if isinstance(types,dict) and '单位' not in types:
            expected.pop('单位')
            expected['玩家'].pop('已选天赋')
            expected['英雄'].pop('已穿装备')
            operations.pop('单位.标签')
            aliases = {**aliases, '单位': '英雄'}
            unit_types = None
        if isinstance(types,dict) and '标签' not in types.get('英雄', {}):
            for owner in ('英雄','装备','效果牌','天赋'):
                expected[owner].pop('标签',None)
                operations.pop(owner+'.标签',None)
        if previous_lineups:
            expected.pop('阵容')
            expected['玩家'].pop('当前阵容')
            operations.pop('阵容.阵容名')
        old_population = deepcopy(expected)
        for field in ('场上英雄数', '人口上限'):
            old_population['玩家'].pop(field)
        if (types not in (expected, old_population) or imported_catalog.get('operations') != operations
                or imported_catalog.get('aliases') != aliases
                or imported_catalog.get('unit_types') != unit_types
                or any(imported_catalog.get(k)!=current[k] for k in ('roots','enums'))):
            raise ValueError('配置的类型目录与当前项目不一致')
    if not isinstance(doc['events'],list) or not isinstance(doc['groups'],list):
        raise ValueError('事件与模板组必须为列表')
    all_events = {e['id']:e for e in public['events']}
    old_groups = {g['id']:g for g in public['groups']}
    imported_names = {}
    for event in doc['events']:
        if not isinstance(event,dict):raise ValueError('事件必须为对象')
        signature=event.pop('signature',None)
        signature_params=None
        if signature is not None:
            declared_name,signature_params=rules.parse_signature(signature)
            if event.setdefault('name',declared_name)!=declared_name:
                raise ValueError('事件签名与名称不一致：'+declared_name)
            if 'parameters' not in event:
                event['parameters']=[rules.parameter(k,t) for k,t in signature_params.items()]
        name = schema.text(event.get('name'))
        existing = rules.resolve_event(all_events.values(),name,event.get('id'))
        event.setdefault('id', existing['id'] if existing else 'event_'+uuid.uuid4().hex)
        schema.identity(event['id'])
        if not isinstance(event.get('parameters'),list) or any(not isinstance(p,dict) for p in event['parameters']):
            raise ValueError('事件参数必须为对象列表')
        params = rules.definition(event)['parameters']
        if signature_params is not None and list(signature_params.items())!=list(params.items()):
            raise ValueError('事件签名与参数定义不一致：'+name)
        if imported_catalog is not None and imported_catalog.get('events',{}).get(name)!=rules.definition(event):
            raise ValueError('配置目录与事件定义不一致：'+name)
        if existing and event['id']==existing['id'] and name!=existing['name']:
            event.update(name=existing['name'],category=existing['category'])
        if name in imported_names and imported_names[name] != event['id']:
            raise ValueError('事件名称有歧义：'+name)
        imported_names[name]=event['id']
        all_events[event['id']] = event
    extras = {}
    group_names = Counter()
    for group in doc['groups']:
        if not isinstance(group,dict):
            raise ValueError('模板组必须为对象')
        name = schema.text(group.get('event_name'))
        hint = old_groups.get(group.get('id'), {}).get('event_id')
        event = all_events.get(imported_names.get(name)) or rules.resolve_event(all_events.values(),name,hint)
        if event is None:raise ValueError('未知事件：'+name)
        group['event_name'] = event['name']
        group_names[(event['name'],schema.text(group.get('name')))] += 1
    for group in doc['groups']:
        schema.fields(group,{'id','name','explanation','event_name','scope','conditions','utterances','related_entities','effective_expression'}|rules.RULE_FIELDS,
                      {'name','event_name','expression','utterances'})
        # A copied preview can be stale after hand-editing the scope or expression.
        group.pop('effective_expression', None)
        event = _find(all_events.values(),'name',group['event_name'],'事件')
        if event is None:raise ValueError('未知事件：'+str(group['event_name']))
        group['event_id'] = event['id']
        if 'id' not in group:
            if group_names[(group['event_name'],group['name'])] != 1:
                raise ValueError('同一事件下重名的模板组需要身份')
            existing = _find([g for g in public['groups'] if g['event_id']==event['id']],'name',group['name'],'模板组')
            group['id'] = existing['id'] if existing else 'group_'+uuid.uuid4().hex
        schema.identity(group['id'])
        previous = old_groups.get(group['id'], {})
        previous_scope = previous.get('scope', {})
        retired = (kwargs.get('retired_entities') or {}).get(group['id'], {})
        scope = group.get('scope',{})
        schema.fields(scope,{'player','lineup'})
        players = {k:v for k,v in entities.items() if v.get('category')=='players'}
        previous_player = previous_scope.get('player_id')
        if previous_player in retired:
            players.setdefault(previous_player, retired[previous_player])
        if previous_player in retired and retired[previous_player].get('name') == scope.get('player'):
            player = previous_player
        else:
            player = _scope_match(players, previous_player, 'name', scope.get('player'), '棋手')
        lineups = {k:r for k,r in notes.items() if r.get('type')=='lineup' and player and r.get('player_id')==player}
        lineup = _scope_match(lineups, previous_scope.get('lineup_note_id'), 'title', scope.get('lineup'), '阵容')
        group['scope'] = {'player_id':player,'lineup_note_id':lineup}
        restored = {k:group.pop(k) for k in rules.RULE_FIELDS if k in group}
        restored.setdefault('priority',0)
        restored.setdefault('editor_mode','text')
        if 'related_entities' in group:
            restored['related_entities'] = _restore_related(group.pop('related_entities'), previous, entities, retired)
        if group['id'] in extras:raise ValueError('模板组名称或身份重复')
        extras[group['id']] = restored
        group.setdefault('conditions',[])
    doc['schema_version'] = 2
    rule_fields = {uid: {key:value for key,value in fields.items() if key in rules.RULE_FIELDS}
                   for uid,fields in extras.items()}
    result = old_decode(doc,public,entities,notes,rule_fields=rule_fields,**kwargs)
    for group in result['groups']:
        group.update(extras[group['id']])
    return result

