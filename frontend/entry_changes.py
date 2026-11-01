"""Per-entry deltas checked against fenced, server-captured baselines."""
from copy import deepcopy
import uuid

import json_store
from proposals import _entry, _section, _now
from workspace import Conflict


def target(item):
    return ({'kind':'slot','section_id':item['section_id'],'left_id':item['_context']['left']}
            if item['kind']=='insert' else {'kind':'entry','id':item['node_id']})


def prepare(store, conn, actor, payload):
    locks=store.edit_locks
    if set(payload)-{'note_id','client_id','request_id','changes'}:raise ValueError('不支持的条目字段')
    changes=payload.get('changes')
    if not isinstance(changes,list) or not 0<len(changes)<=1000:raise ValueError('请选择需要保存的条目')
    record=store._note(payload['note_id']);nodes=record['body']['nodes'];items=[];refs=[];seen=set()
    batch=locks.request_key(actor,payload['client_id'],payload['request_id'],'entries')
    for index,change in enumerate(changes):
        if not isinstance(change,dict) or set(change)-{'kind','lease','node'}:raise ValueError('无效的条目修改')
        kind=change.get('kind')
        if kind not in ('update','insert','delete'):raise ValueError('无效的修改类型')
        lease=locks.validate(conn,actor,payload['client_id'],change.get('lease'),payload['note_id'],record=record)
        slot=lease['resource']['kind']=='slot'
        if slot!=(kind=='insert'):raise ValueError('编辑凭证与修改类型不一致')
        base=None if slot else lease['baseline']['node']
        if not slot:
            if base['id'] in seen:raise ValueError('同一条目只能修改一次')
            seen.add(base['id'])
        proposed=None if kind=='delete' else _entry(change.get('node'),base)
        nid=base['id'] if base else 'entry-'+json_store.digest([batch,index])[:32]
        if proposed is not None:proposed={**proposed,'id':nid}
        section=lease['baseline']['section'];left=lease['baseline'].get('left_id');right=lease['baseline'].get('right_id')
        items.append({'id':uuid.uuid4().hex,'note_id':payload['note_id'],'note_title':record['metadata']['title'],
            'author':actor['username'],'kind':kind,'node_id':nid,'section_id':section[-1]['id'] if section else None,
            'after_id':left,'base_node':deepcopy(base),'proposed_node':proposed,'revision':1,'status':'pending',
            'created_at':_now(),'updated_at':_now(),'reviewed_by':None,'result_revision':None,'order':index,
            '_batch':batch,'_context':{'section':section,'left':left,'right':right,
                'left_section':_section(nodes,left),'right_section':_section(nodes,right)}})
        refs.append(change['lease'])
    return record,items,refs


def submit(store,actor,payload):
    locks=store.edit_locks;key=locks.request_key(actor,payload.get('client_id'),payload.get('request_id'),'proposal')
    with store._db() as conn:
        store._private_ready();locks.check_epoch(conn)
        prior=locks.replay(conn,key,payload)
        if prior is not None:
            return {'items':[store._public(store._get(conn,pid)) for pid in prior['ids']]}
        record,items,refs=prepare(store,conn,actor,payload)
        for item in items:store._put(conn,item)
        locks.remember(conn,key,payload,{'ids':[i['id'] for i in items]})
        locks.release_in(conn,actor,payload['client_id'],refs)
        return {'items':[store._public(i,record) for i in items]}


def apply(store,actor,payload):
    if actor['role']!='admin':raise PermissionError('只有管理员可以保存正式正文')
    locks=store.edit_locks;store.recover()
    key=locks.request_key(actor,payload.get('client_id'),payload.get('request_id'),'canonical')
    with store._db() as conn:
        locks.check_epoch(conn)
        prior=locks.replay(conn,key,payload)
        if prior is not None:return json_store.resolve_note(store.root,payload['note_id'])
        record,items,refs=prepare(store,conn,actor,payload)
        current={**record,'body':deepcopy(record['body'])};last={}
        for item in items:
            if item['kind']=='insert':
                anchor=item['_context']['left'];ids=[n['id'] for n in current['body']['nodes']]
                current['body']['nodes'].insert(ids.index(last.get(anchor,anchor))+1,deepcopy(item['proposed_node']))
                last[anchor]=item['node_id']
            else:current['body']=store._apply_body(conn,item,current)
        current['body'].setdefault('supporting_nodes',[])
        current['body'].setdefault('semantics',{})
        receipt={'kind':'entry-save','request_key':key,'payload':payload,'actor':actor,'refs':refs,
            'pre_body':record['body'],'post_body':current['body'],'pre_revision':record['metadata']['revision'],
            'history_index':len(record['metadata'].get('history',[])),'note_id':payload['note_id'],
            'workspace':str(store.root.resolve())}
        store._write_receipt(receipt)
        result=json_store.edit(store.root,payload['note_id'],{'revision':record['metadata']['revision'],'document':current['body']},public=True)
        locks.remember(conn,key,payload,{'saved':True})
        locks.release_in(conn,actor,payload['client_id'],refs)
    store._clear_receipt()
    return result
