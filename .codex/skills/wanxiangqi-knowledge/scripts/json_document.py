"""Ordered, editable knowledge nodes with lossless Markdown serialization."""
from copy import deepcopy
import hashlib
import re

VERSION = 6


def parse(text):
    nodes, pending, fence = [], [], None

    def flush():
        if not pending:
            return
        raw = ''.join(pending)
        pending.clear()
        content = raw.rstrip('\r\n')
        ending = raw[len(content):]
        heading = re.fullmatch(r'(#{1,6})([ \t]+)([^\r\n]+)', content)
        if heading:
            node = {'type': 'heading', 'level': len(heading[1]), 'title': heading[3], 'space': heading[2]}
        else:
            pair = re.match(r'^(?P<prefix>(?:[-*+] |\d+[.)] )?\*\*)(?P<key>[^*\n]+?)(?P<suffix>(?:[：:]\*\*|\*\*[：:])[ \t]*)(?P<value>[\s\S]*)$', content)
            if not pair:
                pair = re.match(r'^(?P<prefix>(?:[-*+] |\d+[.)] )?)(?P<key>[^*`|#\n：:]{1,30})(?P<suffix>[：:][ \t]*)(?P<value>[\s\S]*)$', content)
                if pair and not re.search(r'[\u3400-\u9fff]', pair['key']):pair = None
            node = {'type': 'entry', 'key': '正文', 'show_key': False, 'value': content}
            if pair:
                node.update(key=pair['key'], show_key=True, prefix=pair['prefix'], key_suffix=pair['suffix'], value=pair['value'])
        node['separator'] = ending
        node['id'] = 'n-' + hashlib.sha256((str(len(nodes)) + '\0' + raw).encode()).hexdigest()[:20]
        nodes.append(node)

    leading = ''
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        mark = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if fence:
            pending.append(line)
            if mark and mark[1][0] == fence[0] and len(mark[1]) >= len(fence) and not line[mark.end():].strip():
                fence = None
            continue
        if mark:
            flush()
            fence = mark[1]
            pending.append(line)
        elif not stripped:
            flush()
            if nodes:
                nodes[-1]['separator'] += line
            else:
                leading += line
        elif re.match(r'^#{1,6}[ \t]+', line):
            flush()
            pending.append(line)
            flush()
        else:
            # Adjacent keyed list rows are independently editable/copyable.
            if re.match(r'^(?:[-*+] |\d+[.)] )?\*\*[^*\n]+(?:[：:]\*\*|\*\*[：:])', line):
                flush()
            pending.append(line)
    flush()
    result = {'schema_version': VERSION, 'leading': leading, 'nodes': nodes}
    validate(result)
    return result


def render_node(node):
    if node['type'] == 'heading':
        value = '#' * node['level'] + node.get('space', ' ') + node['title']
    else:
        value = node['value']
        if node.get('show_key'):
            value = node.get('prefix', '**') + node['key'] + node.get('key_suffix', '：** ') + value
    return value + node.get('separator', '\n\n')


def markdown(document):
    return document.get('leading', '') + ''.join(render_node(n) for n in document['nodes'])


def copy_entry(node, body=None, note_title='正文'):
    key=node['key']
    if not node.get('show_key') and body:
        key=note_title
        for previous in body['nodes']:
            if previous['id']==node['id']:break
            if previous['type']=='heading':key=previous['title']
    key=key.replace('**','').strip().rstrip('：:').strip()
    if re.fullmatch(r'(?:【[^【】]+】|\[[^\[\]]+\])',key):key=key[1:-1].strip()
    return key + '：' + node['value']


def clean_labels(body):
    """Repair presentation wrappers; do not touch links or value formatting."""
    body=deepcopy(body)
    for node in body['nodes']:
        if node['type']!='entry' or not node.get('show_key'):continue
        key=node['key'];value=node['value']
        if key.startswith('【') and value.lstrip().startswith('】'):
            key=key[1:];value=value.lstrip()[1:].lstrip()
        key=key.replace('**','').strip()
        if key.startswith('【') and key.endswith('】'):key=key[1:-1].strip()
        node.update(key=key.rstrip('：:').strip(),value=value)
    return body


def section(document, node_id):
    nodes = document['nodes']
    start = next(i for i, n in enumerate(nodes) if n['id'] == node_id)
    level = nodes[start].get('level', 7)
    end = next((i for i in range(start + 1, len(nodes)) if nodes[i]['type'] == 'heading' and nodes[i]['level'] <= level), len(nodes))
    return ''.join(render_node(n) for n in nodes[start:end])


