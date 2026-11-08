"""Recoverable, revision-fenced speech templates independent of knowledge notes.

Canonical records and their history/baselines are tracked under templates/.
Only the redo journal lives in raw/. Public reads and import previews never seed
files. Mutations acquire the existing non-reentrant workspace lock exactly once.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import json_store
from workspace import Conflict, store_lock
import templates_schema as schema

META = 'templates/library.meta.json'
JOURNAL = 'raw/templates/pending.json'
FOLDERS = {'event':'events','group':'groups'}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _meta():
    return {'schema_version':1,'audit':[],'tombstones':{'event':{},'group':{}},'baselines':{},'entity_archive':{},'event_entity_archive':{},'entity_bindings':{}}


def _actor(actor):
    if isinstance(actor,dict):actor=actor.get('username')
    return schema.text(actor,'操作者')


def _path(kind, uid):
    schema.identity(uid)
    if kind not in FOLDERS:raise ValueError('未知模板记录类型')
    return f'templates/{FOLDERS[kind]}/{uid}.json'


def _safe_path(root, relative):
    """Recovery journals may only target the canonical template domain."""
    if not isinstance(relative,str):raise ValueError('事务路径无效')
    parts=Path(relative).parts
    allowed=(relative==META or len(parts)==3 and parts[0]=='templates' and parts[1] in (*FOLDERS.values(),'resolutions')
             and parts[2].endswith('.json') and schema.ID.fullmatch(parts[2][:-5]))
    target=(Path(root)/relative).resolve()
    if not allowed or not target.is_relative_to((Path(root)/'templates').resolve()):raise ValueError('模板事务路径无效')
    return target


def _journal(root):
    value=json_store.read(Path(root)/JOURNAL)
    if value is None:return None
    if not isinstance(value,dict) or value.get('schema_version')!=1 or not isinstance(value.get('writes'),dict) or not isinstance(value.get('deletes'),list):raise ValueError('模板恢复事务无效')
    for relative in [*value['writes'],*value['deletes']]:_safe_path(root,relative)
    return value


def _recover_locked(root):
    """Caller owns workspace.store_lock. Idempotent redo, never takes a lock."""
    journal=_journal(root)
    if journal is None:return False
    # Metadata is the final generation marker. The journal remains until every
    # canonical write and deletion is durable and can always be replayed.
    for relative,value in journal['writes'].items():
        if relative!=META:json_store.write_file(_safe_path(root,relative),value)
    for relative in journal['deletes']:_safe_path(root,relative).unlink(missing_ok=True)
    if META in journal['writes']:json_store.write_file(_safe_path(root,META),journal['writes'][META])
    (Path(root)/JOURNAL).unlink(missing_ok=True)
    return True


def recover(root):
    if not (Path(root)/JOURNAL).exists():return False
    with store_lock(root,wait=True):return _recover_locked(root)


def _load(root):
    """Read public arrays and tracked metadata; pending committed after-image wins.

    This helper never writes, so proposal/import previews are strictly read-only.
    Callers already holding the workspace lock may use it directly.
    """
    root=Path(root);journal=_journal(root)
    overlay=journal['writes'] if journal else {};deleted=set(journal['deletes']) if journal else set()
    meta=deepcopy(overlay.get(META,json_store.read(root/META,_meta())))
    if not isinstance(meta,dict) or meta.get('schema_version')!=1:raise ValueError('模板元数据版本无效')
    for key,default in _meta().items():meta.setdefault(key,deepcopy(default))
    public={'schema_version':1,'events':[],'groups':[]}
    for kind,folder in FOLDERS.items():
        values={e['id']:e for e in schema.builtin_events()} if kind=='event' else {}
        for uid in meta['tombstones'].get(kind,{}):values.pop(uid,None)
        relatives={p.relative_to(root).as_posix() for p in (root/'templates'/folder).glob('*.json')}
        relatives.update(p for p in overlay if p.startswith(f'templates/{folder}/'))
        for relative in sorted(relatives-deleted):
            path=_safe_path(root,relative)
            value=deepcopy(overlay[relative]) if relative in overlay else json_store.read(path)
            if not isinstance(value,dict) or value.get('id')!=path.stem:raise ValueError('模板文件身份与路径不一致')
            if value['id'] not in meta['tombstones'].get(kind,{}):values[value['id']]=value
        public[folder]=schema.order_events(values.values()) if kind=='event' else sorted(values.values(),key=lambda row:row['id'])
    # A writer that started after the first journal read owns the complete logical
    # after-image; retry instead of exposing a partially replaced file batch.
    if journal is None and (root/JOURNAL).exists():return _load(root)
    latest=json_store.read(root/META,_meta()) if journal is None else meta
    if isinstance(latest,dict):
        for key,default in _meta().items():latest.setdefault(key,deepcopy(default))
    if journal is None and latest!=meta:return _load(root)
    return public,meta


def _revision(public,meta):
    return json_store.digest({'library':public,'metadata':meta})


def _snapshot(public,meta):
    return {**deepcopy(public),'revision':_revision(public,meta)}


def snapshot(root):
    recover(root)
    return _snapshot(*_load(root))


def _catalog(root, entities=None):
    """Return effective IDs plus authoritative categories (missing != deleted)."""
    root=Path(root);catalog={};complete=set()
    if entities is not None:
        if isinstance(entities,dict) and 'items' in entities:
            schema.fields(entities,{'items','complete_categories'},{'items','complete_categories'})
            rows=entities['items'];categories=entities['complete_categories']
            if not isinstance(categories,list) or any(not isinstance(c,str) or c not in schema.CATEGORIES for c in categories):raise ValueError('实体完整类别列表无效')
            complete=set(categories)
        else:
            rows=list(entities.values()) if isinstance(entities,dict) else entities
            complete=set(schema.CATEGORIES)
        if not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('id'),str) or not isinstance(row.get('category'),str) or row['category'] not in schema.CATEGORIES for row in rows):raise ValueError('实体资料格式无效')
        return {row['id']:deepcopy(row) for row in rows},complete
    for category in sorted(schema.CATEGORIES):
        path=root/'entities'/(category+'.json')
        try:rows=json_store.read(path)
        except (ValueError,OSError):continue
        if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) for r in rows):continue
        complete.add(category)
        for row in rows:catalog[row['id']]={**deepcopy(row),'category':category}
    # The public package supplies the semantic card projection on website copies.
    try:published=json_store.read(root/'website-data/cards.json')
    except (ValueError,OSError):published=None
    if isinstance(published,list) and all(isinstance(r,dict) and isinstance(r.get('id'),str) and r.get('category') in schema.CATEGORIES for r in published):
        categories={r['category'] for r in published}
        for row in published:
            if row['category'] not in complete:catalog[row['id']]=deepcopy(row)
        complete.update(categories)
    return catalog,complete


def _notes(root):
    root=Path(root);index=json_store.read(root/'knowledge/index.meta.json',{'notes':[]})
    if not isinstance(index,dict) or not isinstance(index.get('notes'),list):raise ValueError('阵容笔记索引无效')
    return {row['id']:row for row in index['notes'] if isinstance(row,dict) and isinstance(row.get('id'),str)}


def validation_context(root, *, entities=None, before=None, metadata=None):
    """Catalog, notes and record-scoped previously known references for validators.

    A tracked archive is usable only while the BEFORE record still associates
    that entity. Removing an association revokes it; new records cannot borrow
    another group's archive. Baselines support existing libraries without an
    archive until their next real save.
    """
    if before is None or metadata is None:
        current,meta=_load(root)
        if before is None:before=current
        if metadata is None:metadata=meta
    events={e['id']:e for e in before['events']};retired={}
    for group in before['groups']:
        archived={**metadata.get('baselines',{}).get(group['id'],{}),
                  **metadata.get('entity_archive',{}).get(group['id'],{})}
        known=set(_references(group,events,bindings=metadata.get('entity_bindings',{}).get(group['id'],{})))|{ref['id'] for ref in group.get('related_entities',[])}
        retired[group['id']]={eid:deepcopy(archived[eid]) for eid in known
                              if isinstance(archived.get(eid),dict) and archived[eid].get('id')==eid}
    return _catalog(root,entities)[0],_notes(root),retired


def validate(root, events, groups, *, entities=None, before=None, metadata=None):
    catalog,notes,retired=validation_context(root,entities=entities,before=before,metadata=metadata)
    suggestions=event_validation_context(root,before=before,metadata=metadata)
    return schema.validate_library({'schema_version':1,'events':events,'groups':groups},catalog,notes,
                                   retired_entities=retired,retired_suggestions=suggestions)


def _suggestion_refs(event):
    return {p['id']:{v['id'] for v in p.get('suggestions',[]) if isinstance(v,dict) and isinstance(v.get('id'),str)}
            for p in event['parameters'] if p['type']=='entity'}


def event_validation_context(root, *, before=None, metadata=None):
    """Known retired suggestions scoped to event and stable parameter identity."""
    if before is None or metadata is None:
        current,meta=_load(root)
        if before is None:before=current
        if metadata is None:metadata=meta
    result={}
    for event in before['events']:
        archive=metadata.get('event_entity_archive',{}).get(event['id'],{})
        result[event['id']]={pid:{eid:deepcopy(archive[pid][eid]) for eid in refs
                                 if isinstance(archive.get(pid,{}).get(eid),dict) and archive[pid][eid].get('id')==eid}
                             for pid,refs in _suggestion_refs(event).items()}
    return result


def _project(root, public, revision, meta, changes, entities=None, allow_conflicts=False):
    if revision!=_revision(public,meta):raise Conflict('模板库已更新，请刷新；草稿已保留')
    if not isinstance(changes,list) or len(changes)>5000:raise ValueError('模板修改必须为列表，且不能超过 5000 项')
    maps={kind:{item['id']:deepcopy(item) for item in public[folder]} for kind,folder in FOLDERS.items()}
    seen=set()
    for change in changes:
        schema.fields(change,{'kind','action','id','value'},{'kind','action','id'})
        kind=change['kind'];uid=schema.identity(change['id']);action=change['action']
        if not isinstance(kind,str) or kind not in maps or action not in ('put','delete'):raise ValueError('模板修改类型无效')
        if (kind,uid) in seen:raise ValueError('同一模板记录只能修改一次')
        seen.add((kind,uid))
        if not allow_conflicts:
            try:
                import templates_sync
            except ImportError:templates_sync=None
            if templates_sync is not None and templates_sync.is_blocked(root,kind,uid):raise Conflict('该模板记录存在同步冲突，请先解决')
        if action=='delete':
            if 'value' in change:raise ValueError('删除记录不能携带值')
            maps[kind].pop(uid,None)
        else:
            if not isinstance(change.get('value'),dict) or change['value'].get('id')!=uid:raise ValueError('模板修改身份不一致')
            maps[kind][uid]=deepcopy(change['value'])
    projected=validate(root,[maps['event'][uid] for uid in sorted(maps['event'])],
                       [maps['group'][uid] for uid in sorted(maps['group'])],entities=entities,before=public,metadata=meta)
    return projected


def preview_changes(root,revision,changes,*,entities=None):
    public,meta=_load(root)
    projected=_project(root,public,revision,meta,changes,entities)
    return _snapshot(projected,meta)


_SEMANTIC_KEYS={'id','name','category','aliases','description','effect','skills','options','properties','faction','tier','awakened','stats','attributes','type'}
_NOISE={'history','sources','source','retrieved_at','updated_at','created_at','fetched_at','checked_at','version','timestamp','time','date','image','images','icon','thumb','portrait','portraitV2','bgImg','banShenImg','avatar','image_url','thumb_url','official_url','url','skills_source','roleData','isOwn','ProficiencyLv','championRate'}


def semantic(entity):
    """Stable gameplay semantics, recursively excluding acquisition/media fields."""
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in sorted(value.items()) if k not in _NOISE and not k.endswith(('_at','_url','_path')) and not any(word in k.lower() for word in ('image','icon','thumb','portrait','timestamp'))}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    return clean({key:value for key,value in entity.items() if key in _SEMANTIC_KEYS})


def _bindings(group,events,catalog,previous=None):
    """Selectors track every matching version, retaining known renamed/deleted IDs."""
    from templates_entities import resolve
    previous=previous or {};result={}
    params={p['key']:p for p in events.get(group['event_id'],{}).get('parameters',[])}
    for condition in group['conditions']:
        parameter=params.get(condition['parameter_key'],{});value=condition['value']
        if parameter.get('type')!='entity' or not isinstance(value,dict):continue
        selector={'key':condition['parameter_key'],'categories':sorted(parameter.get('entity_categories',[])),
                  'name':value['name'].strip(),'anchor':value['id']}
        old=previous.get(condition['id'],{})
        ids=set(old.get('ids',[])) if old.get('selector')==selector else set()
        # The canonical anchor is stable even after a catalog rename/removal.
        ids.add(value['id'])
        try:ids.update(row['id'] for row in resolve(value['name'],parameter,catalog))
        except ValueError:pass # Existing retired selectors remain editable and monitorable.
        result[condition['id']]={'selector':selector,'ids':sorted(ids)}
    return result


def _references(group,events,catalog=None,bindings=None):
    refs={}
    player=group['scope'].get('player_id')
    if player:refs[player]=player
    event=events.get(group['event_id'],{})
    params={p['key']:p for p in event.get('parameters',[])}
    for condition in group['conditions']:
        if params.get(condition['parameter_key'],{}).get('type')=='entity' and isinstance(condition['value'],dict):
            refs[condition['value']['id']]=condition['value']['name']
    links=_bindings(group,events,catalog if catalog is not None else {},bindings)
    for link in links.values():
        for eid in link.get('ids',[]):refs.setdefault(eid,link.get('selector',{}).get('name',eid))
    return refs


def entity_link_projection(root,entities=None):
    """Read-only projection; derived fields never contaminate editable records."""
    public,meta=_load(root);catalog,_=_catalog(root,entities);events={e['id']:e for e in public['events']}
    result={};conditions={}
    for group in public['groups']:
        archive={**meta.get('baselines',{}).get(group['id'],{}),**meta.get('entity_archive',{}).get(group['id'],{})}
        bindings=_bindings(group,events,catalog,meta.get('entity_bindings',{}).get(group['id'],{}))
        refs=_references(group,events,bindings=bindings)
        def render(refs):return [{'id':eid,'name':(catalog.get(eid) or archive.get(eid) or {}).get('name',name)} for eid,name in sorted(refs.items())]
        result[group['id']]=render(refs)
        conditions[group['id']]={cid:render({eid:link['selector']['name'] for eid in link['ids']}) for cid,link in bindings.items()}
    return {'entity_links':result,'entity_condition_links':conditions}


def entity_links(root,entities=None):
    return entity_link_projection(root,entities)['entity_links']


def _baseline(meta,before,after,catalog):
    """New links start at today's baseline; existing links retain unreviewed deltas."""
    events={e['id']:e for e in after['events']};existing=meta['baselines']
    retained={};archives={};bindings={}
    old_groups={g['id']:g for g in before['groups']};old_events={e['id']:e for e in before['events']}
    for group in after['groups']:
        old=existing.get(group['id'],{})
        bindings[group['id']]=_bindings(group,events,catalog,meta.get('entity_bindings',{}).get(group['id'],{}))
        prior=_bindings(old_groups[group['id']],old_events,{},meta.get('entity_bindings',{}).get(group['id'],{})) if group['id'] in old_groups else {}
        continuing={eid for cid,link in bindings[group['id']].items() if prior.get(cid,{}).get('selector')==link['selector'] for eid in link['ids']}
        refs=_references(group,events,bindings=bindings[group['id']])
        retained[group['id']]={eid:deepcopy(old[eid]) if eid in old else None if eid in continuing else semantic(catalog[eid]) if eid in catalog else None
                               for eid in refs}
        archived={**old,**meta.get('entity_archive',{}).get(group['id'],{})}
        archives[group['id']]={eid:semantic(catalog[eid]) if eid in catalog else deepcopy(archived[eid])
                               for eid in refs if eid in catalog or isinstance(archived.get(eid),dict)}
        for ref in group.get('related_entities',[]):
            eid=ref['id']
            if eid in catalog:archives[group['id']][eid]=semantic(catalog[eid])
            elif isinstance(archived.get(eid),dict):archives[group['id']][eid]=deepcopy(archived[eid])
    meta['baselines']=retained
    meta['entity_archive']=archives
    meta['entity_bindings']=bindings
    event_archive={}
    for event in after['events']:
        archived=meta.get('event_entity_archive',{}).get(event['id'],{})
        event_archive[event['id']]={pid:{eid:semantic(catalog[eid]) if eid in catalog else deepcopy(archived[pid][eid])
                                        for eid in refs if eid in catalog or isinstance(archived.get(pid,{}).get(eid),dict)}
                                    for pid,refs in _suggestion_refs(event).items()}
    meta['event_entity_archive']=event_archive


