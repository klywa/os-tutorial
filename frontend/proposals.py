"""Private, durable per-entry review; canonical edits use the normal JSON pipeline.

HTTP canonical approvals/recovery hold sync_lock. Private HTTP mutations pass
_recover=False and check receipts inside SQLite's write transaction instead.
json_store.edit owns the non-reentrant workspace lock. No Git operations live here.
"""
from contextlib import contextmanager, closing
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import uuid

import json_document
import json_store
from workspace import Conflict, store_lock


class ProposalForbidden(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sync_directory(path):
    if os.name!='nt':
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)


def _authority(actor):
    if not isinstance(actor, dict) or actor.get('role') not in ('admin', 'annotator') or not actor.get('username'):
        raise ProposalForbidden('当前身份不能访问提案')
    return actor['role']


def _scope(nodes, scope_id):
    start = next((i for i,n in enumerate(nodes) if n['id'] == scope_id), None)
    if start is None:raise Conflict('编辑范围不存在')
    node = nodes[start]
    if node['type'] == 'entry':return nodes[start:start+1]
    if node['level'] == 1:raise ValueError('请选择章节或正文条目')
    end = next((i for i in range(start+1,len(nodes)) if nodes[i]['type']=='heading' and nodes[i]['level']<=node['level']),len(nodes))
    return nodes[start:end]


def _section(nodes, node_id):
    chain=[]
    for node in nodes:
        if node['type']=='heading':
            chain=[h for h in chain if h['level']<node['level']]+[node]
        if node['id']==node_id:return deepcopy(chain)
    return None


def _entry(node, base=None):
    if not isinstance(node,dict):raise ValueError('提案必须为正文条目')
    if base is None:
        if set(node)-{'id','type','key','value','show_key','separator','prefix','key_suffix'}:
            raise ValueError('新条目不能携带隐藏字段')
    elif any(node.get(k)!=base.get(k) for k in set(node)|set(base) if k not in ('key','value','show_key')):
        raise ValueError('不能修改条目的格式或隐藏字段')
    if node.get('type')!='entry':raise ValueError('只能提议正文条目')
    json_document.validate({'schema_version':6,'nodes':[node]})
    cleaned=json_document.clean_labels({'schema_version':6,'nodes':[node]})['nodes'][0]
    return cleaned


def sibling_boundary(nodes, source_id):
    start = next((i for i, node in enumerate(nodes) if node['id'] == source_id), None)
    if start is None or nodes[start]['type'] != 'heading' or nodes[start]['level'] == 1:
        raise Conflict('来源章节已变化，请刷新')
    level = nodes[start]['level']
    end = next((i for i in range(start + 1, len(nodes))
                if nodes[i]['type'] == 'heading' and nodes[i]['level'] <= level), len(nodes))
    return end, {
        'section': _section(nodes, source_id),
        'before': nodes[start - 1]['id'] if start else None,
        'right': nodes[end]['id'] if end < len(nodes) else None,
        'headings': [[node['id'], node['level']] for node in nodes[start + 1:end]
                     if node['type'] == 'heading'],
    }


def sibling_heading(node, level):
    if (not isinstance(node, dict) or set(node) - {'id','type','title','level','space','separator'}
            or node.get('type') != 'heading' or node.get('level') != level
            or not isinstance(node.get('title'), str) or not node['title'].strip()
            or '\r' in node['title'] or '\n' in node['title']):
        raise ValueError('请输入有效的同级章节标题')
    result = {**node, 'level': level, 'title': node['title'].strip(), 'space': ' ', 'separator': '\n\n'}
    json_document.validate({'schema_version':6,'nodes':[result]})
    return result


