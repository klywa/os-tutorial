"""Versioned official cards, independent of code releases and knowledge saves."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import shutil
import tempfile

import json_store as store
import wxq

CLOCK = '09:00'


class CardVersionChanged(KeyError):
    pass


def home(state):
    return Path(state)/'cards'


def prune_versions(state):
    folder=home(state);current=store.read(folder/'current.json',{}).get('version')
    if not isinstance(current,str) or not re.fullmatch('[0-9a-f]{64}',current) or not (folder/'versions'/current).is_dir():return
    for old in (folder/'versions').iterdir():
        if old.name!=current and re.fullmatch('[0-9a-f]{64}',old.name) and old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)


def verify(folder):
    manifest=store.read(folder/'manifest.json',{})
    files=manifest.get('files',{})
    if not {'cards.json','images.json'} <= files.keys():raise ValueError('卡牌发布包不完整')
    for relative,digest in files.items():
        path=(folder/relative).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('卡牌发布包校验失败')
    rows=store.read(folder/'cards.json',[])
    if not rows or len({c['id'] for c in rows})!=len(rows):raise ValueError('卡牌发布包为空或存在重复标识')
    images=store.read(folder/'images.json',{})
    for kinds in images.get('entities',{}).values():
        for key in kinds.values():
            entry=images.get('assets',{}).get(key,{})
            if entry.get('path') not in files:raise ValueError('卡牌图片不完整')
    return manifest


def dataset_version(folder):
    return store.digest({'cards':store.read(folder/'cards.json',[]),'images':store.read(folder/'images.json',{})})


def publish(workspace, state, *, bundled=False):
    from website_data import export_cards
    folder=home(state);versions=folder/'versions';versions.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.stage-',dir=folder) as temp:
        stage=Path(temp)
        if bundled:
            source=Path(workspace)/'website-data'
            for name in ('cards.json','images.json'):shutil.copyfile(source/name,stage/name)
            images=store.read(stage/'images.json',{})
            for entry in images.get('assets',{}).values():
                relative=entry['path'];path=(source/relative).resolve()
                if not path.is_relative_to(source.resolve()):raise ValueError('图片路径越界')
                target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,target)
        else:export_cards(workspace,stage)
        files={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
        manifest={'schema_version':1,'files':files}
        store.write_file(stage/'manifest.json',manifest)
        verify(stage)
        version=dataset_version(stage)
        destination=versions/version
        if destination.exists():verify(destination)
        else:stage.rename(destination)
        # Rename moved the TemporaryDirectory; recreating it lets its cleanup be harmless.
        stage.mkdir(exist_ok=True)
        wxq.atomic_json(folder/'current.json',{'version':version})
    prune_versions(state)
    return version


def resolve(root,state,version=None):
    folder=home(state)
    current=store.read(folder/'current.json',{}).get('version')
    if current and version and version!=current and re.fullmatch('[0-9a-f]{64}',version):
        raise CardVersionChanged('卡牌资料已更新，请重新载入')
    wanted=version or current
    if wanted:
        if not re.fullmatch('[0-9a-f]{64}',wanted):raise KeyError('卡牌版本不存在')
        target=folder/'versions'/wanted
        if target.is_dir():return target,wanted
        # A release-bundled version can still be requested before daily bootstrap.
    fallback=Path(root)/'website-data'
    digest=dataset_version(fallback)
    if version and version!=digest:raise KeyError('卡牌版本已过期，请刷新卡牌库')
    if current and not version:raise ValueError('已发布卡牌版本不可用')
    return fallback,digest


def status(root,state):
    import official_sync
    from processing_lock import file_lock
    from workspace import Busy
    raw=store.read(home(state)/'status.json',{})
    if raw.get('state')=='running':
        try:
            with file_lock(home(state)/'worker.lock'):raw={**raw,'state':'failed'}
        except Busy:pass
    worker=official_sync.status(home(state)/'workspace',CLOCK)
    _,version=resolve(root,state)
    value={k:raw.get(k,worker.get(k)) for k in ('state','last_check')}
    value['last_success']=raw.get('last_success')
    value.update(version=version,next_check=worker['next_check'])
    if value['state']=='failed' and not worker.get('retry_at'):
        now=datetime.now(timezone.utc)
        value['next_check']=(now.replace(second=0,microsecond=0)+timedelta(minutes=5-now.minute%5)).isoformat()
    value['error']='官网同步暂未完成，正在保留上次成功数据并自动重试。' if value['state']=='failed' else None
    return value
