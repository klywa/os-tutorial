"""Rebuildable read projections. Canonical note pairs remain the only facts."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import threading
import json_store as store
import json_document
import wxq

FORMAT=1
PROJECTION_FORMAT=2
FOLDER='raw/knowledge/reader'
_building=set()
_guard=threading.Lock()


def signature(path):
    try:
        s=Path(path).stat();return [s.st_mtime_ns,s.st_ctime_ns,s.st_size]
    except FileNotFoundError:return None


def workspace_id(root):
    return store.digest(str(Path(root).resolve()).casefold())[:24]


def index(root):
    pending=store.read(Path(root)/store.JOURNAL)
    return pending['index'] if pending else store.read(Path(root)/store.INDEX,{'notes':[]})


def basic(row):
    return {**row,'summary':True,'schema_version':6,'aliases':[],'entities':[],'core':[],
            'claims':[],'manual_sections':[],'conflicts':[],'related':[]}


def projection(record):
    body=record['body'];m=record['metadata']
    texts={n['id']:n.get('value',n.get('title','')) for n in [*body['nodes'],*body.get('supporting_nodes',[])]}
    texts.update({n['id']+':markdown':json_document.render_node(n).rstrip('\r\n') for n in [*body['nodes'],*body.get('supporting_nodes',[])]})
    keys=('players','core_heroes','compositions','required_factions','ban_conditions','late_variants','player_branches','operation_routes')
    meta=store.resolve_value({k:v for k,v in body.get('semantics',{}).items() if k in keys},texts)
    refs=list(m.get('entities',[]))+meta.get('core_heroes',[])+meta.get('players',[])
    for members in meta.get('compositions',{}).values():refs.extend(x.get('hero','') for x in members)
    fields=[m['title'],json_document.markdown(body),*m.get('aliases',[])]
    for claim in m.get('claim_annotations',[]):
        ref=claim.get('text_ref','')+(':markdown' if claim.get('text_format')=='markdown' else '')
        fields.append(texts.get(ref,''))
    for route in meta.get('operation_routes',[]):fields.extend(route.get(k,'') for k in ('name','condition','advantages','risks','transition'))
    for v in meta.get('late_variants',[]):
        refs.extend(v.get('core_heroes',[]));fields.extend([v.get('name',''),v.get('condition','')])
        for member in v.get('members',[]):
            refs.extend([member.get('hero',''),member.get('replaces','')]);fields.append(member.get('role','')+' '+member.get('replacement_note',''))
    fields.extend(r[8:] for r in refs if r.startswith('pending:'))
    summary=basic({k:m.get(k) for k in ('id','type','title','path','player_id','revision')})
    summary.update({k:deepcopy(m[k]) for k in ('aliases','entities','migration','lineup_links','lineup_ids') if k in m})
    summary['core']=meta.get('core_heroes',[])
    if m['type']=='lineup':
        slim={k:deepcopy(v) for k,v in meta.items() if k not in ('operation_routes',)}
        def member(value):return {**{k:value.get(k,'') for k in ('hero','necessity','replaces')},'role':'','replacement_note':''}
        def bans(values):return [{'faction':b['faction'],'status':b['status'],'reason':''} for b in values]
        slim['compositions']={stage:[member(x) for x in values] for stage,values in slim.get('compositions',{}).items()}
        slim['ban_conditions']=bans(slim.get('ban_conditions',[]))
        if 'player_branches' in slim:slim['player_branches']=[{k:b[k] for k in ('id','player') if k in b} for b in slim['player_branches']]
        for v in slim.get('late_variants',[]):
            for k in list(v):
                if k not in ('id','core_heroes','members','required_factions','ban_conditions','ban_combinations'):v.pop(k)
            v['members']=[member(x) for x in v.get('members',[])]
            v['ban_conditions']=bans(v.get('ban_conditions',[]))
            v['ban_combinations']=[{'factions':x['factions'],'status':x['status'],'reason':''} for x in v.get('ban_combinations',[])]
        slim.setdefault('players',[]);slim.setdefault('core_heroes',[]);slim.setdefault('required_factions',[])
        slim.setdefault('compositions',{'early':[],'middle':[],'late':[]});slim.setdefault('ban_conditions',[])
        summary['meta']=slim
    return {'format':PROJECTION_FORMAT,'revision':m.get('revision'),'summary':summary,'text':' '.join(str(s) for s in fields).lower(),'refs':list(set(refs))}


def write_record(root,record):
    root=Path(root);m=record['metadata'];value=projection(record)
    paths=[root/m['path'],root/store.meta_path(m['path'])]
    value['signature']=[signature(p) for p in paths]
    actual=store.cached_read(paths[1])
    if actual.get('revision')!=m.get('revision'):return
    store.write_file(root/FOLDER/'notes'/(m['id']+'.json'),value)


def cached(root,row):
    path=Path(root)/FOLDER/'notes'/(row['id']+'.json')
    try:
        value=store.cached_read(path)
        if not isinstance(value,dict) or not isinstance(value.get('summary'),dict):return None
        sig=[signature(Path(root)/row['path']),signature(Path(root)/store.meta_path(row['path']))]
        summary=value.get('summary',{})
        if value.get('format')==PROJECTION_FORMAT and value.get('revision')==row.get('revision') and value.get('signature')==sig and summary.get('id')==row['id'] and isinstance(value.get('text'),str) and isinstance(value.get('refs'),list):return value
    except (OSError,ValueError,KeyError):pass
    return None


def rebuild(root):
    root=Path(root)
    for row in index(root)['notes']:
        if cached(root,row):continue
        try:
            record=store.load_record(root,row['id'],clone=False)
            if record:write_record(root,record)
        except (OSError,ValueError,KeyError):continue


def schedule_rebuild(root):
    key=str(Path(root).resolve())
    with _guard:
        if key in _building:return
        _building.add(key)
    def work():
        try:rebuild(root)
        finally:
            with _guard:_building.discard(key)
    thread=threading.Thread(target=work,name='reader-index',daemon=True)
    thread.start();return thread


def catalog(root,schedule=True):
    data=index(root);rows=[];ready=True
    for row in data['notes']:
        value=cached(root,row)
        rows.append(value['summary'] if value else basic(row))
        ready=ready and value is not None
    if not ready and schedule:schedule_rebuild(root)
    entity_stamp=[signature(Path(root)/'entities'/(c+'.json')) for c in wxq.CATEGORIES]
    return {'workspace_id':workspace_id(root),'format':FORMAT,'revision':store.digest([data,PROJECTION_FORMAT,entity_stamp]),
            'ready':ready,'notes':rows}


@lru_cache(maxsize=32)
def _entity_rows(paths):
    rows=[]
    for path,*_ in paths:
        for e in store.read(path,[]):
            rows.append({**{k:e.get(k) for k in ('id','name','category','aliases')},'properties':{'type':e.get('properties',{}).get('type')}})
    return rows


def entities(root):
    paths=tuple((str(Path(root)/'entities'/(c+'.json')),*((signature(Path(root)/'entities'/(c+'.json')) or [0,0,0]))) for c in wxq.CATEGORIES)
    return _entity_rows(paths)


def options(root):
    from workspace import FACTIONS
    factions={x['id']:dict(x) for x in FACTIONS}
    for row in catalog(root)['notes']:
        meta=row.get('meta',{})
        from tactics import faction_references
        for ref in faction_references(meta):
            if ref.startswith('pending:'):factions[ref]={'id':ref,'name':ref[8:]+'（待确认）'}
    return {'entities':entities(root),'factions':list(factions.values()),'sections':wxq.SECTIONS}


def search(root,query):
    cat=catalog(root);wanted=query.strip().lower().split();ids=[]
    labels={e['id']:' '.join([e.get('name') or '',*(e.get('aliases') or [])]).lower() for e in entities(root)}
    for row in index(root)['notes']:
        value=cached(root,row)
        if value:
            text=value['text']+' '+' '.join(labels.get(r,'') for r in value['refs'])
            if all(term in text for term in wanted):ids.append(row['id'])
    return {'ready':cat['ready'],'revision':cat['revision'],'ids':ids}


@lru_cache(maxsize=4)
def _card_summaries(root,fingerprint):
    from reference_store import json_cards
    keys=('id','name','category','aliases','effect','faction','tier','awakened')
    return [{k:c.get(k) for k in keys} for c in json_cards(root)]


def cards(root):
    rows=store.read(Path(root)/'knowledge/cards/index.meta.json',{'cards':[]})['cards']
    fingerprint=tuple((r['path'],tuple(signature(Path(root)/r['path']) or []),tuple(signature(Path(root)/store.meta_path(r['path'])) or [])) for r in rows)
    return _card_summaries(str(Path(root).resolve()),fingerprint)