def validate(document):
    if not isinstance(document, dict) or document.get('schema_version') != VERSION or not isinstance(document.get('nodes'), list):
        raise ValueError('正文必须是版本6结构化JSON')
    seen = set()
    for n in document['nodes']:
        if not isinstance(n, dict) or not isinstance(n.get('id'), str) or not n['id'] or n['id'] in seen:
            raise ValueError('正文节点ID缺失或重复')
        seen.add(n['id'])
        if n.get('type') == 'heading':
            if type(n.get('level')) is not int or not 1 <= n['level'] <= 6 or not isinstance(n.get('title'), str) or '\n' in n['title']:
                raise ValueError('标题格式无效')
        elif n.get('type') == 'entry':
            if not isinstance(n.get('key'), str) or not n['key'].strip() or not isinstance(n.get('value'), str) or type(n.get('show_key')) is not bool:
                raise ValueError('知识条目格式无效')
            if not n['show_key'] and n['key'] != '正文':
                raise ValueError('隐藏key必须为正文')
        else:
            raise ValueError('未知正文节点类型')
        for field in ('separator', 'prefix', 'key_suffix', 'space'):
            if field in n and not isinstance(n[field], str):
                raise ValueError('节点格式字段无效')
    return document


def claim_display_refs(document, claims):
    """Resolve migrated evidence to visible nodes; text is used only to locate."""
    entries = [n for n in document['nodes'] if n['type'] == 'entry']
    ids = {n['id'] for n in entries}
    result = {}
    for claim in claims:
        ref = claim.get('display_ref', claim.get('text_ref'))
        if ref in ids:
            result[claim['id']] = ref
        elif 'display_ref' not in claim:
            text = claim.get('text', '').strip()
            matches = [n for n in entries if text and text in render_node(n)]
            if len(matches) == 1:
                result[claim['id']] = matches[0]['id']
    return result


def overview_operations(document, note):
    """Derive stage cards from current visible nodes, never legacy claim text."""
    rows = {key: [] for key in ('early', 'middle', 'late', 'improvement')}
    labels = {'前期': 'early', '中期': 'middle', '后期': 'late'}
    headings = []
    claims = {}
    for cid, node_id in claim_display_refs(document, note.get('claims', [])).items():
        claims.setdefault(node_id, []).append(cid)
    routes = note.get('meta', {}).get('operation_routes', [])
    for node in document['nodes']:
        if node['type'] == 'heading':
            while headings and headings[-1]['level'] >= node['level']:
                headings.pop()
            headings.append(node)
            continue
        target = None
        for heading in reversed(headings):
            title = heading['title']
            if title == '后期提升思路':
                target = 'improvement'
                break
            target = next((stage for label, stage in labels.items()
                           if title == label or title.startswith(label + '英雄组成与运营')
                           or title.startswith(label + '运营')), None)
            if target:
                break
        text = render_node(node).rstrip('\r\n')
        if not target or not text.strip():
            continue
        refs = claims.get(node['id'], [])
        linked = [route for route in routes
                  if set(refs) & {ref for phase in route.get('phases', {}).values() for ref in phase}]
        rows[target].append({'node_id': node['id'], 'markdown': text, 'claim_refs': refs,
                             'route_ids': [r['id'] for r in linked],
                             'route_names': [r['name'] for r in linked]})
    return rows


def reading(document, note):
    sections = []
    nodes = document['nodes']
    starts = [i for i, n in enumerate(nodes) if n['type'] == 'heading' and n['level'] == 2]
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(nodes)
        heading = nodes[start]
        sections.append({'id': heading['id'], 'title': heading['title'], 'nodes': deepcopy(nodes[start:end]),
                         'markdown': ''.join(render_node(n) for n in nodes[start + 1:end])})
    first = starts[0] if starts else len(nodes)
    opening = [n for n in nodes[:first] if not (n['type'] == 'heading' and n['level'] == 1)]
    if not starts and opening:
        sections.append({'id': 'content', 'title': '知识内容', 'nodes': opening, 'markdown': ''.join(render_node(n) for n in opening)})
        opening = []
    result = {'note_id': note['id'], 'revision': note['revision'], 'profile': 'json-v6', 'layout_version': 6,
            'sections': sections, 'opening': ''.join(render_node(n) for n in opening), 'section_aliases': {},
            'document': deepcopy(document), 'markdown': markdown(document)}
    if note.get('type') == 'lineup':
        result['overview_operations'] = overview_operations(document, note)
    return result
