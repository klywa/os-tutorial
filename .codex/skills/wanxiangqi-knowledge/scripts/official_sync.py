"""One recoverable official publication shared by CLI, HTTP and daily workers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import uuid
import wxq
import json_store
import workspace
from processing_lock import file_lock

BJ = timezone(timedelta(hours=8))
STATE = 'raw/official-sync/state.json'
JOURNAL = 'raw/knowledge/pending-official-sync.json'


def semantic(value):
    if isinstance(value, dict):
        return {k:semantic(v) for k,v in value.items() if k not in ('retrieved_at','history','roleData','updated_at','created_at','updateTime','updatedAt','createdAt','update_time')}
    if isinstance(value, list):return [semantic(v) for v in value]
    if isinstance(value,str) and '/CDNResources/' in value:
        parsed=urllib.parse.urlparse(value)
        if parsed.hostname=='video2.osgame.qq.com':
            # Official video URLs rotate signature/expiry path segments; the asset path is stable.
            return 'https://video2.osgame.qq.com/CDNResources/'+parsed.path.split('/CDNResources/',1)[1]
    return value


def window(clock, current=None):
    current = current or datetime.now(BJ)
    hour,minute=map(int,clock.split(':'))
    due=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if due>current:due-=timedelta(days=1)
    return due.isoformat()


def status(root, clock='09:00'):
    value={'enabled':True,'state':'idle',**wxq.read_json(Path(root)/STATE,{})}
    if value['state']=='running':
        try:
            with file_lock(Path(root)/'raw/official-sync/run.lock'):
                value.update(state='failed',interrupted=True,error='上次检查已中断，将在服务恢复后重试。')
        except workspace.Busy:pass
    current=datetime.now(BJ)
    due=datetime.fromisoformat(window(clock,current))
    next_due=due if value.get('window')!=due.isoformat() else due+timedelta(days=1)
    value.update(clock=clock,next_check=value.get('retry_at') or next_due.isoformat())
    return value


def configure(root,payload):
    root=Path(root)
    with workspace.store_lock(root,wait=True):
        value=wxq.read_json(root/STATE,{})
        if 'enabled' in payload:
            if not isinstance(payload['enabled'],bool):raise ValueError('enabled 必须为布尔值')
            value['enabled']=payload['enabled']
        if payload.get('action') in ('run','retry'):
            value.update(requested=True,retry_at=None)
        wxq.atomic_json(root/STATE,value)
    return value


def due(root,clock,current=None):
    current=current or datetime.now(BJ)
    s=status(root,clock)
    if s.get('requested'):return True
    if not s['enabled']:return False
    if s.get('interrupted'):return True
    if s.get('retry_at'):return current>=datetime.fromisoformat(s['retry_at'])
    return s.get('window')!=window(clock,current)


def fetch_bundle(root,run_dir):
    import official
    from official_profiles import merge_values
    buckets={c:{} for c in wxq.CATEGORIES};sources=[];errors=[];identities={}
    def get(url):
        try:body=official.fetch(url)
        except Exception as exc:
            sources.append({'url':url,'at':wxq.now(),'error':str(exc)})
            wxq.atomic_json(run_dir/'sources.json',sources)
            raise
        name=hashlib.sha256(url.encode()).hexdigest()[:16]+'.txt'
        wxq.atomic_text(run_dir/name,body)
        sources.append({'url':url,'path':str((run_dir/name).relative_to(root)).replace('\\','/'),
                        'sha256':hashlib.sha256(body.encode()).hexdigest(),'at':wxq.now()})
        wxq.atomic_json(run_dir/'sources.json',sources)
        return body
    homepage=get(official.OFFICIAL);endpoints=set()
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)',homepage):
        if re.search(r'/(cards|role)\.js$',src):
            body=get(urllib.parse.urljoin(official.OFFICIAL,src))
            endpoints.update(re.findall(r'["\']((?:https?:)?//[^"\'\s]+(?:\.js|\.json))(?:\?[^"\']*)?["\']',body))
    endpoints=sorted({'https:'+u if u.startswith('//') else u for u in endpoints
                      if 'oscard_new_' in u or ('info_article_' in u and '/prod/' in u)})
    if not endpoints:raise ValueError('官网结构变化：未发现数据入口')
    for url in endpoints:
        try:
            data=json.loads(get(url))
            for card in official.walk_cards(data):
                facts={k:official.plain(card[k]) if k=='desc' else card[k] for k in ('name','type','desc') if card.get(k) not in (None,'')}
                prior=identities.get(card['id'],{})
                if any(k in prior and prior[k]!=v for k,v in facts.items()):
                    raise ValueError('官网同 ID 内容冲突：'+str(card['id']))
                identities[card['id']]={**prior,**facts}
            parsed=official.normalize(data,url,wxq.now())
            for c,rows in parsed.items():
                for eid,row in rows.items():buckets[c][eid]=merge_values(buckets[c].get(eid,{}),row)
            unknown=[{'id':c['id'],'type':c['type']} for c in official.walk_cards(data) if c['type'] not in (1,2,5,6,7,9)]
            if unknown:errors.append({'url':url,'unknown_types':unknown})
        except Exception as exc:errors.append({'url':url,'error':str(exc)})
    for c,rows in buckets.items():
        if not rows:errors.append({'missing_category':c})
    for player in buckets['players'].values():
        props=player['properties']
        groups=props.get('talent',[])
        if len(groups)<3 or any(not g.get('cards') for g in groups):errors.append({'missing_player_groups':player['id']})
        if props.get('official_issues'):errors.append({'player':player['id'],'issues':props['official_issues']})
    for eid in buckets['player-skills']:
        for c in buckets:
            if c!='player-skills':buckets[c].pop(eid,None)
    wxq.atomic_json(run_dir/'sources.json',sources)
    # A partial response is retained for diagnosis and never treated as deletion.
    if errors:raise ValueError('官网响应不完整：'+json.dumps(errors,ensure_ascii=False))
    return buckets


def recover(root):
    """Caller holds the store lock. Immutable manifest can be replayed repeatedly."""
    root=Path(root);manifest=wxq.read_json(root/JOURNAL)
    if not manifest:return
    for item in manifest['files']:
        path=(root/item['path']).resolve();stage=(root/item['stage']).resolve()
        if not path.is_relative_to(root.resolve()) or not stage.is_relative_to((root/'raw/official-sync/runs').resolve()):
            raise ValueError('Invalid official transaction path')
        value=json_store.read(stage)
        if json_store.digest(value)!=item['sha256']:raise ValueError('Official stage checksum mismatch')
        json_store.write_file(path,value)
    if manifest.get('notes'):
        json_store.write_file(root/'raw/knowledge/pending-json-save.json',manifest['notes'])
        json_store.recover(root,official=False)
    # Publish success only after all projections, snapshots and notes are restored.
    state={**wxq.read_json(root/STATE,{}),**manifest['success']}
    wxq.atomic_json(root/STATE,state)
    (root/JOURNAL).unlink()


def publish(root,buckets,run_dir,images=None):
    from official_profiles import merge_profile,merge_values
    from acquisition import register_snapshot
    from reference_store import normalize_cards,save_json_cards,json_cards
    root=Path(root);files=[];changed=[];reports=[]
    with workspace.store_lock(root,wait=True):
        workspace.recover(root)
        prior={r['id']:r for c in wxq.CATEGORIES for r in wxq.read_json(root/'entities'/f'{c}.json',[])}
        for old in prior.values():
            if old['category']=='players' and old.get('properties',{}).get('official_cards'):
                new=buckets['players'].get(old['id'])
                absent=set(old['properties']['official_cards'])-set((new or {}).get('properties',{}).get('official_cards',{}))
                if absent:raise ValueError('官网缺少既有棋手关联资料，保留原数据待复核：'+old['id']+' '+','.join(sorted(absent)))
        merged=deepcopy(prior)
        for c,rows in buckets.items():
            for eid,new in rows.items():
                old=prior.get(eid)
                row=deepcopy(new)
                if old:row['aliases']=old.get('aliases',[])
                if old and semantic(row)==semantic(old):row=old
                else:
                    changed.append(eid)
                    if old:row['history']=[*old.get('history',[]),{k:v for k,v in old.items() if k!='history'}]
                merged[eid]=row
        def stage(path,value):
            path=Path(path)
            if json_store.read(path)==value:return
            target=run_dir/f'publish-{len(files):05d}.json'
            json_store.write_file(target,value)
            files.append({'path':path.relative_to(root).as_posix(),'stage':target.relative_to(root).as_posix(),'sha256':json_store.digest(value)})
        for c in wxq.CATEGORIES:
            stage(root/'entities'/f'{c}.json',sorted([r for r in merged.values() if r['category']==c],key=lambda r:r['id']))
        # Immutable source paragraphs authorize only official-bound facts.
        refs=register_snapshot(root,list(merged.values()),locked=True) if changed else {}
        index=json_store.read(root/'knowledge/index.meta.json',{})
        records=index.get('notes',[])
        updates=[]
        state=wxq.read_json(root/STATE,{})
        profile_revisions=dict(state.get('profile_revisions',{}))
        reconciliation=wxq.read_json(root/'raw/reports/official-profile-reconciliation.json',{})
        for player in buckets['players'].values():
            target=next((r for r in records if r.get('player_id')==player['id'] and r.get('type')=='player'),None)
            if target and player['id'] not in changed and profile_revisions.get(target['id'])==target.get('revision'):continue
            record=json_store.load_record(root,target['id']) if target else None
            if not refs:refs=register_snapshot(root,list(merged.values()),locked=True)
            updated,report=merge_profile(record,merged[player['id']],refs,reconciliation)
            reports.append(report)
            if updated!=record:updates.append(updated)
        notes=json_store.save(root,updates,origin='official',partial=True,prepare_only=True) if updates else None
        if notes:
            for row in notes['index']['notes']:
                if row['type']=='player':profile_revisions[row['id']]=row['revision']
        else:
            for row in records:
                if row['type']=='player':profile_revisions[row['id']]=row['revision']
        if changed:
            cards=normalize_cards(list(merged.values()))
            old_cards={c['id']:c for c in json_cards(root)}
            affected={c['id'] for c in cards if any(semantic(c.get(k))!=semantic(old_cards.get(c['id'],{}).get(k)) for k in c if k!='retrieved_at')}
            save_json_cards(root,cards,refs,writer=stage,only_ids=affected)
        if images and images.get('_manifest'):
            assets=wxq.read_json(root/'entities/assets/index.json',{'version':1,'assets':{},'entities':{}})
            assets['assets'].update(images['_manifest'].get('assets',{}))
            for eid in images.get('_entity_ids',[]):
                if eid in images['_manifest'].get('entities',{}):
                    assets['entities'].setdefault(eid,{}).update(images['_manifest']['entities'][eid])
            stage(root/'entities/assets/index.json',assets)
        report={'at':wxq.now(),'changed_ids':changed,'updated_notes':len(updates),'players':reports,
                'counts':{c:len(rows) for c,rows in buckets.items()},'errors':[],'missing':[],'unknown_types':[],
                'review_required':changed if prior else [],'snapshot':run_dir.relative_to(root).as_posix(),
                'images':{k:v for k,v in (images or {}).items() if not k.startswith('_')}}
        report['unresolved_relations']=[{'from':r['id'],'to':link['id']} for r in merged.values() for link in r.get('relations',[]) if link['id'] not in merged]
        wxq.atomic_json(run_dir/'report.json',report)
        stage(root/'raw/official-sync/latest-report.json',report)
        state=wxq.read_json(root/STATE,{})
        manifest={'files':files,'notes':notes,'success':{'state':'success','last_success':wxq.now(),
            'error':None,'retry_at':None,'failures':0,'requested':False,'report':report,
            'window':state.get('attempt_window'),'profile_revisions':profile_revisions}}
        wxq.atomic_json(root/JOURNAL,manifest)
        recover(root)
    return report


def configured_clock(root):
    import sqlite3
    path=Path(root).resolve()/'raw/crawler/queue.sqlite3'
    if path.exists():
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute("SELECT value FROM settings WHERE key='clock'").fetchone()
            if row:return json.loads(row[0])
    return '09:00'


def run(root,clock=None):
    root=Path(root).resolve()
    clock=clock or configured_clock(root)
    with file_lock(root/'raw/official-sync/run.lock'):
        with workspace.store_lock(root,wait=True):
            workspace.recover(root)
            s=wxq.read_json(root/STATE,{})
            s.update(state='running',last_check=wxq.now(),attempt_window=window(clock),requested=False)
            wxq.atomic_json(root/STATE,s)
        run_dir=root/'raw/official-sync/runs'/uuid.uuid4().hex
        try:
            buckets=fetch_bundle(root,run_dir)
            from card_images import sync_images
            prior={r['id']:r for c in wxq.CATEGORIES for r in wxq.read_json(root/'entities'/f'{c}.json',[])}
            assets=wxq.read_json(root/'entities/assets/index.json',{}).get('entities',{})
            image_keys=('icon','thumb','cardImage','image')
            wanted=[r for b in buckets.values() for r in b.values() if r['id'] not in assets or
                    any(r.get('properties',{}).get(k)!=prior.get(r['id'],{}).get('properties',{}).get(k) for k in image_keys)]
            images=sync_images(root,wanted,prepare_only=True) if wanted else None
            if images and images['errors']:raise ValueError('官网图片获取失败：'+json.dumps(images['errors'],ensure_ascii=False))
            return publish(root,buckets,run_dir,images)
        except Exception as exc:
            with workspace.store_lock(root,wait=True):
                # A published manifest remains authoritative after a write interruption.
                if (root/JOURNAL).exists():raise
                s=wxq.read_json(root/STATE,{})
                failures=s.get('failures',0)+1
                s.update(state='failed',error=str(exc),failures=failures,
                    retry_at=(datetime.now(BJ)+timedelta(minutes=min(360,15*2**min(failures-1,5)))).isoformat())
                wxq.atomic_json(root/STATE,s)
            raise
