"""Disposable sync-conflict browser fixture; never opens the real knowledge store."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'frontend'), str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts')]
import json_store as store
import knowledge_conflicts as conflicts
import server
import website_data
from workspace import store_lock


def inject(folder):
    root = Path(folder).resolve()
    assert root.parent == (ROOT / 'raw/reports/knowledge-sync-20261103/browser').resolve()
    assert root.name.startswith('fixture-') and (root / 'browser-fixture').is_file()
    request = store.read(next((root / 'knowledge-sync/requests').glob('*.json')))
    third = deepcopy(request['right'])
    third['body']['nodes'][2]['value'] = '第三端新到达正文'
    with store_lock(root):
        conflicts.write_request(root, conflicts.create_request(request['base'], request['left'], third))


def run():
    output = ROOT / 'raw/reports/knowledge-sync-20261103/browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=output) as folder:
        root = Path(folder)
        (root / 'browser-fixture').touch()
        store.initialize(root)
        def record(nid, title):
            return {'body': {'schema_version': 6, 'nodes': [
                {'id': 'h', 'type': 'heading', 'level': 1, 'title': title},
                {'id': 'chapter', 'type': 'heading', 'level': 2, 'title': '核心机制'},
                {'id': 'a', 'type': 'entry', 'key': '说明', 'show_key': True, 'value': '共同原文正文'}]},
                'metadata': {'id': nid, 'type': 'other', 'title': title, 'path': 'knowledge/other/' + nid + '.json'}}
        base = record('sync-note', '同步冲突样例')
        current, incoming = deepcopy(base), deepcopy(base)
        current['body']['nodes'][2]['value'] = '网站当前正文'
        incoming['body']['nodes'][2]['value'] = '另一端待合并正文'
        store.save(root, [current, record('other-note', '正常编辑样例')], storage_version=2)
        with store_lock(root):
            conflicts.write_request(root, conflicts.create_request(base, current, incoming))
        website_data.export(root)
        config = root / 'accounts.json'
        config.write_text(json.dumps({'schema_version': 2, 'sessionSecret': 's' * 48,
            'accounts': [{'username': name, 'password': 'fixture', 'role': role}
                         for name, role in [('reviewer', 'admin'), ('alice', 'annotator')]]}), encoding='utf-8')
        http = server.create_server(root, 0, public=True, base_path='', auth_config=config, state_dir=root / 'state')
        http.auth.secure = False
        def status(**kwargs):
            ids = [group['note_id'] for group in conflicts.list_groups(root)]
            return {'state': 'pending-deploy', 'phase': 'pending-deploy', 'conflict_note_ids': ids, 'conflict_count': len(ids)}
        http.sync = SimpleNamespace(status=status, enqueue=status)
        print(json.dumps({'port': http.server_port, 'root': str(root)}), flush=True)
        try:
            http.serve_forever()
        finally:
            http.server_close()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--inject':
        inject(sys.argv[2])
    else:
        run()
