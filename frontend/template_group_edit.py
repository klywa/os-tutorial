"""Shared identity and merge rules for template-group editing."""
from copy import deepcopy
from difflib import SequenceMatcher
import ast
import json
import re
import uuid

import template_rules as rules
from src.python.condition import _tokens
from workspace import Conflict


def apply_fields(group, patch):
    from templates_schema import fields, WORKFLOW_METADATA
    fields(patch,{'set','remove'},{'set','remove'})
    added,removed=patch['set'],patch['remove']
    if not isinstance(added,dict) or not isinstance(removed,list) or any(not isinstance(key,str) for key in removed):
        raise ValueError('模板字段修改格式无效')
    if ({*added,*removed} & ({'id'}|WORKFLOW_METADATA)) or len(set(removed))!=len(removed) or set(added).intersection(removed):
        raise ValueError('模板字段修改范围无效')
    value=deepcopy(group)
    for key in removed:value.pop(key,None)
    value.update(deepcopy(added))
    return value


def _parts(expression, operator):
    depth = 0
    starts = []
    for kind, _, column in _tokens(expression):
        if kind == '(':
            depth += 1
        elif kind == ')':
            depth -= 1
        elif not depth and kind == operator:
            starts.append(column - 1)
    if not starts:
        return [expression.strip()]
    ends = [*starts, len(expression)]
    return [expression[start:end].strip() for start, end in zip([0, *(pos + len(operator) for pos in starts)], ends)]


def _strip_outer(expression):
    while expression.startswith('(') and expression.endswith(')'):
        depth = 0
        for kind, _, column in _tokens(expression):
            if kind == '(':
                depth += 1
            elif kind == ')':
                depth -= 1
                if not depth:
                    break
        if column != len(expression):
            break
        expression = expression[1:-1].strip()
    return expression


def _expression(group, event):
    if 'expression' in group:
        return group['expression']
    return rules.editor_rule(group, event).get('expression', '') if event else ''


def _boolean_signature(operator, parts):
    return operator, tuple(sorted(term for part in parts for term in (
        part[1] if part[0] == operator else (part,))))


def _v04_signature(node):
    if isinstance(node, ast.BoolOp):
        return _boolean_signature(type(node.op).__name__, map(_v04_signature, node.values))
    return 'atom', ast.dump(node)


def _legacy_signature(expression):
    expression = _strip_outer(expression.strip())
    for operator in ('or', 'and'):
        parts = _parts(expression, operator)
        if len(parts) > 1:
            return _boolean_signature(operator, map(_legacy_signature, parts))
    return 'atom', tuple((kind, repr(value)) for kind, value, _ in _tokens(expression) if kind != 'end')


def formal_merge_key(group, event, entities, notes):
    from template_package import effective_expression
    from template_v04 import compile_expression, effective_expression as effective_v04
    from templates_schema import group_season

    scope = group['scope']
    player = entities.get(scope['player_id'], {}).get('name')
    lineup = notes.get(scope['lineup_note_id'], {}).get('title')
    if (scope['player_id'] and not player) or (scope['lineup_note_id'] and not lineup):
        return None
    display = {'player': player, 'lineup': lineup}
    if group.get('syntax_version') == '0.4':
        condition = effective_v04(display, group['expression'])
        node = compile_expression(event['name'], condition).node
        rule = _v04_signature(node) if node is not None else None
    else:
        expression = rules.editor_rule(group, event, entities).get('expression', '')
        rule = _legacy_signature(effective_expression(display, expression))
    return (group['event_id'], group['name'].strip(), group.get('syntax_version'), group.get('extra_key'), rule,
            group_season(group), group.get('mode', ''), bool(group.get('ignored')),
            group.get('publication_hold'))


def merge_formal_group(target, source):
    """Keep the first group and record where each source utterance moved."""
    from json_store import digest

    if source.get('priority', 0) > target.get('priority', 0):
        target['priority'] = source['priority']
    rows = target['utterances']
    ids = {row['id'] for row in rows}
    by_text = {}
    for row in rows:
        by_text.setdefault(row['text'], row)
    moved = {}
    new_speech = False
    for original in source['utterances']:
        uid, text = original['id'], original['text']
        existing = by_text.get(text)
        if existing is not None:
            if original.get('fixed'):
                new_speech |= bool(existing.get('ignored'))
                existing['fixed'] = True
                existing.pop('ignored', None)
            elif existing.get('ignored') and not original.get('ignored'):
                existing.pop('ignored', None)
                new_speech = True
            moved[uid] = existing['id']
            continue
        row = deepcopy(original)
        while row['id'] in ids:
            row['id'] = 'utterance_' + digest([source['id'], row['id'], text])[:32]
        ids.add(row['id'])
        by_text[text] = row
        rows.append(row)
        moved[uid] = row['id']
        new_speech |= not row.get('ignored')
    if new_speech:
        target['review_status'] = None
        target.pop('reviewed_by', None)
        target.pop('reviewed_at', None)
        if 'last_modified_by' in source:
            target['last_modified_by'] = deepcopy(source['last_modified_by'])
    return moved