def _commit(root,before,after,meta,actor,changes,*,entities=None,extra_writes=None):
    """Caller holds workspace lock. Validate before journal (the commit point)."""
    root=Path(root);actor=_actor(actor)
    after=validate(root,after['events'],after['groups'],entities=entities,before=before,metadata=meta)
    newmeta=deepcopy(meta)
    changed=[]
    for kind,folder in FOLDERS.items():
        old={v['id']:v for v in before[folder]};new={v['id']:v for v in after[folder]}
        for uid in sorted(set(old)|set(new)):
            if old.get(uid)==new.get(uid):continue
            change={'kind':kind,'action':'put' if uid in new else 'delete','id':uid}
            if uid in new:change['value']=new[uid]
            changed.append(change)
            if uid in new:newmeta['tombstones'].setdefault(kind,{}).pop(uid,None)
            else:newmeta['tombstones'].setdefault(kind,{})[uid]={'actor':actor,'at':_now(),'revision':_revision(before,meta)}
    if not changed and newmeta==_load(root)[1] and not extra_writes:return _snapshot(before,meta)
    _baseline(newmeta,before,after,_catalog(root,entities)[0])
    newmeta['audit'].append({'id':uuid.uuid4().hex,'actor':actor,'at':_now(),'changes':deepcopy(changed),
                             'before':deepcopy(before),'after':deepcopy(after)})
    return _persist_locked(root,before,after,newmeta,extra_writes=extra_writes)


