"""Daily usage snapshots and read-only composition/player joins for the dashboard."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

import json_store as store
from processing_lock import file_lock
from workspace import Busy,store_lock
import wxq

BJ=timezone(timedelta(hours=8))
SNAPSHOT='raw/lineup-usage/snapshot.json'
STATE='raw/lineup-usage/state.json'
LOCK='raw/lineup-usage/run.lock'
MAX_PAIRS=50
SCOPES={'usage_top10':10,'usage_top20':20,'usage_top50':50}


def now():
    return datetime.now(BJ)


def window(current=None):
    current=(current or now()).astimezone(BJ)
    value=current.replace(hour=9,minute=0,second=0,microsecond=0)
    if value>current:value-=timedelta(days=1)
    return value.isoformat()


def cached_snapshot(root):
    try:
        value=store.cached_read(Path(root)/SNAPSHOT)
    except FileNotFoundError:return None
    if not isinstance(value,dict) or not isinstance(value.get('pairs'),list):
        raise ValueError('使用率快照无效，请重新更新使用率')
    return value


def status(root,current=None):
    current=current or now();root=Path(root)
    state=store.read(root/STATE,{})
    snapshot=cached_snapshot(root)
    result={'state':'idle','error':'','retry_at':None,**state,'ready':snapshot is not None,
            'stale':not snapshot or (snapshot.get('window')!=window(current) or snapshot.get('capacity',10)<MAX_PAIRS),
            'last_success':snapshot.get('fetched_at') if snapshot else None,
            'scope':snapshot.get('scope') if snapshot else None,'clock':'09:00',
            'url':'https://www.datawxq.com/lineups'}
    if result['state']=='running':
        try:
            with file_lock(root/LOCK):
                # Completion can race our first state read. Re-read while
                # holding the probe lock before declaring an interrupted run.
                latest=store.read(root/STATE,{})
                if latest.get('state')=='running':
                    result.update(state='failed',error='上次使用率更新已中断，将自动补刷。',retry_at=None,interrupted=True)
                else:
                    result.update(latest)
                    snapshot=cached_snapshot(root)
                    result.update(ready=snapshot is not None,stale=not snapshot or (snapshot.get('window')!=window(current) or snapshot.get('capacity',10)<MAX_PAIRS),
                                  last_success=snapshot.get('fetched_at') if snapshot else None,scope=snapshot.get('scope') if snapshot else None)
        except Busy:pass
    due_at=datetime.fromisoformat(window(current))
    if snapshot and snapshot.get('capacity',10)>=MAX_PAIRS and snapshot.get('window')==due_at.isoformat():due_at+=timedelta(days=1)
    result['next_check']=result.get('retry_at') or due_at.isoformat()
    return result


def due(root,current=None):
    current=current or now();value=status(root,current)
    if value['state']=='running':return False
    if value.get('retry_at') and datetime.fromisoformat(value['retry_at'])>current:return False
    return value['stale'] or bool(value.get('error'))


def rank_pairs(groups,limit=10):
    pairs=[];seen=set()
    for group in groups:
        for player in group['commanders']:
            if player['count']<50:continue
            identity=group['id']+'@'+player['id']
            if identity in seen:raise ValueError('使用率组合身份重复')
            seen.add(identity)
            pairs.append({'id':identity,'source_id':group['id'],'source_name':group['name'],
                          'heroes':group['heroes'],'hero_names':group.get('hero_names',[]),
                          'player_id':player['id'],'player_name':player['name'],'games':player['count'],
                          'usage':group['usage']*player['count']/group['count']})
    pairs.sort(key=lambda row:(-row['usage'],-row['games'],row['id']))
    return [{**row,'rank':i+1} for i,row in enumerate(pairs[:limit])]


def run(root,fetcher=None,current=None):
    root=Path(root);fixed_clock=current is not None;current=current or now()
    try:
        with file_lock(root/LOCK):
            old=store.read(root/STATE,{})
            wxq.atomic_json(root/STATE,{'state':'running','started_at':current.isoformat(),
                                      'last_success':old.get('last_success'),'error':'','retry_at':None})
            try:
                if fetcher is None:
                    from lineup_website import fetch_usage
                    fetcher=lambda root:fetch_usage(root,limit=MAX_PAIRS)
                source=fetcher(root);pairs=rank_pairs(source['groups'],limit=MAX_PAIRS)
                stamp=(current if fixed_clock else now()).isoformat()
                rid=uuid.uuid4().hex
                raw_path=f'raw/lineup-usage/responses/{rid}.json'
                wxq.atomic_json(root/raw_path,source.get('raw',{}))
                bundle={'capacity':MAX_PAIRS,'id':rid,'window':window(current),'fetched_at':stamp,'scope':source['scope'],
                        'url':source.get('url','https://www.datawxq.com/lineups'),'pairs':pairs,'raw_snapshot':raw_path}
                from usage_aliases import sync_locked
                try:
                    with store_lock(root,wait=True):
                        sync_locked(root,pairs)
                        wxq.atomic_json(root/SNAPSHOT,bundle)
                except Exception as exc:
                    raise ValueError('阵容别名同步失败，请重试：'+str(exc)) from exc
                wxq.atomic_json(root/STATE,{'state':'idle','last_success':stamp,'error':'','retry_at':None})
            except Exception as exc:
                failed_at=current if fixed_clock else now()
                wxq.atomic_json(root/STATE,{'state':'failed','last_success':old.get('last_success'),
                                          'error':str(exc),'retry_at':(failed_at+timedelta(minutes=30)).isoformat()})
    except Busy:pass
    return status(root,current if fixed_clock else now())


class UsageWorker:
    """Own executor: network I/O never occupies crawler media/official workers."""
    def __init__(self,root):
        self.root=Path(root);self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lineup-usage')
        self.future=None;self.guard=threading.Lock();self.next_poll=0;self.closed=False

    def request(self):
        with self.guard:
            if self.closed:raise ValueError('使用率后台已关闭')
            if self.future is None or self.future.done():
                self.future=self.pool.submit(run,self.root)
        return {**status(self.root),'state':'queued' if not self.future.done() else status(self.root)['state']}

    def tick(self):
        if self.closed or time.monotonic()<self.next_poll:return
        self.next_poll=time.monotonic()+5
        with self.guard:
            if self.future is not None and not self.future.done():return
        if due(self.root):self.request()

    def close(self):
        with self.guard:self.closed=True
        self.pool.shutdown(wait=True,cancel_futures=True)


def read_catalog(root):
    """Never construct the mutating LineupCatalog/TopicStore on a GET."""
    path=Path(root)/'raw/crawler/topics.sqlite3'
    if not path.exists():return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'topic_lineups' not in tables:return []
        all_rows={r['id']:dict(r) for r in db.execute('SELECT * FROM topic_lineups')};rows=[]
        for original in all_rows.values():
            row=dict(original)
            if not row.get('enabled') or row.get('merged_into') or row.get('deleted_at'):continue
            for key in ('heroes','sources'):row[key]=json.loads(row.get(key) or '[]')
            row['variants']=[];row['links']=[]
            row['excluded']=[r[0] for r in db.execute('SELECT note FROM lineup_note_exclusions WHERE lineup=?',(row['id'],))] if 'lineup_note_exclusions' in tables else []
            if {'lineup_variants','lineup_variant_links'}<=tables:
                row['variants']=[json.loads(v[0]) for v in db.execute('SELECT v.heroes FROM lineup_variants v JOIN lineup_variant_links l ON v.id=l.variant WHERE l.lineup=?',(row['id'],))]
            if 'lineup_notes' in tables:
                for link in db.execute('SELECT note FROM lineup_notes WHERE lineup=?',(row['id'],)):
                    role=db.execute('SELECT role FROM lineup_note_roles WHERE lineup=? AND note=?',(row['id'],link[0])).fetchone() if 'lineup_note_roles' in tables else None
                    row['links'].append({'note':link[0],'role':role[0] if role else 'legacy'})
            rows.append(row)
        active={r['id']:r for r in rows}
        for old in all_rows.values():
            if not old.get('merged_into'):continue
            target=old;seen=set()
            while target.get('merged_into'):
                if target['id'] in seen:raise ValueError('阵容合并重定向存在循环')
                seen.add(target['id']);target=all_rows.get(target['merged_into'])
                if target is None:raise ValueError('阵容合并重定向目标不存在')
            if target['id'] in active:
                active[target['id']]['sources'].extend(json.loads(old.get('sources') or '[]'))
                old_heroes=json.loads(old.get('heroes') or '[]')
                if old_heroes:active[target['id']]['variants'].append(old_heroes)
        return rows


def note_formations(root,rows):
    from reader_store import signature
    root=Path(root).resolve()
    entries=tuple((r['id'],r.get('player_id'),r['title'],r['path'],
                   tuple(signature(store.target(root,r['path'])) or ()),
                   tuple(signature(root/store.meta_path(r['path'])) or ()))
                  for r in rows if r['type']=='lineup')
    return _note_formations(str(root),entries)


@lru_cache(maxsize=8)
def _note_formations(root,entries):
    root=Path(root)
    values=[]
    for nid,player,title,path,_,_ in entries:
        body=store.read(store.target(root,path));semantic=body.get('semantics') or {}
        members=[v for k,v in semantic.get('compositions',{}).items() if k in ('middle','late')]
        members.extend(v.get('members',[]) for v in semantic.get('late_variants',[]))
        formations=[]
        for group in members:
            ids=sorted({m['hero'] for m in group if isinstance(m,dict) and m.get('hero')})
            if ids and ids not in formations:formations.append(ids)
        if formations:
            metadata=root/store.meta_path(path)
            meta=store.read(metadata) if metadata.exists() else {}
            values.append({'id':nid,'player_id':player,'title':title,
                           'name':meta.get('lineup_name') or title.rsplit('-',1)[0],'formations':formations})
    return values


def formation_fallback(pair,match,formations,catalog,notes):
    if match['match_status']!='missing_note':return match
    wanted=set(pair['heroes']);excluded=set()
    for row in catalog:
        if row['id']==match.get('lineup_id'):excluded.update(row['excluded'])
    options=[f for f in formations if f['player_id']==pair['player_id'] and f['id'] not in excluded]
    exact=[f for f in options if any(wanted==set(c) for c in f['formations'])]
    if len(exact)==1:
        f=exact[0]
        return {**match,'match_status':'matched','note_id':f['id'],'note':notes[f['id']],
                'local_name':match.get('local_name') or f['name'],'match_basis':'note_composition'}
    if exact:return {**match,'match_status':'ambiguous','candidates':[f['title'] for f in exact]}
    nearby=[]
    for f in options:
        score=max((len(wanted & set(c))/len(wanted | set(c)) if len(wanted & set(c))>=3 else 0 for c in f['formations']),default=0)
        if score>=.5:nearby.append((score,f['title']))
    if nearby:
        return {**match,'match_status':'ambiguous','candidates':[name for _,name in sorted(nearby,key=lambda n:(-n[0],n[1]))[:3]]}
    return match


def match_pair(pair,catalog,notes):
    wanted=set(pair['heroes']);source_hits=[];changed=[]
    for row in catalog:
        for source in row['sources']:
            raw=source.get('raw',{})
            if raw.get('lineupKey')!=pair['source_id']:continue
            units=source.get('heroes') or raw.get('heroes',[])
            ids={h if isinstance(h,str) else 'card:'+str(h['id']) for h in units}
            (source_hits if ids==wanted else changed).append(row)
    if changed:
        return {'match_status':'ambiguous','candidates':[r.get('common_name') or r['name'] for r in changed]}
    hits=source_hits or [r for r in catalog if wanted==set(r['heroes']) or any(wanted==set(v) for v in r['variants'])]
    hits=list({r['id']:r for r in hits}.values())
    if len(hits)>1:return {'match_status':'ambiguous','candidates':[r.get('common_name') or r['name'] for r in hits]}
    if not hits:return {'match_status':'missing_note','candidates':[]}
    row=hits[0];local={'lineup_id':row['id'],'local_name':row.get('common_name') or row['name']}
    linked=[(notes[link['note']],link['role']) for link in row['links'] if link['note'] in notes and notes[link['note']].get('player_id')==pair['player_id']]
    primary=[n for n,role in linked if role=='primary'];candidates=primary or [n for n,_ in linked]
    candidates=list({n['id']:n for n in candidates}.values())
    if len(candidates)>1:return {**local,'match_status':'ambiguous','candidates':[n['title'] for n in candidates]}
    if not candidates:return {**local,'match_status':'missing_note','candidates':[]}
    return {**local,'match_status':'matched','note_id':candidates[0]['id'],'note':candidates[0]}


def project(root,base,scope='usage_top10'):
    import dashboard
    import usage_matches
    root=Path(root)
    with store_lock(root):
        index=store.read(root/store.INDEX,{'notes':[]})
        rows=list({r['id']:r for r in index['notes'] if r['type'] in ('player','lineup')}.values())
        if store.digest(dashboard.fingerprint(root,rows))!=base['revision']:
            raise Busy('知识库正在更新，请稍后刷新看板')
        value=status(root);source=cached_snapshot(root)
        if source and source.get('capacity',10)<SCOPES[scope]:
            source=None;value.update(ready=False)
        catalog=read_catalog(root) if source else []
        notes={n['id']:n for n in base['notes']};results=[];formations=note_formations(root,rows) if source else []
        manual=usage_matches.read(root)
        for pair in source['pairs'][:SCOPES[scope]] if source else []:
            match=usage_matches.apply(pair,manual,notes)
            if match is None:match=formation_fallback(pair,match_pair(pair,catalog,notes),formations,catalog,notes)
            note=match.pop('note',None)
            fields=deepcopy(note['fields']) if note else {k:{'covered':False,'section':None,'node_id':None} for k,_ in dashboard.FIELDS}
            title=(match.get('local_name') or pair['source_name'])+'－'+pair['player_name']
            results.append({**pair,**match,'title':title,'fields':fields,
                            'covered':note['covered'] if note else 0,
                            'rate':note['rate'] if note else None if match['match_status']=='ambiguous' else 0})
        n=len(results);covered=sum(r['covered'] for r in results)
        value.update(ambiguous=sum(r['match_status']=='ambiguous' for r in results),missing=sum(r['match_status']=='missing_note' for r in results),selected_count=n)
        return {**base,'scope':scope,'usage':value,'notes':results,
                'revision':store.digest([base['revision'],source['id'] if source else None,catalog,formations,value,manual]),
                'summary':{'covered':covered,'total':n*7,'rate':covered/(n*7) if n else None},
                'fields':[{'id':key,'label':label,'covered':sum(r['fields'][key]['covered'] for r in results),
                           'total':n,'rate':sum(r['fields'][key]['covered'] for r in results)/n if n else None}
                          for key,label in dashboard.FIELDS]}
