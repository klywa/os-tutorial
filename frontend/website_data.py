"""Export/verify/prepare an offline website dataset. Never fetch external content."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts'),str(ROOT/'frontend')]
import json_store as store
import wxq

FOLDER='website-data'
MATCHES='usage-matches.json'
ENTITY_KEYS={'id','name','category','aliases','properties','description','effect','skills','options','faction','tier','awakened','type','official_url','image_url','thumb_url'}
PRIVATE_KEYS={'cookies','cookie','local_path','absolute_path','file_path','transcript_path','raw_path','history','evidence','sources','source_ids','source_path','credential','password'}


def sanitize(value):
    if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items() if k not in PRIVATE_KEYS and not k.endswith('_path')}
    if isinstance(value,list):return [sanitize(v) for v in value]
    if isinstance(value,str) and (re.match(r'^[A-Za-z]:[\\/]',value) or value.startswith(('\\\\','/Users/','/home/','/opt/','/root/'))):return ''
    return value


def write(path,value):
    store.write_file(path,value)


def export(root=ROOT):
    from workspace import store_lock
    import lineup_usage
    root=Path(root).resolve()
    with store_lock(root):
        if (root/store.JOURNAL).exists():raise ValueError('存在未恢复的保存事务，请先执行 website_data.py recover')
        # Stage the whole export; errors never destroy an existing usable package.
        with tempfile.TemporaryDirectory(prefix='website-export-',dir=root) as temporary:
            staging=Path(temporary)
            for category in wxq.CATEGORIES:
                rows=store.read(root/'entities'/(category+'.json'),[])
                write(staging/'entities'/(category+'.json'),[sanitize({k:v for k,v in row.items() if k in ENTITY_KEYS}) for row in rows])
            import reader_store
            from reference_store import json_cards
            try:cards=json_cards(root) if (root/'knowledge/cards/index.meta.json').exists() else []
            except (KeyError,ValueError):raise ValueError('卡牌资料无效，请先修复再发布')
            public_cards=[]
            for card in cards:
                public_cards.append({**sanitize({k:deepcopy(card[k]) for k in ('id','name','category','aliases','effect','faction','tier','awakened','skills','skills_source','stats','attributes','retrieved_at','version') if k in card}),
                    'sources':[],'skills':sanitize(card.get('skills',[])),'stats':sanitize(card.get('stats',{}))})
            write(staging/'cards.json',public_cards)
            images=store.read(root/'entities/assets/index.json',{})
            manifest={'entities':{},'assets':{}}
            from card_images import image_file
            for eid,kinds in images.get('entities',{}).items():
                for kind in ('thumb','image'):
                    if kind not in kinds:continue
                    try:source=image_file(root,eid,kind,images)
                    except KeyError:continue
                    digest=hashlib.sha256(source.read_bytes()).hexdigest()
                    target=staging/'images'/(digest+'.img');target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(source,target)
                    manifest['entities'].setdefault(eid,{})[kind]=digest
                    manifest['assets'][digest]={'path':f'images/{digest}.img'}
            write(staging/'images.json',manifest)
            write(staging/'usage.json',sanitize(lineup_usage.cached_snapshot(root)))
            keys=('id','name','common_name','heroes','variants','links','excluded','sources')
            # Only source identifiers used by the matching join are retained.
            catalog=[]
            for row in lineup_usage.read_catalog(root):
                item={k:deepcopy(row.get(k,[] if k in ('heroes','variants','links','excluded','sources') else '')) for k in keys}
                item['sources']=[{'raw':{'lineupKey':s.get('raw',{}).get('lineupKey')},
                    'heroes':deepcopy(s.get('heroes') or s.get('raw',{}).get('heroes',[]))} for s in item['sources'] if isinstance(s,dict)]
                catalog.append(item)
            write(staging/'catalog.json',catalog)
            files={p.relative_to(staging).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(staging.rglob('*')) if p.is_file()}
            write(staging/'manifest.json',{'schema_version':1,'files':files})
            destination=root/FOLDER
            destination.mkdir(exist_ok=True)
            # The canonical published assignments are never re-exported over online changes.
            matches=destination/MATCHES
            if not matches.exists():
                personal=store.read(root/'personal/lineup-usage-matches.json',{'schema_version':1,'assignments':{}})
                write(matches,personal)
            old=store.read(destination/'manifest.json',{}).get('files',{})
            for path in old:
                target=(destination/path).resolve()
                if path not in files and target.is_relative_to(destination.resolve()) and target.is_file():target.unlink()
            for path in files:
                target=destination/path;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(staging/path,target)
            shutil.copyfile(staging/'manifest.json',destination/'manifest.json')
    return {'files':len(files),'cards':len(public_cards),'images':len(manifest['assets'])}


def verify_package(root):
    folder=Path(root)/FOLDER
    manifest=store.read(folder/'manifest.json')
    if not isinstance(manifest,dict) or manifest.get('schema_version')!=1 or not isinstance(manifest.get('files'),dict):
        raise ValueError('网站发布包不存在或版本无效，请在本机执行 export')
    for relative,digest in manifest['files'].items():
        path=(folder/relative).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('网站发布包校验失败：'+relative)
    return manifest


def prepare(root=ROOT):
    root=Path(root);manifest=verify_package(root)
    for relative in manifest['files']:
        if relative.startswith('entities/'):
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(root/FOLDER/relative,target)
    snapshot=store.read(root/FOLDER/'usage.json')
    if snapshot is not None:write(root/'raw/lineup-usage/snapshot.json',snapshot)
    return {'prepared':True}


def validate(root=ROOT):
    root=Path(root)
    if (root/store.JOURNAL).exists():raise ValueError('存在未恢复的保存事务，请先执行 website_data.py recover')
    verify_package(root)
    result=store.validate(root)
    if result['errors']:raise ValueError('; '.join(result['errors']))
    # Validate against published entities without requiring previously hydrated caches.
    categories=[row for category in wxq.CATEGORIES for row in store.read(root/FOLDER/'entities'/(category+'.json'),[])]
    from unittest.mock import patch
    with patch.object(wxq,'entities',return_value=categories):
        for record in store.records(root,clone=False):store.validate_semantics(root,record)
    from usage_matches import read
    read(root)
    return {'valid':True,'notes':result['notes']}


def recover(root=ROOT):
    """Replay only a durable manual save, never import automatic online content."""
    from workspace import store_lock
    root=Path(root)
    if not (root/store.JOURNAL).exists():return {'recovered':False}
    with store_lock(root,wait=True):
        if not (root/store.JOURNAL).exists():return {'recovered':False}
        if not store.pending_save(root):raise ValueError('存在自动任务事务，请在本机恢复后重新发布')
        store.recover(root,official=False)
    return {'recovered':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['export','validate','prepare','recover'])
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    try:print(json.dumps(globals()[args.command](args.root),ensure_ascii=False))
    except (OSError,ValueError,KeyError,TypeError) as exc:parser.exit(1,str(exc)+'\n')