def used_parameters(group, event):
    if not event or group.get('syntax_version')=='0.4':
        return set()
    tokens = list(_tokens(_expression(group, event)))
    paths = {value for index, (kind, value, _) in enumerate(tokens)
             if kind == 'id' and (not index or tokens[index-1][0] != '.')}
    for row in group['utterances']:
        paths.update(re.findall(r'(?<!\{)\{([A-Za-z_]\w*)(?:\.[^{}]+)?\}(?!\})', row['text']))
    return paths.intersection(p['key'] for p in event['parameters'])


def _bindings(expression, keys):
    expression = _strip_outer(expression.strip())
    if len(_parts(expression, 'or')) > 1:
        return []
    parts = _parts(expression, 'and')
    if len(parts) > 1:
        return [pair for part in parts for pair in _bindings(part, keys)]
    tokens = [(kind, value) for kind, value, _ in _tokens(expression) if kind != 'end']
    if not tokens or tokens[0][0] != 'id' or tokens[0][1] not in keys:
        return []
    key = tokens[0][1]
    path = None
    if len(tokens) == 5 and tokens[1][0] == '.' and tokens[2][0] == 'id':
        path = tokens[2][1]
        tokens = [tokens[0], *tokens[3:]]
    if len(tokens) != 3 or tokens[2][0] not in ('literal', 'number', 'true', 'false'):
        return []
    operator, value = tokens[1][0], tokens[2][1]
    if (path in (None, '名称', 'name') and operator in ('is', '==')
            or path == '阵容名' and operator == 'has'):
        if isinstance(value, (str, int)) or tokens[2][0] == 'number':
            return [(key, str(value))]
    return []


def identity_changed(before, after, old_event, new_event):
    if before['event_id'] != after['event_id']:
        return True
    if before.get('syntax_version')=='0.4' or after.get('syntax_version')=='0.4':
        return before.get('syntax_version')!=after.get('syntax_version') or before.get('extra_key')!=after.get('extra_key')
    old_parameters = {p['key']:p for p in (old_event or {}).get('parameters', [])}
    new_parameters = {p['key']:p for p in (new_event or {}).get('parameters', [])}
    used = used_parameters(before, old_event) | used_parameters(after, new_event)
    if any(old_parameters.get(key) != new_parameters.get(key) for key in used):
        return True

    def arguments(group, event, parameters):
        values = {}
        for key, value in _bindings(_expression(group, event), parameters):
            values.setdefault(key, set()).add(value)
        return {key:next(iter(items)) for key, items in values.items() if len(items)==1}

    return arguments(before, old_event, old_parameters) != arguments(after, new_event, new_parameters)


def fork_group(group, identity=None):
    value = deepcopy(group)
    value['id'] = identity or 'group_' + uuid.uuid4().hex
    for row in value['utterances']:
        row.pop('fixed', None)
    return value


def fork_direct_changes(current, changes):
    if not isinstance(changes, list) or any(not isinstance(change, dict) for change in changes):
        raise ValueError('模板修改必须为列表')
    groups = {row['id']:row for row in current['groups']}
    events = {row['id']:row for row in current['events']}
    if any(row.get('action')=='put' and (not isinstance(row.get('value'),dict)
             or row.get('id')!=row['value'].get('id')) for row in changes):
        raise ValueError('模板修改身份不一致')
    updated_events = {**events, **{row['id']:row['value'] for row in changes
                      if row.get('kind')=='event' and row.get('action')=='put'}}
    result = []
    for change in changes:
        previous = groups.get(change.get('id')) if change.get('kind')=='group' else None
        if previous and change.get('action')=='put':
            value = change['value']
            if not isinstance(value.get('event_id'),str) or not isinstance(value.get('utterances'),list):
                raise ValueError('模板组格式无效')
            if identity_changed(previous,value,events.get(previous['event_id']),updated_events.get(value['event_id'])):
                from json_store import digest
                value = fork_group(value,'group_'+digest([current['revision'],value])[:32])
                change = {**change,'id':value['id'],'value':value}
        result.append(change)
    return result


_MISSING = object()
_RULE = ('expression','condition_tree','editor_mode','conditions','syntax_version','extra_key','publication_hold')
_CONFLICT = '正式条件和提案修改了同一处，请对照两版条件后定稿。草稿已保留。'


def _merge_value(base, current, draft, message):
    if current == base or current == draft:
        return draft
    if draft == base:
        return current
    raise Conflict(message)


def _edits(base, modified):
    def keys(items):
        return [json.dumps(item,sort_keys=True,ensure_ascii=False) for item in items]
    return [(a,b,modified[c:d]) for opcode,a,b,c,d in SequenceMatcher(
        None, keys(base),keys(modified),autojunk=False).get_opcodes() if opcode!='equal']


