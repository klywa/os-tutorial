"""Use the running local reviewer API and its edit locks from Codex."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import uuid


def add_parser(subparsers):
    parser = subparsers.add_parser('proposal-review', help='处理笔记提案批注及查询管理员改稿历史')
    commands = parser.add_subparsers(dest='operation', required=True)
    pending = commands.add_parser('pending')
    pending.add_argument('--note-id')
    commands.add_parser('show').add_argument('proposal_id')
    revise = commands.add_parser('revise')
    revise.add_argument('proposal_id')
    revise.add_argument('--file', type=Path, required=True)
    history = commands.add_parser('history')
    for key in ('note-id', 'proposal-id', 'kind', 'from-date', 'through-date'):
        history.add_argument('--' + key)
    history.add_argument('--export', type=Path)


def request(path, method='GET', payload=None):
    origin = 'http://127.0.0.1:8765'
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = Request(origin + '/api/' + path, method=method, data=body,
                  headers={'Content-Type': 'application/json', 'Origin': origin})
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(json.load(exc).get('error', str(exc))) from exc


def run(args):
    if args.operation == 'pending':
        query = {'status': 'pending'}
        if args.note_id:
            query['note_id'] = args.note_id
        proposals = request('proposals?' + urlencode(query))['items']
        return {'items': [item for item in proposals if any(
            a['status'] == 'open' for a in item['annotations']
        )]}
    if args.operation == 'history':
        keys = ('note_id', 'proposal_id', 'kind', 'from_date', 'through_date')
        result = request('proposals/history?' + urlencode({key: getattr(args, key) for key in keys if getattr(args, key)}))
        if args.export:
            with args.export.open('x', encoding='utf-8') as output:
                json.dump(result, output, ensure_ascii=False, indent=2)
        return result
    path = 'proposals/' + quote(args.proposal_id, safe='')
    item = request(path)
    if args.operation == 'show':
        return item
    changes = json.loads(args.file.read_text(encoding='utf-8'))
    if item['status'] != 'pending' or changes.get('revision') != item['revision']:
        raise ValueError('提案已更新，请重新读取提案后改稿')
    if set(changes) - {'revision', 'proposed_node', 'annotation_responses', 'evidence_changes', 'section_nodes'}:
        raise ValueError('改稿文件包含不支持的字段')
    if 'proposed_node' not in changes:
        raise ValueError('改稿文件需要 proposed_node')
    resource = ({'kind': 'slot', 'section_id': item['section_id'],
                 'left_id': item['after_id'] if item['after_id'] is not None else item['section_id']}
                if item['kind'] == 'insert' else {'kind': 'entry', 'id': item['node_id']})
    client = 'codex-review-' + uuid.uuid4().hex
    acquired = request('edit-locks/acquire', 'POST', {
        'client_id': client, 'note_id': item['note_id'], 'resource': resource,
    })
    lease = {key: acquired[key] for key in ('id', 'token')}
    try:
        return request(path, 'PUT', {**changes, 'client_id': client, 'lease': lease})
    except Exception:
        try:
            request('edit-locks/release', 'POST', {'client_id': client, 'leases': [lease]})
        except (OSError, ValueError):
            pass
        raise
