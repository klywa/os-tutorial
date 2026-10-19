"""Fill automatic source/task titles without touching human overlays or media."""
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.codex/skills/wanxiangqi-knowledge/scripts'))
import wxq,workspace

def placeholder(value,bvid):
    return not isinstance(value,str) or not value.strip() or value.strip() in {bvid,bvid+':p1'}

def cached_entries(root,bvid):
    result=[]
    for folder in (Path(root)/'raw/sources').glob(bvid+'_p*'):
        meta=wxq.read_json(folder/'metadata.json',{});part=meta.get('part')
        if type(part) is int and part>0 and meta.get('id')==f'{bvid}:p{part}' and not placeholder(meta.get('title'),bvid):
            result.append({**meta,'playlist_index':part})
    return sorted(result,key=lambda x:x['playlist_index'])

def sync_entries(root,store,bvid,entries,parts=None):
    """Called immediately after metadata discovery, including cache-only reuse."""
    good=sorted([e for e in entries if not placeholder(e.get('title'),bvid)],key=lambda e:e.get('playlist_index') or e.get('part') or 1)
    counts={'videos_updated':0,'sources_updated':0}
    if not good:return counts
    # Never replace the whole JSON blob based on a pre-network snapshot.
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT data FROM videos WHERE bvid=?',(bvid,)).fetchone()
        if row:
            data=json.loads(row[0])
            if placeholder(data.get('title'),bvid) and data.get('title_origin')!='manual':
                data.update(title=good[0].get('video_title') or good[0].get('playlist_title') or good[0]['title'],title_origin='metadata')
                db.execute('UPDATE videos SET data=? WHERE bvid=?',(json.dumps(data,ensure_ascii=False),bvid));counts['videos_updated']=1
    for entry in good:
        part=int(entry.get('playlist_index') or entry.get('part') or 1)
        if parts is not None and part not in parts:continue
        url=f'https://www.bilibili.com/video/{bvid}?p={part}'
        sid=f'{bvid}:p{part}'
        before=next((x for x in wxq.read_json(Path(root)/'knowledge/source-registry.json',[]) if x['id']==sid),{})
        # Validated discovery metadata avoids enumerating all transcript/evidence
        # state simply to update this one source's annotations.
        row=workspace.register_source(root,{'url':url,'title':entry['title'],'notes':''},preserve_annotations=True,wait=True,
            _metadata={'id':sid,'url':url,'title':entry['title']})
        if row.get('title')==entry['title'] and before.get('title')!=row['title']:counts['sources_updated']+=1
    return counts

def sync_cached(root,store,bvid,parts=None):
    return sync_entries(root,store,bvid,cached_entries(root,bvid),parts)

def backfill(root,store,fetcher=None):
    root=Path(root);targets={};registry=wxq.read_json(root/'knowledge/source-registry.json',[])
    with store.db() as db:
        for bvid,text in db.execute('SELECT bvid,data FROM videos'):
            row=json.loads(text)
            if placeholder(row.get('title'),bvid) and row.get('title_origin')!='manual':targets.setdefault(bvid,set())
    for row in registry:
        bvid=row['id'].split(':p')[0]
        if not re.fullmatch(r'BV[A-Za-z0-9]{10}',bvid) or row.get('title_origin')=='manual' or 'title' in row.get('manual_values',{}):continue
        if placeholder(row.get('title'),bvid):targets.setdefault(bvid,set()).add(int(row['id'].rsplit(':p',1)[1]))
    result={'videos_updated':0,'sources_updated':0,'local_videos':0,'fetched_videos':0,'unresolved':[]}
    for bvid,required in targets.items():
        try:
            entries=cached_entries(root,bvid)
            if not entries or required-{e['playlist_index'] for e in entries}:
                if fetcher is None:raise ValueError('本地缺少标题元数据')
                entries=fetcher(bvid);result['fetched_videos']+=1
            else:result['local_videos']+=1
            counts=sync_entries(root,store,bvid,entries)
            for k in counts:result[k]+=counts[k]
            available={int(e.get('playlist_index') or e.get('part') or 1) for e in entries if not placeholder(e.get('title'),bvid)}
            if not available or required-available:raise ValueError('元数据缺少所需分P的有效标题')
        except Exception as exc:result['unresolved'].append({'bvid':bvid,'parts':sorted(required),'error':str(exc)})
    return result

if __name__=='__main__':
    import argparse
    from crawler import Store
    from bilibili import Bilibili
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--fetch-missing',action='store_true');args=parser.parse_args()
    store=Store(args.root)
    client=Bilibili(store.settings()['cookies'],root=args.root) if args.fetch_missing else None
    report=backfill(args.root,store,fetcher=client.entries if client else None)
    target=args.root/'raw/reports/compact-layout-titles/title-backfill.json';target.parent.mkdir(parents=True,exist_ok=True);wxq.atomic_json(target,report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
