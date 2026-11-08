"""Stable identity template merges and immutable record-level conflict events.

Git integration runs only in disposable candidates, under workspace.store_lock.
Resolution takes that lock itself; reads do not initialize the library.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess

_MISSING = object()
_ID = r'[A-Za-z0-9_-]{1,128}'


def allowed_path(path):
    return (path == 'templates/library.meta.json'
            or bool(re.fullmatch(r'templates/(events|groups)/'+_ID+r'\.json', path))
            or bool(re.fullmatch(r'templates/(conflicts|resolutions)/[0-9a-f]{64}\.json', path)))


def fingerprint(root):
    """Read-only release guard including interrupted writes excluded from Git."""
    root=Path(root)
    paths=[p for p in (root/'templates').rglob('*') if p.is_file() and p.suffix not in ('.bak','.tmp')]
    journal=root/'raw/templates/pending.json'
    if journal.exists():paths.append(journal)
    return _digest([(p.relative_to(root).as_posix(),hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(paths)])


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return deepcopy(default)


def _write(path, value):
    import json_store
    json_store.write_file(Path(path), value)


def _git(root, *args, check=True):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    if check and result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip())
    return result


def known_paths(root, *refs):
    paths = set()
    for ref in dict.fromkeys(refs):
        for path in _git(root, 'ls-tree', '-r', '--name-only', '-z', ref, '--', 'templates').stdout.split('\0'):
            if path:
                if not allowed_path(path):
                    raise ValueError('模板包含未知公开路径：'+path)
                paths.add(path)
    return paths


def _tree(root, ref):
    result = {}
    for path in known_paths(root, ref):
        result[path] = json.loads(_git(root, 'show', ref+':'+path).stdout.lstrip('\ufeff'))
    return result


def _effective(tree):
    """Virtual built-ins are ancestors too; a tombstone is an explicit deletion."""
    import templates_schema
    result=deepcopy(tree)
    retired=tree.get('templates/library.meta.json',{}).get('tombstones',{}).get('event',{})
    for event in templates_schema.builtin_events():
        path='templates/events/'+event['id']+'.json'
        if event['id'] not in retired:result.setdefault(path,event)
        else:result.pop(path,None)
    for kind,folder in (('event','events'),('group','groups')):
        for uid in tree.get('templates/library.meta.json',{}).get('tombstones',{}).get(kind,{}):
            result.pop('templates/'+folder+'/'+uid+'.json',None)
    return result


def _clone(value):
    return _MISSING if value is _MISSING else deepcopy(value)


def _merge(base, left, right, path, issues):
    if left == right:
        return _clone(left)
    if left == base:
        return _clone(right)
    if right == base:
        return _clone(left)
    if all(isinstance(v, dict) for v in (base, left, right)):
        result = {}
        for key in sorted(set(base)|set(left)|set(right)):
            value = _merge(base.get(key,_MISSING), left.get(key,_MISSING), right.get(key,_MISSING), path+'/'+key, issues)
            if value is not _MISSING:
                result[key] = value
        return result
    if all(isinstance(v, list) for v in (base, left, right)):
        identity = next((key for key in ('id','key') if all(isinstance(row,dict) and isinstance(row.get(key),str) for rows in (base,left,right) for row in rows)), None)
        if identity:
            maps = [{row[identity]:row for row in rows} for rows in (base,left,right)]
            if any(len(mapping)!=len(rows) for mapping,rows in zip(maps,(base,left,right))):
                issues.append(path+'/duplicate-id');return deepcopy(left)
            bm,lm,rm = maps
            common = set(lm)&set(rm)
            orders = [[row[identity] for row in rows if row[identity] in common] for rows in (base,left,right)]
            if orders[1]!=orders[0] and orders[2]!=orders[0] and orders[1]!=orders[2]:
                issues.append(path+'/order')
            chosen = right if orders[1]==orders[0] else left
            order=[row[identity] for row in chosen]
            for rows in (left,right):
                sequence=[row[identity] for row in rows]
                for position,key in enumerate(sequence):
                    if key in order:continue
                    anchor=next((later for later in sequence[position+1:] if later in order),None)
                    order.insert(order.index(anchor) if anchor is not None else len(order),key)
            result=[]
            for key in order:
                value=_merge(bm.get(key,_MISSING),lm.get(key,_MISSING),rm.get(key,_MISSING),path+'/'+key,issues)
                if value is not _MISSING:result.append(value)
            return result
    issues.append(path or '/')
    return _clone(left)


def merge_record(base, left, right, *, preferred='left'):
    issues=[]
    value=_merge(_MISSING if base is None else base, _MISSING if left is None else left,
                 _MISSING if right is None else right, '', issues)
    if issues:value=left if preferred=='left' else right
    return {'record':None if value is _MISSING else deepcopy(value), 'conflicts':issues}


def _validate_event(path, value):
    if not allowed_path(path) or not isinstance(value,dict) or value.get('schema_version')!=1:
        raise ValueError('模板冲突事件无效：'+path)
    if value.get('kind') not in ('event','group') or not re.fullmatch(_ID,str(value.get('record_id',''))):
        raise ValueError('模板冲突身份无效：'+path)
    payload={k:v for k,v in value.items() if k!='id'}
    if value.get('id')!=_digest(payload) or Path(path).stem!=value['id']:
        raise ValueError('模板冲突事件摘要不一致：'+path)
    if '/conflicts/' in path:
        if not all(k in value for k in ('base','current','incoming','conflicts')):
            raise ValueError('模板冲突版本不完整')
    elif not isinstance(value.get('request_ids'),list) or not all(re.fullmatch(r'[0-9a-f]{64}',str(x)) for x in value['request_ids']):
        raise ValueError('模板冲突解决引用无效')


def _immutable(root, folder, value):
    path='templates/'+folder+'/'+value['id']+'.json'
    _validate_event(path,value)
    target=Path(root)/path
    existing=_read(target)
    if existing is not None and existing!=value:
        raise ValueError('模板不可变事件被修改：'+path)
    if existing is None:_write(target,value)


def _events(root, folder):
    result=[]
    for path in sorted((Path(root)/'templates'/folder).glob('*.json')):
        value=_read(path);_validate_event(path.relative_to(root).as_posix(),value);result.append(value)
    return result


def validate_events(root):
    root=Path(root)
    requests={r['id']:r for r in _events(root,'conflicts')}
    for resolution in _events(root,'resolutions'):
        for rid in resolution['request_ids']:
            request=requests.get(rid)
            if request is None or (request['kind'],request['record_id'])!=(resolution['kind'],resolution['record_id']):
                raise ValueError('模板冲突解决引用不存在或身份不一致')
    for path in (root/'templates').rglob('*'):
        if path.is_file() and path.suffix not in ('.bak','.tmp') and not allowed_path(path.relative_to(root).as_posix()):
            raise ValueError('模板包含未知公开路径：'+path.relative_to(root).as_posix())
    return {'valid':True}


def list_conflicts(root):
    root=Path(root)
    covered={(resolution['kind'],resolution['record_id'],rid) for resolution in _events(root,'resolutions') for rid in resolution['request_ids']}
    grouped={}
    for request in _events(root,'conflicts'):
        key=(request['kind'],request['record_id'])
        if (*key,request['id']) not in covered:grouped.setdefault(key,[]).append(request)
    items=[]
    for (kind,rid),requests in sorted(grouped.items()):
        by_id={r['id']:r for r in requests}
        depths={}
        def depth(request,seen=None):
            if request['id'] in depths:return depths[request['id']]
            seen=set() if seen is None else seen
            if request['id'] in seen:raise ValueError('模板冲突存在循环父版本')
            depths[request['id']]=1+max((depth(by_id[parent],seen|{request['id']}) for parent in request.get('parents',[]) if parent in by_id),default=0)
            return depths[request['id']]
        ordered=sorted(requests,key=lambda request:(depth(request),request['id']))
        latest=ordered[-1];ids=sorted(by_id)
        ancestors={parent for request in requests for parent in request.get('parents',[])}
        frontier=[deepcopy(request) for request in ordered if request['id'] not in ancestors]
        name=next((v.get('name') for v in (latest['current'],latest['incoming'],latest['base']) if isinstance(v,dict)),rid)
        items.append({**deepcopy(latest),'id':_digest([kind,rid]),'name':name,'revision':_digest(ids),'request_ids':ids,'versions':deepcopy(ordered),'frontier':frontier})
    return {'items':items}


def is_blocked(root, kind, record_id):
    return any(row['kind']==kind and row['record_id']==record_id for row in list_conflicts(root)['items'])


def _resolution(conflict, value, actor):
    if isinstance(actor,dict):actor=actor.get('username')
    result={'schema_version':1,'kind':conflict['kind'],'record_id':conflict['record_id'],
            'request_ids':conflict['request_ids'],'revision':conflict['revision'],'value':deepcopy(value),'actor':actor}
    result['id']=_digest(result)
    return result


def _write_resolution(root, conflict, value, actor):
    _immutable(root,'resolutions',_resolution(conflict,value,actor))


def resolve_conflict(root, conflict_id, revision, value, actor, *, entities=None):
    from workspace import Conflict, store_lock
    import templates_store
    root=Path(root)
    with store_lock(root,wait=True):
        templates_store._recover_locked(root)
        item=next((c for c in list_conflicts(root)['items'] if c['id']==conflict_id),None)
        if item is None or item['revision']!=revision:
            raise Conflict('模板冲突版本已变化，请刷新后处理')
        before,meta=templates_store._load(root)
        after=deepcopy(before);key='events' if item['kind']=='event' else 'groups'
        after[key]=[row for row in after[key] if row['id']!=item['record_id']]
        if value is not None:
            if not isinstance(value,dict) or value.get('id')!=item['record_id']:
                raise ValueError('模板冲突解决身份不一致')
            after[key].append(deepcopy(value))
        templates_store.validate(root,after['events'],after['groups'],entities=entities)
        changes=[{'kind':item['kind'],'action':'delete' if value is None else 'put','id':item['record_id'],**({'value':value} if value is not None else {})}]
        receipt=_resolution(item,value,actor)
        templates_store._commit(root,before,after,meta,actor,changes,
                                entities=entities,extra_writes={'templates/resolutions/'+receipt['id']+'.json':receipt})
    return templates_store.snapshot(root)


def adopt_events(source, destination):
    for folder in ('conflicts','resolutions'):
        for value in _events(Path(source),folder):_immutable(destination,folder,value)


def _metadata(trees, *, preferred='left'):
    result={'schema_version':1,'audit':[],'tombstones':{'event':{},'group':{}},'baselines':{},'entity_archive':{},'event_entity_archive':{},'entity_bindings':{}}
    seen=set()
    ordered=[trees[0],trees[2],trees[1]] if preferred=='left' else trees
    for tree in ordered:
        meta=tree.get('templates/library.meta.json',{})
        for entry in meta.get('audit',[]):
            digest=_digest(entry)
            if digest not in seen:result['audit'].append(deepcopy(entry));seen.add(digest)
        for kind in ('event','group'):result['tombstones'][kind].update(deepcopy(meta.get('tombstones',{}).get(kind,{})))
    def leaves(value,depth,prefix=()):
        if depth==0:return {prefix:value}
        return {key:leaf for uid,child in value.items() for key,leaf in leaves(child,depth-1,prefix+(uid,)).items()}
    for field,depth in (('baselines',2),('entity_archive',2),('event_entity_archive',3),('entity_bindings',2)):
        associations=[leaves(tree.get('templates/library.meta.json',{}).get(field,{}),depth) for tree in trees]
        for key in sorted(set().union(*(version.keys() for version in associations))):
            base,left,right=(version.get(key,_MISSING) for version in associations)
            if left==right:value=left
            elif left==base:value=right
            elif right==base:value=left
            elif field=='entity_bindings' and isinstance(left,dict) and isinstance(right,dict) and left.get('selector')==right.get('selector'):
                value={**deepcopy(left),'ids':sorted(set(left.get('ids',[]))|set(right.get('ids',[])))}
            elif field!='baselines':value=left if preferred=='left' else right
            else:
                # Divergent confirmations retain the ancestor so the new
                # change remains visible; archives only retain identity.
                value=base if base is not _MISSING else None
            if value is _MISSING:continue
            target=result[field]
            for uid in key[:-1]:target=target.setdefault(uid,{})
            target[key[-1]]=deepcopy(value)
    return result


def _pin_dependencies(root, trees, meta, preferred):
    """Turn incompatible independent definition/group edits into record conflicts."""
    import templates_schema as schema
    import templates_store as library
    serving=trees[1 if preferred=='left' else 2]
    catalog,notes,retired=library.validation_context(root)
    def group_catalog(group):
        return {**retired.get(group['id'],{}),**catalog}
    def pin(kind,rid):
        path='templates/'+('events' if kind=='event' else 'groups')+'/'+rid+'.json'
        b,l,r=(tree.get(path) for tree in trees)
        value=l if preferred=='left' else r
        if _read(Path(root)/path)==value:return False
        request={'schema_version':1,'kind':kind,'record_id':rid,'base':b,'current':l if preferred=='left' else r,
                 'incoming':r if preferred=='left' else l,'conflicts':['/dependency']}
        request['id']=_digest(request);_immutable(root,'conflicts',request)
        if value is None:(Path(root)/path).unlink(missing_ok=True)
        else:
            _write(Path(root)/path,value);meta['tombstones'][kind].pop(rid,None)
        _write(Path(root)/'templates/library.meta.json',meta)
        return True
    public=library._load(root)[0]
    retired_suggestions=library.event_validation_context(root)
    for event in public['events']:
        try:schema.validate_event(event,catalog,retired_suggestions=retired_suggestions.get(event['id']))
        except ValueError:pin('event',event['id'])
    # Every repair moves a record to its fixed serving version. Revisit all
    # groups after event repair because an earlier group can become invalid.
    while True:
        before=library._load(root)[0]
        for group in before['groups']:
            effective=library._load(root)[0];events={e['id']:e for e in effective['events']}
            group=next((g for g in effective['groups'] if g['id']==group['id']),None)
            if group is None:continue
            try:schema.validate_group(group,events,group_catalog(group),notes);continue
            except ValueError:pass
            current=serving.get('templates/groups/'+group['id']+'.json')
            if current is None:
                pin('group',group['id']);continue
            try:schema.validate_group(current,events,group_catalog(current),notes)
            except ValueError:
                pin('event',current['event_id'])
                effective=library._load(root)[0];events={e['id']:e for e in effective['events']}
                catalog,notes,retired=library.validation_context(root)
                try:schema.validate_group(group,events,group_catalog(group),notes);continue
                except ValueError:pass
            pin('group',group['id'])
        if library._load(root)[0]==before:break
    _write(Path(root)/'templates/library.meta.json',meta)


def integrate(root, base_ref, left_ref, right_ref, *, preferred='left', origin='local', validate=True):
    """Replace handled files after Git merge, preserving the serving side on conflicts."""
    root=Path(root);trees=[_tree(root,ref) for ref in (base_ref,left_ref,right_ref)]
    if not any(trees):return {'conflict_template_ids':[row['id'] for row in list_conflicts(root)['items']]}
    trees=[_effective(tree) for tree in trees]
    paths=set().union(*(tree.keys() for tree in trees))
    for tree in trees:
        for path,value in tree.items():
            if '/conflicts/' in path or '/resolutions/' in path:
                _immutable(root,Path(path).parent.name,value)
    meta=_metadata(trees,preferred=preferred)
    for path in sorted(paths):
        if not re.fullmatch(r'templates/(events|groups)/'+_ID+r'\.json',path):continue
        b,l,r=(tree.get(path) for tree in trees)
        kind='event' if '/events/' in path else 'group';rid=Path(path).stem
        if any(record is not None and record.get('id')!=rid for record in (b,l,r)):
            raise ValueError('模板路径与身份不一致：'+path)
        merged=merge_record(b,l,r,preferred=preferred)
        pending=next((row for row in list_conflicts(root)['items'] if row['kind']==kind and row['record_id']==rid),None)
        known={_digest(row[side]) for row in (pending or {}).get('versions',[]) for side in ('base','current','incoming')}
        unseen=pending and any(_digest(record) not in known for record in (l,r))
        request={'schema_version':1,'kind':kind,'record_id':rid,'base':b,
                 'current':l if preferred=='left' else r,'incoming':r if preferred=='left' else l,
                 'conflicts':merged['conflicts'] or ['/pending-new-version']}
        if unseen:request['parents']=[row['id'] for row in pending['frontier']]
        request['id']=_digest(request)
        same_inputs={req['id'] for req in _events(root,'conflicts') if req['kind']==kind and req['record_id']==rid and req['base']==b and ((req['current']==l and req['incoming']==r) or (req['current']==r and req['incoming']==l))}
        resolutions=[resolution for resolution in _events(root,'resolutions') if resolution['kind']==kind and resolution['record_id']==rid and same_inputs.intersection(resolution['request_ids'])]
        covered=bool(resolutions)
        if not covered and ((merged['conflicts'] and not pending) or unseen):_immutable(root,'conflicts',request)
        if covered:merged['record']=deepcopy(resolutions[-1]['value'])
        if is_blocked(root,kind,rid):merged['record']=deepcopy(l if preferred=='left' else r)
        value=merged['record'];target=root/path
        if value is None:target.unlink(missing_ok=True)
        else:
            _write(target,value)
            meta['tombstones'][kind].pop(rid,None)
    if paths:_write(root/'templates/library.meta.json',meta)
    if validate and paths:
        import templates_store
        _pin_dependencies(root,trees,meta,preferred)
        snapshot=templates_store._load(root)[0]
        templates_store.validate(root,snapshot['events'],snapshot['groups'])
    return {'conflict_template_ids':[row['id'] for row in list_conflicts(root)['items']]}