def _persist_locked(root,before,after,meta,*,extra_writes=None):
    root=Path(root);writes={META:meta};deletes=[]
    for relative,value in (extra_writes or {}).items():
        if not relative.startswith('templates/resolutions/'):
            raise ValueError('附加模板事务只能写入冲突解决记录')
        _safe_path(root,relative);writes[relative]=deepcopy(value)
    for kind,folder in FOLDERS.items():
        for value in after[folder]:writes[_path(kind,value['id'])]=value
        surviving={v['id'] for v in after[folder]}
        for value in before[folder]:
            if value['id'] not in surviving:deletes.append(_path(kind,value['id']))
    json_store.write_file(root/JOURNAL,{'schema_version':1,'writes':writes,'deletes':deletes})
    _recover_locked(root)
    return _snapshot(after,meta)


def apply(root,revision,changes,actor='admin',*,entities=None,_allow_conflicts=False):
    with store_lock(root,wait=True):
        _recover_locked(root);public,meta=_load(root)
        after=_project(root,public,revision,meta,changes,entities,_allow_conflicts)
        return _commit(root,public,after,meta,actor,changes,entities=entities)


def export_library(root,group_ids=None):
    public=snapshot(root)
    if group_ids is not None:
        if not isinstance(group_ids,list) or any(not isinstance(uid,str) for uid in group_ids):raise ValueError('导出组身份必须为列表')
        wanted=set(group_ids);available={g['id'] for g in public['groups']}
        if wanted-available:raise ValueError('导出组不存在')
        groups=[g for g in public['groups'] if g['id'] in wanted]
        event_ids={g['event_id'] for g in groups};events=[e for e in public['events'] if e['id'] in event_ids]
    else:groups=public['groups'];events=public['events']
    from templates_portable import encode
    return encode({'events':events,'groups':groups})


