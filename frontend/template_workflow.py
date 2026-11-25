"""Author attribution, review, and per-group revisions for the template library."""
from copy import deepcopy

import templates_schema as schema
import templates_store as store
from src.python.condition import _BindingEvaluator, _UNKNOWN
from workspace import Conflict


REVIEWERS = ('admin', 'quality')


def content(group):
    if group is None:
        return None
    return {key: value for key, value in group.items() if key not in schema.WORKFLOW_METADATA}


def equivalent(previous, incoming, events, catalog):
    if previous is None or incoming is None:
        return previous is incoming

    def author_content(group):
        value=content(group)
        for key, default in {'batch':[], 'tags':[], 'ignored':False}.items():
            value[key]=value.get(key) or default
        value['version']=schema.group_versions(group)
        value['mode']=schema.group_modes(group)
        event=events.get(group.get('event_id'))
        if event and 'conditions' in group:
            projection=store.rules.editor_rule(group,event,catalog)
            value.update(projection)
        return value

    return author_content(previous)==author_content(incoming)


def official(root, season, entities=None):
    cached_source=entities if season=='S1' and isinstance(entities,store.EffectiveEntities) else None
    if cached_source is not None and cached_source.official_s1 is not None:
        return cached_source.official_s1
    if season == 'S1':
        rows = list(store._catalog(root, entities, include_season_cards=False)[0].values())
    else:
        rows = store._season_cards(root, season).values()
    items = []
    for row in rows:
        card = store.semantic(row)
        for key in ('version', 'retrieved_at', 'skills_source'):
            if isinstance(row.get(key), str) and row[key]:
                card[key] = row[key]
        items.append(card)
    versions = {row['version'] for row in items if row.get('version')}
    result={'season': season, 'items': items, **({'version': versions.pop()} if len(versions) == 1 else {})}
    if cached_source is not None:cached_source.official_s1=result
    return result


class _ReferencedCards(_BindingEvaluator):
    def __init__(self, expression, event, catalog):
        super().__init__(expression, event, {}, {}, catalog)
        self.cards = set()

    def types_for(self, operand):
        types = operand.types
        if operand.field.endswith('.名称'):
            if operand.path.count('.') == 1:
                types = (self.params.get(operand.path.split('.')[0],operand.field.split('.')[0]),)
            else:
                types = (operand.field.split('.')[0],)
        if len(types)==1 and types[0].startswith('Array<'):
            types = tuple(types[0][6:-1].split('|'))
        return self.unit_variants(tuple(self.canonical(kind) for kind in types))

    def add(self, value, types):
        if isinstance(value,dict):
            kinds = (self.canonical(value['类型']),) if '类型' in value else types
            name = value.get('名称',value.get('name'))
            awakened = value.get('已觉醒')
        else:
            kinds, name, awakened = types, value, None
        if isinstance(name,str) and name.strip():
            categories=tuple(category for category,kind in store.rules.CATEGORY_TYPES.items() if kind in kinds)
            if categories:self.cards.add((name.strip(),categories,awakened))

    def compare(self, op, left, right):
        result = super().compare(op,left,right)
        if op in ('is','has','in'):
            for operand, counterpart in ((left,right),(right,left)):
                if operand.path or operand.value is _UNKNOWN or not counterpart.path:continue
                values=[child.value for child in operand.value] if isinstance(operand.value,list) else [operand.value]
                for raw in values:self.add(raw,self.types_for(counterpart))
        return result

    def count_filter(self, array_type):
        field,value=super().count_filter(array_type)
        if field=='英雄':
            for raw in value:self.add(raw,('英雄',))
        return field,value


