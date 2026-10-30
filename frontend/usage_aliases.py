"""Append confirmed website names to canonical lineup metadata under the store lock."""
from pathlib import Path
import json_store as store
from workspace import store_lock


def sync_locked(root,pairs,manual=None,*,initialize=False,dry_run=False):
    import lineup_usage as usage
    import usage_matches
    root=Path(root)
    if not dry_run:store.recover(root)
    elif (root/store.JOURNAL).exists():raise ValueError('知识事务尚未恢复，请稍后预览别名')
    rows=store.read(root/store.INDEX,{'notes':[]})['notes']
    notes={r['id']:r for r in rows if r['type']=='lineup'}
    manual=usage_matches.read(root) if manual is None else manual
    catalog=usage.read_catalog(root) if pairs else []
    formations=usage.note_formations(root,rows) if pairs else []
    additions={}
    for pair in pairs:
        match=usage_matches.apply(pair,manual,notes)
        if match is None:
            match=usage.formation_fallback(pair,usage.match_pair(pair,catalog,notes),formations,catalog,notes)
        if match['match_status']!='matched':continue
        name=pair.get('source_name','').strip()
        if name:additions.setdefault(match['note_id'],[]).append(name)
    changed=[];details=[]
    for nid in notes if initialize else additions:
        record=store.load_record(root,nid)
        if record is None:raise ValueError('匹配笔记已不存在：'+nid)
        meta=record['metadata'];old=meta.get('aliases',[])
        if not isinstance(old,list) or any(not isinstance(v,str) for v in old):
            raise ValueError('阵容别名必须是字符串列表：'+nid)
        names=list(old);known={name.strip() for name in old}
        for name in additions.get(nid,[]):
            if name not in known:names.append(name);known.add(name)
        if names!=old or 'aliases' not in meta:
            meta['aliases']=names;changed.append(record)
            details.append({'note_id':nid,'title':meta['title'],'added':names[len(old):]})
    if changed and not dry_run:store.save(root,changed,origin='usage_aliases',partial=True)
    return {'changed':len(changed),'added':sum(len(row['added']) for row in details),'notes':details}


def backfill(root,*,dry_run=False):
    import lineup_usage as usage
    with store_lock(root,wait=True):
        snapshot=usage.cached_snapshot(root)
        return sync_locked(root,snapshot['pairs'] if snapshot else [],initialize=True,dry_run=dry_run)