def _merge_sequence(base, current, draft, reconcile=None):
    if len({json.dumps(item,sort_keys=True,ensure_ascii=False) for item in base})!=len(base):
        raise Conflict(_CONFLICT)
    changes = _edits(base,current)
    for start,end,rows in _edits(base,draft):
        for index,(a,b,other) in enumerate(changes):
            if a==start and b==end:
                if rows==other:
                    break
                if start==end:
                    changes[index]=(a,b,[*other,*(row for row in rows if row not in other)])
                    break
                if reconcile and end-start==len(rows)==len(other)==1:
                    changes[index]=(a,b,[reconcile(base[start],other[0],rows[0])])
                    break
                raise Conflict(_CONFLICT)
            if max(a,start)<min(b,end) or a<start<b and start==end or start<a<end and a==b:
                raise Conflict(_CONFLICT)
        else:
            changes.append((start,end,rows))
    merged=list(base)
    for start,end,rows in sorted(changes,key=lambda row:(row[0],row[1]),reverse=True):
        merged[start:end]=rows
    return merged


def _merge_tree(base,current,draft):
    if current==base or draft==base or current==draft:
        return _merge_value(base,current,draft,_CONFLICT)
    kind=base['kind']
    if kind not in ('all','any') or current['kind']!=kind or draft['kind']!=kind:
        raise Conflict(_CONFLICT)
    children=_merge_sequence(base['children'],current['children'],draft['children'],_merge_tree)
    return {'kind':kind,'children':children}


def _text_tree(expression):
    source=_strip_outer(expression.strip())
    for operator,kind in (('or','any'),('and','all')):
        parts=_parts(source,operator)
        if len(parts)>1:
            return {'kind':kind,'children':[_text_tree(part) for part in parts]}
    return {'kind':'leaf','left':source,'operator':'','right':''} if source else {'kind':'all','children':[]}


def _merge_rule(base,current,draft,event,resolve):
    ancestor,saved,edited=({k:group[k] for k in _RULE if k in group} for group in (base,current,draft))
    if resolve or saved==ancestor or edited==ancestor or saved==edited:
        return edited if resolve else _merge_value(ancestor,saved,edited,_CONFLICT)
    if any(group.get('syntax_version')=='0.4' for group in (base,current,draft)):
        raise Conflict(_CONFLICT)
    if all('expression' not in group for group in (base,current,draft)):
        return {'conditions':_merge_sequence(base['conditions'],current['conditions'],draft['conditions'])}
    if all(group.get('editor_mode')=='tree' and group.get('condition_tree') for group in (base,current,draft)):
        tree=_merge_tree(*(group['condition_tree'] for group in (base,current,draft)))
        return {'conditions':[],'expression':rules.tree_text(tree),'condition_tree':tree,'editor_mode':'tree'}
    trees=[_text_tree(_expression(group,event)) for group in (base,current,draft)]
    # Treat an empty or single-clause rule as the same top-level conjunction.
    trees=[tree if tree['kind'] in ('all','any') else {'kind':'all','children':[tree]} for tree in trees]
    return {'conditions':[],'expression':rules.tree_text(_merge_tree(*trees)),'editor_mode':'text'}


def merge_group(base,current,draft,event,resolve=False):
    if current==base:
        return deepcopy(draft)
    if base is None or current is None:
        raise Conflict('原模板组已变化，请核对待审稿。')
    from templates_schema import WORKFLOW_METADATA
    result=dict(current)
    for key in set(base)|set(current)|set(draft):
        if key in _RULE or key in WORKFLOW_METADATA:
            continue
        value=_merge_value(base.get(key,_MISSING),current.get(key,_MISSING),draft.get(key,_MISSING),
                           '正式模板和待审稿同时改了 '+key+'，请在提案浮窗核对。')
        if value is _MISSING:result.pop(key,None)
        else:result[key]=value
    for key in _RULE:result.pop(key,None)
    result.update(_merge_rule(base,current,draft,event,resolve))
    return deepcopy(result)


def required_event(group, current, proposed):
    if not proposed or proposed['id']!=group['event_id']:
        return None,[]
    used=used_parameters(group,proposed)
    desired={p['key']:p for p in proposed['parameters']}
    if current is None:
        parameters=[p for p in proposed['parameters'] if p['key'] in used]
        return {**proposed,'parameters':parameters},[p['key'] for p in parameters]
    published={p['key']:p for p in current['parameters']}
    if any(key in published and published[key]!=desired[key] for key in used):
        raise Conflict('待审事件参数与正式定义冲突，请在提案浮窗核对。')
    missing=[p for p in proposed['parameters'] if p['key'] in used and p['key'] not in published]
    return ({**current,'parameters':[*current['parameters'],*missing]},[p['key'] for p in missing]) if missing else (None,[])
