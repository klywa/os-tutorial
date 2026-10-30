"""Explicit user choices, kept separate from disposable website snapshots."""
from pathlib import Path
import json_store as store
from workspace import Conflict,store_lock
import wxq

FILE='personal/lineup-usage-matches.json'


def read(root):
    value=store.read(Path(root)/FILE,{'schema_version':1,'assignments':{}})
    if (not isinstance(value,dict) or value.get('schema_version')!=1
            or not isinstance(value.get('assignments'),dict)
            or any(not isinstance(k,str) or not isinstance(v,dict)
                   or not isinstance(v.get('note_id'),str) or not isinstance(v.get('heroes'),list)
                   for k,v in value['assignments'].items())):
        raise ValueError('手动匹配记录无效，请检查个人匹配文件；原记录未改动')
    return value


def pair_revision(pair):
    return store.digest([pair['source_id'],pair['player_id'],sorted(set(pair['heroes']))])


def assignment_error(pair,entry,notes):
    if entry.get('source_id')!=pair['source_id'] or entry.get('player_id')!=pair['player_id'] or set(entry['heroes'])!=set(pair['heroes']):
        return '外网阵容组成已变化，请重新确认指定'
    note=notes.get(entry['note_id'])
    if note is None:return '指定笔记已不存在，请重新选择'
    if note.get('player_id')!=pair['player_id']:return '指定笔记的棋手已变化，请重新选择'
    return ''


def apply(pair,document,notes):
    entry=document['assignments'].get(pair['id'])
    if entry is None:return None
    error=assignment_error(pair,entry,notes)
    manual={'manual_note_id':entry['note_id'],'manual_status':'invalid' if error else 'valid',
            'manual_updated_at':entry.get('updated_at'),'manual_error':error}
    if error:
        return {**manual,'match_status':'ambiguous','candidates':[notes.get(entry['note_id'],{}).get('title') or entry.get('note_title') or entry['note_id']]}
    note=notes[entry['note_id']]
    return {**manual,'match_status':'matched','note_id':note['id'],'note':note,
            'local_name':note['title'].rsplit('-',1)[0],'match_basis':'manual'}


def editor(root):
    import lineup_usage as usage
    root=Path(root)
    with store_lock(root):
        document=read(root);snapshot=usage.cached_snapshot(root)
        rows=store.read(root/store.INDEX,{'notes':[]})['notes']
        formations=usage.note_formations(root,rows)
        by_form={f['id']:f for f in formations}
        heroes={h['id']:h['name'] for h in store.read(root/'entities/heroes.json',[])}
        notes=[{'id':r['id'],'title':r['title'],'player_id':r.get('player_id'),
                'formations':[[heroes.get(h,h) for h in f] for f in by_form.get(r['id'],{}).get('formations',[])]}
               for r in rows if r['type']=='lineup']
        by_id={n['id']:n for n in notes};catalog=usage.read_catalog(root) if snapshot else []
        pairs=[]
        for pair in snapshot['pairs'] if snapshot else []:
            automatic=usage.formation_fallback(pair,usage.match_pair(pair,catalog,by_id),formations,catalog,by_id)
            manual=document['assignments'].get(pair['id'])
            pairs.append({**pair,'pair_revision':pair_revision(pair),
                          'automatic_note_id':automatic.get('note_id'),'candidates':automatic.get('candidates',[]),
                          'manual_note_id':manual['note_id'] if manual else None,
                          'manual_error':assignment_error(pair,manual,by_id) if manual else ''})
        return {'revision':store.digest(document),'pairs':pairs,'notes':notes}


def save(root,payload):
    import lineup_usage as usage
    root=Path(root)
    with store_lock(root,wait=True):
        document=read(root)
        if payload.get('revision')!=store.digest(document):raise Conflict('匹配已被其他操作更新，请刷新匹配列表；当前选择仍保留')
        snapshot=usage.cached_snapshot(root)
        pair=next((p for p in snapshot['pairs'] if p['id']==payload.get('pair_id')),None) if snapshot else None
        if pair is None:raise Conflict('该组合已退出当前榜单，请刷新匹配列表；当前选择仍保留')
        if payload.get('pair_revision')!=pair_revision(pair):raise Conflict('外网阵容组成已更新，请核对后重新保存；当前选择仍保留')
        note_id=payload.get('note_id')
        if note_id is not None:
            if not isinstance(note_id,str) or not note_id:raise ValueError('请选择知识库阵容笔记')
            rows=store.read(root/store.INDEX,{'notes':[]})['notes']
            note=next((r for r in rows if r['id']==note_id and r['type']=='lineup'),None)
            if note is None:raise ValueError('所选阵容笔记已不存在，请刷新匹配列表')
            if note.get('player_id')!=pair['player_id']:raise ValueError('只能指定同一棋手的阵容笔记')
            document['assignments'][pair['id']]={'note_id':note_id,'note_title':note['title'],
                'source_id':pair['source_id'],'source_name':pair['source_name'],'player_id':pair['player_id'],
                'heroes':sorted(set(pair['heroes'])),'updated_at':usage.now().isoformat()}
        else:
            document['assignments'].pop(pair['id'],None)
        from usage_aliases import sync_locked
        try:sync_locked(root,[pair],document)
        except Exception as exc:
            raise ValueError('阵容别名保存失败，匹配尚未保存，请重试：'+str(exc)) from exc
        wxq.atomic_json(root/FILE,document)
        return {'revision':store.digest(document),'assignment':document['assignments'].get(pair['id'])}
