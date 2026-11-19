"""Private template review and durable approval receipts, never portable content."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import threading
import uuid

from template_feedback import text
import json_store
import templates_store as library
from workspace import Conflict, Busy

_locks={}
_guard=threading.Lock()


def _now():return datetime.now(timezone.utc).isoformat()


def _authority(actor):
    if not actor or actor.get('role') not in ('admin','annotator') or not actor.get('username'):
        raise PermissionError('浏览者没有模板编辑或提案权限')


def _records(snapshot,changes):
    return {change['kind']+':'+change['id']:next((row for row in snapshot[change['kind']+'s']
        if row['id']==change['id']),None) for change in changes}


def _replace_base(base,change,record):
    rows=base[change['kind']+'s']
    rows[:]=[r for r in rows if r['id']!=change['id']]
    if record is not None:rows.append(deepcopy(record))


class TemplateProposals:
    def __init__(self,root,path,entity_provider=None):
        self.root=Path(root);self.path=Path(path)
        self.entity_provider=entity_provider
        self.receipt=self.path.with_name(self.path.name+'.approval.json')
        self.pending_sync=self.path.with_name(self.path.name+'.pending-sync.json')
        with _guard:self.lock=_locks.setdefault(str(self.path.resolve()),threading.RLock())

    def _entities(self):
        return {'entities':self.entity_provider()} if self.entity_provider else {}

    def _connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(self.path,timeout=10)
        conn.execute('CREATE TABLE IF NOT EXISTS template_comments(id TEXT PRIMARY KEY,group_id TEXT NOT NULL,data TEXT NOT NULL)')
        conn.execute('CREATE INDEX IF NOT EXISTS template_comments_group ON template_comments(group_id)')
        conn.execute('CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS seen(username TEXT PRIMARY KEY,revision TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS seen_changes(username TEXT NOT NULL,token TEXT NOT NULL,PRIMARY KEY(username,token))')
        conn.commit()
        return conn

    def _read(self,conn,pid):
        row=conn.execute('SELECT data FROM proposals WHERE id=?',(pid,)).fetchone()
        if not row:raise KeyError('模板提案不存在')
        return json.loads(row[0])

    def _save(self,conn,item):
        item=deepcopy(item)
        item['proposal_revision']=json_store.digest({k:v for k,v in item.items() if k!='proposal_revision'})
        conn.execute('INSERT OR REPLACE INTO proposals(id,data) VALUES(?,?)',
                     (item['id'],json.dumps(item,ensure_ascii=False)))
        return item

    def list(self,actor):
        _authority(actor)
        with self.lock,closing(self._connection()) as conn:
            items=[json.loads(row[0]) for row in conn.execute('SELECT data FROM proposals ORDER BY rowid')]
            visible=[item for item in items if actor['role']=='admin' or item['author']==actor['username']]
            pending=[item for item in visible if item['status']=='pending']
            if pending:
                current=library.snapshot(self.root)
                for item in pending:
                    actual=_records(current,item['changes'])
                    item['conflicts']={key:{'current':actual[key],'revision':json_store.digest(actual[key])}
                        for key,old in _records(item['base'],item['changes']).items() if old!=actual[key]}
            return visible

    def approved_retry(self,actor,pid,data):
        if actor.get('role')!='admin':raise PermissionError('只有管理员可以审批模板提案')
        with self.lock,closing(self._connection()) as conn:
            item=self._read(conn,pid)
            request=json_store.digest([actor['username'],'approve',data])
            if (item['status']=='approved' and set(data)=={'proposal_revision'}
                or any(r.get('request')==request for r in item['reviews'])):
                return item

    def submit(self,actor,data):
        _authority(actor)
        with self.lock:
            if self.receipt.exists():raise Conflict('上次模板审批尚未恢复，请稍后重试')
            revision=data.get('revision');changes=deepcopy(data.get('changes'))
            base=library.snapshot(self.root)
            library.preview_changes(self.root,revision,changes,**self._entities())
            if not changes:raise ValueError('没有需要提交的模板修改')
            item={'id':uuid.uuid4().hex,'author':actor['username'],'status':'pending',
                  'created_at':_now(),'revision':revision,'changes':changes,
                  'base':{'events':base['events'],'groups':base['groups']},'reviews':[]}
            item['author_role']=actor['role']
            item['source']=text(data.get('source','proposal'),'来源',200)
            item['batch_id']=text(data.get('batch_id',item['id']),'批次',200)
            item['submission']={'before':_records(base,changes),'changes':deepcopy(changes)}
            with closing(self._connection()) as conn:
                for row in conn.execute('SELECT data FROM proposals'):
                    old=json.loads(row[0])
                    if (old['author']==item['author'] and old['status']=='pending'
                        and old['revision']==revision and old['changes']==changes and old.get('source','proposal')==item['source']
                        and ('batch_id' not in data or data['batch_id']==old.get('batch_id'))):return old
                item=self._save(conn,item);conn.commit()
            return item

    def discuss(self,actor,pid,data):
        _authority(actor)
        with self.lock,closing(self._connection()) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            item=self._read(conn,pid)
            if actor['role']!='admin' and item['author']!=actor['username']:raise PermissionError('不能查看其他人的提案讨论')
            if data.get('proposal_revision')!=item['proposal_revision']:raise Conflict('提案已更新，请刷新后回复')
            item.setdefault('discussion',[]).append({'id':uuid.uuid4().hex,'at':_now(),'by':actor['username'],
                'role':actor['role'],'body':text(data.get('body'),'提案讨论')})
            return self._save(conn,item)

    def _finish_receipt(self,receipt):
        with closing(self._connection()) as conn:
            self._save(conn,receipt['proposal']);conn.commit()
        if receipt.get('needs_sync'):
            json_store.write_file(self.pending_sync,{'root':str(self.root.resolve())})
        self.receipt.unlink(missing_ok=True)

    def enqueue_pending(self,enqueue):
        """Called under the site's save lock after recovering any approval."""
        if not self.pending_sync.exists():
            return None
        if json_store.read(self.pending_sync)['root']!=str(self.root.resolve()):
            raise Conflict('待同步的模板审批属于其他发布目录，请先恢复原版本')
        result=enqueue()
        self.pending_sync.unlink(missing_ok=True)
        return result

    def recover(self):
        with self.lock:
            if not self.receipt.exists():return
            receipt=json_store.read(self.receipt)
            current=library.snapshot(self.root)
            actual=_records(current,receipt['changes'])
            if actual!=receipt['after']:
                if actual!=receipt['before']:raise Conflict('模板审批恢复发现新修改，请管理员核对')
                library.apply(self.root,current['revision'],receipt['changes'],actor=receipt['actor'],**self._entities())
            self._finish_receipt(receipt)

    def action(self,actor,pid,action,data,*,needs_sync=False):
        _authority(actor)
        if action not in ('approve','edit','reject','withdraw'):raise KeyError('未知的模板提案操作')
        if action in ('approve','reject') and actor['role']!='admin':raise PermissionError('只有管理员可以审批模板提案')
        if action=='edit' and data.get('rebase') and actor['role']!='admin':
            raise PermissionError('只有管理员可以重新合并基础版本')
        with self.lock:
            self.recover()
            with closing(self._connection()) as conn:item=self._read(conn,pid)
            if actor['role']!='admin' and item['author']!=actor['username']:raise PermissionError('不能操作其他人的提案')
            request=json_store.digest([actor['username'],action,data])
            if any(r.get('request')==request for r in item['reviews']):return item
            target={'approve':'approved','reject':'rejected','withdraw':'withdrawn','edit':'pending'}[action]
            if action!='edit' and item['status']==target and set(data)<= {'proposal_revision'}:return item
            if item['status']!='pending':raise Conflict('该模板提案已处理')
            if data.get('proposal_revision')!=item.get('proposal_revision'):
                raise Conflict('模板提案已变化，请重新核对')
            if 'submission' not in item and not item['reviews']:
                item['submission']={'before':_records(item['base'],item['changes']),'changes':deepcopy(item['changes'])}
            if action in ('withdraw','reject'):
                item['reviews'].append({'action':action,'role':actor['role'],'at':_now(),'by':actor['username'],'request':request,
                    'before':_records(item['base'],item['changes']),'submitted':deepcopy(item['changes'])})
                item.update(status=target,reviewed_by=actor['username'],reviewed_at=_now())
                with closing(self._connection()) as conn:item=self._save(conn,item);conn.commit()
                return item
            indices=data.get('change_ids',list(range(len(item['changes']))))
            if (not isinstance(indices,list) or not indices or any(type(i)!=int or i<0 or i>=len(item['changes']) for i in indices)
                or len(set(indices))!=len(indices)):raise ValueError('请选择有效的审批条目')
            selected=[item['changes'][i] for i in indices]
            changes=deepcopy(data.get('changes',selected))
            allowed={(c['kind'],c['id'],c['action']) for c in selected}
            if (not isinstance(changes,list) or len(changes)!=len(selected)
                or any(not isinstance(c,dict) or (c.get('kind'),c.get('id'),c.get('action')) not in allowed for c in changes)
                or len({(c['kind'],c['id']) for c in changes})!=len(changes)):
                raise ValueError('审批内容必须对应所选提案')
            current=library.snapshot(self.root)
            before=_records(item['base'],selected)
            actual=_records(current,selected)
            conflicts={key:json_store.digest(record) for key,record in actual.items() if record!=before[key]}
            if conflicts and not (action=='edit' and data.get('rebase')==conflicts):
                raise Conflict('模板已被修改，请重新核对提案；建议内容已保留')
            if data.get('rebase') and data['rebase']!=conflicts:raise Conflict('正式版本已变化，请刷新后重试')
            entities=self._entities()
            if action=='edit':
                edited={(c['kind'],c['id']):c for c in changes}
                updated=[edited.get((c['kind'],c['id']),c) for c in item['changes']]
                library.preview_changes(self.root,current['revision'],updated,**entities)
                for change in changes:
                    key=change['kind']+':'+change['id']
                    _replace_base(item['base'],change,actual[key])
                item['reviews'].append({'action':'edit','role':actor['role'],'at':_now(),'by':actor['username'],'before':before,
                    'current':actual,'submitted':selected,'changes':changes,'request':request})
                item['changes']=updated
                with closing(self._connection()) as conn:item=self._save(conn,item);conn.commit()
                return item
            projected=library.preview_changes(self.root,current['revision'],changes,**entities)
            remainder=[]
            approved={(c['kind'],c['id']):c for c in changes}
            for index,original in enumerate(item['changes']):
                accepted=approved.get((original['kind'],original['id']))
                if index not in indices or accepted!=original:remainder.append(original)
            updated=deepcopy(item)
            updated['reviews'].append({'action':'approve','operation':'approve_partial' if remainder else 'approve', 'role':actor['role'],'at':_now(),'by':actor['username'],'before':before,
                'submitted':selected,'changes':changes,'request':request,'after':_records(projected,changes)})
            # Untouched pending records retain the original ancestor: approving
            # one record must never silently rebase another stale suggestion.
            next_base=deepcopy(item['base'])
            for accepted in changes:
                key=accepted['kind']+':'+accepted['id']
                _replace_base(next_base,accepted,_records(projected,[accepted])[key])
            updated.update(status='pending' if remainder else 'approved',changes=remainder,
                base=next_base,
                reviewed_by=actor['username'],reviewed_at=_now())
            receipt={'proposal':updated,'actor':actor['username'],'changes':changes,'needs_sync':needs_sync,
                     'before':_records(current,changes),'after':_records(projected,changes)}
            json_store.write_file(self.receipt,receipt)
            try:
                library.apply(self.root,current['revision'],changes,actor=actor['username'],**entities)
            except (ValueError,Busy):
                # Validation/revision/lock failures happen before a new formal
                # transaction is committed. Keep the proposal pending without
                # leaving a recovery receipt that would replay a rejected edit.
                self.receipt.unlink(missing_ok=True)
                raise
            self._finish_receipt(receipt)
            with closing(self._connection()) as conn:return self._read(conn,pid)

    def unseen(self,username,revision,tokens=None):
        with self.lock,closing(self._connection()) as conn:
            if tokens is not None:
                seen={r[0] for r in conn.execute('SELECT token FROM seen_changes WHERE username=?',(username,))}
                return bool(set(tokens)-seen)
            row=conn.execute('SELECT revision FROM seen WHERE username=?',(username,)).fetchone()
            return not row or row[0]!=revision

    def unseen_tokens(self,username,tokens):
        with self.lock,closing(self._connection()) as conn:
            seen={r[0] for r in conn.execute('SELECT token FROM seen_changes WHERE username=?',(username,))}
            return set(tokens)-seen

    def mark_seen(self,username,revision,tokens=()):
        with self.lock,closing(self._connection()) as conn:
            conn.execute('INSERT OR REPLACE INTO seen(username,revision) VALUES(?,?)',(username,revision))
            conn.executemany('INSERT OR IGNORE INTO seen_changes(username,token) VALUES(?,?)',[(username,token) for token in tokens]);conn.commit()
