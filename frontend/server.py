"""Local-only API and static frontend; run using the project's Python runtime."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, unquote, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
sys.path.insert(0, str(ROOT / 'frontend'))
import wxq
import workspace
import crawler


def recover_before_read(root):
    """Replay abandoned journals when idle; never wait on a live writer.

    Reader projections use the self-contained, atomically replaced index. A
    writer may be updating derived files, but readers can still use its previous
    committed index. Recovery and every actual mutation retain the writer lock.
    """
    journals=('raw/knowledge/pending-json-save.json','raw/knowledge/pending-cards.json','knowledge/pending-save.json','knowledge/pending-cards.json',
              'knowledge/pending-note-link.json','raw/transcript-edit-pending.json')
    if not any((root/path).is_file() for path in journals):
        return
    try:
        with workspace.store_lock(root):
            workspace.recover(root)
    except workspace.Busy:
        pass  # Active save: read the last complete atomic index, without replay.


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def response(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def trusted(self):
        # Avoid cross-origin writes / DNS rebinding on a loopback service.
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in allowed:
            return False
        origin = self.headers.get('Origin')
        return not origin or origin in {'http://' + value for value in allowed} | {'http://127.0.0.1:5173', 'http://localhost:5173'}

    def do_GET(self):
        if not self.trusted():
            return self.response(403, {'error': '只允许本机页面访问'})
        path = unquote(urlsplit(self.path).path)
        player = parse_qs(urlsplit(self.path).query).get('player', [None])[0]
        try:
            if path.startswith('/api/crawler/'):
                suffix = path.removeprefix('/api/crawler/')
                store = self.server.crawler.store
                if suffix == 'settings' or suffix == 'searches':
                    return self.response(200, store.settings())
                if suffix == 'jobs':
                    return self.response(200, store.jobs())
                if suffix == 'activity':
                    return self.response(200, store.activity())
                if suffix.startswith('jobs/'):
                    job = store.job(suffix.split('/')[1])
                    if job['state'] == 'deleted':
                        raise KeyError('任务已删除')
                    return self.response(200, job)
                if suffix == 'creators':
                    return self.response(200, store.creators())
                return self.response(404, {'error': '接口不存在'})
            if path.startswith('/api/sources/') and path.endswith('/transcript'):
                return self.response(200, crawler.transcript(self.server.root, path.split('/')[-2]))
            if path.startswith('/api/topics/'):
                from topics import TopicStore, catalog
                topics=TopicStore(self.server.root)
                suffix=path.removeprefix('/api/topics/')
                from lineup_catalog import LineupCatalog
                if suffix=='lineup-suggestions':return self.response(200,LineupCatalog(self.server.root).suggestions())
                if suffix=='catalog':return self.response(200,catalog(self.server.root))
                if suffix=='queue':return self.response(200,topics.snapshot())
                if suffix=='lineups':return self.response(200,topics.roster())
                if suffix=='lineups/naming-candidates':return self.response(200,LineupCatalog(self.server.root).naming())
                if suffix.startswith('lineups/') and suffix.endswith('/variants'):return self.response(200,LineupCatalog(self.server.root).variants(suffix.split('/')[1]))
                if suffix=='candidates':return self.response(200,topics.pending())
                return self.response(404,{'error':'主题接口不存在'})
            if path == '/api/cards' or path.startswith('/api/cards/'):
                from card_images import image_fields, image_file
                if '/images/' in path:
                    eid, kind = path.removeprefix('/api/cards/').split('/images/', 1)
                    target = image_file(self.server.root, eid, kind)
                    body = target.read_bytes()
                    mime = 'image/png' if body.startswith(b'\x89PNG') else 'image/jpeg' if body.startswith(b'\xff\xd8') else 'image/webp' if body.startswith(b'RIFF') else 'image/gif'
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'private, max-age=3600')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                cards = wxq.read_json(self.server.root / 'knowledge/cards/index.json', {}).get('cards', [])
                images = wxq.read_json(self.server.root / 'entities/assets/index.json', {})
                cards = [{**c, **image_fields(self.server.root, c['id'], images)} for c in cards]
                if path == '/api/cards':
                    return self.response(200, [{k: c.get(k) for k in
                        ['id', 'name', 'category', 'aliases', 'effect', 'faction', 'tier', 'awakened','thumb_url','image_url','image_status']}
                        for c in cards])
                card = next((c for c in cards if c['id'] == path.removeprefix('/api/cards/')), None)
                return self.response(200 if card else 404, card or {'error': '卡牌不存在'})
            if path == '/api/sources/staging':
                from source_staging import Staging
                return self.response(200,Staging(self.server.root).get())
            if path == '/api/sources/tags':
                from source_edit import tag_catalog
                return self.response(200,tag_catalog(self.server.root))
            if path == '/api/sources':
                recover_before_read(self.server.root)
                return self.response(200, crawler.source_rows(self.server.root, self.server.crawler.store))
            if path.startswith('/api/'):
                recover_before_read(self.server.root)
                if path == '/api/markdown-sync':
                    import markdown_sync
                    state=markdown_sync.status(self.server.root)
                    return self.response(200, {'issues':state['issues'],'files':{p:{k:b[k] for k in ('note','branch','revision','hash')} for p,b in state['files'].items()}})
                if path.startswith('/api/notes/') and path.endswith('/revision'):
                    import json_store
                    if json_store.enabled(self.server.root):
                        index=json_store.read(self.server.root/json_store.INDEX,{})
                        nid=path.split('/')[-2]
                        nid=index.get('aliases',{}).get(nid,nid)
                        row=next((n for n in index.get('notes',[]) if n['id']==nid),None)
                        return self.response(200,{'revision':row['revision']}) if row else self.response(404,{'error':'笔记不存在'})
                    note=next((n for n in workspace.notes(self.server.root) if n['id']==path.split('/')[-2]),None)
                    return self.response(200,{'revision':note['revision']}) if note else self.response(404,{'error':'笔记不存在'})
                if path == '/api/notes':
                    from lineup_catalog import LineupCatalog
                    from note_links import project_notes
                    return self.response(200, project_notes(self.server.root))
                if path.startswith('/api/notes/') and path.endswith('/reading'):
                    from lineup_layout import reading_document
                    parts = path.split('/')
                    import json_store
                    note = (json_store.resolve_note(self.server.root, parts[-2], player) if json_store.enabled(self.server.root) else next((n for n in workspace.notes(self.server.root) if n['id'] == parts[-2]), None)) if len(parts) == 5 else None
                    return self.response(200, reading_document(note,player)) if note else self.response(404, {'error': '笔记不存在'})
                if path.startswith('/api/notes/'):
                    import json_store
                    if json_store.enabled(self.server.root):
                        note=json_store.resolve_note(self.server.root,path.split('/')[-1],player)
                        return self.response(200 if note else 404,note or {'error':'笔记不存在'})
                    from note_links import project_notes
                    note = next((n for n in project_notes(self.server.root) if n['id'] == path.split('/')[-1]), None)
                    if note and player:
                        import player_branches
                        note = player_branches.project(note, player)
                    return self.response(200 if note else 404, note or {'error': '笔记不存在'})
                if path == '/api/options':
                    entities = [{**{k: e.get(k) for k in ['id', 'name', 'category', 'aliases']},
                                 'properties': {'type': e.get('properties', {}).get('type')}} for e in wxq.entities(self.server.root)]
                    return self.response(200, {'entities': entities, 'factions': workspace.factions(self.server.root), 'sections': wxq.SECTIONS})
            if path.startswith('/api/'):
                return self.response(404, {'error': '接口不存在'})
            target = (ROOT / 'frontend/dist' / path.lstrip('/')).resolve()
            dist = (ROOT / 'frontend/dist').resolve()
            if not target.is_relative_to(dist):
                return self.response(403, {'error': '非法路径'})
            if not target.is_file():
                target = dist / 'index.html'
            if not target.exists():
                return self.response(503, {'error': '请先在 frontend 运行 npm install 和 npm run build'})
            import mimetypes
            body = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            if target.suffix == '.html':
                self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(body)
        except workspace.Busy as exc:
            self.response(423, {'error': str(exc)})
        except KeyError as exc:
            self.response(404, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.response(400, {'error': str(exc), **({'row_errors':exc.row_errors} if hasattr(exc,'row_errors') else {})})

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def do_DELETE(self):
        self.mutate()

    def mutate(self):
        if not self.trusted() or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.response(403, {'error': '请求来源或格式无效'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2_000_000:
                raise ValueError('请求内容大小无效')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('请求应为对象')
            path = unquote(urlsplit(self.path).path)
            store = self.server.crawler.store
            if path.startswith('/api/markdown-sync/'):
                import markdown_sync
                return self.response(200,markdown_sync.resolve(self.server.root,path.split('/')[-1],payload))
            if path.startswith('/api/topics/'):
                from topics import TopicStore
                topics=TopicStore(self.server.root)
                from lineup_catalog import LineupCatalog
                catalog=LineupCatalog(self.server.root)
                if path=='/api/topics/lineups/cleanup/preview':
                    from lineup_cleanup import Cleanup
                    result=Cleanup(self.server.root).preview()
                elif path=='/api/topics/lineups/cleanup/apply':
                    from lineup_cleanup import Cleanup
                    result=Cleanup(self.server.root).apply(payload.get('token'))
                elif path=='/api/topics/lineups':
                    if 'names' in payload:result=topics.save_roster(payload)
                    else:result=catalog.save(payload)
                elif path=='/api/topics/lineups/batch' and self.command=='PUT':result=catalog.save_batch(payload)
                elif path=='/api/topics/lineups/batch' and self.command=='POST':result=catalog.save_quick_batch(payload)
                elif path.startswith('/api/topics/lineups/') and path.endswith('/restore') and self.command=='POST':result=catalog.restore(path.split('/')[-2],payload)
                elif path.startswith('/api/topics/lineups/') and len(path.split('/'))==5 and self.command=='DELETE':result=catalog.delete(path.split('/')[-1],payload)
                elif path=='/api/topics/lineups/preview':result=catalog.preview()
                elif path=='/api/topics/lineups/apply':result=catalog.apply(payload.get('token'))
                elif path=='/api/topics/lineups/merge':result=catalog.merge(payload)
                elif path=='/api/topics/lineups/variants':result=catalog.save_variants(payload)
                elif path.startswith('/api/topics/lineups/naming-candidates/'):result=catalog.resolve_naming(path.split('/')[-1],payload)
                elif path=='/api/topics/lineups/associate':
                    from note_links import associate
                    result=associate(self.server.root,payload)
                elif path=='/api/topics/lineups/bind':result=catalog.bind(payload)
                elif path=='/api/topics/control':
                    if payload.get('action') in ['retry','extract','reextract']:topics.sync(crawler.source_rows(self.server.root,store))
                    result=topics.control(payload.get('action'),payload.get('source'))
                elif path.startswith('/api/topics/candidates/'):
                    result=topics.resolve(path.split('/')[-1],payload)
                else:return self.response(404,{'error':'主题接口不存在'})
                return self.response(200,result)
            if path == '/api/crawler/settings' or (path == '/api/crawler/searches' and self.command == 'PUT'):
                result = store.settings(payload if path.endswith('settings') else {'search': payload})
            elif path == '/api/crawler/links' and self.command == 'POST':
                from link_jobs import start_links,parse_links
                result=parse_links(payload.get('text','')) if payload.get('preview') else start_links(store,payload.get('text',''),payload.get('tags',[]))
            elif path == '/api/crawler/searches' and self.command == 'POST':
                if not payload.get('keywords'):
                    raise ValueError('请填写搜索关键词')
                store.settings({'search': payload})
                result = store.new_job(payload)
            elif self.command == 'DELETE' and path.startswith('/api/crawler/creators/'):
                result = store.delete_creator(path.split('/')[-1])
            elif path == '/api/crawler/creators' and self.command == 'POST':
                result = store.create_creator(payload)
            elif path.startswith('/api/crawler/creators/') and len(path.split('/')) == 5 and self.command == 'PUT':
                if payload.get('uid') and payload['uid'] != path.split('/')[-1]:
                    raise ValueError('编辑时不可更换UP主UID')
                result = store.update_creator(path.split('/')[-1], payload)
            elif path == '/api/crawler/creators/resume':
                result = store.resume_creators()
            elif path.startswith('/api/crawler/creators/') and path.endswith('/retry-tags'):
                result = store.retry_tags(path.split('/')[-2])
            elif path == '/api/crawler/creators/check':
                result = [store.check_creator(r['uid']) for r in store.creators() if r.get('enabled', True)]
            elif path.startswith('/api/crawler/creators/') and path.endswith('/check'):
                result = store.check_creator(path.split('/')[-2])
            elif path.startswith('/api/crawler/tasks/') and len(path.split('/')) == 6 and self.command == 'POST':
                bvid, operation = path.split('/')[-2:]
                result = store.control_task(bvid, operation)
            elif self.command == 'DELETE' and path.startswith('/api/crawler/jobs/') and len(path.split('/')) == 5:
                result = store.delete_job(path.split('/')[-1])
            elif path.startswith('/api/crawler/jobs/'):
                jid, operation = path.split('/')[-2:]
                if store.job(jid, False)['state'] == 'deleted':
                    raise KeyError('任务已删除')
                if operation == 'stop':
                    store.stop(jid)
                elif operation in ['stop-download', 'stop-transcribe']:
                    store.stop_phase(jid, operation)
                elif operation == 'resume':
                    store.resume(jid)
                elif operation == 'retry':
                    store.retry(jid, payload.get('bvids'))
                elif operation == 'start':
                    store.enqueue(jid, payload.get('bvids', []))
                else:
                    return self.response(404, {'error': '接口不存在'})
                result = store.job(jid)
            elif path.startswith('/api/sources/staging'):
                from source_staging import Staging
                basket=Staging(self.server.root)
                if path.endswith('/paths'):result=basket.paths()
                elif path.endswith('/prompt'):result=basket.prompt()
                elif path.endswith('/clear'):result=basket.clear(payload.get('revision'))
                elif self.command=='DELETE':result=basket.remove(path.split('/')[-1])
                else:result=basket.add(payload.get('ids',[]))
            elif path == '/api/sources/paths':
                result = crawler.batch_paths(self.server.root, payload.get('ids'))
            elif path.startswith('/api/sources/') and path.endswith('/creator'):
                sid = path.split('/')[-2]
                source = next((s for s in workspace.sources(self.server.root) if s['id'] == sid), None)
                if not source:
                    raise KeyError('来源不存在')
                import re
                match = re.search(r'BV[a-zA-Z0-9]+', source['url'])
                if not match:
                    raise ValueError('仅支持B站视频的UP主')
                detail = crawler.Bilibili(store.settings()['cookies'],root=self.server.root).detail(match.group())
                if not detail or not detail.get('space_url'):
                    raise ValueError('无法获取该视频UP主，请重试')
                result = {'name': detail['author'], 'url': detail['space_url']}
            elif self.command == 'POST' and path == '/api/notes':
                result = workspace.create_note(self.server.root, payload)
            elif self.command == 'PUT' and path.startswith('/api/notes/'):
                workspace.edit(self.server.root, path.split('/')[-1], payload)
                from note_links import project_notes
                result=next(n for n in project_notes(self.server.root) if n['id']==path.split('/')[-1])
            elif self.command == 'POST' and path == '/api/sources':
                result = workspace.register_source(self.server.root, payload)
            elif self.command == 'PUT' and path.startswith('/api/sources/') and path.endswith('/transcript'):
                from reference_store import save_transcript
                result = save_transcript(self.server.root, path.split('/')[-2], payload)
            elif self.command == 'PUT' and path.startswith('/api/sources/'):
                from source_edit import save_metadata
                result = save_metadata(self.server.root, path.split('/')[-1], payload, store)
                from source_staging import Staging
                Staging(self.server.root).prune()
            else:
                return self.response(404, {'error': '接口不存在'})
            self.response(200, result)
        except workspace.Conflict as exc:
            self.response(409, {'error': str(exc), **({'uid': exc.uid} if hasattr(exc, 'uid') else {}), **({'lineup_ids': exc.lineup_ids} if hasattr(exc, 'lineup_ids') else {})})
        except workspace.Busy as exc:
            self.response(423, {'error': str(exc)})
        except KeyError as exc:
            self.response(404, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.response(400, {'error': str(exc), **({'row_errors':exc.row_errors} if hasattr(exc,'row_errors') else {})})
        except OSError:
            self.response(500, {'error': '保存失败，草稿已保留；请检查文件权限并重试'})


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_close(self):
        if hasattr(self, 'markdown_watcher'):
            self.markdown_watcher.close()
        if hasattr(self, 'crawler'):
            self.crawler.close()
        super().server_close()


def create_server(root=ROOT, port=8765, start_worker=False):
    server = LocalServer(('127.0.0.1', port), Handler)
    server.root = Path(root)
    server.crawler = crawler.Runtime(root)
    import json_store
    if not json_store.enabled(root):
        import markdown_sync
        server.markdown_watcher = markdown_sync.Watcher(root)
        server.markdown_watcher.start()
    from source_staging import Staging
    Staging(root).prune()
    if start_worker:
        from note_links import auto_link
        auto_link(root)
        server.crawler.start()
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    workspace.migrate(args.root)
    from player_identity import migrate as migrate_players
    migrate_players(args.root)
    server = create_server(args.root, args.port, start_worker=True)
    print(f'万象棋工具：http://127.0.0.1:{args.port}', flush=True)
    if args.open_browser:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    finally:
        server.server_close()
