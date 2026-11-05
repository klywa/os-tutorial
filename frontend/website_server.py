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
from edit_locks import EditLocked
from card_publication import CardVersionChanged


def public_catalog(root):
    index=reader_store.index(root)
    projections=[]
    for row in index.get('notes',[]):
        value=reader_store.cached(root,row)
        if value is None:
            record=store.load_record(root,row['id'],clone=False)
            reader_store.write_record(root,record)
            value=reader_store.cached(root,row) or reader_store.projection(record)
        projections.append(value)
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

        def actor(self):
            return self.server.auth.actor(self.headers.get('Cookie'))

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
            from site_access import session
            return session(self.server,self.headers.get('Cookie'),public=True)

        def discard_small_body(self):
            if getattr(self,'_body_read',False):return
            self._body_read=True
            if self.headers.get('Transfer-Encoding'):return
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:return
            if not 0<length<=65536:return
            previous=self.connection.gettimeout()
            try:
                self.connection.settimeout(2)
                self.rfile.read(length)
            except OSError:pass
            finally:self.connection.settimeout(previous)

        def do_GET(self):
            try:
                path=self.request_path()
                if path=='/api/health' and self.client_address[0] in ('127.0.0.1','::1'):
                    return self.response(200,{'ok':True,'mode':'public'})
                if not self.trusted():return self.response(403,{'error':'请求主机无效'})
                root=self.server.root
                query=parse_qs(urlsplit(self.path).query)
                if path=='/api/auth/me':return self.response(200,self.who())
                if path.startswith('/api/') and not self.actor():
                    return self.response(401,{'error':'请先登录'})
                if path=='/api/edit-locks':
                    if not self.actor():return self.response(401,{'error':'请先登录'})
                    from site_access import get_locks
                    return self.response(200,get_locks(self.server,self.actor(),self.path))
                if path=='/api/proposals':
                    if not self.actor():return self.response(401,{'error':'请先登录'})
                    from site_access import get_proposals
                    return self.response(200,get_proposals(self.server,self.actor(),self.path))
                if path=='/api/sync-conflicts' or re.fullmatch(r'/api/sync-conflicts/[^/]+',path):
                    if not self.actor():return self.response(401,{'error':'请先登录管理员'})
                    from site_access import get_sync_conflicts
                    return self.response(200,get_sync_conflicts(self.server,self.actor(),None if path=='/api/sync-conflicts' else path.rsplit('/',1)[-1]))
                if path=='/api/admin/sync':
                    if not self.actor():return self.response(401,{'error':'请先登录管理员'})
                    from site_access import sync_status
                    return self.response(200,sync_status(self.server)) if self.actor()['role']=='admin' else self.response(403,{'error':'只有管理员可以查看同步状态'})
                if path=='/api/dashboard':
                    import dashboard
                    return self.response(200,sanitize(dashboard.snapshot(root,scope=query.get('scope',['all'])[0])),etag=True)
                if path=='/api/dashboard/usage/matches':
                    if not self.identity():return self.response(401,{'error':'请先登录管理员'})
                    if self.actor()['role']!='admin':return self.response(403,{'error':'只有管理员可以管理匹配'})
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
                if path=='/api/cards/status':
                    from card_publication import status
                    return self.response(200,status(root,self.server.state_dir))
                match=re.fullmatch(r'/api/cards/([^/]+)/images/(thumb|image)',path)
                if match:
                    from card_publication import resolve
                    folder,version=resolve(root,self.server.state_dir,query.get('version',[None])[0])
                    manifest=store.read(folder/'images.json',{})
                    key=manifest.get('entities',{}).get(match[1],{}).get(match[2])
                    entry=manifest.get('assets',{}).get(key,{})
                    folder=folder.resolve();target=(folder/entry.get('path','__missing__')).resolve()
                    if not key or not target.is_relative_to(folder) or not target.is_file():raise KeyError('图片不存在')
                    return self.file(target,cache='private, no-store')
                if path=='/api/cards' or re.fullmatch(r'/api/cards/[^/]+',path):
                    from card_publication import resolve
                    folder,version=resolve(root,self.server.state_dir,query.get('version',[None])[0])
                    try:
                        cards=store.read(folder/'cards.json',[])
                        images=store.read(folder/'images.json',{}).get('entities',{})
                    except OSError:
                        resolve(root,self.server.state_dir,version)
                        raise
                    resolve(root,self.server.state_dir,version)
                    cards=[{**c,'image_status':'ready' if c['id'] in images else 'missing',
                        **{kind+'_url':f'/api/cards/{c["id"]}/images/{kind}?version={version}' if kind in images.get(c['id'],{}) else None for kind in ('thumb','image')}} for c in cards]
                    if path!='/api/cards':
                        cards=next((c for c in cards if c['id']==path.split('/')[-1]),None)
                        if cards is None:raise KeyError('卡牌不存在')
                    resolve(root,self.server.state_dir,version)
                    return self.response(200,cards,etag=True,headers={'X-Cards-Version':version})
                if path.startswith('/api/'):raise KeyError('接口不存在')
                dist=self.server.dist.resolve()
                target=(dist/path.lstrip('/')).resolve()
                if not target.is_relative_to(dist):raise KeyError('页面不存在')
                if not target.is_file():
                    if path not in ('/','/admin','/admin/'):raise KeyError('页面不存在')
                    target=dist/'index.html'
                if not target.exists():return self.response(503,{'error':'前端尚未构建'})
                hashed_asset=path.startswith('/assets/') and re.search(r'-[A-Za-z0-9_-]{8,}\.(?:js|css)$',target.name)
                return self.file(target,cache='public, max-age=31536000, immutable' if hashed_asset else 'no-cache')
            except EditLocked as exc:self.response(423,{'error':str(exc),'reason':exc.reason,'resource':exc.resource})
            except (workspace.Conflict,workspace.Busy) as exc:self.response(423,{'error':str(exc)})
            except PermissionError as exc:self.response(403,{'error':str(exc)})
            except CardVersionChanged:self.response(409,{'error':'卡牌资料已更新，请重新载入','reason':'cards_version_changed'})
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
            from website_sync import SyncBusy, SyncBlocked, save_lock
            from site_access import is_proposal_path,mutate_proposal
            from proposals import ProposalForbidden
            from edit_locks import EditLocked
            try:
                path=self.request_path()
                authpath=path in ('/api/auth/login','/api/auth/logout','/api/auth/role') and self.command=='POST'
                noteedit=(path=='/api/notes' and self.command=='POST') or (re.fullmatch(r'/api/notes/[^/]+',path) and self.command=='PUT')
                matching=path=='/api/dashboard/usage/matches' and self.command=='PUT'
                retry=path=='/api/admin/sync/retry' and self.command=='POST'
                resolving=bool(re.fullmatch(r'/api/sync-conflicts/[^/]+/resolve',path)) and self.command=='POST'
                proposal=is_proposal_path(path)
                lockpath=path.startswith('/api/edit-locks/') and self.command=='POST'
                entries=bool(re.fullmatch(r'/api/notes/[^/]+/entries',path)) and self.command=='PUT'
                if not (authpath or noteedit or matching or proposal or retry or lockpath or entries or resolving):
                    self.discard_small_body()
                    raise KeyError('接口不存在')
                if not self.trusted() or self.headers.get('Origin')!=self.server.public_origin:
                    self.discard_small_body()
                    return self.response(403,{'error':'请求来源无效'})
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    self.discard_small_body()
                    return self.response(415,{'error':'请求必须为JSON'})
                if self.headers.get('Transfer-Encoding'):raise ValueError('不支持此请求格式')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2_000_000:raise ValueError('请求大小无效')
                self._body_read=True
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('请求必须为对象')
                if path=='/api/auth/login':
                    status,cookie=self.server.auth.login(data.get('username'),data.get('password'),self.login_peer())
                    return self.auth_reply(status,{'ok':True} if status==200 else {'error':'登录尝试过多，请15分钟后重试' if status==429 else '账号或密码不正确'},cookie)
                if path=='/api/auth/logout':return self.auth_reply(200,{'ok':True},self.server.auth.cookie())
                if not self.identity():return self.response(401,{'error':'请先登录管理员'})
                if path=='/api/auth/role':
                    cookie=self.server.auth.switch_role(self.headers.get('Cookie'),data.get('role'))
                    from site_access import session
                    return self.auth_reply(200,session(self.server,cookie,public=True),cookie)
                if lockpath:
                    from site_access import mutate_locks
                    return self.response(200,mutate_locks(self.server,self.actor(),path,data))
                if proposal:
                    return self.response(200,mutate_proposal(self.server,self.actor(),path,self.command,data,public=True))
                if self.actor()['role']!='admin':return self.response(403,{'error':'编写员请通过正文编辑提交待审提案'})
                if resolving:
                    from site_access import resolve_sync_conflict
                    return self.response(200,resolve_sync_conflict(self.server,self.actor(),path.split('/')[-2],data,public=True))
                from site_access import enqueue_sync,formal_save
                if retry:
                    with save_lock(self.server.state_dir):value=enqueue_sync(self.server,force=True)
                    return self.response(202,value)
                with save_lock(self.server.state_dir),formal_save(self.server):
                    getattr(self.server.sync,'_assert_active',lambda:None)()
                    if entries:
                        from site_access import proposal_store,sync_status
                        if data.get('note_id')!=path.split('/')[-2]:raise ValueError('笔记标识不一致')
                        proposal_store(self.server).recover()
                        previous=proposal_store(self.server).saved_changes(self.actor(),data)
                        if previous is not None:return self.response(200,sanitize({**previous,'sync':sync_status(self.server)}))
                    from site_access import assert_formal_write
                    assert_formal_write(self.server,path.split('/')[3] if entries or (noteedit and path!='/api/notes') else None,public=True)
                    if matching:
                        import usage_matches
                        value=usage_matches.save(self.server.root,data)
                    elif entries:
                        from site_access import proposal_store
                        if data.get('note_id')!=path.split('/')[-2]:raise ValueError('笔记标识不一致')
                        value=proposal_store(self.server).apply_changes(self.actor(),data)
                    elif path=='/api/notes':value=workspace.create_note(self.server.root,data)
                    else:
                        from site_access import edit_note
                        value=edit_note(self.server,self.actor(),path.split('/')[-1],data)
                    value={**value,'sync':enqueue_sync(self.server)}
                return self.response(200,sanitize(value))
            except EditLocked as exc:self.response(423,{'error':str(exc),'reason':exc.reason,'resource':exc.resource})
            except Unconfigured:self.response(503,{'error':'管理员配置不可用'})
            except PermissionError as exc:self.response(403,{'error':str(exc)})
            except ProposalForbidden as exc:self.response(403,{'error':str(exc)})
            except SyncBusy:self.response(423,{'error':'其他保存或发布正在完成，请稍后重试；当前草稿已保留','reason':'save_busy'})
            except (SyncBlocked,workspace.Busy) as exc:self.response(423,{'error':str(exc)})
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
    from site_access import proposal_store
    proposals=proposal_store(server)
    if proposals.recovery_pending():
        with sync_lock(server.state_dir):proposals.recover()
    server.dist=Path(__file__).resolve().parent/'dist'
    # Clean staged releases start while the publisher holds its activation lock.
    # Only an interrupted existing release needs to acquire it for recovery.
    if (server.root/store.JOURNAL).exists():
        with sync_lock(server.state_dir):recover(server.root)
