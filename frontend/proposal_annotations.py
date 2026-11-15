"""Private feedback and administrator audit records for note proposals."""
from copy import deepcopy
import json
import uuid

from workspace import Conflict


def fields(item):
    result = {}

    def add(node, evidence):
        if not node:
            return
        values = ({'title': node['title']} if node['type'] == 'heading'
                  else {'body': node['value'], **({'name': node['key']} if node['show_key'] else {})})
        if evidence:
            values['evidence'] = evidence
        result.update({f'{node["id"]}:{key}': value for key, value in values.items()})

    add(item['base_node'] if item['kind'] == 'delete' else item['proposed_node'], item.get('evidence_changes'))
    for entry in item.get('section_entries', []):
        add(entry['node'], entry.get('evidence_changes'))
    return result


def message(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError('请输入 1–4000 字的批注或回应')
    return value.strip()


def annotation_at(item, annotation_id, revision):
    annotation = next((a for a in item.get('annotations', []) if a['id'] == annotation_id), None)
    if annotation is None:
        raise KeyError('批注不存在')
    if type(revision) is not int or revision != annotation['revision'] or annotation['status'] == 'closed':
        raise Conflict('批注已更新，请重新载入')
    return annotation


def add(item, actor, payload, now):
    field = payload.get('field')
    available = fields(item)
    if field is not None and (not isinstance(field, str) or field not in available):
        raise ValueError('批注字段不存在')
    annotation = {
        'id': uuid.uuid4().hex, 'field': field, 'snapshot': deepcopy(available.get(field)),
        'proposal_revision': item['revision'], 'author': actor['username'], 'created_at': now,
        'text': message(payload.get('text')), 'status': 'open', 'revision': 1, 'responses': [],
    }
    item.setdefault('annotations', []).append(annotation)
    return annotation


def audit(item, actor, kind, now, before, after):
    return {
        'id': uuid.uuid4().hex, 'proposal_id': item['id'], 'note_id': item['note_id'],
        'actor': actor['username'], 'kind': kind, 'created_at': now,
        'proposal_revision': item['revision'], 'before': deepcopy(before), 'after': deepcopy(after),
    }


def draft_audit(before, after, actor, now):
    keys = ('base_node', 'proposed_node', 'evidence_changes', 'section_entries')
    changes = [key for key in keys if before.get(key) != after.get(key)]
    if changes and actor['role'] == 'admin':
        event = audit(after, actor, 'draft_edit', now,
                      {key: before.get(key) for key in changes},
                      {key: after.get(key) for key in changes})
        event['previous_proposal_revision'] = before['revision']
        return event
    return None


def record(conn, event):
    if event:
        conn.execute(
            'INSERT OR IGNORE INTO proposal_audit(id, note_id, proposal_id, kind, created_at, data) VALUES (?, ?, ?, ?, ?, ?)',
            (event['id'], event['note_id'], event['proposal_id'], event['kind'], event['created_at'],
             json.dumps(event, ensure_ascii=False)),
        )
