"""Preview and apply note content transfers between players of one lineup."""
from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

import json_document
import json_store
import knowledge_history
import note_review
import seasons
from edit_locks import EditLocked
from player_identity import catalog as player_catalog
from site_access import assert_formal_write, proposal_store
from workspace import Busy, Conflict, store_lock


class Ambiguous(ValueError):
    pass


@dataclass(eq=False)
class Scope:
    node: dict
    start: int
    end: int
    children: list = field(default_factory=list)

    @property
    def key(self):
        if self.node['type'] == 'heading':
            return ('heading', self.node['level'], self.node['title'].strip())
        return ('entry', self.node['key'].strip() if self.node['show_key'] else None)


def tree(nodes):
    root = Scope({}, -1, len(nodes))
    stack = [root]
    paths = {}
    for index, node in enumerate(nodes):
        heading = node['type'] == 'heading'
        if heading:
            while len(stack) > 1 and stack[-1].node['level'] >= node['level']:
                stack.pop().end = index
        # The document title identifies the note, not a position within it.
        if heading and node['level'] == 1:
            continue
        item = Scope(node, index, len(nodes) if heading else index + 1)
        stack[-1].children.append(item)
        paths[node['id']] = ([*stack[1:], item], stack[-1])
        if heading:
            stack.append(item)
    return root, paths


def match(parent, item):
    choices = [child for child in parent.children if child.key == item.key]
    if len(choices) > 1:
        raise Ambiguous('有多个同名章节或条目，无法定位')
    return choices[0] if choices else None


def position(source_parent, target_parent, item):
    # A flat heading list only preserves a sibling if its level closes the
    # preceding heading and the following heading closes it in turn.
    headings = [child for child in target_parent.children if child.node['type'] == 'heading']
    lower = target_parent.start + 1
    upper = target_parent.end
    if item.node['type'] == 'entry':
        if headings:
            upper = headings[0].start
    else:
        level = item.node['level']
        for child in target_parent.children:
            if child.node['type'] == 'entry' or child.node['level'] > level:
                lower = child.end
        upper = next((child.start for child in headings if child.node['level'] < level), upper)
    siblings = source_parent.children
    index = siblings.index(item)
    for choices, edge in ((siblings[index + 1:], 'start'), (reversed(siblings[:index]), 'end')):
        for sibling in choices:
            if sum(other.key == sibling.key for other in siblings) != 1:
                continue
            try:
                anchor = match(target_parent, sibling)
            except Ambiguous:
                continue
            if anchor:
                boundary = getattr(anchor, edge)
                if lower <= boundary <= upper:
                    return boundary
    return upper


def replacement(item, target):
    # Keep target IDs and presentation fields wherever the structure matches.
    node = deepcopy(target.node if target else item.node)
    if not target:
        node['id'] = 'sync-' + uuid4().hex
    if item.node['type'] == 'entry':
        node['value'] = item.node['value']
    nodes = [node]
    for child in item.children:
        corresponding = None
        if target and sum(other.key == child.key for other in item.children) == 1:
            corresponding = match(target, child)
        elif target and any(other.key == child.key for other in target.children):
            raise Ambiguous('章节内有多个同名节点，无法定位')
        nodes.extend(replacement(child, corresponding))
    return nodes


def target_scope(source_root, path, body):
    target_parent, _ = tree(body['nodes'])
    source_parent = source_root
    for depth, item in enumerate(path):
        if match(source_parent, item) is not item:
            raise Ambiguous('源笔记中的位置无法唯一定位')
        target = match(target_parent, item)
        if target is None:
            at = position(source_parent, target_parent, item)
            headers = []
            for ancestor in path[depth:-1]:
                headers.append({**ancestor.node, 'id': 'sync-' + uuid4().hex})
            return None, at, at, headers + replacement(path[-1], None)
        if depth == len(path) - 1:
            return target, target.start, target.end, replacement(item, target)
        source_parent, target_parent = item, target


def content(item):
    if item.node['type'] == 'entry':
        return item.node['value']
    return [(child.key, content(child)) for child in item.children]


def markdown(item, *, root=True):
    node = item.node
    if node['type'] == 'entry':
        return (node['key'] + '：' if node['show_key'] and not root else '') + node['value']
    lines = [] if root else ['#' * node['level'] + ' ' + node['title']]
    return '\n\n'.join(lines + [markdown(child, root=False) for child in item.children])


def edited_replacement(item, target, draft):
    if item.node['type'] == 'entry':
        return [{**target.node, 'value': draft}]
    children = json_document.parse(draft)['nodes']
    if any(node['type'] == 'heading' and node['level'] <= target.node['level'] for node in children):
        raise ValueError('编辑稿的子章节标题必须低于当前章节')
    root, _ = tree([target.node, *children])
    return replacement(root.children[0], target)


def previous_scope(root, note_id, item):
    current = content(item)
    if knowledge_history.enabled(root):
        versions = sorted(knowledge_history.version_entries(root, note_id),
                          key=lambda row: (row['at'], row['id']), reverse=True)
    else:
        versions = (note_review.version(root, note_id, row['id'])
                    for row in note_review.versions(root, note_id))
    for version in versions:
        body = version['record']['body']
        _, paths = tree(body['nodes'])
        path = paths.get(item.node['id'])
        if path and content(path[0][-1]) != current:
            return path[0][-1]
        if not path:
            break
    return None


def lineup_ids(row):
    return set(row.get('lineup_ids', ())) | {link['lineup'] for link in row.get('lineup_links', ())}


def lineup_name(row):
    return (row.get('lineup_name') or row['title'].rpartition('-')[0]).strip()


def same_lineup(source, target):
    source_ids, target_ids = lineup_ids(source), lineup_ids(target)
    if source_ids and target_ids:
        return bool(source_ids & target_ids)
    return bool(lineup_name(source)) and lineup_name(source) == lineup_name(target)


