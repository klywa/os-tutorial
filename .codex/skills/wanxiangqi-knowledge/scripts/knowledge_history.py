"""Immutable shared history. Ordinary record reads never traverse this archive."""
from pathlib import Path
from copy import deepcopy
import json_store as store
import re

AUDIT_KEYS = {'history', 'history_head', 'history_count'}

def enabled(root):
    return store.read(Path(root)/store.INDEX, {}).get('storage_version') == 2

def folder(nid):
    return 'knowledge-history/' + store.digest(nid)[:32]

def validate_archive(relative, value, nid=None):
    match=re.fullmatch(r'knowledge-history/([0-9a-f]{32})/(audit|versions|migrations)/([0-9a-f]{64})\.json',relative)
    if not match or not isinstance(value,dict): raise ValueError('Invalid history path')
    note=value.get('note_id')
    if not note or (nid is not None and note!=nid) or store.digest(note)[:32]!=match[1] or store.digest(value)!=match[3]:
        raise ValueError('History integrity mismatch')
    return value

def immutable(root, relative, value):
    validate_archive(relative,value)
    path = (Path(root)/relative).resolve()
    base = (Path(root)/'knowledge-history').resolve()
    if not path.is_relative_to(base) or path.suffix != '.json':
        raise ValueError('Invalid history path')
    if path.exists() and store.read(path) != value:
        raise ValueError('Immutable history collision: '+relative)
    store.write_file(path, value)
    if '/versions/' in relative:
        # Optional, reconstructible metadata must never determine save success.
        try:
            entries=_summary_cache(root,value['note_id'])
            entries[path.name]={'signature':_signature(path),'summary':_summary(value)}
            _write_summaries(root,value['note_id'],entries)
        except (OSError,ValueError,KeyError,TypeError):pass

def extract(record):
    """Return archive transaction writes; replace pending history with a linked head."""
    meta=record['metadata']; head=meta.get('history_head'); count=meta.get('history_count',0)
    writes=[]
    for entry in meta.pop('history',[]):
        value={'note_id':meta['id'],'previous':head,'history_index':count,'entry':deepcopy(entry)}
        relative=folder(meta['id'])+'/audit/'+store.digest(value)+'.json'
        writes.append({'path':relative,'value':value})
        head=relative; count+=1
    if head:
        meta.update(history_head=head,history_count=count)
    return writes

def history_entries(root, record):
    """Resolve legacy history order, including stable legacy history_index positions."""
    meta=record['metadata']; result=[]; head=meta.get('history_head'); seen=set()
    pending=store.pending_save(root)
    overlay={e['path']:e['value'] for e in pending.get('archives',[])} if pending else {}
    while head:
        if head in seen or not head.startswith(folder(meta['id'])+'/audit/'):
            raise ValueError('Invalid history chain')
        seen.add(head)
        row=overlay.get(head) or store.read(Path(root)/head)
        if not row or row['note_id']!=meta['id']:
            raise ValueError('Missing history evidence: '+head)
        validate_archive(head,row,meta['id'])
        result.append(deepcopy(row['entry'])); head=row['previous']
    return list(reversed(result))+deepcopy(meta.get('history',[]))

def version_entries(root,nid):
    entries={p.relative_to(root).as_posix():store.read(p) for p in (Path(root)/folder(nid)/'versions').glob('*.json')}
    pending=store.pending_save(root)
    if pending:
        entries.update({e['path']:e['value'] for e in pending.get('archives',[]) if e['path'].startswith(folder(nid)+'/versions/')})
    return [validate_archive(relative,value,nid) for relative,value in entries.items()]


def _signature(path):
    stat=path.stat()
    return [stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size]


def _summary(value):
    return {**{k:v for k,v in value.items() if k!='record'},'snapshot_sha256':store.digest(value['record'])}


def _summary_path(root,nid):
    return Path(root)/'raw/knowledge/history-summaries'/(store.digest(nid)[:32]+'.json')


def _summary_cache(root,nid):
    try:
        data=store.read(_summary_path(root,nid))
        if (isinstance(data,dict) and data.get('format')==1 and data.get('note_id')==nid
                and isinstance(data.get('entries'),dict) and data.get('checksum')==store.digest(data['entries'])
                and all(isinstance(entry,dict) and isinstance(entry.get('signature'),list)
                        and isinstance(entry.get('summary'),dict) and entry['summary'].get('note_id')==nid
                        and all(isinstance(entry['summary'].get(key),str) for key in ('id','at','snapshot_sha256'))
                        for entry in data['entries'].values())):
            return data['entries']
    except (OSError,ValueError,TypeError):pass
    return {}


def _write_summaries(root,nid,entries):
    store.write_file(_summary_path(root,nid),{'format':1,'note_id':nid,'entries':entries,'checksum':store.digest(entries)})


def version_summaries(root,nid):
    """Validate each immutable snapshot once per file signature, not per save.

    Cached metadata lives outside canonical history and is disposable. Pending
    journal overlays are always validated afresh and never persisted in the cache.
    """
    root=Path(root);saved=_summary_cache(root,nid);entries={}
    for path in (root/folder(nid)/'versions').glob('*.json'):
        signature=_signature(path);cached=saved.get(path.name,{})
        if cached.get('signature')==signature and isinstance(cached.get('summary'),dict):
            entries[path.name]=cached
        else:
            value=validate_archive(path.relative_to(root).as_posix(),store.read(path),nid)
            entries[path.name]={'signature':signature,'summary':_summary(value)}
    if entries!=saved:
        try:_write_summaries(root,nid,entries)
        except OSError:pass
    rows={name:value['summary'] for name,value in entries.items()}
    pending=store.pending_save(root)
    for entry in pending.get('archives',[]) if pending else ():
        if entry['path'].startswith(folder(nid)+'/versions/'):
            value=validate_archive(entry['path'],entry['value'],nid)
            rows[Path(entry['path']).name]=_summary(value)
    return sorted(rows.values(),key=lambda r:(r['at'],r['id']),reverse=True)

def version_write(value):
    return {'path':folder(value['note_id'])+'/versions/'+store.digest(value)+'.json','value':value}

def archive_record(record, *, origin='sync', parents=()):
    """Pure plan for a current snapshot, retaining parent heads without traversing them.

    Add writes to journal['archives']; ref names its immutable version object.
    Parents are opaque history-head refs, suitable for B/L/R ancestry union.
    """
    snap=deepcopy(record)
    conflicts=snap['metadata'].pop('conflicts',None)
    if conflicts:
        snap['metadata'].setdefault('history',[]).append({'conflicts':conflicts})
    writes=extract(snap)
    value={'id':store.digest(snap)[:32],'note_id':snap['metadata']['id'],
           'at':'','origin':origin,'body_sha256':store.digest(snap['body']),
           'review_refs':[], 'parents':sorted(set(parents)), 'record':snap}
    write=version_write(value)
    return {'ref':write['path'],'writes':writes+[write]}
