"""Bilibili discovery adapter. All site-specific requests live here."""
import json
import math
import html
import re
import time
import threading
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

BJ = timezone(timedelta(hours=8))


class BilibiliError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        self.category = 'risk' if code in (-352, -401, 403, 412, 429) else 'login' if code in (-101, -111) else 'unavailable' if code in (-404,404,410) else 'remote'
        hint = '等待解除风控；请在浏览器确认能访问空间，检查本机cookies后重新检查' if self.category == 'risk' else '请检查本机cookies并重新检查' if self.category == 'login' else '视频不可访问，请确认视频状态或账号权限' if self.category == 'unavailable' else '请稍后重试'
        super().__init__(f'B站请求失败（{code}）：{message}。{hint}')


def creator_uid(url):
    parsed = urlsplit(url.strip())
    match = re.fullmatch(r'/(\d+)(?:/.*)?', parsed.path)
    if parsed.scheme != 'https' or parsed.hostname != 'space.bilibili.com' or not match:
        raise ValueError('请输入 https://space.bilibili.com/数字UID 空间地址')
    return match[1]


def normalize(row):
    bvid = row.get('bvid') or re.search(r'BV[\w]+', row.get('webpage_url', '') or row.get('url', ''))
    if hasattr(bvid, 'group'):
        bvid = bvid.group()
    if not bvid or not re.fullmatch(r'BV[a-zA-Z0-9]+', bvid):
        return None
    stamp = row.get('pubdate') or row.get('created') or row.get('timestamp')
    date = datetime.fromtimestamp(float(stamp), BJ).date().isoformat() if stamp else row.get('published')
    if not date and row.get('upload_date'):
        date = datetime.strptime(row['upload_date'], '%Y%m%d').date().isoformat()
    duration = row.get('duration', row.get('length'))
    if isinstance(duration, str) and ':' in duration:
        duration = sum(int(v) * 60 ** i for i, v in enumerate(reversed(duration.split(':'))))
    def number(value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    uid = str(row.get('mid') or row.get('uploader_id') or '')
    return {'bvid': bvid, 'url': f'https://www.bilibili.com/video/{bvid}',
            'title': html.unescape(re.sub('<[^>]*>', '', row.get('title') or '')),
            'description': row.get('description') or '', 'author': row.get('author') or row.get('uploader') or '',
            'uid': uid, 'space_url': f'https://space.bilibili.com/{uid}' if uid.isdigit() else '',
            'published': date, 'duration': number(duration),
            'view_count': number(row.get('view_count', row.get('play')))}


def subtitle_candidates(rows):
    def lang(row):return str(row.get('lan') or '').lower()
    def automatic(row):return lang(row).startswith('ai-') or bool(row.get('ai_type'))
    def language_rank(row):
        code = lang(row).removeprefix('ai-')
        return 1 if any(v in code for v in ['tw', 'hk', 'hant']) else 0
    return sorted([r for r in rows if r.get('subtitle_url') and
                   (lang(r).startswith(('zh', 'ai-zh')))],
                  key=lambda r: (automatic(r), language_rank(r), str(r.get('id', ''))))


def subtitle_segments(raw, duration):
    body = raw.get('body') if isinstance(raw, dict) else None
    if not isinstance(body, list) or not body:raise ValueError('字幕为空或格式无效')
    segments = []; previous = -1
    for row in body:
        if not isinstance(row, dict):raise ValueError('字幕条目格式无效')
        try:a, b = float(row['from']), float(row['to'])
        except (KeyError, TypeError, ValueError):raise ValueError('字幕时间轴无效')
        text = row.get('content')
        if not isinstance(text, str):raise ValueError('字幕正文无效')
        text = html.unescape(re.sub('<[^>]*>', '', text)).strip()
        if not text or not math.isfinite(a) or not math.isfinite(b) or not 0 <= a < b or a < previous or (duration and b > duration + 1):
            raise ValueError('字幕为空或时间轴无效')
        segments.append({'id':len(segments), 'start':a, 'end':b, 'text':text})
        previous = a
    return segments


class Bilibili:
    _rate_lock = threading.Lock()
    _last_request = 0

    def __init__(self, cookies='', refresh=False, root=None):
        from acquisition_network import NetworkGate
        self.gate = NetworkGate(root) if root else None
        self.root = root
        import yt_dlp
        from yt_dlp.extractor.bilibili import BiliBiliIE
        self.request_interval = 3 if refresh else 1
        self.ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'socket_timeout': 20,
                                  'retries': 2, **({'cookiefile': cookies} if cookies else {})})
        self.ie = BiliBiliIE(self.ydl)
        self.ie.initialize()
        # A retry reloads the configured cookies and fetches fresh signing material.
        self.ie._wbi_key_cache = {}
        if refresh or not self.ie._get_cookies('https://api.bilibili.com').get('buvid3'):
            self.refresh_session()
        self.last_request = 0

    def refresh_session(self):
        if getattr(self,'root',None):
            from processing_lock import file_lock
            from pathlib import Path
            folder=Path(self.root)/'raw/crawler'
            folder.mkdir(parents=True,exist_ok=True)
            with file_lock(folder/'session-refresh.lock'):
                cached=folder/'session-cookies.txt'
                configured=self.ydl.params.get('cookiefile')
                import hashlib
                fingerprint=hashlib.sha256((str(Path(configured).resolve()).encode()+Path(configured).read_bytes()) if configured else b'anonymous').hexdigest()
                identity=folder/'session-config.sha256'
                changed=not identity.exists() or identity.read_text(encoding='utf-8')!=fingerprint
                if cached.exists() and time.time()-cached.stat().st_mtime<60 and not changed:
                    self.ydl.cookiejar.load(str(cached),ignore_discard=True,ignore_expires=False)
                    return
                result=self._refresh_session()
                temp=cached.with_suffix('.tmp')
                self.ydl.cookiejar.save(str(temp),ignore_discard=True,ignore_expires=False)
                temp.replace(cached)
                identity.write_text(fingerprint,encoding='utf-8')
                return result
        return self._refresh_session()

    def _refresh_session(self):
        self.ie._wbi_key_cache = {}
        self.ie._download_webpage('https://www.bilibili.com/', 'crawler', fatal=False, note=False)
        session = self.request('x/frontend/finger/spi', {})
        current = self.ie._get_cookies('https://api.bilibili.com')
        for key, field in [('buvid3','b_3'),('buvid4','b_4')]:
            if not current.get(key) and session.get(field):
                self.ie._set_cookie('.bilibili.com',key,session[field])

    def request(self, path, query, signed=False, referer='https://www.bilibili.com/', headers=None):
        scope = 'subtitles' if path.startswith('x/player/') else 'discovery'
        for attempt in range(3):
            if getattr(self,'gate',None):self.gate.wait(scope)
            # Parallel scans share one request-start limiter instead of multiplying the rate.
            with Bilibili._rate_lock:
                time.sleep(max(0, getattr(self, 'request_interval', 1) - (time.monotonic() - Bilibili._last_request)))
                Bilibili._last_request = time.monotonic()
            try:
                args = self.ie._sign_wbi(dict(query), 'crawler') if signed else query
                result = self.ie._download_json('https://api.bilibili.com/' + path, 'crawler',
                                                query=args, headers={'Referer': referer, **(headers or {})})
                if result.get('code', 0) != 0:
                    raise BilibiliError(result.get('code'), result.get('message', '请求失败'))
                return result.get('data') or {}
            except BilibiliError as exc:
                if getattr(self,'gate',None) and exc.category=='risk':self.gate.defer(scope)
                raise
            except Exception as exc:
                status = getattr(getattr(exc, 'cause', None), 'status', None)
                if status in (403,412,429):
                    if getattr(self,'gate',None):self.gate.defer(scope)
                    raise BilibiliError(status, '访问被限制') from exc
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def search_page(self, keyword, page, order):
        data = self.request('x/web-interface/search/type', {'search_type': 'video', 'keyword': keyword,
                            'page': page, 'order': order, 'page_size': 20})
        rows = [v for r in data.get('result', []) if (v := normalize(r))]
        return rows, page < int(data.get('numPages') or 1)

    def entries(self,bvid):
        view=self.request('x/web-interface/view',{'bvid':bvid})
        self._view_cache={bvid:view}
        pages=view.get('pages')
        if not isinstance(pages,list) or not pages:raise BilibiliError(-404,'视频分P不可访问')
        return [{'id':str(p['cid']),'cid':p['cid'],'playlist_index':p['page'],
                 'title':view.get('title',''),'uploader':view.get('owner',{}).get('name',''),
                 'timestamp':view.get('pubdate'),'duration':p.get('duration'),
                 'webpage_url':f'https://www.bilibili.com/video/{bvid}/?p={p["page"]}'} for p in pages]

    def metadata_entries(self,bvid):
        import yt_dlp
        if getattr(self,'gate',None):self.gate.wait('metadata')
        with yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True,'socket_timeout':20,'skip_download':True,
                              'ignore_no_formats_error':True}) as downloader:
            downloader.cookiejar=self.ydl.cookiejar
            info=downloader.extract_info(f'https://www.bilibili.com/video/{bvid}',download=False)
        rows=list(info.get('entries') or [info])
        if not rows or any(not r.get('id') for r in rows):raise ValueError('视频元数据不完整，不能推测分P')
        for i,row in enumerate(rows,1):row['playlist_index']=row.get('playlist_index') or i
        return rows

    def download(self,url,options,attempts=3):
        import yt_dlp
        from pathlib import Path
        for attempt in range(attempts):
            if getattr(self,'gate',None):self.gate.wait('media')
            # The refreshed cookie jar is shared with discovery and subtitles.
            try:
                with yt_dlp.YoutubeDL({**options,'retries':0,'fragment_retries':0}) as downloader:
                    downloader.cookiejar=self.ydl.cookiejar
                    info=downloader.extract_info(url,download=True)
                    return info,Path(downloader.prepare_filename(info))
            except Exception as exc:
                from acquisition_errors import describe_error
                detail=describe_error(exc,'downloading')
                if detail['category']=='risk':
                    if getattr(self,'gate',None):self.gate.defer('media')
                    raise
                if detail['category'] in ['login','unavailable']:raise
                if attempt==attempts-1:raise
                if detail['category']=='formats':
                    if attempt:raise
                    self.refresh_session()
                time.sleep(2**attempt)

    def subtitles(self, bvid, part, duration=None, progress=None):
        if progress:progress({'phase':'checking_subtitles'})
        view = getattr(self,'_view_cache',{}).get(bvid) or self.request('x/web-interface/view', {'bvid':bvid})
        page = next((p for p in view.get('pages', []) if p.get('page') == part), None)
        if not page:raise ValueError('字幕检查未找到对应分P')
        data = self.request('x/player/wbi/v2', {'bvid':bvid, 'cid':page['cid']}, signed=True,
                            referer=f'https://www.bilibili.com/video/{bvid}/?p={part}')
        if data.get('need_login_subtitle'):raise BilibiliError(-101, '字幕需要登录，请检查本机cookies')
        for track in subtitle_candidates(data.get('subtitle', {}).get('subtitles', [])):
            url = track['subtitle_url']
            if url.startswith('//'):url = 'https:' + url
            if progress:progress({'phase':'fetching_subtitles'})
            raw = None
            for attempt in range(3):
                try:
                    with self._rate_lock:
                        time.sleep(max(0, self.request_interval - (time.monotonic() - Bilibili._last_request)))
                        Bilibili._last_request = time.monotonic()
                    if getattr(self,'gate',None):self.gate.wait('subtitle_file')
                    raw = self.ie._download_json(url, bvid, headers={'Referer':'https://www.bilibili.com/'})
                    break
                except Exception as exc:
                    if isinstance(exc, json.JSONDecodeError) or isinstance(getattr(exc, 'cause', None), json.JSONDecodeError):
                        break  # Invalid JSON is a damaged candidate, not a network failure.
                    status = getattr(getattr(exc, 'cause', None), 'status', None)
                    if status in [403,412,429]:
                        if getattr(self,'gate',None):self.gate.defer('subtitle_file')
                        raise BilibiliError(status, '字幕访问被限制') from exc
                    if attempt == 2:raise
                    time.sleep(2 ** attempt)
            try:segments = subtitle_segments(raw, duration or page.get('duration'))
            except ValueError:continue
            return {'language':track['lan'], 'automatic':str(track['lan']).startswith('ai-') or bool(track.get('ai_type')),
                    'url':url, 'raw':raw, 'segments':segments}
        return None

    def creator_page(self, uid, page):
        query = {'mid': uid, 'pn': page, 'ps': 30, 'order': 'pubdate', 'keyword': '',
                 'platform': 'web', 'web_location': '333.1387', 'order_avoided': 'true',
                 'tid': 0, 'special_type': '', 'index': 0, **self.ie._dm_params}
        data = self.request('x/space/wbi/arc/search', query, True, f'https://space.bilibili.com/{uid}/video',
                            {'Origin': 'https://space.bilibili.com', 'Accept-Language': 'en,zh-CN;q=0.9,zh;q=0.8'})
        rows = [v for r in data.get('list', {}).get('vlist', []) if (v := normalize({**r, 'mid': uid}))]
        return rows, page * 30 < int(data.get('page', {}).get('count') or 0)

    def detail(self, bvid):
        try:
            data = self.request('x/web-interface/view', {'bvid': bvid})
        except BilibiliError:
            raise
        except Exception:
            # yt-dlp also supports extracting the public watch-page metadata when this API is unavailable.
            info = self.ydl.extract_info(f'https://www.bilibili.com/video/{bvid}', download=False)
            if info.get('entries'):
                info = next(iter(info['entries']))
            return normalize({**info, 'bvid': bvid})
        return normalize({**data, 'view_count': data.get('stat', {}).get('view'),
                          'author': data.get('owner', {}).get('name'), 'mid': data.get('owner', {}).get('mid'),
                          'description': data.get('desc', '')})