def check_locks(service, conn, pending):
    locks = service.edit_locks
    locks.check_epoch(conn)
    for lock in locks._rows(conn):
        documents = pending.get(lock['note_id'])
        if documents is None or not locks._live(lock):
            continue
        before, after = documents
        try:
            changed = locks.snapshot({'body': before}, lock['resource']) != locks.snapshot({'body': after}, lock['resource'])
        except Conflict:
            changed = True
        if changed:
            raise EditLocked('目标位置正在编辑，请稍后重新打开同步列表', resource=lock['resource'])


def run(server, actor, note_id, data, season, *, apply=False, public=False):
    if not actor or actor['role'] != 'admin':
        raise PermissionError('只有管理员可以同步正式笔记')
    service = proposal_store(server)
    if not apply:
        return transfer(server, service, note_id, data, season, public=public)
    service.recover()
    # Use the same lock order as inline saves. This also fences edits from CLI tools.
    with service._db() as conn, store_lock(server.root, wait=True):
        json_store.recover(server.root)
        return transfer(server, service, note_id, data, season, public=public, conn=conn)


def transfer(server, service, note_id, data, season, *, public, conn=None):
    apply = conn is not None
    root = server.root
    rows = {row['id']: row for row in json_store.reader_index(root) if seasons.matches(row, season)}
    source_row = rows[note_id]
    if (source_row['type'] != 'lineup' or not source_row.get('player_id')
            or not (lineup_ids(source_row) or lineup_name(source_row))):
        raise ValueError('当前笔记没有可用的棋手或阵容关联')
    assert_formal_write(server, note_id, public=public)
    source = service._note(note_id)
    source_revision = source['metadata']['revision']
    if data.get('revision') != source_revision:
        raise Conflict('源笔记已更新，请刷新后重试')
    node_id = data.get('node_id')
    if not isinstance(node_id, str):
        raise ValueError('缺少同步位置')
    source_root, paths = tree(source['body']['nodes'])
    path = paths[node_id][0]
    item = path[-1]
    previous = previous_scope(root, note_id, item)
    baseline = previous or item
    source_text = markdown(item)
    selected = data.get('targets')
    draft = data.get('draft')
    if apply and (not isinstance(selected, dict) or not selected or len(selected) > len(rows)):
        raise ValueError('请选择要同步的笔记')
    if 'draft' in data and (not apply or len(selected) != 1 or not isinstance(draft, str)):
        raise ValueError('编辑稿只能同步到一篇目标笔记')
    candidates = []
    changes = {}
    players = {} if apply else player_catalog(root)
    for nid, row in rows.items():
        if (nid == note_id or row['type'] != 'lineup' or not row.get('player_id')
                or row['player_id'] == source_row['player_id']
                or not same_lineup(source_row, row)
                or (apply and nid not in selected)):
            continue
        record = service._note(nid)
        revision = record['metadata']['revision']
        player = players.get(row['player_id'], {}).get('name') or row['title'].rpartition('-')[2]
        candidate = {'id': nid, 'title': row['title'], 'player': player, 'revision': revision}
        candidates.append(candidate)
        if apply:
            if selected[nid] != revision:
                raise Conflict('目标笔记已更新，请重新打开同步列表')
            assert_formal_write(server, nid, public=public)
        before = record['body']
        try:
            target, start, end, nodes = target_scope(source_root, path, before)
        except Ambiguous as exc:
            if apply:
                raise Conflict(str(exc)) from exc
            candidate.update(status='ambiguous', reason=str(exc))
            continue
        latest = target is not None and content(target) == content(item)
        if target is None:
            candidate['status'] = 'missing'
        else:
            candidate.update(status='same' if latest or content(target) == content(baseline) else 'conflict',
                             text=markdown(target))
        candidate['latest'] = latest
        if not apply:
            continue
        if candidate['status'] == 'conflict' and not latest and draft is None:
            raise Conflict('目标段落存在冲突，请打开冲突浮窗确认编辑稿')
        if draft is not None:
            if target is None:
                raise Conflict('目标段落已不存在，请刷新同步列表')
            if draft == markdown(target):
                continue
            if draft != source_text:
                try:
                    nodes = edited_replacement(item, target, draft)
                except Ambiguous as exc:
                    raise Conflict(str(exc)) from exc
        if not latest or draft is not None:
            after = {**deepcopy(before), 'nodes': [*before['nodes'][:start], *nodes, *before['nodes'][end:]]}
            json_document.validate(after)
            if before != after:
                changes[nid] = (before, after)
    if not apply:
        return {'historical': previous is not None, 'baseline': markdown(baseline),
                'source_text': source_text, 'candidates': candidates}
    if set(selected) != {row['id'] for row in candidates}:
        raise Conflict('目标笔记的阵容或赛季关联已变化，请重新打开同步列表')
    results = []
    check_locks(service, conn, changes)
    for candidate in candidates:
        nid = candidate['id']
        if nid not in changes:
            results.append({'id': nid, 'status': 'latest'})
            continue
        try:
            json_store.edit(root, nid, {'revision': candidate['revision'], 'document': changes[nid][1]},
                            public=True, _locked=True)
            results.append({'id': nid, 'status': 'saved'})
        except OSError:
            results.append({'id': nid, 'status': 'unknown', 'error': '保存结果待确认，请刷新列表核对'})
            break
        except (Busy, ValueError) as exc:
            results.append({'id': nid, 'status': 'failed', 'error': str(exc)})
    done = {row['id'] for row in results}
    results.extend({'id': nid, 'status': 'failed', 'error': '前一篇保存中断，本篇尚未写入'} for nid in selected if nid not in done)
    return {'results': results}
