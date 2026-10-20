"""Canonical, unique ownership of player notes across every write entry point."""
from copy import deepcopy
from pathlib import Path

def catalog(root):
    import wxq
    return {e['id']:e for e in wxq.entities(root) if e.get('category')=='players'}

def bind(note, players, previous=None):
    if note.get('type')!='player':
        if note.get('player_id'):raise ValueError('只有棋手笔记可绑定棋手身份')
        return None
    explicit=note.get('player_id')
    if 'player_id' in note and (not isinstance(explicit,str) or not explicit):raise ValueError('棋手身份无效')
    prior=previous.get('player_id') if previous else None
    if prior and explicit and prior!=explicit:raise ValueError('棋手笔记不能改绑其他棋手')
    pid=explicit or prior
    if not pid:
        refs={r for r in note.get('entities',[]) if r in players}
        if len(refs)!=1:raise ValueError('棋手身份缺失或存在歧义，请明确player_id')
        pid=next(iter(refs))
    if not isinstance(pid,str) or pid not in players:raise ValueError('请选择有效的官方棋手')
    title=players[pid]['name']
    old=note.get('title','')
    if old and old!=title:note['aliases']=list(dict.fromkeys([*note.get('aliases',[]),old]))
    note.update(player_id=pid,title=title)
    note['entities']=list(dict.fromkeys([*note.get('entities',[]),pid]))
    return pid

def normalize(root, items):
    import wxq
    players=catalog(root);owners={}
    previous={n['id']:n for n in wxq.read_json(Path(root)/'knowledge/index.json',{'notes':[]})['notes']}
    for n in items:
        old=deepcopy(previous.get(n['id']))
        if old and old.get('type')=='player':bind(old,players)
        pid=bind(n,players,old)
        if pid:
            if pid in owners:raise ValueError('同一棋手只能有一份笔记：'+players[pid]['name'])
            owners[pid]=n['id']
            import workspace
            target='knowledge/players/'+workspace.filename(n['title'])+'.md'
            if (Path(root)/target).exists() and not (old and old.get('path')==target):
                raise ValueError('棋手规范路径已有未管理文件，请先核对：'+target)
            n['path']=target
    return items

def import_notes(root, incoming, existing):
    players=catalog(root);by_id={n['id']:n for n in existing};owners={}
    for old in existing:
        if old['type']=='player':
            copy=deepcopy(old);pid=bind(copy,players)
            if pid in owners:raise ValueError('已有重复棋手笔记，请先合并')
            owners[pid]=old['id']
    result=deepcopy(incoming);remap={}
    for n in result:
        if n['type']!='player':continue
        old=by_id.get(n['id'])
        if old and old['type']!='player':raise ValueError('不能改变已有笔记类型')
        if old:
            old=deepcopy(old);bind(old,players)
        pid=bind(n,players,old)
        canonical=owners.get(pid,n['id']);remap[n['id']]=canonical;n['id']=canonical
        # Caller-supplied legacy paths cannot move or overwrite an existing owner.
        if canonical in by_id:n['path']=by_id[canonical].get('path')
        owners[pid]=canonical
    for n in result:
        for link in n.get('related',[]):link['id']=remap.get(link['id'],link['id'])
        for link in n.get('guide_related',[]):
            if 'note' in link:link['note']=remap.get(link['note'],link['note'])
    return result

def migration_items(root, items):
    import wxq,workspace
    previous={n['id']:deepcopy(n) for n in items};normalize(root,items);obsolete=[];links={}
    for n in items:
        if n['type']!='player':continue
        old=previous[n['id']];target='knowledge/players/'+workspace.filename(n['title'])+'.md'
        if old.get('path')!=target:
            if (Path(root)/target).exists() and not any(x.get('path')==target and x['id']==n['id'] for x in items):
                raise ValueError('新路径已有未管理文件，请先核对：'+target)
            if old.get('path'):
                obsolete.append(old['path']);links[Path(old['path']).name]=Path(target).name
            n['path']=target
        if any(n.get(k)!=old.get(k) for k in ('title','path','player_id','aliases')):
            n.setdefault('history',[]).append({'at':wxq.now(),'origin':'editorial','reason':'棋手唯一身份与纯棋手名迁移',
                'previous':{k:old.get(k) for k in ('title','path','player_id','aliases')}})
    def replace(value):
        if isinstance(value,str):
            for old,new in links.items():value=value.replace('../players/'+old,'../players/'+new).replace('knowledge/players/'+old,'knowledge/players/'+new)
            return value
        if isinstance(value,list):return [replace(x) for x in value]
        if isinstance(value,dict):return {k:(v if k in ('history','evidence','creation') else replace(v)) for k,v in value.items()}
        return value
    return [replace(n) for n in items],obsolete

def migrate(root):
    import workspace,wxq
    from markdown_sync import scan
    with workspace.store_lock(root,wait=True):
        workspace.recover(root)
        if wxq.read_json(Path(root)/'knowledge/pending-commit.json'):raise ValueError('请先恢复待提交知识')
        scan(root,_locked=True)
        items=deepcopy(workspace.notes(root));updated,obsolete=migration_items(root,items)
        if updated!=workspace.notes(root):workspace.persist(root,updated,obsolete)
        return {'players':sum(n['type']=='player' for n in updated),'moved':len(obsolete)}
