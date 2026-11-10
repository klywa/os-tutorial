"""Shared local/public identities and private proposal HTTP operations."""
import json
from contextlib import contextmanager,nullcontext
from pathlib import Path
import re
from urllib.parse import parse_qs,urlsplit

from website_sync import SyncBlocked,sync_lock,save_lock


def state_dir(server):
    return Path(getattr(server,'state_dir',Path(server.root)/'raw/site-state'))


def actor(server,cookie):
    auth=getattr(server,'auth',None)
    if auth:return auth.actor(cookie)
    return {'username':'local','role':'admin','account_role':'admin','allowed_roles':['admin','annotator','viewer']}


def session(server,cookie,public=False):
    identity=actor(server,cookie)
    result={'mode':'public' if public else 'local','base_path':getattr(server,'base_path',''),
            **(identity or {'username':None,'role':'guest','account_role':'guest','allowed_roles':[]})}
    if identity and (public or identity['role']=='admin'):
        try:result['sync']=sync_status(server)
        except (RuntimeError,OSError,ValueError):result['sync']={'state':'conflict','message':'Git同步暂时不可用，正式编辑已暂停'}
    return result


def proposal_store(server):
    if not hasattr(server,'proposals'):
        from proposals import ProposalStore
        path=state_dir(server)/'proposals.sqlite3' if hasattr(server,'public_origin') else Path(server.root)/'raw/proposals.sqlite3'
        server.proposals=ProposalStore(server.root,path)
        from edit_locks import EditLocks
        server.edit_locks=EditLocks(server.proposals)
    return server.proposals


def initialize_local(server):
    from website_auth import LocalAuth
    server.state_dir=Path(server.root)/'raw/site-state'
    server.auth=LocalAuth(Path(server.root)/'raw/auth-debug.json')
    proposals=proposal_store(server)
    if proposals.recovery_pending():
        with sync_lock(server.state_dir):proposals.recover()
    from templates_http import proposal_store as template_proposal_store
    templates=template_proposal_store(server)
    if templates.receipt.exists():
        with sync_lock(server.state_dir):templates.recover()


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
    if not identity:raise PermissionError('请先登录')
    if identity['role'] not in ('admin','annotator'):raise PermissionError('浏览者没有编辑权限')


def get_proposals(server,identity,request_url):
    require_identity(identity)
    query=parse_qs(urlsplit(request_url).query)
    return proposal_store(server).list(identity,**{key:query.get(key,[None])[0] for key in ('note_id','status','author')})


SYNC_FIELDS=('state','phase','message','job_id','updated_at','next_retry_at','attempts','conflict_note_ids','conflict_count')


def sync_status(server):
    if not hasattr(server,'sync'):
        import knowledge_conflicts
        ids=[g['note_id'] for g in knowledge_conflicts.list_groups(server.root)]
        return {'state':'synced','conflict_note_ids':ids,'conflict_count':len(ids)}
    value=server.sync.status(light=True)
    return {key:value[key] for key in SYNC_FIELDS if key in value}


def assert_formal_write(server,note_id=None,public=False):
    # Pending commits/deployments are durable work, not a global editing ban.
    if public and server.sync.status(light=True).get('state')=='conflict':
        raise SyncBlocked('Git同步冲突尚未解决，请稍后重试')
    if note_id:
        import knowledge_conflicts
        from edit_locks import EditLocked
        if knowledge_conflicts.is_blocked(server.root,note_id):
            raise EditLocked('此笔记存在同步冲突，请先确认合并方案',reason='sync_conflict',resource={'note_id':note_id})


def get_sync_conflicts(server,identity,note_id=None):
    require_identity(identity)
    if identity['role']!='admin':raise PermissionError('只有管理员可以查看同步冲突')
    import knowledge_conflicts
    def titled(group):
        bodies=[group['current']['body'],*[v['body'] for v in group['variants']]]
        title=next((n.get('title') for b in bodies if b for n in b.get('nodes',[]) if n.get('type')=='heading' and n.get('level')==1),group['note_id'])
        return {**group,'title':title}
    if note_id is None:return [titled(g) for g in knowledge_conflicts.list_groups(server.root)]
    group=knowledge_conflicts.get_group(server.root,note_id)
    if group is None:raise KeyError('同步冲突不存在')
    return titled(group)


