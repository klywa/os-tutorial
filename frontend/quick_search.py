"""Read-only Bilibili discovery, independent of the acquisition queue."""
from datetime import date
import re


def parameters(keyword, date_from, cursor):
    keyword = keyword.strip()
    if not 1 <= len(keyword) <= 100:
        raise ValueError('请输入 1 至 100 字的搜索关键词')
    if date_from and (not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', date_from)):
        raise ValueError('请输入有效的最早发布日期')
    if date_from:
        try:
            date.fromisoformat(date_from)
        except ValueError:
            raise ValueError('请输入有效的最早发布日期') from None
    match = re.fullmatch(r'([1-9][0-9]{0,8}):([0-9]{1,2})', cursor or '1:0')
    if not match:
        raise ValueError('分页位置无效，请重新搜索')
    return keyword, *map(int, match.groups())


def search(adapter, keyword, date_from, cursor):
    keyword, page, offset = parameters(keyword, date_from, cursor)
    items = []
    seen = set()
    for _ in range(3):
        rows, more = adapter.search_page(keyword, page, 'totalrank')
        for i in range(offset, len(rows)):
            row = rows[i]
            if row['bvid'] in seen or (date_from and (row.get('published') or '') < date_from):
                continue
            seen.add(row['bvid'])
            items.append({k: row.get(k) for k in ('bvid', 'url', 'title', 'author', 'published', 'view_count')})
            if len(items) == 20:
                next_cursor = f'{page}:{i+1}' if i+1 < len(rows) else f'{page+1}:0' if more else None
                return {'items': items, 'next_cursor': next_cursor}
        if not more:
            return {'items': items, 'next_cursor': None}
        page, offset = page + 1, 0
    return {'items': items, 'next_cursor': f'{page}:0'}
