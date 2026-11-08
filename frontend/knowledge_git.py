"""Canonical knowledge integration inside disposable Git candidates only.

Ordinary source files retain Git's normal conflict behavior. Knowledge pairs,
indexes, and immutable archives are integrated as data, never conflict markers.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'.codex/skills/wanxiangqi-knowledge/scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
import json_store as store
import knowledge_history as history

def _git(root,*args,check=True):
    result=subprocess.run(['git','-c','core.longpaths=true','-C',str(root),*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    if check and result.returncode:raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result

def _blob(root,ref,path):
    result=_git(root,'show',ref+':'+path,check=False)
    if result.returncode:
        if path==store.INDEX and ('does not exist' in result.stderr or 'exists on disk, but not in' in result.stderr):return None
        raise ValueError('无法读取知识版本 '+ref+':'+path+'：'+result.stderr.strip())
    return json.loads(result.stdout.lstrip('\ufeff'))

def _tree(root,ref):
    index=_blob(root,ref,store.INDEX)
    if not isinstance(index,dict) or index.get('schema_version')!=6:return None,None
    records={}
    for row in index.get('notes',[]):
        # Enforce identity/path constraints before touching candidate files.
        store.target(root,row['path'])
        record={'body':_blob(root,ref,row['path']),'metadata':_blob(root,ref,store.meta_path(row['path']))}
        store.check_record(record)
        if record['metadata']['id']!=row['id']:raise ValueError('笔记索引身份不一致')
        if store.digest(record['body'])!=record['metadata'].get('body_sha256'):raise ValueError('来源正文与附件不一致')
        records[row['id']]=record
    return index,records

def _immutable_paths(root,ref):
    result=_git(root,'ls-tree','-r','--name-only','-z',ref,'--','knowledge-history','knowledge-sync')
    return [p for p in result.stdout.split('\0') if p]

def _resolve_archive_conflicts(root,unmerged):
    """Resolve serialization-only conflicts after validating both Git stages."""
    import knowledge_conflicts as conflicts
    for relative in sorted(unmerged):
        if not relative.startswith(('knowledge-history/','knowledge-sync/')):continue
        left=_blob(root,':2',relative);right=_blob(root,':3',relative)
        validate=history.validate_archive if relative.startswith('knowledge-history/') else conflicts.validate_event
        validate(relative,left);validate(relative,right)
        if left!=right:raise ValueError('Immutable archive collision: '+relative)
        store.write_file(Path(root)/relative,left)


def _import_archives(root,refs):
    import knowledge_conflicts as conflicts
    for ref in dict.fromkeys(refs):
        for relative in _immutable_paths(root,ref):
            existing=store.read(Path(root)/relative)
            if existing is not None:
                if relative.startswith('knowledge-history/'):history.validate_archive(relative,existing)
                else:conflicts.validate_event(relative,existing)
                continue
            value=_blob(root,ref,relative)
            if relative.startswith('knowledge-history/'):history.immutable(root,relative,value)
            else:conflicts.immutable_event(root,relative,value)

def canonical(root):
    return store.read(Path(root)/store.INDEX,{}).get('schema_version')==6

def pending_ids(root):
    root=Path(root).resolve()
    signature=tuple((p.relative_to(root).as_posix(),p.stat().st_size,p.stat().st_mtime_ns)
                    for p in sorted((root/'knowledge-sync').rglob('*.json')))
    return list(_pending_ids(str(root),signature))

@lru_cache(maxsize=8)
def _pending_ids(root,signature):
    import knowledge_conflicts as conflicts
    return tuple(sorted({value['note_id'] for _,value in conflicts._requests(Path(root))}))

def adopt_events(source,destination):
    """Copy only immutable data; never install candidate code or note bodies."""
    import knowledge_conflicts as conflicts
    import templates_sync
    templates_sync.adopt_events(source,destination)
    for folder in ('knowledge-history','knowledge-sync'):
        for path in (Path(source)/folder).rglob('*.json'):
            relative=path.relative_to(source).as_posix()
            value=store.read(path)
            current=store.read(Path(destination)/relative)
            if current==value:continue
            if folder=='knowledge-history':history.immutable(destination,relative,value)
            else:conflicts.immutable_event(destination,relative,value)

def _aliases(base,left,right,preferred):
    result={}
    for key in sorted(set(base)|set(left)|set(right)):
        b,l,r=base.get(key),left.get(key),right.get(key)
        if l==r:value=l
        elif l==b:value=r
        elif r==b:value=l
        else:
            # Rebinding legacy identities is not an ordinary JSON conflict.
            raise ValueError('同一旧笔记标识指向不同身份，需要先核对：'+key)
        if value is not None:result[key]=value
    return result

def _meaning(record):
    if record is None:return None
    from knowledge_merge import IGNORED
    return {'body':record['body'],'metadata':{k:v for k,v in record['metadata'].items() if k not in IGNORED}}

def merge_branches(root,left,right,*,preferred='right',origin='local'):
    from workspace import store_lock
    with store_lock(root,wait=True):
        return _merge_branches(root,left,right,preferred=preferred,origin=origin)

def _merge_branches(root,left,right,*,preferred='right',origin='local'):
    """Merge and commit a disposable candidate; return handled=False for legacy data.

    left/right are immutable commit IDs. preferred=left is used by the serving
    site; callers must recheck its live snapshot before activation.
    """
    import knowledge_conflicts as conflicts
    import templates_sync
    from knowledge_merge import merge_record
    root=Path(root)
    if canonical(root) and (left==right or _git(root,'merge-base','--is-ancestor',right,left,check=False).returncode==0):
        return {'handled':True,'conflict_note_ids':pending_ids(root),'new_conflict_note_ids':[],
                'conflict_template_ids':[row['id'] for row in templates_sync.list_conflicts(root)['items']],'head':left}
    li,ls=_tree(root,left);ri,rs=_tree(root,right)
    if li is None or ri is None:return {'handled':False,'conflict_note_ids':[]}
    base_ref=_git(root,'merge-base',left,right).stdout.strip()
    bi,bs=_tree(root,base_ref);bs=bs or {};bi=bi or {}
    known={store.INDEX}
    for records in (bs,ls,rs):
        for record in records.values():
            path=record['metadata']['path'];known.update((path,store.meta_path(path)))
    for ref in (base_ref,left,right):known.update(_immutable_paths(root,ref))
    known.update(templates_sync.known_paths(root,base_ref,left,right))
    merge=_git(root,'merge','--no-edit','--no-commit',right,check=False)
    unmerged={p for p in _git(root,'diff','--name-only','--diff-filter=U','-z').stdout.split('\0') if p}
    code_conflicts=unmerged-known
    if code_conflicts:raise RuntimeError('代码文件仍有冲突，未选择任一方：'+', '.join(sorted(code_conflicts)))
    if merge.returncode and not unmerged:raise RuntimeError(merge.stderr.strip() or merge.stdout.strip())

    _resolve_archive_conflicts(root,unmerged)
    _import_archives(root,(base_ref,left,right))
    # Restore a consistent baseline pair in this disposable directory. The live
    # checkout is never rewritten here, even if its incoming index has markers.
    for record in ls.values():
        path=record['metadata']['path']
        store.write_file(store.target(root,path),record['body'])
        store.write_file(store.target(root,store.meta_path(path),True),record['metadata'])
    store.write_file(root/store.INDEX,li)
    incoming=[];archives=[];new_conflicts=[]
    for nid in sorted(set(bs)|set(ls)|set(rs)):
        b,l,r=bs.get(nid),ls.get(nid),rs.get(nid)
        pending=conflicts._requests(root,nid)
        if l==r:merged=deepcopy(l);issues=[]
        elif l==b:merged=deepcopy(r);issues=[]
        elif r==b:merged=deepcopy(l);issues=[]
        else:
            value=merge_record(b,l,r,preferred=preferred);merged=value['record'];issues=value['conflicts']
        known_versions={store.digest(_meaning(req[side])) for _,req in pending for side in ('base','left','right')}
        unseen=bool(pending) and any(store.digest(_meaning(v)) not in known_versions for v in (l,r))
        if (issues and not pending) or unseen:
            request=conflicts.create_request(b,l,r,preferred=preferred,origin=origin)
            conflicts.write_request(root,request);new_conflicts.append(nid)
        if issues:
            merged=deepcopy(l if preferred=='left' else r)
        # Incoming pending requests must be pinned to the actual serving tree,
        # not assumed to match the latest GitHub body.
        if conflicts.is_blocked(root,nid):merged=deepcopy(l if preferred=='left' else r)
        if _meaning(b)!=_meaning(l) and _meaning(b)!=_meaning(r) and _meaning(l)!=_meaning(r):
            parents=[x['metadata']['history_head'] for x in (b,l,r) if x and x['metadata'].get('history_head')]
            refs=[]
            for record in (b,l,r):
                if record:
                    planned=history.archive_record(record,origin='merge-input',parents=parents)
                    archives.extend(planned['writes']);refs.append(planned['ref'])
            if merged:
                planned=history.archive_record(merged,origin='merge',parents=refs);archives.extend(planned['writes'])
        if merged is not None:incoming.append(merged)
    aliases=_aliases(bi.get('aliases',{}),li.get('aliases',{}),ri.get('aliases',{}),preferred)
    external=max(li.get('storage_version',1),ri.get('storage_version',1))==2
    storage_change=external and li.get('storage_version')!=2
    journal=store.save(root,incoming,aliases=aliases,origin='knowledge_sync',prepare_only=True,
                       **({'storage_version':2} if storage_change else {}))
    if journal:
        journal.setdefault('archives',[]).extend(archives)
        store.write_file(root/store.JOURNAL,journal);store.recover(root)
    else:
        for entry in archives:history.immutable(root,entry['path'],entry['value'])
    template_result=templates_sync.integrate(root,base_ref,left,right,preferred=preferred,origin=origin)
    validation=store.validate(root)
    if validation['errors']:raise ValueError('知识合并校验失败：'+'; '.join(validation['errors']))
    paths=[p for p in ('knowledge','knowledge-history','knowledge-sync','templates') if (root/p).exists()]
    if paths:_git(root,'add','--all','--',*paths)
    staged=_git(root,'diff','--cached','--name-only').stdout.strip()
    merging=_git(root,'rev-parse','-q','--verify','MERGE_HEAD',check=False).returncode==0
    if staged or merging:_git(root,'commit','-m','sync: merge knowledge by stable node identity')
    return {'handled':True,**template_result,'conflict_note_ids':pending_ids(root),
            'new_conflict_note_ids':new_conflicts,'head':_git(root,'rev-parse','HEAD').stdout.strip()}
