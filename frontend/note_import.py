"""Translate an uploaded note into the existing per-entry approval workflow."""
from copy import deepcopy
import uuid

import json_document
import json_store
from edit_locks import EditLocks
from proposals import _authority, _entry, _section, _now
from workspace import Conflict


def unpack(document, note_id):
    if not isinstance(document, dict):
        raise ValueError('请选择知识笔记 JSON 对象')
    if 'notes' in document:
        notes = document['notes']
        if not isinstance(notes, list) or len(notes) != 1 or not isinstance(notes[0], dict) or 'body' not in notes[0]:
            raise ValueError('上传包必须只含当前笔记')
        document = notes[0]
    if 'body' not in document:
        return document, []
    metadata = document.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('笔记附件必须为对象')
    if 'id' in metadata and metadata['id'] != note_id:
        raise ValueError('上传文件属于另一篇笔记')
    claims = metadata.get('claim_annotations', [])
    if not isinstance(claims, list) or any(not isinstance(row, dict) for row in claims):
        raise ValueError('结论证据格式无效')
    return document['body'], claims


def changes(store, record, document, batch):
    note = record['metadata']
    body, claims = unpack(document, note['id'])
    json_document.validate(body)
    original = record['body']
    old = {n['id']: n for n in original['nodes']}
    incoming = {n['id']: n for n in body['nodes']}
    if [n for n in old.values() if n['type']=='heading'] != [n for n in incoming.values() if n['type']=='heading']:
        raise ValueError('章节标题或层级已变化，只能导入段落增改删')
    if [k for k in old if k in incoming] != [k for k in incoming if k in old]:
        raise ValueError('既有段落顺序或章节归属已变化')
    if any(v != original.get(k) for k,v in body.items() if k not in ('schema_version','nodes')
           and not (k == 'leading' and not v and not original.get(k))):
        raise ValueError('上传文件修改了段落以外的内容')
    if any(nid in incoming for nid in {n['id'] for n in original.get('supporting_nodes', [])}):
        raise ValueError('段落 ID 与支撑条目冲突')
    nodes = original['nodes']
    evidence = {}
    for row in claims:
        ref = row.get('text_ref')
        if not isinstance(ref,str):
            raise ValueError('证据需关联有效的段落 ID')
        if ref not in incoming:
            if ref in {n['id'] for n in original.get('supporting_nodes',[])}:
                continue
            raise ValueError(f'找不到证据对应的段落 {ref}')
        if 'evidence' in row and not isinstance(row['evidence'],list):
            raise ValueError('结论证据必须为列表')
        if row.get('evidence'):
            if incoming[ref]['type'] != 'entry':
                raise ValueError('证据只能关联正文段落')
            evidence.setdefault(ref,[]).append(row)

    items = []
    now = _now()
    retained = set(old) & set(incoming)

    def item(kind, node_id, base, proposed, section, left=None, right=None):
        return {'id':uuid.uuid4().hex,'note_id':note['id'],'note_title':note['title'],
                'kind':kind,'node_id':node_id,'base_node':base,'proposed_node':proposed,
                'section_id':section[-1]['id'] if section else None,'after_id':left,'revision':1,
                'status':'pending','created_at':now,'updated_at':now,'reviewed_by':None,
                'result_revision':None,'order':len(items),'_batch':batch,
                '_context':{'section':section,'left':left,'right':right,
                            'left_section':_section(nodes,left),'right_section':_section(nodes,right)}}

    left = None
    next_anchor = iter(k for k in incoming if k in retained)
    right = next(next_anchor,None)
    for ref,node in incoming.items():
        base = old.get(ref)
        if base is not None:
            left,right = ref,next(next_anchor,None)
        if node['type']=='heading':
            continue
        if base is None and left is None:
            raise ValueError('新增段落必须位于章节标题之后')
        node_id = ref if base is not None else 'entry-'+json_store.digest([batch,ref])[:32]
        proposed = {**_entry(node,base),'id':node_id}
        section = _section(nodes,ref if base is not None else left)
        added = base is None
        draft = item('insert' if added else 'update',node_id,base,proposed,section,
                     left if added else None,right if added else None)
        if ref in evidence:
            baseline = json_store.entry_claims(record,node_id)
            rows = evidence[ref]
            if not baseline and len(rows)!=1:
                raise ValueError(f'段落 {ref} 首次添加证据时需要一条结论')
            updates = [{'claim_id':row.get('id') if baseline else node_id+'-claim',
                        'evidence':row['evidence'],'inference':row.get('inference',False)} for row in rows]
            updates,baseline = json_store.prepare_entry_evidence(
                store.root,record,node_id,updates,inserting=added)
            previous = {row['id']:row for row in baseline}
            if proposed != base or any(
                u['evidence'] != previous.get(u['claim_id'],{}).get('evidence',[]) or
                u['inference'] != previous.get(u['claim_id'],{}).get('inference',False) for u in updates
            ):
                draft.update(evidence_changes=updates,_base_claims=baseline)
        if proposed != base or 'evidence_changes' in draft:
            items.append(draft)
    for ref,base in old.items():
        if ref not in incoming:
            deletion = item('delete',ref,base,None,_section(nodes,ref))
            try:
                store._apply_body(None,deletion,record)
            except ValueError as exc:
                deletion['blocked_reason']=str(exc)
            items.append(deletion)
    if len(items)>1000:
        raise ValueError('一次最多上传 1000 条段落修改')
    return items


def request(store,actor,action,data):
    _authority(actor)
    fields = {'note_id','document','client_id','request_id'}
    if action=='submit':
        fields.add('revision')
    if set(data)!=fields or not isinstance(data['note_id'],str):
        raise ValueError('上传参数无效')
    key = EditLocks.request_key(actor,data['client_id'],data['request_id'],'note-import')
    with store._db(write=action=='submit') as conn:
        if action=='submit':
            store._private_ready()
            if replay := EditLocks.replay(conn,key,data):
                return replay
        record = store._note(data['note_id'])
        revision = record['metadata']['revision']
        if action=='submit' and data['revision']!=revision:
            raise Conflict('笔记已更新，请重新预览上传文件')
        items = changes(store,record,data['document'],key)
        if action=='preview':
            return {'revision':revision,'items':[
                {k:deepcopy(v) for k,v in row.items() if k in
                 ('kind','node_id','base_node','proposed_node','section_id','evidence_changes','blocked_reason')}
                for row in items]}
        for item in items:
            item.pop('blocked_reason',None)
            item['author']=actor['username']
            store._put(conn,item)
        result = {'ids':[i['id'] for i in items]}
        EditLocks.remember(conn,key,data,result)
        return result
