"""Human source metadata overlays, independent of acquisition task membership."""
import math
import uuid
from datetime import datetime
from pathlib import Path
import wxq
import workspace
from bilibili import BJ, creator_uid

FIELDS={'title','url','author','uid','space_url','published','view_count','duration','collected_at','keywords','batches','notes'}
FIELDS.update({'topic_players','topic_lineups','topic_heroes','topic_cards','ignored'})

def save_metadata(root, sid, payload, store):
    from crawler import source_rows
    root=Path(root)
    with workspace.store_lock(root, wait=True):
        current=next((s for s in source_rows(root,store) if s['id']==sid),None)
        if current is None:raise KeyError('来源不存在')
        if payload.get('revision')!=current['revision']:raise workspace.Conflict('资料已被修改，请刷新后重新编辑；草稿仍保留')
        if set(payload)-FIELDS-{'revision','restore_topics'}:raise ValueError('包含不可编辑的系统字段')
        from topics import catalog, TOPIC_FIELDS
        choices=catalog(root) if set(payload)&set(TOPIC_FIELDS) else {}
        changes={k:v for k,v in payload.items() if k in FIELDS}
        for k,v in list(changes.items()):
            if k=='ignored':
                if not isinstance(v,bool):raise ValueError('忽略状态须为布尔值')
            elif k in TOPIC_FIELDS:
                if not isinstance(v,list) or any(not isinstance(x,str) or x not in {e['id'] for e in choices[k]} for x in v):raise ValueError('主题实体或阵容不在名单中')
                changes[k]=list(dict.fromkeys(v))
            elif k in ['view_count','duration']:
                if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0):raise ValueError('播放量和时长必须为非负数字')
                if k=='view_count' and v is not None and int(v)!=v:raise ValueError('播放量必须为整数')
            elif k in ['keywords','batches']:
                if not isinstance(v,list) or any(not isinstance(x,str) for x in v):raise ValueError('关键词和批次必须为文字列表')
                changes[k]=list(dict.fromkeys(x.strip() for x in v if x.strip()))
            elif not isinstance(v,str):raise ValueError('资料字段必须为文字')
        if changes.get('published'):datetime.strptime(changes['published'],'%Y-%m-%d')
        if changes.get('collected_at'):
            value=datetime.fromisoformat(changes['collected_at'])
            changes['collected_at']=(value.replace(tzinfo=BJ) if value.tzinfo is None else value.astimezone(BJ)).isoformat(timespec='seconds')
        if changes.get('uid') and not changes['uid'].isdigit():raise ValueError('UID必须为数字字符串')
        if changes.get('space_url'):
            uid=creator_uid(changes['space_url'])
            if changes.get('uid') and changes['uid']!=uid:raise ValueError('UID与空间URL不一致')
            changes['space_url']=f'https://space.bilibili.com/{uid}'
        if 'url' in changes:
            normalized,identity=workspace.canonical_url(changes['url'])
            if identity!=workspace.canonical_url(current['url'])[1]:raise ValueError('不能更换来源身份；其他视频请添加为新内容')
            changes['url']=normalized
        path=root/'knowledge/source-registry.json';rows=wxq.read_json(path,[])
        row=next((r for r in rows if r['id']==sid),None)
        if row is None:
            row={'id':sid,'url':current['url']};rows.append(row)
        row['manual_values']={**row.get('manual_values',{}),**changes}
        restore=payload.get('restore_topics',[])
        if not isinstance(restore,list) or any(k not in ['topic_players','topic_lineups'] for k in restore):raise ValueError('只可恢复棋手和阵容自动值')
        for k in restore:row['manual_values'].pop(k,None)
        row['manual_revision']=uuid.uuid4().hex
        row['manual_updated_at']=wxq.now()
        wxq.atomic_json(path,rows)
        updated=next(s for s in source_rows(root,store) if s['id']==sid)
        # Invalidate in-flight chunks promptly; periodic worker scans recover an enqueue failure.
        try:
            from topics import TopicStore
            TopicStore(root).sync([updated])
        except Exception:
            import logging
            logging.getLogger(__name__).exception('资料已保存，主题队列等待后台补查')
        return updated
