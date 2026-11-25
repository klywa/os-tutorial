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
from save_timing import timed
import template_group_edit as group_edit
import templates_store as library
from workspace import Conflict, Busy

_locks={}
_guard=threading.Lock()


def _now():return datetime.now(timezone.utc).isoformat()


def _authority(actor):
    if not actor or actor.get('role') not in ('admin','annotator','quality') or not actor.get('username'):
        raise PermissionError('浏览者没有模板编辑或提案权限')


def _records(snapshot,changes,aliases=None):
    aliases=aliases or {}
    return {change['kind']+':'+change['id']:next((row for row in snapshot[change['kind']+'s']
        if row['id']==(aliases.get(change['id'],change['id']) if change['kind']=='group' else change['id'])),None)
        for change in changes}


def _replace_base(base,change,record):
    rows=base[change['kind']+'s']
    rows[:]=[r for r in rows if r['id']!=change['id']]
    if record is not None:rows.append(deepcopy(record))


def _apply_review_status(record,status,actor):
    record['review_status']=status
    if status=='final_reviewed':
        record.update(reviewed_by=actor['username'],reviewed_at=_now())
    else:
        record.pop('reviewed_by',None)
        record.pop('reviewed_at',None)


def _accepted_status(item):
    return 'partially_approved' if any(row.get('action')=='reject' for row in item['reviews']) else 'approved'


def _approved_response(item, request):
    review=next((row for row in item['reviews'] if row.get('request')==request), {})
    return {**item, 'formal_write':review['formal_write']} if 'formal_write' in review else item


def _formal_write(saved, previous_revision, changes, aliases):
    return {'revision':saved['revision'],'previous_revision':previous_revision,
            'changes':[{**change,**({'value':record} if record is not None else {})}
                       for change,record in zip(changes,_records(saved,changes).values())],
            **({'merged_groups':library.merged_group_ids(aliases)} if aliases else {})}


def proposal_summary(item):
    current={(row['kind'],row['id']) for row in item['changes']}
    historical={}
    submission=item.get('submission') or {}
    reviews=item.get('reviews',[])
    for row in [*submission.get('changes',[]),*(change for review in reviews for change in review.get('changes',[]))]:
        key=row['kind'],row['id']
        if key not in current and key not in historical:
            original=submission.get('before',{}).get(':'.join(key))
            historical[key]={'kind':key[0],'id':key[1],'action':row['action'],
                             'target_name':(row.get('value') or original or {}).get('name')}
    return {**{key:value for key,value in item.items() if key not in ('base','submission','reviews')},
            'base':{**item['base'],'groups':[row for row in item['base']['groups'] if ('group',row['id']) in current]},
            'has_history':bool(submission or reviews),'history_targets':list(historical.values()),
            'previously_approved':any(row.get('action')=='approve' for row in reviews)}