def _snapshot(group, events, catalog, rules_catalog):
    from templates_entities import resolve
    rows = {row['id']: row for row in catalog['items']}
    refs = store._references(group, events, catalog=rows)
    event=events.get(group['event_id'])
    if event and group.get('syntax_version')=='0.4':
        import ast
        from src.python.condition.v04 import compile_expression
        expression=compile_expression(event['name'],group.get('expression','')).node
        names={node.value for node in ast.walk(expression)
               if isinstance(node,ast.Constant) and isinstance(node.value,str)} if expression else set()
        if group.get('extra_key'):
            names.update(group['extra_key'].split('-'))
        refs.update({row['id']:row['name'] for row in rows.values() if row.get('name') in names})
    elif event and group.get('expression'):
        parser=_ReferencedCards(group['expression'],event['name'],rules_catalog)
        parser.parse()
        for name,categories,awakened in parser.cards:
            try:
                matches=resolve(name,{'entity_categories':categories},rows)
            except ValueError:
                refs.setdefault('/'.join(categories)+':'+name,name)
                continue
            for row in matches:
                if awakened is None or row.get('awakened')==awakened:
                    refs[row['id']]=row['name']
    return {**{key: value for key, value in catalog.items() if key != 'items'}, 'entities': {
        identity: deepcopy(rows[identity]) if identity in rows else {'name': name, 'missing': True}
        for identity, name in refs.items()
    }}


def prepare(root, current, changes, actor, *, source='editor', entities=None, origins=None, selected_season=None):
    """Resolve workflow fields once, before validation and approval receipt creation."""
    if not isinstance(changes, list):
        raise ValueError('模板修改必须为列表')
    previous = {group['id']: group for group in current['groups']}
    events = {event['id']: event for event in current['events']}
    for change in changes:
        if isinstance(change, dict) and change.get('kind') == 'event' and change.get('action') == 'put':
            value = change.get('value')
            if isinstance(value, dict) and isinstance(value.get('id'), str):
                events[value['id']] = value
    catalogs = {}
    comparison_catalog = store._catalog(root,entities)[0]
    rules_catalog = None
    result = []
    for change in changes:
        if not isinstance(change, dict) or change.get('kind') != 'group' or change.get('action') != 'put':
            result.append(change)
            continue
        supplied = change.get('value')
        if not isinstance(supplied, dict) or not isinstance(change.get('id'), str) or supplied.get('id') != change['id']:
            raise ValueError('模板组身份不一致')
        value = content(supplied)
        try:
            if equivalent(previous.get(change['id']),value,events,comparison_catalog):continue
        except (KeyError, AttributeError) as exc:
            raise ValueError('模板组条件格式无效') from exc
        origin, operation = (origins or {}).get(change['id'], (actor, source))
        modifier = {'kind': 'user', 'username': origin['username']}
        if operation in ('file-import', 'import'):
            claimed = supplied.get('last_modified_by')
            if isinstance(claimed, dict) and (claimed.get('kind') == 'ai' or
                    claimed.get('kind') == 'user' and isinstance(claimed.get('username'), str) and claimed['username'].strip()):
                modifier = {'kind': 'ai'} if claimed['kind'] == 'ai' else {'kind': 'user', 'username': claimed['username']}
            elif operation=='file-import':
                modifier = {'kind':'ai'}
        if operation == 'ai':
            modifier = {'kind': 'ai'}
        status = 'ai_generated' if modifier['kind'] == 'ai' else None
        if operation in ('file-import', 'import'):
            authored = supplied.get('review_status')
            if 'review_status' in supplied and authored is None:
                status = None
            if authored in ('ai_generated', 'initial_reviewed'):
                status = authored
            if authored == 'final_reviewed':
                status = None
            if authored == 'final_reviewed' and origin['role'] in REVIEWERS:
                status = 'final_reviewed'
                value.update(reviewed_by=origin['username'], reviewed_at=store._now())
        versions = schema.group_versions(value)
        supplied_snapshot = supplied.get('entity_snapshot')
        snapshot_season = supplied_snapshot.get('season') if isinstance(supplied_snapshot, dict) else None
        prior_snapshot = previous.get(change['id'], {}).get('entity_snapshot', {})
        season = next((season for season in (selected_season, snapshot_season, prior_snapshot.get('season'))
                       if season in versions), versions[0])
        if season not in catalogs:
            # Older custom version labels remain editable and have no assigned catalog.
            catalogs[season] = official(root, season, entities) if season in ('S1','S2') else {'season': season, 'items': []}
        value.update(review_status=status, last_modified_by=modifier)
        try:
            if rules_catalog is None:rules_catalog=store.rules.library_catalog(events.values(),root=root)
            file_snapshot=supplied_snapshot if operation in ('file-import','import') else None
            if isinstance(file_snapshot,dict) and file_snapshot.get('season')==season:
                value['entity_snapshot'] = deepcopy(file_snapshot)
            else:
                value['entity_snapshot'] = _snapshot(value, events, catalogs[season], rules_catalog)
        except (KeyError, AttributeError) as exc:
            raise ValueError('模板组关联实体格式无效') from exc
        result.append({**change, 'value': value})
    return result


