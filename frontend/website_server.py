"""Public request surface. No crawler runtime, timers or online fetches."""
import json
import mimetypes
import ipaddress
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit

import json_store as store
import reader_store
import workspace
from website_auth import Auth, Unconfigured
from website_data import sanitize


def public_catalog(root):
    index=reader_store.index(root)
    projections=[reader_store.projection(store.load_record(root,row['id'],clone=False)) for row in index.get('notes',[])]
    return {'workspace_id':reader_store.workspace_id(root),'format':1,'revision':store.digest(index),
            'ready':True,'notes':[p['summary'] for p in projections]},projections


def handler_class(base):
    class PublicHandler(base):
        def trusted(self):
            return self.headers.get('Host','').lower()==urlsplit(self.server.public_origin).netloc.lower()

        def request_path(self):
            raw=urlsplit(self.path).path
            prefix=self.server.base_path
            if prefix and not (raw==prefix or raw.startswith(prefix+'/')):raise KeyError('页面不存在')
            path=unquote(raw[len(prefix):] if prefix else raw) or '/'
            if '\\' in path or any(p in ('.','..') for p in path.split('/')):raise KeyError('页面不存在')
            return path

        def identity(self):
            return self.server.auth.identity(self.headers.get('Cookie'))

        def login_peer(self):
            peer=self.client_address[0]
            # The service binds loopback. Caddy sets/appends the actual client
            # address; using the rightmost entry ignores caller-supplied prefixes.
            if peer in ('127.0.0.1','::1'):
                forwarded=self.headers.get('X-Forwarded-For','').split(',')[-1].strip()
                try:return str(ipaddress.ip_address(forwarded))
                except ValueError:pass
            return peer

        def auth_reply(self,code,data,cookie=None):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(body)

        def who(self):
            username=self.identity()
            result={'mode':'public','role':'admin' if username else 'guest','username':username,'base_path':self.server.base_path}
            if username:
                try:result['sync']=self.server.sync.status()
                except (RuntimeError,OSError,ValueError):result['sync']={'state':'conflict','message':'Git同步暂时不可用，编辑已暂停'}
            return result

        def do_GET(self):
            try:
                path=self.request_path()
                if path=='/api/health' and self.client_address[0] in ('127.0.0.1','::1'):
                    return self.response(200,{'ok':True,'mode':'public'})
                if not self.trusted():return self.response(403,{'error':'请求主机无效'})
                root=self.server.root
                query=parse_qs(urlsplit(self.path).query)
                if path=='/api/auth/me':return self.response(200,self.who())
                if path=='/api/admin/sync':
                    return self.response(200,self.server.sync.status()) if self.identity() else self.response(401,{'error':'请先登录管理员'})
                if path=='/api/dashboard':
                    import dashboard
                    return self.response(200,sanitize(dashboard.snapshot(root,scope=query.get('scope',['all'])[0])),etag=True)
                if path=='/api/dashboard/usage/matches':
                    if not self.identity():return self.response(401,{'error':'请先登录管理员'})
                    import usage_matches
                    return self.response(200,sanitize(usage_matches.editor(root)))
                if path in ('/api/notes/catalog','/api/notes/search','/api/notes'):
                    cat,projections=public_catalog(root)
                    if path=='/api/notes/search':
                        wanted=query.get('q',[''])[0].lower().split()
                        labels={e['id']:' '.join([e.get('name') or '',*(e.get('aliases') or [])]).lower() for e in reader_store.entities(root)}
                        ids=[p['summary']['id'] for p in projections if all(term in p['text']+' '+' '.join(labels.get(ref,'') for ref in p['refs']) for term in wanted)]
                        return self.response(200,{'ready':True,'revision':cat['revision'],'ids':ids},etag=True)
                    return self.response(200,sanitize(cat if path.endswith('catalog') else cat['notes']),etag=True)
                if path=='/api/options':
                    import wxq
                    from tactics import faction_references
                    factions={f['id']:dict(f) for f in workspace.FACTIONS}
                    cat,_=public_catalog(root)
                    for row in cat['notes']:
                        for ref in faction_references(row.get('meta',{})):
                            if ref.startswith('pending:'):factions[ref]={'id':ref,'name':ref[8:]+'（待确认）'}
                    return self.response(200,sanitize({'entities':reader_store.entities(root),'factions':list(factions.values()),'sections':wxq.SECTIONS}),etag=True)
                match=re.fullmatch(r'/api/notes/([^/]+)(?:/(reading|revision))?',path)
                if match:
                    nid,kind=match.groups()
                    note=store.resolve_note(root,nid,query.get('player',[None])[0])
                    if not note:raise KeyError('笔记不存在')
                    if kind=='revision':value={'revision':note['revision']}
                    elif kind=='reading':
                        from lineup_layout import reading_document
                        value=reading_document(note,query.get('player',[None])[0])
                    else:value=note
                    return self.response(200,sanitize(value),etag=True)
                match=re.fullmatch(r'/api/cards/([^/]+)/images/(thumb|image)',path)
                if match:
                    manifest=store.read(root/'website-data/images.json',{})
                    key=manifest.get('entities',{}).get(match[1],{}).get(match[2])
                    entry=manifest.get('assets',{}).get(key,{})
                    folder=(root/'website-data').resolve();target=(folder/entry.get('path','__missing__')).resolve()
                    if not key or not target.is_relative_to(folder) or not target.is_file():raise KeyError('图片不存在')
                    return self.file(target,cache='public, max-age=3600')
                if path=='/api/cards' or re.fullmatch(r'/api/cards/[^/]+',path):
                    cards=store.read(root/'website-data/cards.json',[])
                    images=store.read(root/'website-data/images.json',{}).get('entities',{})
                    cards=[{**c,'image_status':'ready' if c['id'] in images else 'missing',
                        **{kind+'_url':f'/api/cards/{c["id"]}/images/{kind}' if kind in images.get(c['id'],{}) else None for kind in ('thumb','image')}} for c in cards]
                    if path!='/api/cards':
                        cards=next((c for c in cards if c['id']==path.split('/')[-1]),None)
                        if cards is None:raise KeyError('卡牌不存在')
                    return self.response(200,cards,etag=True)
                if path.startswith('/api/'):raise KeyError('接口不存在')
                dist=self.server.dist.resolve()
                target=(dist/path.lstrip('/')).resolve()
                if not target.is_relative_to(dist):raise KeyError('页面不存在')
                if not target.is_file():
                    if path not in ('/','/admin','/admin/'):raise KeyError('页面不存在')
                    target=dist/'index.html'
                if not target.exists():return self.response(503,{'error':'前端尚未构建'})
                return self.file(target)
            except (workspace.Conflict,workspace.Busy) as exc:self.response(423,{'error':str(exc)})
            except KeyError:self.response(404,{'error':'页面或接口不存在'})
            except (ValueError,TypeError) as exc:self.response(400,{'error':str(exc)})
            except OSError:self.response(503,{'error':'网站资料暂时不可用'})

        def file(self,target,cache='no-cache'):
            body=target.read_bytes()
            mime=mimetypes.guess_type(target.name)[0]
            if target.suffix=='.img':
                mime='image/png' if body.startswith(b'\x89PNG') else 'image/jpeg' if body.startswith(b'\xff\xd8') else 'image/webp' if body.startswith(b'RIFF') else 'image/gif'
            self.send_response(200);self.send_header('Content-Type',mime or 'application/octet-stream')
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control',cache)
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)

        def mutate(self):
            from website_sync import SyncBusy, SyncBlocked, sync_lock
            try:
                path=self.request_path()
                authpath=path in ('/api/auth/login','/api/auth/logout') and self.command=='POST'
                noteedit=(path=='/api/notes' and self.command=='POST') or (re.fullmatch(r'/api/notes/[^/]+',path) and self.command=='PUT')
                matching=path=='/api/dashboard/usage/matches' and self.command=='PUT'
                if not (authpath or noteedit or matching):raise KeyError('接口不存在')
                if not self.trusted() or self.headers.get('Origin')!=self.server.public_origin:
                    return self.response(403,{'error':'请求来源无效'})
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    return self.response(415,{'error':'请求必须为JSON'})
                if self.headers.get('Transfer-Encoding'):raise ValueError('不支持此请求格式')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2_000_000:raise ValueError('请求大小无效')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('请求必须为对象')
                if path=='/api/auth/login':
                    status,cookie=self.server.auth.login(data.get('username'),data.get('password'),self.login_peer())
                    return self.auth_reply(status,{'ok':True} if status==200 else {'error':'登录尝试过多，请15分钟后重试' if status==429 else '账号或密码不正确'},cookie)
                if path=='/api/auth/logout':return self.auth_reply(200,{'ok':True},self.server.auth.cookie())
                if not self.identity():return self.response(401,{'error':'请先登录管理员'})
                with sync_lock(self.server.state_dir):
                    if self.server.sync.status().get('state')!='synced':raise SyncBlocked('修改正在等待同步或发布，请稍后重试')
                    if matching:
                        import usage_matches
                        value=usage_matches.save(self.server.root,data)
                    elif path=='/api/notes':value=workspace.create_note(self.server.root,data)
                    else:value=workspace.edit(self.server.root,path.split('/')[-1],data)
                    self.server.sync.record_save()
                return self.response(200,sanitize(value))
            except Unconfigured:self.response(503,{'error':'管理员配置不可用'})
            except (SyncBusy,SyncBlocked,workspace.Busy) as exc:self.response(423,{'error':str(exc)})
            except workspace.Conflict as exc:self.response(409,{'error':str(exc)})
            except KeyError:self.response(404,{'error':'接口或笔记不存在'})
            except (ValueError,TypeError) as exc:self.response(400,{'error':str(exc)})
            except OSError:self.response(503,{'error':'保存或同步暂时不可用，请确认同步状态后重试'})

    return PublicHandler


def configure(server,base_path,origin,config,state_dir):
    from website_sync import SyncManager,sync_lock
    from website_data import recover
    parsed=urlsplit(origin)
    if parsed.scheme!='https' or not parsed.netloc or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('公网origin必须为HTTPS域名且不含路径')
    if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*',base_path):raise ValueError('无效的公网路径前缀')
    server.base_path=base_path
    server.public_origin=origin.rstrip('/')
    server.auth=Auth(config,base_path)
    server.state_dir=Path(state_dir)
    server.sync=SyncManager(server.root,server.state_dir)
    server.dist=Path(__file__).resolve().parent/'dist'
    # Clean staged releases start while the publisher holds its activation lock.
    # Only an interrupted existing release needs to acquire it for recovery.
    if (server.root/store.JOURNAL).exists():
        with sync_lock(server.state_dir):recover(server.root)
