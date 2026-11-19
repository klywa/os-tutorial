"""Strict portable v1/v2 conversion without persistence or catalog mutation."""
from collections import defaultdict, deque
from copy import deepcopy
import json
import uuid

import templates_schema as schema
import template_rules as rules
from templates_entities import resolve


def _id(prefix):
    return prefix + '_' + uuid.uuid4().hex


def _list(value):
    if not isinstance(value, list):
        raise ValueError('导入条目必须为列表')
    return value


def _stable_rows(rows, previous, prefix):
    """Reuse duplicate occurrences first, then pair ordered replacement blocks.

    Matched rows act as boundaries only when they retain their relative order;
    moved exact rows retain identity and do not consume replacement identities.
    """
    def token(row):
        return json.dumps({k: v for k, v in row.items() if k != 'id'}, sort_keys=True, ensure_ascii=False)
    available = defaultdict(deque)
    for i, row in enumerate(previous): available[token(row)].append(i)
    matches = {}; used = set()
    for i, row in enumerate(rows):
        queue = available[token(row)]
        if queue:
            old = queue.popleft(); matches[i] = old; used.add(old)
    # Exact matches partition replacement runs; crossing/moved anchors are
    # omitted so a reorder does not turn neighboring edits into new identities.
    anchors = []; last = -1
    for new, old in sorted(matches.items()):
        if old > last: anchors.append((new, old)); last = old
    bounds = [(-1, -1), *anchors, (len(rows), len(previous))]
    for (new_a, old_a), (new_b, old_b) in zip(bounds, bounds[1:]):
        new_slots = [i for i in range(new_a + 1, new_b) if i not in matches]
        old_slots = [i for i in range(old_a + 1, old_b) if i not in used]
        for new, old in zip(new_slots, old_slots): matches[new] = old; used.add(old)
    # With crossing anchors, remaining unmatched rows are the ordered
    # replacement block left after all exact occurrences have been retained.
    for new, old in zip((i for i in range(len(rows)) if i not in matches),
                        (i for i in range(len(previous)) if i not in used)):
        matches[new] = old
    return [{**row, 'id': previous[matches[i]]['id'] if i in matches else _id(prefix)}
            for i, row in enumerate(rows)]


def _entity(value, parameter, catalog, previous=None, retired=None):
    selector = value.strip() if isinstance(value, str) else None
    if isinstance(previous, dict) and previous.get('name') == selector and previous.get('id') in {**(retired or {}), **catalog}:
        return deepcopy(previous)
    matches = resolve(value, parameter, catalog)
    return {'id': matches[0]['id'], 'name': selector}


def _condition_anchors(current, previous):
    def signature(condition, old=False):
        value = condition.get('value')
        selector = value.get('name') if old and isinstance(value, dict) else value
        if not isinstance(selector, str) or not isinstance(condition.get('parameter_key'), str) or not isinstance(condition.get('operator'), str):
            return None
        return condition['parameter_key'], condition['operator'], selector.strip()
    old_signatures = [signature(row, True) for row in previous]
    new_signatures = [signature(row) for row in current]
    assigned = {}; used = set()
    # Reserve unchanged positions before another same-selector occurrence can
    # consume their anchor after an operator edit.
    for index, token in enumerate(new_signatures):
        if token is not None and index < len(previous) and token == old_signatures[index]:
            assigned[index] = index; used.add(index)
    for exact in (True, False):
        for new, token in enumerate(new_signatures):
            if new in assigned or token is None: continue
            for old, old_token in enumerate(old_signatures):
                if old in used or old_token is None: continue
                if token == old_token or not exact and (token[0], token[2]) == (old_token[0], old_token[2]):
                    assigned[new] = old; used.add(old); break
    return {new: previous[old]['value'] for new, old in assigned.items()}


def _insert_retained(rows, previous, keep):
    for index, row in enumerate(previous):
        if keep(row):
            rows.insert(index, deepcopy(row))
    return rows