class TemplateProposals:
    def __init__(self,root,path,entity_provider=None,*,workflow_enabled=False):
        self.root=Path(root);self.path=Path(path)
        self.entity_provider=entity_provider
        self.workflow_enabled=workflow_enabled
        self.receipt=self.path.with_name(self.path.name+'.approval.json')
        self.pending_sync=self.path.with_name(self.path.name+'.pending-sync.json')
        with _guard:self.lock=_locks.setdefault(str(self.path.resolve()),threading.RLock())
        self.history_lock=threading.Lock()

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

    @timed('template_proposal_write')
    def _save(self,conn,item):
        group_ids={row['id'] for row in item['changes'] if row['kind']=='group'}
        group_ids.update(row['id'] for row in (item.get('submission') or {}).get('changes',[]) if row['kind']=='group')
        item['base']['groups']=[row for row in item['base']['groups'] if row['id'] in group_ids]
        item=deepcopy(item)
        item['proposal_revision']=json_store.digest({k:v for k,v in item.items() if k!='proposal_revision'})
        conn.execute('INSERT OR REPLACE INTO proposals(id,data) VALUES(?,?)',
                     (item['id'],json.dumps(item,ensure_ascii=False)))
        return item

    def list(self,actor,proposal_id=None,*,summary=False):
        _authority(actor)
        with closing(self._connection()) as conn:
            query='SELECT data FROM proposals ORDER BY rowid' if proposal_id is None else 'SELECT data FROM proposals WHERE id=?'
            rows=conn.execute(query,() if proposal_id is None else (proposal_id,)).fetchall()
        items=[json.loads(row[0]) for row in rows]
        visible=[item for item in items if actor['role']=='admin' or item['author']==actor['username']]
        pending=[item for item in visible if item['status']=='pending']
        if pending:
            current=library.snapshot(self.root)
            for item in pending:
                actual=_records(current,item['changes'])
                item['conflicts']={key:{'current':actual[key],'revision':json_store.digest(actual[key])}
                    for key,old in _records(item['base'],item['changes']).items() if old!=actual[key]}
        return [proposal_summary(item) for item in visible] if summary else visible

    def card_previews(self,actor,proposal_id=None):
        _authority(actor)
        with closing(self._connection()) as conn:
            query="SELECT data FROM proposals WHERE json_extract(data,'$.status')='pending'"
            params=[]
            if proposal_id is not None:
                query+=' AND id=?'
                params.append(proposal_id)
            if actor['role']!='admin':
                query+=" AND json_extract(data,'$.author')=?"
                params.append(actor['username'])
            items=[json.loads(row[0]) for row in conn.execute(query,params)]
        previews=[]
        for item in items:
            base={group['id']:group for group in item['base']['groups']}
            events={change['id']:change['value'] for change in item['changes']
                    if change['kind']=='event' and change['action']=='put'}
            for index,change in enumerate(item['changes']):
                if change['kind']!='group':continue
                group=base.get(change['id'])
                event=events.get((change.get('value') or group or {}).get('event_id'))
                previews.append({'proposal_id':item['id'],'author':item['author'],'created_at':item['created_at'],
                    'proposal_revision':item['proposal_revision'],'change_index':index,
                    'review_status_changed':change['id'] in item.get('group_review_overrides',{}),
                    'source':item.get('source'),'change':change,'base':group,**({'event':event} if event else {})})
        return previews

    def approved_retry(self,actor,pid,data):
        if actor.get('role')!='admin':raise PermissionError('只有管理员可以审批模板提案')
        with self.lock,closing(self._connection()) as conn:
            item=self._read(conn,pid)
            request=json_store.digest([actor['username'],'approve',data])
            if (item['status']=='approved' and set(data)=={'proposal_revision'}
                or any(r.get('request')==request for r in item['reviews'])):
                return _approved_response(item,request)

    def submit(self,actor,data,*,workflow_source=None,restored_from=None,prepare=None):
        _authority(actor)
        with self.lock:
            if self.receipt.exists():raise Conflict('上次模板审批尚未恢复，请稍后重试')
            revision=data.get('revision');changes=deepcopy(data.get('changes'))
            base=library.snapshot(self.root)
            if prepare is not None:
                if revision!=base['revision']:raise Conflict('模板库已更新，请刷新；草稿已保留')
                changes=prepare(base)
            inherited=set()
            if workflow_source=='editor':
                changes=group_edit.fork_direct_changes(base,changes)
                changes,inherited=library.related_copy_changes(base,changes)
            edit_targets=library.editor_utterance_targets(base,changes) if workflow_source=='editor' else set()
            library.preview_changes(self.root,revision,changes,authorized_fixed=edit_targets|inherited,**self._entities())
            if not changes:raise ValueError('没有需要提交的模板修改')
            item={'id':uuid.uuid4().hex,'author':actor['username'],'status':'pending',
                  'created_at':_now(),'revision':revision,'changes':changes,
                  'base':{'events':base['events'],'groups':base['groups']},'reviews':[]}
            item['author_role']=actor['role']
            if workflow_source:
                item['workflow_source']=workflow_source
            if inherited:
                item['group_fixed_edits']={}
                for gid,uid in sorted(inherited):
                    item['group_fixed_edits'].setdefault(gid,[]).append(uid)
            if restored_from:
                item['restored_from']=restored_from
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

    def _finish_receipt(self,receipt,saved):
        if receipt.get('aliases'):
            latest=receipt['proposal']['reviews'][-1]
            latest['formal_write']=_formal_write(saved,receipt['previous_revision'],receipt['changes'],receipt['aliases'])
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
                current=library.apply(self.root,current['revision'],receipt['changes'],actor=receipt['actor'],manual=receipt.get('manual'),
                    authorized_fixed={tuple(pair) for pair in receipt.get('authorized_fixed',[])},aliases=receipt.get('aliases'),**self._entities())
            self._finish_receipt(receipt,current)

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
            if any(r.get('request')==request for r in item['reviews']):return _approved_response(item,request)
            target={'approve':'approved','reject':'rejected','withdraw':'withdrawn','edit':'pending'}[action]
            if action!='edit' and item['status']==target and set(data)<= {'proposal_revision'}:return item
            if item['status']!='pending':raise Conflict('该模板提案已处理')
            if data.get('proposal_revision')!=item.get('proposal_revision'):
                raise Conflict('模板提案已变化，请重新核对')
            if 'submission' not in item and not item['reviews']:
                item['submission']={'before':_records(item['base'],item['changes']),'changes':deepcopy(item['changes'])}
            if action in ('withdraw','reject'):
                indices=data.get('change_ids')
                selected=item['changes']
                if 'change_ids' in data:
                    if (action!='reject' or not isinstance(indices,list) or len(indices)!=1
                            or type(indices[0]) is not int or not 0<=indices[0]<len(selected)
                            or selected[indices[0]]['kind']!='group'):
                        raise ValueError('请选择一个待审模板组驳回')
                    selected=[selected[indices[0]]]
                    item['changes']=[row for i,row in enumerate(item['changes']) if i!=indices[0]]
                    for field in ('group_review_overrides','group_fixed_edits'):
                        item.get(field,{}).pop(selected[0]['id'],None)
                item['reviews'].append({'action':action,'role':actor['role'],'at':_now(),'by':actor['username'],'request':request,
                    'before':_records(item['base'],selected),'submitted':deepcopy(selected),'changes':deepcopy(selected)})
                if 'change_ids' in data and item['changes']:
                    target='pending'
                elif action=='reject' and any(row['action']=='approve' for row in item['reviews']):
                    target='partially_approved'
                item.update(status=target,reviewed_by=actor['username'],reviewed_at=_now())
                with closing(self._connection()) as conn:item=self._save(conn,item);conn.commit()
                return item
            indices=data.get('change_ids',list(range(len(item['changes']))))
            if (not isinstance(indices,list) or not indices or any(type(i)!=int or i<0 or i>=len(item['changes']) for i in indices)
                or len(set(indices))!=len(indices)):raise ValueError('请选择有效的审批条目')
            selected=[item['changes'][i] for i in indices]
            if 'group_editor' in data:
                if action not in ('approve','edit') or len(selected)!=1 or selected[0]['kind']!='group':
                    raise ValueError('请选中一个模板组进行编辑或采纳')
                operation=data['group_editor']
                if action=='edit' and isinstance(operation,dict) and set(operation) in ({'ignore'},{'fixed'}):
                    return self._save_utterance_flag(actor,item,indices[0],operation,request)
                return self._group_action(actor,item,action,data,indices[0],request,needs_sync)
            changes=deepcopy(data.get('changes',selected))
            status_only=item.get('workflow_source')=='review-status'
            complete_group=data.get('complete_group',False)
            if type(complete_group) is not bool or complete_group and (
                    action!='approve' or status_only or len(selected)!=1 or
                    selected[0]['kind']!='group' or selected[0]['action']!='put'):
                raise ValueError('保存并采纳只适用于单个待审模板组修改')
            if status_only and (action=='edit' or changes!=selected):
                raise ValueError('状态提案只能按原申请审核，请撤回后重新提交。')
            allowed={(c['kind'],c['id'],c['action']) for c in selected}
            if (not isinstance(changes,list) or len(changes)!=len(selected)
                or any(not isinstance(c,dict) or (c.get('kind'),c.get('id'),c.get('action')) not in allowed for c in changes)
                or len({(c['kind'],c['id']) for c in changes})!=len(changes)):
                raise ValueError('审批内容必须对应所选提案')
            current=library.snapshot(self.root)
            before=_records(item['base'],selected)
            actual=_records(current,selected)
            conflicts={key:json_store.digest(record) for key,record in actual.items() if record!=before[key]}
            merge_changes=changes
            if conflicts:
                if action=='approve' and not status_only and changes==selected and all(
                        row['kind']=='group' and row['action']=='put'
                        for row in changes if row['kind']+':'+row['id'] in conflicts):
                    events={row['id']:row for row in current['events']}
                    events.update({row['id']:row['value'] for row in changes if row['kind']=='event' and row['action']=='put'})
                    merge_changes=[]
                    for row in changes:
                        key=row['kind']+':'+row['id']
                        if key in conflicts:
                            value=group_edit.merge_group(before[key],actual[key],row['value'],events.get(row['value']['event_id']))
                            row={**row,'value':value}
                        merge_changes.append(row)
                elif not (action=='edit' and data.get('rebase')==conflicts):
                    raise Conflict('模板已被修改，请重新核对提案；建议内容已保留')
            if data.get('rebase') and data['rebase']!=conflicts:raise Conflict('正式版本已变化，请刷新后重试')
            entities=self._entities()
            if action=='edit':
                edited={(c['kind'],c['id']):c for c in changes}
                updated=[edited.get((c['kind'],c['id']),c) for c in item['changes']]
                edit_targets=library.editor_utterance_targets(current,updated) if item.get('workflow_source')=='editor' else set()
                edit_targets.update((gid,uid) for gid,rows in item.get('group_fixed_edits',{}).items() for uid in rows)
                library.preview_changes(self.root,current['revision'],updated,authorized_fixed=edit_targets,**entities)
                for change in changes:
                    key=change['kind']+':'+change['id']
                    _replace_base(item['base'],change,actual[key])
                item['reviews'].append({'action':'edit','role':actor['role'],'at':_now(),'by':actor['username'],'before':before,
                    'current':actual,'submitted':selected,'changes':changes,'request':request})
                item['changes']=updated
                with closing(self._connection()) as conn:item=self._save(conn,item);conn.commit()
                return item
            approved_changes=merge_changes
            manual={'source':'review-status'} if status_only else None
            if not status_only and (self.workflow_enabled or item.get('workflow_source')):
                import template_workflow as workflow
                source=item.get('workflow_source','editor')
                origin={'username':item['author'],'role':item.get('author_role','annotator')}
                selected_groups={c['id']:c.get('value') for c in selected if c['kind']=='group'}
                origins={}
                for review in item['reviews']:
                    if review['action']!='edit':continue
                    old={c['id']:c.get('value') for c in review['submitted'] if c['kind']=='group'}
                    for change in review['changes']:
                        if change['kind']=='group' and workflow.content(change.get('value'))!=workflow.content(old.get(change['id'])):
                            origins[change['id']]=({'username':review['by'],'role':review['role']},'editor')
                for change in changes:
                    if change['kind']=='group' and workflow.content(change.get('value'))!=workflow.content(selected_groups.get(change['id'])):
                        origins[change['id']]=(actor,'editor')
                approved_changes=workflow.prepare(self.root,current,merge_changes,origin,source=source,origins=origins,**entities)
                if item.get('restored_from'):
                    manual={'source':'restore','restored_from':item['restored_from']}
            overrides=item.get('group_review_overrides',{})
            selected_fixed={(row['id'],uid) for row in selected if row['kind']=='group'
                            for uid in item.get('group_fixed_edits',{}).get(row['id'],[])}
            for change in changes:
                value=change.get('value',{})
                uid=change['id']
                if change['kind']=='group' and uid in overrides and 'review_status' in value and value['review_status']==overrides[uid]:
                    approved=next((row['value'] for row in approved_changes if row['kind']=='group' and row['id']==uid),None)
                    if approved is None:
                        approved=deepcopy(actual['group:'+uid] or value)
                        approved_changes.append({**change,'value':approved})
                    _apply_review_status(approved,overrides[uid],actor)
            if item.get('workflow_source')=='editor':
                selected_fixed.update(library.editor_utterance_targets(current,approved_changes,pin=True,explicit=selected_fixed))
            projected,approved_changes,aliases,selected_fixed=library.approval_projection(
                self.root,current['revision'],approved_changes,authorized_fixed=selected_fixed,
                merge_groups=item.get('workflow_source')=='editor',**entities)
            merged_groups=library.merged_group_ids(aliases)
            remainder=[]
            approved={(c['kind'],c['id']):c for c in changes}
            for index,original in enumerate(item['changes']):
                accepted=approved.get((original['kind'],original['id']))
                if index not in indices or not complete_group and accepted!=original:remainder.append(original)
            updated=deepcopy(item)
            updated['reviews'].append({'action':'approve','operation':'approve_partial' if remainder else 'approve', 'role':actor['role'],'at':_now(),'by':actor['username'],'before':before,
                'submitted':selected,'changes':merge_changes,'request':request,'after':_records(projected,merge_changes,merged_groups),
                **({'merged_groups':merged_groups} if merged_groups else {})})
            # Untouched pending records retain the original ancestor: approving
            # one record must never silently rebase another stale suggestion.
            next_base=deepcopy(item['base'])
            for accepted in changes:
                key=accepted['kind']+':'+accepted['id']
                _replace_base(next_base,accepted,_records(projected,[accepted])[key])
            updated.update(status='pending' if remainder else _accepted_status(updated),changes=remainder,
                base=next_base,
                reviewed_by=actor['username'],reviewed_at=_now())
            receipt={'proposal':updated,'actor':actor['username'],'changes':approved_changes,'needs_sync':needs_sync,
                     'before':_records(current,approved_changes),'after':_records(projected,approved_changes),
                     **({'aliases':aliases,'previous_revision':current['revision']} if aliases else {}),
                     **({'authorized_fixed':sorted(selected_fixed)} if selected_fixed else {}),
                     **({'manual':manual} if manual else {})}
            return self._apply_receipt(current,receipt,entities,include_write=data.get('return_write') is True)

    def _apply_receipt(self,current,receipt,entities,*,include_write=False):
        json_store.write_file(self.receipt,receipt)
        try:
            saved=library.apply(self.root,current['revision'],receipt['changes'],actor=receipt['actor'],manual=receipt.get('manual'),
                authorized_fixed={tuple(pair) for pair in receipt.get('authorized_fixed',[])},aliases=receipt.get('aliases'),**entities)
        except (ValueError,Busy,Conflict):
            # Validation and revision failures occur before the formal commit.
            self.receipt.unlink(missing_ok=True)
            raise
        self._finish_receipt(receipt,saved)
        with closing(self._connection()) as conn:result=self._read(conn,receipt['proposal']['id'])
        if not include_write:return result
        return {**result,'formal_write':_formal_write(saved,current['revision'],receipt['changes'],receipt.get('aliases'))}

    def _save_utterance_flag(self,actor,item,index,operation,request):
        import templates_schema as schema
        action,payload=next(iter(operation.items()))
        schema.fields(payload,{'id','value'},{'id','value'})
        schema.identity(payload['id'])
        if type(payload['value']) is not bool:
            raise ValueError('话术状态必须为布尔值')
        if action=='fixed' and actor['role']!='admin':
            raise PermissionError('只有管理员可以固定话术')
        selected=item['changes'][index]
        gid=selected['id']
        base=_records(item['base'],[selected])['group:'+gid]
        value=deepcopy(selected.get('value',base))
        row=next((row for row in (value or {}).get('utterances',[]) if row['id']==payload['id']),None)
        if row is None:
            raise Conflict('话术已不存在，请重新核对')
        field='ignored' if action=='ignore' else 'fixed'
        library.check_utterance_flags(row, {**row,field:payload['value']})
        if payload['value']:row[field]=True
        elif field=='fixed':row[field]=False
        else:row.pop(field,None)
        if field=='fixed':
            permissions=item.setdefault('group_fixed_edits',{})
            permissions[gid]=sorted({*permissions.get(gid,[]),row['id']})
        if item.get('workflow_source')=='review-status':
            item.get('submission',{}).setdefault('source',item.get('source','review-status'))
            item.setdefault('group_review_overrides',{})[gid]=value.get('review_status')
            item.update(workflow_source='editor',source='editor')
        change={'kind':'group','action':'put','id':gid,'value':value}
        item['changes'][index]=change
        item['reviews'].append({'action':'edit','role':actor['role'],'at':_now(),'by':actor['username'],
            'request':request,'before':{'group:'+gid:base},'submitted':[selected],'changes':[change]})
        with closing(self._connection()) as conn:
            result=self._save(conn,item);conn.commit()
        return result

    def _group_action(self,actor,item,action,data,index,request,needs_sync):
        import template_workflow as workflow
        import templates_schema as schema

        operation=data['group_editor']
        if isinstance(operation,dict) and 'fields' in operation:
            if 'group' in operation:
                raise ValueError('不能同时提供完整模板和字段修改')
            candidate=item['changes'][index]
            working=candidate.get('value') or _records(item['base'],[candidate]).get('group:'+candidate['id'])
            if not working:raise Conflict('待审模板已不存在')
            operation={**operation}
            operation['group']=group_edit.apply_fields(working,operation.pop('fields'))
        schema.fields(operation,{'group','event','delete','fixed','status','resolve_conditions','preview','dependency_token'},set())
        selected=item['changes'][index]
        gid=selected['id']
        current=library.snapshot(self.root)
        group_key='group:'+gid
        actual=_records(current,[selected])[group_key]
        base=_records(item['base'],[selected])[group_key]
        working=selected.get('value',base)
        draft=deepcopy(operation.get('group',working))
        dropping=operation.get('delete') is True or selected['action']=='delete' and not {'group','status','fixed'}.intersection(operation)
        if not dropping and (not isinstance(draft,dict) or draft.get('id')!=gid):
            raise ValueError('模板组身份不一致')

        if 'event' in operation and actor['role'] not in ('admin','annotator'):
            raise PermissionError('当前身份没有新增事件参数的权限')
        events={row['id']:row for row in current['events']}
        draft_event_id=(draft or {}).get('event_id')
        pending_events={row['id']:(i,row) for i,row in enumerate(item['changes'])
                        if row['kind']=='event' and row['action']=='put'}
        pending_event=pending_events.get(draft_event_id)
        proposed=operation.get('event',pending_event[1]['value'] if pending_event else None)
        if ('event' in operation and not isinstance(proposed,dict)
                or proposed is not None and proposed.get('id')!=draft_event_id):
            raise ValueError('事件定义必须对应本模板组')
        event=events.get(draft_event_id)
        if 'event' in operation:
            schema.fields(proposed,{'id','name','category','parameters'},{'id','name','parameters'})
            prior=pending_event[1]['value'] if pending_event else event
            if not prior or any(proposed.get(key)!=value for key,value in prior.items() if key!='parameters'):
                raise ValueError('模板组编辑只支持为对应事件新增参数')
            if not isinstance(proposed.get('parameters'),list) or any(
                    row not in proposed['parameters'] for row in prior['parameters']):
                raise ValueError('请在事件设置中修改已有参数定义')

        overrides=item.setdefault('group_review_overrides',{})
        explicit_status='status' in operation or gid in overrides or item.get('workflow_source')=='review-status'
        desired=operation.get('status',overrides.get(gid,(working or {}).get('review_status')))
        if 'status' in operation:
            workflow.review_status_change({'groups':[draft]},gid,actor,desired)
        authorized=item.setdefault('group_fixed_edits',{})
        allowed=set(authorized.get(gid,[]))
        if 'fixed' in operation:
            if actor['role']!='admin':raise PermissionError('只有管理员可以固定话术')
            fixed=operation['fixed']
            schema.fields(fixed,{'id','value'},{'id','value'})
            if 'group' in operation or dropping or type(fixed['value']) is not bool:
                raise ValueError('请单独保存话术固定操作')
            row=next((row for row in draft['utterances'] if row['id']==fixed['id']),None)
            if row is None:raise Conflict('话术已不存在，请重新核对')
            row['fixed']=fixed['value']
            allowed.add(row['id'])
        editor_proposal=item.get('workflow_source')=='editor'
        if working:
            edit_targets=library.editor_utterance_targets({'groups':[working]},
                [{'kind':'group','action':'put','id':gid,'value':draft}]) if editor_proposal and not dropping else ()
            library.check_fixed_utterances({'groups':[working]},{'groups':[] if dropping else [draft]},
                (gid,operation['fixed']['id']) if 'fixed' in operation else None,authorized_fixed=edit_targets)

        resolve=operation.get('resolve_conditions')
        if resolve is not None and (actor['role']!='admin' or resolve!=current['revision']):
            raise Conflict('正式模板已变化，请重新对照条件后定稿。')
        new_gid=gid
        if dropping:
            if base!=actual:raise Conflict('原模板组已变化，请先核对再删除。')
            change={'kind':'group','action':'delete','id':gid} if actual else None
        else:
            draft=group_edit.merge_group(base,actual,draft,proposed or event,resolve is not None)
            if actual and group_edit.identity_changed(actual,draft,events.get(actual['event_id']),proposed or event):
                if actor['role'] not in ('admin','annotator'):
                    raise PermissionError('触发动作变化需要新建模板组，请由有新建权限的账号处理')
                draft=group_edit.fork_group(draft)
                new_gid=draft['id']
                allowed=set()
            if explicit_status:
                draft['review_status']=desired
            change={'kind':'group','action':'put','id':new_gid,'value':draft}

        dependency,keys=group_edit.required_event(draft,event,proposed) if not dropping else (None,[])
        token=json_store.digest(dependency) if dependency else None
        if operation.get('preview') is True:
            if action!='approve':raise ValueError('只支持预览采纳')
            return {'dependency_token':token,'event':dependency['name'] if dependency else None,
                'parameters':[p['name'] for p in dependency['parameters'] if p['key'] in keys] if dependency else []}
        if action=='approve' and token and operation.get('dependency_token')!=token:
            raise Conflict('请先在卡片确认同时发布所需事件参数。')
        dependencies=[{'kind':'event','action':'put','id':dependency['id'],'value':dependency}] if dependency else []
        changes=[*dependencies,*([change] if change else [])]
        fixed_targets={(new_gid,row_id) for row_id in allowed}
        entities=self._entities()
        submitted=[selected]
        review={'action':action,'role':actor['role'],'at':_now(),'by':actor['username'],'request':request,
                'before':{group_key:base},'submitted':submitted,'changes':changes}
        remaining=[row for i,row in enumerate(item['changes']) if i!=index]
        overrides.pop(gid,None)
        authorized.pop(gid,None)
        if action=='edit':
            validation_changes=changes
            if proposed and 'event' in operation:
                validation_changes=[{'kind':'event','action':'put','id':proposed['id'],'value':proposed},
                                    *([change] if change else [])]
            validation_targets=fixed_targets|library.editor_utterance_targets(current,validation_changes) if editor_proposal else fixed_targets
            library.preview_changes(self.root,current['revision'],validation_changes,authorized_fixed=validation_targets,**entities)
            if proposed and 'event' in operation:
                remaining=[row for row in remaining if not (row['kind']=='event' and row['id']==draft_event_id)]
                remaining.append({'kind':'event','action':'put','id':draft_event_id,'value':proposed})
                _replace_base(item['base'],remaining[-1],event)
            if change:
                remaining.insert(index,change)
                _replace_base(item['base'],change,actual if gid==new_gid else None)
                if explicit_status and not dropping:overrides[new_gid]=desired
                if allowed:authorized[new_gid]=sorted(allowed)
            if item.get('workflow_source')=='review-status' and {'group','fixed','delete'}.intersection(operation):
                item['submission'].setdefault('source',item.get('source','review-status'))
                item.update(workflow_source='editor',source='editor')
            item['changes']=remaining
            if not remaining:item['status']='withdrawn'
            item['reviews'].append(review)
            with closing(self._connection()) as conn:
                result=self._save(conn,item);conn.commit()
            return result

        origin={'username':item['author'],'role':item.get('author_role','annotator')}
        if 'group' in operation:
            origin=actor
        else:
            for entry in reversed(item.get('reviews',[])):
                if entry['action']=='edit' and any(row['kind']=='group' and row['id']==gid for row in entry['changes']):
                    origin={'username':entry['by'],'role':entry['role']}
                    break
        approved=workflow.prepare(self.root,current,changes,origin,source='editor',entities=entities.get('entities'))
        if explicit_status and not dropping:
            materialized=next((row['value'] for row in approved if row['kind']=='group'),None)
            if materialized is None and actual:
                materialized=deepcopy(actual)
                approved.append({**change,'value':materialized})
            if materialized is not None:
                _apply_review_status(materialized,desired,actor)
        if editor_proposal:
            fixed_targets.update(library.editor_utterance_targets(current,approved,pin=True,explicit=fixed_targets))
        projected,approved,aliases,fixed_targets=library.approval_projection(
            self.root,current['revision'],approved,authorized_fixed=fixed_targets,merge_groups=editor_proposal,**entities)
        merged_groups=library.merged_group_ids(aliases)
        for row in dependencies:
            actual_event=_records(projected,[row])['event:'+row['id']]
            pending=pending_events.get(row['id'])
            if pending and pending[1]['value']==actual_event:
                remaining.remove(pending[1])
            _replace_base(item['base'],row,actual_event)
        review.update(operation='approve_partial' if remaining else 'approve',after=_records(projected,changes,merged_groups))
        if merged_groups:
            review['merged_groups']=merged_groups
        item['reviews'].append(review)
        item.update(changes=remaining,status='pending' if remaining else _accepted_status(item),reviewed_by=actor['username'],reviewed_at=_now())
        receipt={'proposal':item,'actor':actor['username'],'changes':approved,'needs_sync':needs_sync,
                 'before':_records(current,approved),'after':_records(projected,approved),
                 **({'aliases':aliases,'previous_revision':current['revision']} if aliases else {}),
                 'authorized_fixed':sorted(fixed_targets)}
        return self._apply_receipt(current,receipt,entities,include_write=data.get('compact') is True)

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
