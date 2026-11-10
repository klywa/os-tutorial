"""Short SQLite entry leases. No Git, network, or private draft persistence."""
from contextlib import contextmanager
from copy import deepcopy
import hmac
import json
import re
import time
import uuid

import json_store
from proposals import _section
from workspace import Conflict


class EditLocked(RuntimeError):
    def __init__(self,message='条目正在由其他人编辑',*,reason='locked',resource=None):
        super().__init__(message);self.reason=reason;self.resource=resource


def identity(actor):
    if not actor or actor.get('role') not in ('admin','annotator') or not actor.get('username'):
        raise PermissionError('请先登录')
    return actor


def identifier(value,label='编辑窗口'):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',value):
        raise ValueError(label+'标识无效，请刷新页面')
    return value


def resource(value):
    if not isinstance(value,dict):raise ValueError('编辑目标无效')
    fields={'kind','id'} if value.get('kind')=='entry' else {'kind','section_id','left_id'}
    if value.get('kind') not in ('entry','slot') or set(value)!=fields:
        raise ValueError('编辑目标无效')
    if any(not isinstance(value[k],str) or not value[k] or len(value[k])>240 for k in fields):
        raise ValueError('编辑目标无效')
    return dict(value)


def resource_key(value):return json.dumps(resource(value),sort_keys=True,ensure_ascii=False)