def _group(current, group_id):
    record = next((group for group in current['groups'] if group['id'] == group_id), None)
    if record is None:
        raise KeyError('模板组不存在')
    return record


def review_change(current, group_id, actor):
    if actor['role'] not in REVIEWERS:
        raise PermissionError('只有管理员或质检员可以复核模板')
    record = _group(current, group_id)
    if record.get('review_status') != 'initial_reviewed':
        raise Conflict('只有初核完成的模板组可以复核')
    return {'kind':'group', 'action':'put', 'id':group_id, 'value':{
        **record, 'review_status':'final_reviewed', 'reviewed_by':actor['username'], 'reviewed_at':store._now()}}


def review_status_change(current, group_id, actor, status):
    if status is not None and (not isinstance(status,str) or status not in schema.REVIEW_STATUSES):
        raise ValueError('模板组审核状态无效')
    role=actor['role']
    if role not in (*REVIEWERS,'annotator') or status=='final_reviewed' and role not in REVIEWERS:
        raise PermissionError('当前身份不能设置此审核状态')
    record=_group(current,group_id)
    if record.get('review_status','ai_generated')==status:return None
    value={**record,'review_status':status}
    value.pop('reviewed_by',None)
    value.pop('reviewed_at',None)
    if status=='final_reviewed':
        value.update(reviewed_by=actor['username'],reviewed_at=store._now())
    return {'kind':'group','action':'put','id':group_id,'value':value}


def revisions(root, group_id, *, loaded=None):
    """Project saved group revisions from legacy and current audit rows."""
    schema.identity(group_id)
    current, metadata = loaded if loaded is not None else store._load(root)
    tombstones = metadata['tombstones']
    group_id = store.merged_reference(tombstones, group_id)[0]
    record = _group(current, group_id)
    entries = []
    inherited = []
    audit=[*metadata['audit'],*store.review_history(root)]
    for row in sorted(reversed(audit),key=lambda row:row.get('at') or '',reverse=True):
        changes = [(change['id'], next((group for group in row.get('before', {}).get('groups', [])
                    if group['id'] == change['id']), None), change.get('value'))
                   for change in row.get('changes', []) if change.get('kind') == 'group']
        if not changes and row.get('action') == 'resolve_conflict':
            changes = [(row.get('group_id'), row.get('before_group'), row.get('after_group'))]
        for uid, before, value in changes:
            if store.merged_reference(tombstones, uid)[0] != group_id:
                continue
            canonical = uid == group_id
            entry = {'id':row['id'] if canonical else row['id']+':'+uid, 'at':row.get('at'), 'by':row.get('actor'),
                     'restored_from':row.get('manual', {}).get('restored_from'), 'value':value, 'before':before,
                     'restorable':canonical and isinstance(value,dict) and
                     {'id','event_id','scope','conditions','utterances'} <= set(value)}
            (entries if canonical else inherited).append(entry)
    if entries and isinstance(entries[-1]['before'],dict) and entries[-1]['before']!=entries[-1]['value']:
        oldest=entries[-1]
        entries.append({'id':oldest['id']+'-before','value':oldest['before'],'restorable':True})
    if not entries or entries[0]['value'] != record:
        entries.insert(0, {'id':'current', 'at':None, 'by':None, 'value':record, 'restorable':False})
    entries[0]['current'] = True
    entries[0]['restorable'] = False
    return [entries[0], *sorted([*entries[1:], *inherited], key=lambda row:row.get('at') or '', reverse=True)]


def restore_change(root, current, group_id, revision_id):
    record = _group(current, group_id)
    entry = next((entry for entry in revisions(root, group_id) if entry['id'] == revision_id), None)
    if entry is None or not entry['restorable']:
        raise ValueError('该历史版本不可回退')
    target = deepcopy(entry['value'])
    if not {'id','event_id','scope','conditions','utterances'} <= set(target):
        raise ValueError('该历史版本缺少完整模板数据')
    if content(target) == content(record):
        return None
    return {'kind':'group', 'action':'put', 'id':group_id, 'value':target}