def _v1(document, public, catalog, notes, *, retired_entities=None, retired_suggestions=None):
    doc = deepcopy(document)
    prior_groups = {group['id']: group for group in public['groups']}
    for folder in ('events', 'groups'):
        for record in _list(doc[folder]):
            if not isinstance(record, dict): raise ValueError('导入记录格式无效')
            record.setdefault('id', _id('event' if folder == 'events' else 'group'))
            for field in (('parameters',) if folder == 'events' else ('conditions', 'utterances')):
                for item in _list(record.get(field)):
                    if not isinstance(item, dict): raise ValueError('导入条目格式无效')
                    item.setdefault('id', _id(field))
            if folder == 'groups':
                previous = prior_groups.get(record['id'], {}).get('utterances', [])
                fixed_ids = {row['id'] for row in previous if row.get('fixed')}
                editable = [row for row in record['utterances'] if row['id'] not in fixed_ids]
                record['utterances'] = _insert_retained(editable, previous, lambda row: row.get('fixed'))
    return schema.validate_library(doc, catalog, notes,
                                   retired_entities=retired_entities, retired_suggestions=retired_suggestions)


def decode(document, public, catalog, notes, *, retired_entities=None, retired_suggestions=None):
    # Whole-library exports from earlier releases carry unused retired events.
    if isinstance(document,dict) and isinstance(document.get('events'),list):
        document = {**document,'events':[event for event in document['events']
                    if not (isinstance(event,dict) and isinstance(event.get('name'),str)
                            and event['name'].endswith('（旧版）'))]}
    if isinstance(document,dict) and type(document.get('schema_version')) is int and document['schema_version']==3 and document.get('kind')=='speech-template-library':
        from template_package import decode as decode_rules
        return decode_rules(document,public,catalog,notes,retired_entities=retired_entities,retired_suggestions=retired_suggestions)
    schema.fields(document, {'kind', 'schema_version', 'events', 'groups'}, {'kind', 'schema_version', 'events', 'groups'})
    if document['kind'] != 'speech-template-library' or type(document['schema_version']) is not int or document['schema_version'] not in (1, 2):
        raise ValueError('模板库格式或版本无效')
    if document['schema_version'] == 1:
        return _v1(document, public, catalog, notes, retired_entities=retired_entities, retired_suggestions=retired_suggestions)
    old_events = {e['id']: e for e in public.get('events', [])}
    old_groups = {g['id']: g for g in public.get('groups', [])}
    events = []
    for external in _list(document['events']):
        schema.fields(external, {'id', 'name', 'category', 'parameters'}, {'name', 'parameters'})
        event = deepcopy(external); event.setdefault('id', _id('event'))
        schema.identity(event['id'])
        previous = old_events.get(event['id'], {})
        if previous and previous['name'] != event['name']:
            matched = rules.resolve_event(old_events.values(),event['name'],event['id'])
            if matched and matched['id']==event['id']:
                event.update(name=previous['name'],category=previous['category'])
        old_parameters = {p['key']: p for p in previous.get('parameters', [])}
        for parameter in _list(event['parameters']):
            schema.fields(parameter, {'id', 'key', 'name', 'type', 'dsl_type','entity_categories', 'suggestions', 'min', 'max'}, {'key', 'name', 'type'})
            if not isinstance(parameter['key'], str) or not schema.KEY.fullmatch(parameter['key']): raise ValueError('参数英文键无效或重复')
            parameter.setdefault('id', old_parameters.get(parameter['key'], {}).get('id', _id('parameters')))
            if parameter['type'] == 'entity' and 'suggestions' in parameter:
                prior = defaultdict(deque)
                for value in old_parameters.get(parameter['key'], {}).get('suggestions', []):
                    if isinstance(value, dict): prior[value.get('name')].append(value)
                retired = (retired_suggestions or {}).get(event['id'], {}).get(parameter['id'], {})
                parameter['suggestions'] = [_entity(value, parameter, catalog,
                                                    prior[value.strip()].popleft() if isinstance(value, str) and prior[value.strip()] else None,
                                                    retired)
                                            for value in _list(parameter['suggestions'])]
        schema.validate_event(event, catalog, retired_suggestions=(retired_suggestions or {}).get(event['id']))
        events.append(event)
    schema.unique(events, '事件')
    # A group may reference an existing event omitted from a partial import.
    event_map = {**old_events, **{e['id']: e for e in events}}
    names = defaultdict(list)
    # File events take precedence for name-only lookup, avoiding an old event
    # with the same name hijacking a newly created file event.
    for event in events: names[event['name']].append(event)
    groups = []; archives = {}
    for external in _list(document['groups']):
        schema.fields(external, {'id', 'name', 'explanation', 'event_id', 'event_name', 'scope', 'conditions', 'utterances'},
                      {'name', 'scope', 'conditions', 'utterances'})
        group = deepcopy(external); group.setdefault('id', _id('group'))
        schema.identity(group['id'])
        if 'event_name' in group: schema.text(group['event_name'], '事件名称')
        event_id = group.get('event_id'); event_name = group.pop('event_name', None)
        if event_id is None:
            schema.text(event_name, '事件名称')
            found = names.get(event_name, [])
            if not found:
                match = rules.resolve_event(event_map.values(),event_name)
                if match: found = [match]
            if len(found) != 1: raise ValueError('事件名称不存在或重名：' + event_name)
            event_id = found[0]['id']
        event = event_map.get(event_id) if isinstance(event_id, str) else None
        if event is None: raise ValueError('话术组引用的事件不存在')
        if event_name is not None:
            match = rules.resolve_event(event_map.values(),event_name,event_id)
            if not match or match['id']!=event_id: raise ValueError('事件 ID 与名称不一致')
        group['event_id'] = event_id
        parameters = {p['key']: p for p in event['parameters']}
        previous = old_groups.get(group['id'], {})
        for condition in _list(group['conditions']):
            schema.fields(condition, {'parameter_key', 'operator', 'value'}, {'parameter_key', 'operator', 'value'})
        prior_conditions = _condition_anchors(group['conditions'], previous.get('conditions', []))
        for index, condition in enumerate(group['conditions']):
            key = condition['parameter_key']
            parameter = parameters.get(key) if isinstance(key, str) else None
            if parameter is None: raise ValueError('条件引用了未知参数')
            if parameter['type'] == 'entity':
                value = condition['value']
                prior = prior_conditions.get(index)
                condition['value'] = _entity(value, parameter, catalog, prior, (retired_entities or {}).get(group['id']))
        group['conditions'] = _stable_rows(group['conditions'], previous.get('conditions', []), 'conditions')
        utterances = []
        for value in _list(group['utterances']):
            schema.text(value, '话术'); utterances.append({'text': value})
        prior_utterances = previous.get('utterances', [])
        def retained(row):
            return row.get('ignored') or row.get('fixed')
        for row in prior_utterances:
            if row.get('fixed') and not row.get('ignored') and {'text': row['text']} in utterances:
                utterances.remove({'text': row['text']})
        editable = _stable_rows(utterances, [row for row in prior_utterances if not retained(row)], 'utterances')
        group['utterances'] = _insert_retained(editable, prior_utterances, retained)
        if 'ignored' in previous:
            group['ignored'] = previous['ignored']
        archives[group['id']] = deepcopy(previous.get('related_entities', []))
        group['related_entities'] = []
        groups.append(group)
    # Validation needs referenced existing events, but return only imported rows.
    referenced = {group['event_id'] for group in groups}
    imported = {event['id'] for event in events}
    validation = schema.validate_library({'kind': 'speech-template-library', 'schema_version': 1,
                                         'events': [event for identity, event in event_map.items() if identity in referenced | imported],
                                         'groups': groups}, catalog, notes,
                                        retired_entities=retired_entities, retired_suggestions=retired_suggestions)
    validation['events'] = [event for event in validation['events'] if event['id'] in imported]
    for group in validation['groups']: group['related_entities'] = archives[group['id']]
    return validation


def encode(public):
    events = []
    for original in public['events']:
        event = {key: deepcopy(original[key]) for key in ('id', 'name', 'category') if key in original}
        event['parameters'] = []
        for original_parameter in original['parameters']:
            parameter = {key: deepcopy(value) for key, value in original_parameter.items() if key != 'id'}
            if parameter['type'] == 'entity' and 'suggestions' in parameter:
                parameter['suggestions'] = [value['name'] for value in parameter['suggestions']]
            event['parameters'].append(parameter)
        events.append(event)
    groups = []
    for original in public['groups']:
        group = {key: deepcopy(original[key]) for key in ('id', 'name', 'event_id', 'scope')}
        if 'explanation' in original:
            group['explanation'] = original['explanation']
        group['conditions'] = [{key: deepcopy(value) for key, value in condition.items() if key != 'id'}
                               for condition in original['conditions']]
        for condition in group['conditions']:
            if isinstance(condition['value'], dict): condition['value'] = condition['value']['name']
        group['utterances'] = [utterance['text'] for utterance in original['utterances']]
        groups.append(group)
    return {'kind': 'speech-template-library', 'schema_version': 2, 'events': events, 'groups': groups}