def preview_import(root,document,*,entities=None):
    public,meta=_load(root);revision=_revision(public,meta)
    result={'revision':revision,'changes':[],'summary':{'created':0,'updated':0,'unchanged':0},'errors':[]}
    try:
        from templates_portable import decode
        catalog,notes,retired=validation_context(root,entities=entities,before=public,metadata=meta)
        doc=decode(document,public,catalog,notes,retired_entities=retired,
                   retired_suggestions=event_validation_context(root,before=public,metadata=meta))
        for kind,folder in FOLDERS.items():
            current={v['id']:v for v in public[folder]}
            for value in doc[folder]:
                old=current.get(value['id'])
                if value==old:result['summary']['unchanged']+=1;continue
                result['summary']['created' if old is None else 'updated']+=1
                result['changes'].append({'kind':kind,'action':'put','id':value['id'],'value':value})
        _project(root,public,revision,meta,result['changes'],entities)
    except (ValueError,TypeError,KeyError) as exc:
        result['errors']=[str(exc)];result['changes']=[]
        result['summary']={'created':0,'updated':0,'unchanged':0}
    return result


def _warnings(public,meta,catalog,complete):
    result=[];events={e['id']:e for e in public['events']}
    for group in public['groups']:
        baseline=meta['baselines'].get(group['id'],{});changes=[];current={}
        for eid,name in _references(group,events,catalog,meta.get('entity_bindings',{}).get(group['id'],{})).items():
            before=baseline.get(eid);entity=catalog.get(eid)
            if entity is None and (not before or before.get('category') not in complete):continue
            after=semantic(entity) if entity else None;current[eid]=after
            if before!=after:changes.append({'id':eid,'name':(entity or before or {}).get('name',name),'before':deepcopy(before),'after':after})
        if changes:
            result.append({'group_id':group['id'],'group_name':group['name'],
                           'revision':json_store.digest({'group':group,'baseline':baseline,'current':current}),
                           'entities':sorted(changes,key=lambda row:row['id'])})
    return result