class EditLocks:
    ttl=60

    def __init__(self,store,*,clock=time.time):
        self.store=store;store.edit_locks=self;self.clock=clock;self.epoch=uuid.uuid4().hex
        with store._db() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS edit_locks (id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS edit_requests (id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS edit_meta (id TEXT PRIMARY KEY,value TEXT NOT NULL)')
            conn.execute('INSERT OR REPLACE INTO edit_meta VALUES (?,?)',('epoch',self.epoch))
            for row in self._rows(conn):
                if row['status']=='active':self._revoke(conn,row,'server_restart')
                if row['updated_at']<self.clock()-7*86400:
                    conn.execute('DELETE FROM edit_locks WHERE id=?',(row['id'],))

    @staticmethod
    def _rows(conn):return [json.loads(row[0]) for row in conn.execute('SELECT data FROM edit_locks')]

    @staticmethod
    def _put(conn,row):
        conn.execute('INSERT OR REPLACE INTO edit_locks VALUES (?,?)',(row['id'],json.dumps(row,ensure_ascii=False)))

    def check_epoch(self,conn):
        epoch=conn.execute('SELECT value FROM edit_meta WHERE id=?',('epoch',)).fetchone()
        if not epoch or epoch[0]!=self.epoch:raise EditLocked('服务已更新，请刷新后继续编辑',reason='server_restart')

    def snapshot(self,record,target):
        target=resource(target);nodes=record['body']['nodes'];byid={n['id']:n for n in nodes}
        if target['kind']=='entry':
            node=byid.get(target['id'])
            if not node or node['type']!='entry':raise Conflict('条目已变化，请刷新')
            return {'node':deepcopy(node),'section':_section(nodes,node['id'])}
        section=byid.get(target['section_id']);left=byid.get(target['left_id'])
        if not section or section['type']!='heading' or section['level']==1 or not left:
            raise Conflict('插入位置已变化，请刷新')
        chain=_section(nodes,left['id'])
        if not chain or chain[-1]['id']!=section['id']:raise Conflict('插入位置不在对应章节')
        index=next(i for i,n in enumerate(nodes) if n['id']==left['id'])
        return {'left_id':left['id'],'right_id':nodes[index+1]['id'] if index+1<len(nodes) else None,'section':chain}

    def _live(self,row):return row['status']=='active' and row['epoch']==self.epoch and row['expires_at']>self.clock()

    def _revoke(self,conn,row,reason):
        row.update(status='revoked',reason=reason,updated_at=self.clock())
        self._put(conn,row)

    @staticmethod
    def _public(row,actor,client):
        return {'id':row['id'],'note_id':row['note_id'],'resource':row['resource'],'owner':row['owner'],
                'role':row['role'],'expires_at':row['expires_at'],
                'mine':row['owner']==actor['username'] and row['client_id']==client}

    def list(self,actor,note_id,client):
        identity(actor);identifier(client)
        with self.store._db(write=False) as conn:
            self.check_epoch(conn)
            rows=[r for r in self._rows(conn) if r['note_id']==note_id]
            return {'epoch':self.epoch,'leases':[self._public(r,actor,client) for r in rows if self._live(r)],
                    'revoked':[{'id':r['id'],'resource':r['resource'],
                        'reason':r.get('reason','expired')} for r in rows
                        if not self._live(r) and r['owner']==actor['username'] and r['client_id']==client]}

    def _acquire(self,conn,actor,client,note_id,target,takeover=False,*,record=None):
        self.check_epoch(conn);target=resource(target)
        record=record or self.store._note(note_id)
        baseline=self.snapshot(record,target)
        for row in self._rows(conn):
            if row['note_id']!=note_id or row['resource']!=target or not self._live(row):continue
            if row['owner']==actor['username'] and row['client_id']==client and row['role']==actor['role']:
                if row['baseline']==baseline:return row
                self._revoke(conn,row,'changed');continue
            if actor['role']!='admin' or row['role']=='annotator' and not takeover:
                raise EditLocked(row['owner']+' 正在编辑',resource=target)
            if row['role']=='annotator':self._revoke(conn,row,'admin_takeover')
        row={'id':uuid.uuid4().hex,'token':uuid.uuid4().hex+uuid.uuid4().hex,'epoch':self.epoch,
             'note_id':note_id,'resource':target,'owner':actor['username'],'role':actor['role'],
             'client_id':client,'baseline':baseline,'status':'active','expires_at':self.clock()+self.ttl,
             'updated_at':self.clock()}
        self._put(conn,row);return row

    def acquire(self,actor,payload):
        identity(actor);client=identifier(payload.get('client_id'))
        if payload.get('takeover') and actor['role']!='admin':raise PermissionError('只有管理员可以接管')
        with self.store._db() as conn:
            return self._acquire(conn,actor,client,payload['note_id'],payload['resource'],bool(payload.get('takeover')))

    def validate(self,conn,actor,client,reference,note_id,*,target=None,record=None):
        identity(actor);identifier(client);self.check_epoch(conn)
        if not isinstance(reference,dict):raise EditLocked('请先取得编辑权限',reason='missing_lease')
        rowdata=conn.execute('SELECT data FROM edit_locks WHERE id=?',(reference.get('id'),)).fetchone()
        row=json.loads(rowdata[0]) if rowdata else None
        if (not row or row['owner']!=actor['username'] or row['client_id']!=client or
                not isinstance(reference.get('token'),str) or not hmac.compare_digest(row['token'],reference['token'])):
            raise EditLocked('编辑权限已失效，请重新进入编辑',reason='invalid_lease',resource=target)
        if row['note_id']!=note_id or target is not None and row['resource']!=resource(target):
            raise EditLocked('编辑凭证与目标不一致',reason='invalid_lease',resource=target)
        if not self._live(row) or row['role']!=actor['role']:
            raise EditLocked('编辑权限已失效',reason=row.get('reason','expired'),resource=row['resource'])
        baseline=self.snapshot(record or self.store._note(note_id),row['resource'])
        if baseline!=row['baseline']:raise EditLocked('条目已更新，请核对后继续',reason='changed',resource=row['resource'])
        return row

    def renew(self,actor,payload):
        identity(actor);client=identifier(payload.get('client_id'));result=[];lost=[]
        with self.store._db() as conn:
            self.check_epoch(conn)
            for reference in payload.get('leases',[]):
                try:
                    raw=conn.execute('SELECT data FROM edit_locks WHERE id=?',(reference.get('id'),)).fetchone()
                    row=json.loads(raw[0]) if raw else None
                    lease=self.validate(conn,actor,client,reference,row['note_id'] if row else '')
                    lease.update(expires_at=self.clock()+self.ttl,updated_at=self.clock());self._put(conn,lease);result.append(lease)
                except (EditLocked,Conflict) as exc:
                    lost.append({'id':reference.get('id'),'reason':getattr(exc,'reason','changed')})
        return {'epoch':self.epoch,'leases':result,'lost':lost}

    def release_in(self,conn,actor,client,references):
        for ref in references:
            raw=conn.execute('SELECT data FROM edit_locks WHERE id=?',(ref.get('id'),)).fetchone()
            if not raw:continue
            row=json.loads(raw[0])
            if (row['owner']==actor['username'] and row['client_id']==client and
                    isinstance(ref.get('token'),str) and hmac.compare_digest(row['token'],ref['token']) and self._live(row)):
                self._revoke(conn,row,'released')

    def release(self,actor,payload):
        identity(actor);client=identifier(payload.get('client_id'))
        with self.store._db() as conn:
            self.check_epoch(conn);self.release_in(conn,actor,client,payload.get('leases',[]))
        return {'ok':True}

    def revoke_annotators(self,conn,note_id,targets):
        self.check_epoch(conn);keys={resource_key(target) for target in targets};revoked=[]
        for row in self._rows(conn):
            if row['note_id']==note_id and row['role']=='annotator' and self._live(row) and resource_key(row['resource']) in keys:
                self._revoke(conn,row,'admin_takeover');revoked.append(row['id'])
        return revoked

    @contextmanager
    def admin_guard(self,actor,note_id,before,after):
        identity(actor)
        if actor['role']!='admin':raise PermissionError('只有管理员可以保存正式正文')
        old={n['id']:n for n in before['nodes']};new={n['id']:n for n in after['nodes']}
        affected=[{'kind':'entry','id':nid} for nid,node in old.items() if node['type']=='entry'
                  and (new.get(nid)!=node or _section(before['nodes'],nid)!=_section(after['nodes'],nid))]
        client='admin-api-'+uuid.uuid4().hex;references=[]
        with self.store._db() as conn:
            for row in self._rows(conn):
                if row['note_id']!=note_id or not self._live(row) or row['resource'] in affected:continue
                try:changed=self.snapshot({'body':before},row['resource'])!=self.snapshot({'body':after},row['resource'])
                except Conflict:changed=True
                if changed:affected.append(row['resource'])
            self.revoke_annotators(conn,note_id,affected)
            for target in affected:
                references.append(self._acquire(conn,actor,client,note_id,target,True))
        try:yield
        finally:
            with self.store._db() as conn:self.release_in(conn,actor,client,references)

    @staticmethod
    def request_key(actor,client,request_id,kind):
        identifier(client);identifier(request_id,'请求')
        return json_store.digest([actor['username'],client,request_id,kind])

    @staticmethod
    def replay(conn,key,payload):
        row=conn.execute('SELECT data FROM edit_requests WHERE id=?',(key,)).fetchone()
        if not row:return None
        value=json.loads(row[0])
        if value['digest']!=json_store.digest(payload):raise Conflict('请求标识已用于其他修改')
        return value['result']

    @staticmethod
    def remember(conn,key,payload,result):
        conn.execute('INSERT OR REPLACE INTO edit_requests VALUES (?,?)',
                     (key,json.dumps({'digest':json_store.digest(payload),'result':result},ensure_ascii=False)))

    @staticmethod
    def recover_receipt(conn,receipt):
        """Replay exact old lease IDs without allocating a new server epoch."""
        released=receipt.get('released_lease')
        for lid in [*receipt.get('revoked_leases',[]), *([released] if released else [])]:
            raw=conn.execute('SELECT data FROM edit_locks WHERE id=?',(lid,)).fetchone()
            if raw:
                row=json.loads(raw[0]);row.update(status='revoked',reason='released' if lid==released else 'admin_takeover',updated_at=time.time())
                EditLocks._put(conn,row)
        if receipt.get('kind')=='entry-save':
            EditLocks.remember(conn,receipt['request_key'],receipt['payload'],{'saved':True})
            for ref in receipt['refs']:
                raw=conn.execute('SELECT data FROM edit_locks WHERE id=?',(ref['id'],)).fetchone()
                if not raw:continue
                row=json.loads(raw[0])
                if row['owner']==receipt['actor']['username'] and row['client_id']==receipt['payload']['client_id'] and hmac.compare_digest(row['token'],ref['token']):
                    row.update(status='revoked',reason='released',updated_at=time.time());EditLocks._put(conn,row)
