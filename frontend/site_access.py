"""Shared local/public identities and private proposal HTTP operations."""
import json
from pathlib import Path
import re
from urllib.parse import parse_qs,urlsplit

from website_sync import SyncBlocked,sync_lock


def state_dir(server):
    return Path(getattr(server,'state_dir',Path(server.root)/'raw/site-state'))


def actor(server,cookie):
    auth=getattr(server,'auth',None)
    if auth:return auth.actor(cookie)
    return {'username':'local','role':'admin','account_role':'admin','allowed_roles':['admin','annotator']}


def session(server,cookie,public=False):
    identity=actor(server,cookie)
    result={'mode':'public' if public else 'local','base_path':getattr(server,'base_path',''),
            **(identity or {'username':None,'role':'guest','account_role':'guest','allowed_roles':[]})}
    if public and identity:
        try:result['sync']=server.sync.status()
        except (RuntimeError,OSError,ValueError):result['sync']={'state':'conflict','message':'Git同步暂时不可用，正式编辑已暂停'}
    return result


def proposal_store(server):
    if not hasattr(server,'proposals'):
        from proposals import ProposalStore
        path=state_dir(server)/'proposals.sqlite3' if hasattr(server,'public_origin') else Path(server.root)/'raw/proposals.sqlite3'
        server.proposals=ProposalStore(server.root,path)
    return server.proposals


def initialize_local(server):
    from website_auth import LocalAuth
    server.state_dir=Path(server.root)/'raw/site-state'
    server.auth=LocalAuth(Path(server.root)/'raw/auth-debug.json')
    proposals=proposal_store(server)
    if proposals.recovery_pending():
        with sync_lock(server.state_dir):proposals.recover()


def payload(handler):
    if handler.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('请求必须为JSON')
    if handler.headers.get('Transfer-Encoding'):raise ValueError('不支持此请求格式')
    length=int(handler.headers.get('Content-Length','0'))
    if not 0<length<=2_000_000:raise ValueError('请求大小无效')
    data=json.loads(handler.rfile.read(length))
    if not isinstance(data,dict):raise ValueError('请求必须为对象')
    return data


def is_proposal_path(path):
    return path=='/api/proposals' or bool(re.fullmatch(r'/api/proposals/[^/]+(?:/(approve|reject|withdraw))?',path))


def require_identity(identity):
    if not identity or identity['role'] not in ('admin','annotator'):raise PermissionError('请先登录')


def get_proposals(server,identity,request_url):
    require_identity(identity)
    query=parse_qs(urlsplit(request_url).query)
    return proposal_store(server).list(identity,**{key:query.get(key,[None])[0] for key in ('note_id','status','author')})


def mutate_proposal(server,identity,path,command,data,public=False):
    require_identity(identity)
    service=proposal_store(server)
    with sync_lock(state_dir(server)):
        service.recover()
        if path=='/api/proposals' and command=='POST':return service.submit(identity,data)
        match=re.fullmatch(r'/api/proposals/([^/]+)(?:/(approve|reject|withdraw))?',path)
        if not match:raise KeyError('提案接口不存在')
        item_id,action=match.groups()
        if action is None and command=='PUT':return service.update(identity,item_id,data)
        if action and command=='POST':
            if action=='approve':
                if identity['role']!='admin':raise PermissionError('只有管理员可以确认提案')
                # A retry after a lost HTTP response is a read of the completed
                # item, including when Git is still unavailable.
                approved=next((p for p in service.list(identity)['items'] if p['id']==item_id and p['status']=='approved'),None)
                if approved:return approved
                if public and server.sync.status().get('state')!='synced':
                    raise SyncBlocked('正式修改等待同步或发布，请稍后确认；仍可暂存提案')
            result=service.action(identity,item_id,action,data)
            if action=='approve' and public:server.sync.record_save()
            return result
        raise KeyError('提案操作不存在')