def warnings(root,entities=None):
    public,meta=_load(root);catalog,complete=_catalog(root,entities)
    return _warnings(public,meta,catalog,complete)


def confirm_warning(root,group_id,revision,actor='admin',*,entities=None):
    actor=_actor(actor)
    with store_lock(root,wait=True):
        _recover_locked(root);public,meta=_load(root);catalog,complete=_catalog(root,entities)
        warning=next((w for w in _warnings(public,meta,catalog,complete) if w['group_id']==group_id),None)
        if warning is None or warning['revision']!=revision:raise Conflict('关联实体或话术组已变化，请重新查看后确认')
        newmeta=deepcopy(meta)
        group=next(g for g in public['groups'] if g['id']==group_id)
        newmeta.setdefault('entity_bindings',{})[group_id]=_bindings(group,{e['id']:e for e in public['events']},catalog,meta.get('entity_bindings',{}).get(group_id,{}))
        for entity in warning['entities']:
            # A schema-1 library created before entity_archive existed still has
            # its last known record in the baseline. Preserve it before acking a
            # deletion, otherwise the next unrelated save could not validate it.
            if isinstance(entity['before'],dict):
                newmeta.setdefault('entity_archive',{}).setdefault(group_id,{}).setdefault(entity['id'],deepcopy(entity['before']))
            newmeta['baselines'][group_id][entity['id']]=deepcopy(entity['after'])
        newmeta['audit'].append({'id':uuid.uuid4().hex,'actor':actor,'at':_now(),'action':'confirm_warning','group_id':group_id,'warning_revision':revision})
        result=_persist_locked(root,public,public,newmeta)
        return {'confirmed':True,'group_id':group_id,'revision':result['revision']}
