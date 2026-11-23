"""Private annotations on durable group/utterance identities and administrator activity."""
from contextlib import closing
import json
import uuid

import templates_store as library
from workspace import Conflict


def text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label}须为 1 至 {limit} 字的文本')
    return value.strip()


def comments(service, status='open', group_id=None):
    if status not in ('all', 'open', 'closed'):
        raise ValueError('批注状态无效')
    with closing(service._connection()) as conn:
        rows = conn.execute('SELECT data FROM template_comments WHERE (? IS NULL OR group_id=?) ORDER BY rowid DESC', (group_id, group_id))
        return [thread for (data,) in rows if (thread := json.loads(data))['status'] == status or status == 'all']


def comment_counts(service):
    with closing(service._connection()) as conn:
        rows = conn.execute("""
            SELECT group_id, json_extract(data, '$.utterance_id'), count(*)
            FROM template_comments GROUP BY 1, 2
        """)
        return [{'group_id': gid, 'utterance_id': uid, 'count': count} for gid, uid, count in rows]


def annotate(service, actor, data, thread_id=None, action='create'):
    from templates_proposals import _now
    if action in ('close','reopen') and actor['role'] != 'admin':
        raise PermissionError('只有管理员可以关闭或重开批注')
    with service.lock, closing(service._connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if thread_id:
            row = conn.execute('SELECT data FROM template_comments WHERE id=?', (thread_id,)).fetchone()
            if not row: raise KeyError('批注不存在')
            thread = json.loads(row[0])
        else:
            snapshot = library.snapshot(service.root)
            if data.get('revision',snapshot['revision']) != snapshot['revision']: raise Conflict('正式库已变化，请刷新后核对批注对象')
            groups = snapshot['groups']
            group = next((g for g in groups if g['id'] == data.get('group_id')), None)
            if not group: raise Conflict('模板组已删除，请刷新')
            uid = data.get('utterance_id')
            utterance = next((u for u in group['utterances'] if u['id'] == uid), None)
            if uid is not None and not utterance: raise Conflict('话术已删除，请刷新')
            original = utterance['text'] if utterance else group['name']
            if data.get('original_text', original) != original: raise Conflict('批注原文已变化，请刷新后核对')
            thread = {'id':uuid.uuid4().hex, 'group_id':group['id'], 'group_name':group['name'], 'utterance_id':uid,
                      'original_text':original, 'status':'open', 'messages':[]}
            if not utterance: thread['original_group'] = group
        message = {'action':action,'by':actor['username'],'role':actor['role'],'at':_now()}
        if action in ('create','reply'):
            if thread['status'] == 'closed': raise Conflict('请先重新打开批注')
            message['body'] = text(data.get('body'), '批注内容')
        elif action == 'edit':
            index = data.get('message_index')
            if type(index) is not int or not 0 <= index < len(thread['messages']):
                raise ValueError('批注消息不存在')
            original = thread['messages'][index]
            if original['action'] not in ('create', 'reply') or original['by'] != actor['username']:
                raise PermissionError('只能编辑本人发布的批注内容')
            if thread['status'] == 'closed': raise Conflict('请先重新打开批注')
            revisions = original.setdefault('revisions', [])
            if type(data.get('message_revision')) is not int or data['message_revision'] != len(revisions):
                raise Conflict('这条内容已有修改，请核对最新版本')
            body = text(data.get('body'), '批注内容')
            if original['body'] == body: return thread
            revisions.append({'body': original['body'], 'at': original.get('edited_at', original['at'])})
            original.update(body=body, edited_at=message['at'])
            message.update(body=body, message_index=index)
        else:
            status = 'closed' if action == 'close' else 'open'
            if thread['status'] == status: return thread
            thread['status'] = status
        thread['messages'].append(message)
        conn.execute('INSERT OR REPLACE INTO template_comments VALUES(?,?,?)', (thread['id'], thread['group_id'], json.dumps(thread, ensure_ascii=False)))
        return thread


def direct_action(before, after):
    if not after: return 'delete'
    if not before: return 'create'
    if bool(before.get('ignored')) != bool(after.get('ignored')): return 'ignore' if after.get('ignored') else 'unignore'
    old = {u['id']:u for u in before['utterances']}
    new_ids = {u['id'] for u in after['utterances']}
    if new_ids < old.keys(): return 'delete_utterance'
    if old.keys() < new_ids: return 'add_utterance'
    for u in after['utterances']:
        if u['id'] in old and bool(u.get('ignored')) != bool(old[u['id']].get('ignored')):
            return 'ignore_utterance' if u.get('ignored') else 'unignore_utterance'
        if u['id'] in old and bool(u.get('fixed')) != bool(old[u['id']].get('fixed')):
            return 'fix_utterance' if u.get('fixed') else 'unfix_utterance'
    if before['utterances'] != after['utterances']: return 'edit_utterance'
    if before.get('review_status','ai_generated')!=after.get('review_status','ai_generated'): return 'review_status'
    return 'edit_group'


def history(service, actor, group_id=None, latest=False):
    items = []
    def add(gid, **entry):
        if not group_id or gid == group_id: items.append(dict(group_id=gid, **entry))
    audit_rows=library._read_metadata(service.root)['audit']
    audits=[*(row for row in audit_rows if row.get('manual') or row.get('action') in ('confirm_warning','resolve_conflict')),
            *library.review_history(service.root)]
    for audit in audits:
        context = audit.get('manual')
        if audit.get('action') == 'confirm_warning':
            add(audit['group_id'],id=f"{audit['id']}:{audit['group_id']}", action='confirm_warning', at=audit['at'], by=audit['actor'], source='manual')
        if audit.get('action')=='resolve_conflict' and audit.get('group_id'):
            gid=audit['group_id']
            add(gid,id=f"{audit['id']}:{gid}",action='resolve_conflict',at=audit['at'],by=audit['actor'],source='sync',batch_id=audit.get('batch_id'),before=audit.get('before_group'),after=audit.get('after_group'))
        if not context: continue
        for change in audit['changes']:
            if change['kind'] != 'group': continue
            gid = change['id']
            if group_id and gid != group_id: continue
            before, after = (next((g for g in audit.get(key,{}).get('groups',[]) if g['id']==gid),None) for key in ('before','after'))
            add(gid, id=f"{audit['id']}:{gid}", action=direct_action(before,after), at=audit['at'], by=audit['actor'], before=before, after=after, **context)
    with closing(service._connection()) as conn:
        proposals=conn.execute("SELECT json_remove(data,'$.base') FROM proposals").fetchall()
    for (raw,) in proposals:
        p = json.loads(raw)
        private = actor['role'] == 'admin' or p['author'] == actor['username']
        original=p.get('submission',{}).get('changes',p['changes'])
        if private:
            for change in original:
                if change['kind']!='group': continue
                gid=change['id']
                common={'source':p.get('source','proposal'),'batch_id':p.get('batch_id',p['id']),'proposal_id':p['id']}
                if p.get('author_role')=='admin' and p.get('source')=='web-import':
                    add(gid,id=f"{p['id']}:submit:{gid}",action='submit',at=p['created_at'],by=p['author'],submitted=change.get('value'),**common)
                for message in p.get('discussion',[]):
                    if message['role']=='admin':
                        add(gid,id=f"{p['id']}:{message['id']}:{gid}",action='proposal_comment',at=message['at'],by=message['by'],body=message['body'],**common)
        for index,review in enumerate(p['reviews']):
            action = review.get('action','approve')
            if not private and action != 'approve': continue
            if review.get('role') != 'admin' and not ('role' not in review and action in ('approve','reject')): continue
            for change in review.get('submitted',review.get('changes',p['changes'])):
                if change['kind'] != 'group': continue
                gid = change['id']; key = 'group:'+gid
                record_id=f"{p['id']}:{review.get('request',index)}:{gid}"
                if not private:
                    add(gid,id=record_id,action=review.get('operation',action),at=review['at'],by=review['by'],source='proposal',after=review.get('after',{}).get(key))
                    continue
                changes = review.get('changes',[])
                suggested = next((c.get('value') for c in changes if c['kind']=='group' and c['id']==gid),None)
                original = next((c.get('value') for c in p.get('submission',{}).get('changes',[]) if c['kind']=='group' and c['id']==gid),None)
                add(gid,id=record_id, original_submission=original,action=review.get('operation',action), at=review['at'], by=review['by'],
                    source=p.get('source','proposal'), batch_id=p.get('batch_id',p['id']), proposal_id=p['id'], author=p['author'],
                    before=review.get('before',{}).get(key), submitted=change.get('value'), reviewed=suggested, after=review.get('after',{}).get(key))
    for thread in comments(service,'all',group_id):
        for index,m in enumerate(thread['messages']):
            if m['role'] == 'admin': add(thread['group_id'],id=f"{thread['id']}:{index}",action='comment_'+m['action'],at=m['at'],by=m['by'],source='comment',
                comment_id=thread['id'],utterance_id=thread['utterance_id'],original_text=thread['original_text'],body=(m.get('revisions') or [m])[0].get('body'))
    items.sort(key=lambda row:row['at'], reverse=True)
    if latest:
        seen = set(); summaries = []
        for row in items:
            if row['group_id'] in seen: continue
            seen.add(row['group_id']); summaries.append({k:row[k] for k in ('id','group_id','action','at','by')})
        return summaries
    return items


def latest_history(service, actor):
    def stamps():
        result=[]
        for path in (service.root / library.META,service.root / library.REVIEW_HISTORY,service.path):
            try: stat=path.stat()
            except FileNotFoundError: result.append(None)
            else: result.append((stat.st_mtime_ns,stat.st_size,stat.st_ino))
        return tuple(result)
    with service.history_lock:
        gen=stamps()
        if getattr(service,'_summary_stamp',None)!=gen:
            service._summary_stamp=gen
            service._summary_cache={}
        key=actor['role'],actor['username']
        if key not in service._summary_cache:
            result=history(service,actor,latest=True)
            if gen==stamps():service._summary_cache[key]=result
            return result
        return service._summary_cache[key]
