"""Bilibili discovery adapter. All site-specific requests live here."""
import html
import re
import time
import threading
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

BJ = timezone(timedelta(hours=8))


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


class Bilibili:
    _rate_lock = threading.Lock()
    _last_request = 0

    def __init__(self, cookies=''):
        import yt_dlp
        from yt_dlp.extractor.bilibili import BiliBiliIE
        self.ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'socket_timeout': 20,
                                  'retries': 2, **({'cookiefile': cookies} if cookies else {})})
        self.ie = BiliBiliIE(self.ydl)
        self.ie.initialize()
        if not self.ie._get_cookies('https://api.bilibili.com').get('buvid3'):
            self.ie._set_cookie('.bilibili.com', 'buvid3', f'{uuid.uuid4()}infoc')
        self.last_request = 0

    def request(self, path, query, signed=False, referer='https://www.bilibili.com/'):
        for attempt in range(3):
            # Parallel scans share one request-start limiter instead of multiplying the rate.
            with Bilibili._rate_lock:
                time.sleep(max(0, 1 - (time.monotonic() - Bilibili._last_request)))
                Bilibili._last_request = time.monotonic()
            try:
                args = self.ie._sign_wbi(dict(query), 'crawler') if signed else query
                result = self.ie._download_json('https://api.bilibili.com/' + path, 'crawler',
                                                query=args, headers={'Referer': referer})
                if result.get('code', 0) != 0:
                    raise RuntimeError(f"B站请求失败（{result.get('code')}）：{result.get('message', '请稍后重试或配置cookies')}")
                return result.get('data') or {}
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def search_page(self, keyword, page, order):
        data = self.request('x/web-interface/search/type', {'search_type': 'video', 'keyword': keyword,
                            'page': page, 'order': order, 'page_size': 20})
        rows = [v for r in data.get('result', []) if (v := normalize(r))]
        return rows, page < int(data.get('numPages') or 1)

    def creator_page(self, uid, page):
        query = {'mid': uid, 'pn': page, 'ps': 30, 'order': 'pubdate', 'keyword': '',
                 'platform': 'web', 'web_location': '333.1387', **self.ie._dm_params}
        data = self.request('x/space/wbi/arc/search', query, True, f'https://space.bilibili.com/{uid}/video')
        rows = [v for r in data.get('list', {}).get('vlist', []) if (v := normalize({**r, 'mid': uid}))]
        return rows, page * 30 < int(data.get('page', {}).get('count') or 0)

    def detail(self, bvid):
        try:
            data = self.request('x/web-interface/view', {'bvid': bvid})
        except Exception:
            # yt-dlp also supports extracting the public watch-page metadata when this API is unavailable.
            info = self.ydl.extract_info(f'https://www.bilibili.com/video/{bvid}', download=False)
            if info.get('entries'):
                info = next(iter(info['entries']))
            return normalize({**info, 'bvid': bvid})
        return normalize({**data, 'view_count': data.get('stat', {}).get('view'),
                          'author': data.get('owner', {}).get('name'), 'mid': data.get('owner', {}).get('mid'),
                          'description': data.get('desc', '')})
