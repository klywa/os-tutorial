"""Incremental official image cache; HTTP reads only registered, local assets."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import wxq


def fetch_image(url):
    host = urlsplit(url).hostname or ''
    if urlsplit(url).scheme != 'https' or not (host.endswith('.qq.com') or host.endswith('.gtimg.cn')):
        raise ValueError('仅允许官方HTTPS图片地址')
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://wxq.qq.com/'}), timeout=25) as response:
        data = response.read(12_000_001)
    if len(data) > 12_000_000 or not (data.startswith(b'\x89PNG') or data.startswith(b'\xff\xd8') or data.startswith(b'RIFF') or data.startswith(b'GIF8')):
        raise ValueError('官网返回了无效或过大的图片')
    return data


def sync_images(root, rows=None, prepare_only=False):
    from workspace import store_lock
    root = Path(root)
    rows = wxq.entities(root) if rows is None else rows
    folder = root / 'entities/assets'
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'index.json'
    from processing_lock import file_lock
    with file_lock(folder / '.sync.lock'):
        manifest = wxq.read_json(manifest_path, {'version':1,'entities':{},'assets':{}})
        wanted = {}
        for row in rows:
            p = row.get('properties', {})
            for kind, url in [('thumb', p.get('thumb') or p.get('icon')), ('image', p.get('cardImage') or p.get('image') or p.get('icon'))]:
                if url: wanted.setdefault(url, []).append((row['id'], kind))
        report = {'downloaded':0,'cached':0,'errors':[]}
        def download(url):
            key = hashlib.sha256(url.encode()).hexdigest()
            target = folder / (key + '.img')
            if target.is_file() and target.stat().st_size:
                return url, key, False, None
            try:
                error = None
                for _ in range(3):
                    try:
                        data = fetch_image(url)
                        temp = target.with_suffix('.tmp')
                        temp.write_bytes(data)
                        temp.replace(target)
                        return url, key, True, None
                    except Exception as exc:
                        error = str(exc)
                return url, key, False, error
            except Exception as exc:
                return url, key, False, str(exc)
        with ThreadPoolExecutor(max_workers=6) as pool:
            for url, key, downloaded, error in pool.map(download, wanted):
                if error:
                    report['errors'].append({'url':url,'error':error})
                    continue
                report['downloaded' if downloaded else 'cached'] += 1
                manifest['assets'][key] = {'url':url,'path':key+'.img'}
                for eid, kind in wanted[url]:
                    manifest['entities'].setdefault(eid, {})[kind] = key
        if prepare_only:return {**report,'_manifest':manifest,'_entity_ids':list({eid for pairs in wanted.values() for eid,kind in pairs})}
        # Do not hold the knowledge lock during network downloads.
        with store_lock(root, wait=True):
            wxq.atomic_json(manifest_path, manifest)
        wxq.atomic_json(folder / 'last-sync.json', report)
        return report


def image_file(root, eid, kind, manifest=None):
    if kind not in ['thumb','image']: raise KeyError('图片类型不存在')
    folder = (Path(root) / 'entities/assets').resolve()
    manifest = manifest if manifest is not None else wxq.read_json(folder / 'index.json', {})
    key = manifest.get('entities', {}).get(eid, {}).get(kind)
    entry = manifest.get('assets', {}).get(key, {})
    target = (folder / entry.get('path','__missing__')).resolve()
    if not key or not target.is_relative_to(folder) or not target.is_file():
        raise KeyError('图片尚未缓存')
    return target


def image_fields(root, eid, manifest=None):
    result = {'thumb_url':None,'image_url':None,'image_status':'missing'}
    manifest = manifest if manifest is not None else wxq.read_json(Path(root) / 'entities/assets/index.json', {})
    for kind in ['thumb','image']:
        try:
            target = image_file(root, eid, kind, manifest)
            result[kind+'_url'] = f'/api/cards/{quote(eid, safe="")}/images/{kind}?v={target.stem}'
        except KeyError:
            pass
    if result['thumb_url'] or result['image_url']: result['image_status'] = 'ready'
    return result