def resolve_sync_conflict(server,identity,note_id,data,public=False):
    require_identity(identity)
    if identity['role']!='admin':raise PermissionError('只有管理员可以解决同步冲突')
    import knowledge_conflicts
    with save_lock(state_dir(server)),formal_save(server) if public else nullcontext():
        if public:getattr(server.sync,'_assert_active',lambda:None)()
        # The resolver owns store_lock and its atomic note/history/event journal.
        value=knowledge_conflicts.resolve(server.root,note_id,data)
        result={'note':value}
        if public:result['sync']=enqueue_sync(server)
        return result


def enqueue_sync(server,force=False):
    worker=getattr(server,'sync_worker',None)
    try:
        value=server.sync.enqueue(force=True) if force else server.sync.enqueue()
        return {key:value[key] for key in SYNC_FIELDS if key in value}
    except OSError:
        if worker:worker.initialized=False
        raise
    finally:
        if worker:worker.wake()


@contextmanager
def formal_save(server):
    """Keep any durable partial save recoverable even if receipt cleanup fails."""
    try:yield
    except OSError:
        worker=getattr(server,'sync_worker',None)
        if worker:worker.initialized=False
        try:enqueue_sync(server)
        except Exception:pass  # Preserve the original error; startup/worker scans durable journals.
        finally:
            if worker:worker.wake()
        raise


def mutate_proposal(server,identity,path,command,data,public=False):
    require_identity(identity)
    service=proposal_store(server)
    match=re.fullmatch(r'/api/proposals/([^/]+)(?:/(approve|reject|withdraw))?',path)
    if match and match[2]=='approve' and command=='POST':
        if identity['role']!='admin':raise PermissionError('只有管理员可以确认提案')
        existing=service.get(identity,match[1])
        if existing['status']=='approved':
            if 'proposed_node' in data:existing=service.action(identity,match[1],'approve',data)
            return {**existing,**({'sync':sync_status(server)} if public else {})}
        with save_lock(state_dir(server)),formal_save(server) if public else nullcontext():
            if public:getattr(server.sync,'_assert_active',lambda:None)()
            service.recover()
            existing=service.get(identity,match[1])
            if existing['status']=='approved':
                if 'proposed_node' in data:existing=service.action(identity,match[1],'approve',data)
                return {**existing,**({'sync':sync_status(server)} if public else {})}
            assert_formal_write(server,existing['note_id'],public=public)
            result=service.action(identity,match[1],'approve',data)
            if public:result={**result,'sync':enqueue_sync(server)}
            return result
    # Private proposal CRUD never waits for a long Git operation. A leftover
    # approval receipt alone requires the canonical/global lock for recovery.
    if service.recovery_pending():
        with save_lock(state_dir(server)):service.recover()
    if path=='/api/proposals' and command=='POST':return service.submit_delta(identity,data,_recover=False)
    if not match:raise KeyError('提案接口不存在')
    item_id,action=match.groups()
    if action is None and command=='PUT':return service.update(identity,item_id,data,_recover=False)
    if action in ('reject','withdraw') and command=='POST':return service.action(identity,item_id,action,data,_recover=False)
    raise KeyError('提案操作不存在')


def get_locks(server,identity,request_url):
    require_identity(identity);proposal_store(server)
    query=parse_qs(urlsplit(request_url).query)
    return server.edit_locks.list(identity,query.get('note_id',[''])[0],query.get('client_id',[''])[0])


def mutate_locks(server,identity,path,data):
    require_identity(identity);proposal_store(server)
    action=path.rsplit('/',1)[-1]
    if action not in ('acquire','renew','release'):raise KeyError('编辑锁操作不存在')
    return getattr(server.edit_locks,action)(identity,data)


def edit_note(server,identity,nid,data):
    """Legacy admin editor: revision first, then revoke only affected entries."""
    import workspace
    import json_store
    if not json_store.enabled(server.root):
        return workspace.edit(server.root,nid,data)
    service=proposal_store(server);service.recover()
    record=service._note(nid)
    if data.get('revision')!=record['metadata']['revision']:raise workspace.Conflict('笔记已更新，请重新载入后合并草稿')
    with server.edit_locks.admin_guard(identity,nid,record['body'],data.get('document',record['body'])):
        return workspace.edit(server.root,nid,data)
