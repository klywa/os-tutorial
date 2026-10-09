"""Local-only API and static frontend; run using the project's Python runtime."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
import wxq
import workspace


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
        try:
            with workspace.store_lock(self.server.root, wait=True):
                workspace.recover(self.server.root)
                if path == '/api/notes':
                    return self.response(200, workspace.notes(self.server.root))
                if path.startswith('/api/notes/'):
                    note = next((n for n in workspace.notes(self.server.root) if n['id'] == path.split('/')[-1]), None)
                    return self.response(200 if note else 404, note or {'error': '笔记不存在'})
                if path == '/api/options':
                    entities = [{**{k: e.get(k) for k in ['id', 'name', 'category', 'aliases']},
                                 'properties': {'type': e.get('properties', {}).get('type')}} for e in wxq.entities(self.server.root)]
                    return self.response(200, {'entities': entities, 'factions': workspace.factions(self.server.root), 'sections': wxq.SECTIONS})
                if path == '/api/sources':
                    return self.response(200, workspace.sources(self.server.root))
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
            self.end_headers()
            self.wfile.write(body)
        except workspace.Busy as exc:
            self.response(423, {'error': str(exc)})

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
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
            if self.command == 'PUT' and path.startswith('/api/notes/'):
                result = workspace.edit(self.server.root, path.split('/')[-1], payload)
            elif self.command == 'POST' and path == '/api/sources':
                result = workspace.register_source(self.server.root, payload)
            elif self.command == 'PUT' and path.startswith('/api/sources/'):
                result = workspace.register_source(self.server.root, payload, path.split('/')[-1])
            else:
                return self.response(404, {'error': '接口不存在'})
            self.response(200, result)
        except workspace.Conflict as exc:
            self.response(409, {'error': str(exc)})
        except workspace.Busy as exc:
            self.response(423, {'error': str(exc)})
        except KeyError as exc:
            self.response(404, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self.response(400, {'error': str(exc)})
        except OSError:
            self.response(500, {'error': '保存失败，草稿已保留；请检查文件权限并重试'})


def create_server(root=ROOT, port=8765):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.root = Path(root)
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    workspace.migrate(args.root)
    server = create_server(args.root, args.port)
    print(f'万象棋工具：http://127.0.0.1:{args.port}', flush=True)
    if args.open_browser:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    server.serve_forever()