class ProposalStore:
    def __init__(self, root, db_path):
        self.root=Path(root)
        self.db_path=Path(db_path)
        self.journal_path=self.db_path.with_name(self.db_path.name+'.approval.json')

    def _write_receipt(self,receipt):
        temporary=self.journal_path.with_name(self.journal_path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as handle:
                json.dump(receipt,handle,ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary,self.journal_path)
            _sync_directory(self.journal_path.parent)
        finally:temporary.unlink(missing_ok=True)

    def _clear_receipt(self):
        self.journal_path.unlink(missing_ok=True)
        _sync_directory(self.journal_path.parent)

    @contextmanager
    def _db(self,write=True):
        fresh=not self.db_path.parent.exists()
        self.db_path.parent.mkdir(parents=True,exist_ok=True)
        if fresh:os.chmod(self.db_path.parent,0o700)
        conn=sqlite3.connect(self.db_path,timeout=30)
        try:
            if write:
                os.chmod(self.db_path,0o600)
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=FULL')
                conn.execute('CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
                conn.commit()
                conn.execute('BEGIN IMMEDIATE')
            else:
                conn.execute('PRAGMA query_only=ON')
                conn.execute('BEGIN')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:conn.close()

    @staticmethod
    def _rows(conn):
        return [json.loads(row[0]) for row in conn.execute('SELECT data FROM proposals ORDER BY rowid')]

    @staticmethod
    def _put(conn,item):
        conn.execute('INSERT OR REPLACE INTO proposals(id,data) VALUES (?,?)',(item['id'],json.dumps(item,ensure_ascii=False)))

    @staticmethod
    def _get(conn,pid):
        row=conn.execute('SELECT data FROM proposals WHERE id=?',(pid,)).fetchone()
        if not row:raise KeyError('提案不存在')
        return json.loads(row[0])

    @staticmethod
    def _access(actor,item):
        if _authority(actor)!='admin' and item['author']!=actor['username']:
            raise ProposalForbidden('不能访问他人的提案')

    @staticmethod
    def _revision(item,payload):
        if type(payload.get('revision')) is not int or payload['revision']!=item['revision']:
            raise Conflict('提案已更新，请重新载入')

    def _note(self,nid):
        record=json_store.load_record(self.root,nid,clone=False)
        if record is None:raise KeyError('笔记不存在')
        return record

    def _conflict(self,item,record):
        nodes=record['body']['nodes'];byid={n['id']:n for n in nodes}
        context=item['_context']
        if item['kind']!='insert':
            if byid.get(item['node_id'])!=item['base_node']:return True
            return _section(nodes,item['node_id'])!=context['section']
        if item['node_id'] in byid:return True
        if source := context.get('sibling_of'):
            try:
                _, boundary = sibling_boundary(nodes, source)
            except Conflict:
                return True
            return boundary != context['sibling_boundary']
        for name in ('left','right'):
            anchor=context[name]
            if anchor is not None and (anchor not in byid or _section(nodes,anchor)!=context[name+'_section']):return True
        if context['left'] and context['right']:
            ids=[n['id'] for n in nodes]
            if ids.index(context['left'])>=ids.index(context['right']):return True
        return False

    def _public(self,item,record=None):
        result={k:deepcopy(v) for k,v in item.items() if not k.startswith('_')}
        if item['status']=='pending':
            try:
                record=record or self._note(item['note_id'])
                result['conflict']=self._conflict(item,record)
                result['current_node']=next((deepcopy(n) for n in record['body']['nodes'] if n['id']==item['node_id']),None)
            except (KeyError,ValueError):result['conflict']=True;result['current_node']=None
        return result

    def list(self,actor,note_id=None,status=None,author=None):
        role=_authority(actor)
        if not self.db_path.exists():return {'items':[]}
        with self._db(write=False) as conn:
            rows=[r for r in self._rows(conn) if (role=='admin' or r['author']==actor['username'])
                and (note_id is None or r['note_id']==note_id) and (status is None or r['status']==status)
                and (author is None or r['author']==author)]
            records={}
            result=[]
            for item in rows:
                if item['status']=='pending' and item['note_id'] not in records:
                    try:records[item['note_id']]=self._note(item['note_id'])
                    except (KeyError,ValueError):records[item['note_id']]=None
                result.append(self._public(item,records.get(item['note_id'])))
            return {'items':result}

    def get(self,actor,pid):
        _authority(actor)
        if not self.db_path.exists():raise KeyError('提案不存在')
        with self._db(write=False) as conn:
            item=self._get(conn,pid)
            self._access(actor,item)
            return self._public(item)

    def _private_ready(self):
        # Called only after BEGIN IMMEDIATE: an approval cannot create its
        # receipt between this check and the private mutation's commit.
        if self.journal_path.exists():raise Conflict('审批正在恢复，请稍后重试')

    def submit_delta(self,actor,payload,*,_recover=True):
        _authority(actor)
        if _recover:self.recover()
        from entry_changes import submit
        return submit(self,actor,payload)

    def saved_changes(self,actor,payload):
        _authority(actor)
        if actor['role']!='admin':raise PermissionError('只有管理员可以保存正式正文')
        from edit_locks import EditLocks
        key=EditLocks.request_key(actor,payload.get('client_id'),payload.get('request_id'),'canonical')
        with self._db(write=False) as conn:
            if EditLocks.replay(conn,key,payload) is not None:return json_store.resolve_note(self.root,payload['note_id'])
        return None

    def apply_changes(self,actor,payload):
        _authority(actor)
        from entry_changes import apply
        return apply(self,actor,payload)

    def submit(self,actor,payload,*,_recover=True):
        _authority(actor)
        if set(payload)-{'note_id','revision','scope_id','nodes'}:raise ValueError('提案包含不支持的字段')
        if _recover:self.recover()
        with self._db() as conn:
            if not _recover:self._private_ready()
            record=self._note(payload['note_id']);all_nodes=record['body']['nodes']
            if payload.get('revision')!=record['metadata']['revision']:raise Conflict('笔记已更新')
            original=_scope(all_nodes,payload['scope_id']);incoming=payload.get('nodes')
            if not isinstance(incoming,list):raise ValueError('nodes必须为列表')
            json_document.validate({'schema_version':6,'nodes':incoming})
            old={n['id']:n for n in original};all_ids={n['id'] for n in all_nodes}
            if original[0]['type']=='entry' and (len(incoming)>1 or (incoming and incoming[0]['id']!=original[0]['id'])):
                raise ValueError('条目范围不能插入其他条目')
            if [n['id'] for n in incoming if n['id'] in old]!=[n['id'] for n in original if n['id'] in {v['id'] for v in incoming}]:
                raise ValueError('不能重排既有节点')
            if [n for n in incoming if n.get('type')=='heading']!=[n for n in original if n['type']=='heading']:
                raise ValueError('章节标题不可修改')
            batch=uuid.uuid4().hex;now=_now();items=[]
            for index,node in enumerate(incoming):
                nid=node['id'];base=old.get(nid)
                if base is not None:
                    if node==base:continue
                    proposed=_entry(node,base);kind='update'
                else:
                    if nid in all_ids:raise ValueError('条目超出编辑范围')
                    proposed=_entry(node);proposed['id']='proposal-'+uuid.uuid4().hex;nid=proposed['id'];kind='insert'
                left=right=None
                if kind=='insert':
                    left=next((n['id'] for n in reversed(incoming[:index]) if n['id'] in old),None)
                    right=next((n['id'] for n in incoming[index+1:] if n['id'] in old),None)
                    # The first node is immutable for heading scopes; its descendants
                    # give every insertion an original anchor, including chapter end.
                    if left is None:raise ValueError('插入必须位于章节标题之后')
                target=left if kind=='insert' else nid
                section=_section(all_nodes,target)
                item={'id':uuid.uuid4().hex,'note_id':payload['note_id'],'note_title':record['metadata']['title'],
                    'author':actor['username'],'kind':kind,'node_id':nid,'section_id':section[-1]['id'] if section else None,
                    'after_id':left,'base_node':deepcopy(base),'proposed_node':proposed,'revision':1,'status':'pending',
                    'created_at':now,'updated_at':now,'reviewed_by':None,'result_revision':None,'order':index,
                    '_batch':batch,'_context':{'section':section,'left':left,'right':right,
                        'left_section':_section(all_nodes,left),'right_section':_section(all_nodes,right)}}
                items.append(item)
            incoming_ids={n['id'] for n in incoming}
            for node in original:
                if node['id'] in incoming_ids:continue
                if node['type']!='entry':raise ValueError('不能删除标题')
                section=_section(all_nodes,node['id'])
                items.append({'id':uuid.uuid4().hex,'note_id':payload['note_id'],'note_title':record['metadata']['title'],
                    'author':actor['username'],'kind':'delete','node_id':node['id'],'section_id':section[-1]['id'] if section else None,
                    'after_id':None,'base_node':deepcopy(node),'proposed_node':None,'revision':1,'status':'pending',
                    'created_at':now,'updated_at':now,'reviewed_by':None,'result_revision':None,'order':len(items),
                    '_batch':batch,'_context':{'section':section}})
            for item in items:self._put(conn,item)
            return {'items':[self._public(i,record) for i in items]}

    @staticmethod
    def _set_proposed_node(item, proposed):
        if item['kind']=='delete':
            if proposed is not None:raise ValueError('删除提案不接受正文')
            return
        if not isinstance(proposed,dict) or proposed.get('id')!=item['node_id']:
            raise ValueError('提案节点ID不可变')
        item['proposed_node'] = (sibling_heading(proposed, item['proposed_node']['level'])
                                 if item['_context'].get('sibling_of') else _entry(proposed, item['base_node']))

    def update(self,actor,pid,payload,*,_recover=True):
        _authority(actor)
        if set(payload)-{'revision','proposed_node','rebase','client_id','lease'}:raise ValueError('不支持的提案字段')
        if _recover:self.recover()
        with self._db() as conn:
            if not _recover:self._private_ready()
            item=self._get(conn,pid);self._access(actor,item);self._revision(item,payload)
            if item['status']!='pending':raise Conflict('已处理提案不能修改')
            locks=getattr(self,'edit_locks',None)
            if locks:
                from entry_changes import target
                locks.validate(conn,actor,payload.get('client_id'),payload.get('lease'),item['note_id'],target=target(item))
            sibling = item['_context'].get('sibling_of')
            if sibling and self._conflict(item, self._note(item['note_id'])):
                raise Conflict('章节插入位置已变化，请重新提交')
            if payload.get('rebase'):
                if actor['role']!='admin':raise ProposalForbidden('只有管理员可重新合并基础版本')
                record=self._note(item['note_id']);nodes=record['body']['nodes']
                if item['kind']=='insert':
                    if self._conflict(item,record):raise Conflict('插入锚点已变化，请重新提交')
                else:
                    base=next((n for n in nodes if n['id']==item['node_id']),None)
                    if base is None or base['type']!='entry':raise Conflict('原条目已删除')
                    item['base_node']=deepcopy(base);item['_context']['section']=_section(nodes,item['node_id'])
            self._set_proposed_node(item,payload.get('proposed_node'))
            item.update(revision=item['revision']+1,updated_at=_now())
            self._put(conn,item)
            if locks:locks.release_in(conn,actor,payload['client_id'],[payload['lease']])
            return self._public(item)

    def _apply_body(self,conn,item,record):
        body=deepcopy(record['body']);nodes=body['nodes'];nid=item['node_id']
        body.setdefault('supporting_nodes',[])
        body.setdefault('semantics',{})
        if item['kind']=='delete':
            # Canonical edit detaches references on deletion. Review must never
            # silently mutate semantics, evidence associations or hidden nodes.
            def refers(value):
                if isinstance(value,dict):return any((k in ('$text','text_ref','display_ref') and v==nid) or refers(v) for k,v in value.items())
                if isinstance(value,list):return any(refers(v) for v in value)
                return False
            if refers(body.get('semantics',{})) or refers(body.get('supporting_nodes',[])) or refers(record['metadata'].get('claim_annotations',[])):
                raise ValueError('条目仍被结构化知识或证据引用，不能删除')
            body['nodes']=[n for n in nodes if n['id']!=nid]
        elif item['kind']=='update':
            body['nodes']=[deepcopy(item['proposed_node']) if n['id']==nid else n for n in nodes]
        elif source := item['_context'].get('sibling_of'):
            position, _ = sibling_boundary(nodes, source)
            nodes.insert(position, deepcopy(item['proposed_node']))
        else:
            ctx=item['_context'];ids=[n['id'] for n in nodes]
            siblings=[r for r in self._rows(conn) if r['_batch']==item['_batch'] and r['kind']=='insert'
                and not r['_context'].get('sibling_of')
                and r['_context']['left']==ctx['left'] and r['_context']['right']==ctx['right']
                and r['status']=='approved' and r['node_id'] in ids
                and _section(nodes,r['node_id'])==ctx['section']
                and ids.index(r['node_id'])>ids.index(ctx['left'])
                and (ctx['right'] is None or ids.index(r['node_id'])<ids.index(ctx['right']))]
            later=sorted([r for r in siblings if r['order']>item['order']],key=lambda r:r['order'])
            earlier=sorted([r for r in siblings if r['order']<item['order']],key=lambda r:r['order'])
            position=ids.index(later[0]['node_id']) if later else ids.index(earlier[-1]['node_id'])+1 if earlier else ids.index(ctx['left'])+1
            nodes.insert(position,deepcopy(item['proposed_node']))
        return json_document.clean_labels(body)

    def action(self,actor,pid,action,payload,*,_recover=True):
        role=_authority(actor)
        if action not in ('approve','reject','withdraw'):raise ValueError('未知提案操作')
        if action in ('approve','reject') and role!='admin':raise ProposalForbidden('当前身份不能审核提案')
        with_draft=action=='approve' and 'proposed_node' in payload
        if with_draft and set(payload)!={'revision','proposed_node','client_id','lease'}:
            raise ValueError('确认改稿需要提案版本及条目锁')
        if _recover:self.recover()
        with self._db() as conn:
            if not _recover:self._private_ready()
            item=self._get(conn,pid);self._access(actor,item)
            if action=='approve' and item['status']=='approved':
                if with_draft:
                    replay=deepcopy(item)
                    self._set_proposed_node(replay,payload['proposed_node'])
                    if replay['proposed_node']!=item['proposed_node']:
                        raise Conflict('提案已确认，当前改稿未应用')
                return self._public(item)
            self._revision(item,payload)
            if item['status']!='pending':raise Conflict('提案已经处理')
            if action=='withdraw' and actor['username']!=item['author']:raise ProposalForbidden('只有作者可撤回')
            if action=='approve':
                record=self._note(item['note_id'])
                if self._conflict(item,record):raise Conflict('正文或插入锚点已变化，请重新合并')
                locks=getattr(self,'edit_locks',None);revoked=[]
                if with_draft:
                    if not locks or item['kind']=='delete':raise ValueError('当前提案无法直接确认改稿')
                    from entry_changes import target
                    locks.validate(conn,actor,payload['client_id'],payload['lease'],item['note_id'],target=target(item),record=record)
                    self._set_proposed_node(item,payload['proposed_node'])
                if locks:
                    from entry_changes import target
                    revoked=locks.revoke_annotators(conn,item['note_id'],[target(item)])
                body=self._apply_body(conn,item,record)
                receipt={'proposal_id':pid,'revoked_leases':revoked,'reviewed_by':actor['username'],'pre_body':record['body'],
                    'post_body':body,'pre_revision':record['metadata']['revision'],
                    'history_index':record['metadata'].get('history_count',0)+len(record['metadata'].get('history',[])),'note_id':item['note_id'],
                    'workspace':str(self.root.resolve())}
                if with_draft:
                    receipt['proposed_node']=item['proposed_node']
                    receipt['released_lease']=payload['lease']['id']
                if body!=record['body']:
                    self._write_receipt(receipt)
                    result=json_store.edit(self.root,item['note_id'],{'revision':record['metadata']['revision'],'document':body},public=True)
                    item['result_revision']=result['revision']
                else:item['result_revision']=record['metadata']['revision']
                if with_draft:locks.release_in(conn,actor,payload['client_id'],[payload['lease']])
            item.update(status={'approve':'approved','reject':'rejected','withdraw':'withdrawn'}[action],
                reviewed_by=actor['username'],revision=item['revision']+1,updated_at=_now())
            self._put(conn,item)
        if action=='approve':self._clear_receipt()
        return self._public(item)

    def recover(self):
        if not self.journal_path.exists():return
        with self._db() as conn:
            receipt=json_store.read(self.journal_path)
            if not receipt:return
            if receipt['workspace']!=str(self.root.resolve()):
                raise Conflict('审批回执属于旧工作目录，请先在原版本恢复再切换发布目录')
            with store_lock(self.root,wait=True):
                json_store.recover(self.root)
                record=self._note(receipt['note_id'])
            from knowledge_history import history_entries
            history=history_entries(self.root,record)
            index=receipt['history_index']
            transition=history[index].get('previous',{}) if len(history)>index else {}
            after=history[index+1].get('previous',{}) if len(history)>index+1 else record
            # Bind the receipt to the exact new history transition, rather than
            # accepting an identical body that happened to exist long ago.
            applied=(transition.get('metadata',{}).get('revision')==receipt['pre_revision']
                and transition.get('body')==receipt['pre_body'] and after.get('body')==receipt['post_body'])
            if applied:
                from edit_locks import EditLocks
                EditLocks.recover_receipt(conn,receipt)
            if applied and receipt.get('kind')!='entry-save':
                item=self._get(conn,receipt['proposal_id'])
                if item['status']!='approved':
                    if 'proposed_node' in receipt:item['proposed_node']=receipt['proposed_node']
                    item.update(status='approved',reviewed_by=receipt['reviewed_by'],revision=item['revision']+1,
                        result_revision=after['metadata']['revision'],updated_at=_now())
                    self._put(conn,item)
        # A receipt before canonical preparation is harmless: leave pending and
        # let the next explicit approval compare the current target again.
        self._clear_receipt()

    def recovery_pending(self):
        return self.journal_path.is_file()

    def backup(self,path):
        self.recover()
        destination=Path(path)
        if destination.resolve()==self.db_path.resolve():raise ValueError('备份不能覆盖原数据库')
        destination.parent.mkdir(parents=True,exist_ok=True)
        # backup() includes committed WAL pages, unlike copying the main file.
        with self._db():pass
        with closing(sqlite3.connect(self.db_path)) as source,closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        os.chmod(destination,0o600)
