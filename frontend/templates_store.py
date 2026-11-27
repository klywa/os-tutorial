"""Recoverable, revision-fenced speech templates independent of knowledge notes.

Canonical records and their history/baselines are tracked under templates/.
Only the redo journal lives in raw/. Public reads and import previews never seed
files. Mutations acquire the existing non-reentrant workspace lock exactly once.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import stat
from threading import Lock
import uuid

import json_store
from save_timing import timed
from workspace import Conflict, store_lock
import templates_schema as schema
import template_rules as rules
from template_v04 import CURRENT_VERSION, KEYED_SYNTAX_VERSIONS, upgrade_rule

META = 'templates/library.meta.json'
STATE = 'templates/library.state.json'
JOURNAL = 'raw/templates/pending.json'
GENERATION = 'raw/templates/generation.json'
PUBLISHED = 'raw/templates/published.json'
PUBLISHED_V3 = 'raw/templates/published-v3.json'
REVIEW_HISTORY = 'templates/review-history'
FOLDERS = {'event':'events','group':'groups'}
_review_cache={}
_review_cache_lock=Lock()
_metadata_cache={}
_legacy_metadata_cache={}
_records_cache={}
_published_cache={}
_index_cache={}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _meta():
    return {'schema_version':1,'audit':[],'tombstones':{'event':{},'group':{}},'baselines':{},'entity_archive':{},'event_entity_archive':{},'entity_bindings':{},'syntax_version':None}


def _actor(actor):
    if isinstance(actor,dict):actor=actor.get('username')
    return schema.text(actor,'操作者')


def _path(kind, uid):
    schema.identity(uid)
    if kind not in FOLDERS:raise ValueError('未知模板记录类型')
    return f'templates/{FOLDERS[kind]}/{uid}.json'


def _safe_path(root, relative):
    """Recovery journals may only target the canonical template domain."""
    if not isinstance(relative,str):raise ValueError('事务路径无效')
    if relative in (PUBLISHED,GENERATION):
        target=(Path(root)/relative).resolve()
        if target.is_relative_to(Path(root).resolve()):return target
        raise ValueError('发布路径无效')
    parts=Path(relative).parts
    allowed=(relative in (META,STATE) or re.fullmatch(REVIEW_HISTORY+r'/[0-9a-f]{32}\.json',relative) or len(parts)==3 and parts[0]=='templates' and parts[1] in (*FOLDERS.values(),'resolutions')
             and parts[2].endswith('.json') and schema.ID.fullmatch(parts[2][:-5]))
    target=(Path(root)/relative).resolve()
    if not allowed or not target.is_relative_to((Path(root)/'templates').resolve()):raise ValueError('模板事务路径无效')
    return target


def _journal(root):
    value=json_store.read(Path(root)/JOURNAL)
    if value is None:return None
    if not isinstance(value,dict) or value.get('schema_version')!=1 or not isinstance(value.get('writes'),dict) or not isinstance(value.get('deletes'),list):raise ValueError('模板恢复事务无效')
    for relative in [*value['writes'],*value['deletes']]:_safe_path(root,relative)
    return value


@timed('template_commit')
def _recover_locked(root):
    """Caller owns workspace.store_lock. Idempotent redo, never takes a lock."""
    journal=_journal(root)
    if journal is None:return False
    # Metadata is the final generation marker. The journal remains until every
    # canonical write and deletion is durable and can always be replayed.
    for relative,value in journal['writes'].items():
        if relative!=META:json_store.write_file(_safe_path(root,relative),value)
    for relative in journal['deletes']:_safe_path(root,relative).unlink(missing_ok=True)
    if META in journal['writes']:json_store.write_file(_safe_path(root,META),journal['writes'][META])
    json_store.write_file(_safe_path(root,GENERATION),uuid.uuid4().hex)
    (Path(root)/JOURNAL).unlink(missing_ok=True)
    return True


def recover(root):
    if not (Path(root)/JOURNAL).exists():return False
    with store_lock(root,wait=True):return _recover_locked(root)


def _file_stamp(state):
    return state.st_mtime_ns,state.st_ctime_ns,state.st_size,state.st_ino


def _stamp(path):
    try:
        state=path.stat()
        return _file_stamp(state)
    except FileNotFoundError:
        return None


class _LoadedMetadata(dict):
    def __init__(self,original,digest):
        # An audit entry is immutable. Callers can append to their own list.
        super().__init__({key:list(value) if key=='audit' else deepcopy(value) for key,value in original.items()})
        self.original=original
        self.digest=digest


def _read_metadata(root):
    path=(root/META).resolve()
    stamp=(_stamp(path),_stamp(root/STATE))
    cached=_metadata_cache.get(path)
    if cached is None or cached[0]!=stamp:
        legacy=_legacy_metadata_cache.get(path)
        if legacy is None or legacy[0]!=stamp[0]:
            original=json_store.read(path,_meta())
            if not isinstance(original,dict) or original.get('schema_version')!=1:
                raise ValueError('模板元数据版本无效')
            original={**_meta(),**original}
            legacy=(stamp[0],original,json_store.digest(original))
            if len(_legacy_metadata_cache)>=8:_legacy_metadata_cache.clear()
            _legacy_metadata_cache[path]=legacy
        state=json_store.read(root/STATE,{})
        if not isinstance(state,dict) or any(key not in _meta() or key in ('audit','schema_version') for key in state):
            raise ValueError('模板状态格式无效')
        cached=(stamp,{**legacy[1],**state},json_store.digest([legacy[2],state]) if state else legacy[2])
        if len(_metadata_cache)>=8:_metadata_cache.clear()
        _metadata_cache[path]=cached
    return _LoadedMetadata(cached[1],cached[2])


def _read_record(path,stamp):
    cached=_records_cache.get(path)
    if cached is None or cached[0]!=stamp:
        cached=(stamp,json_store.read(path))
        if len(_records_cache)>=4000:_records_cache.clear()
        _records_cache[path]=cached
    return deepcopy(cached[1])


@timed('template_read')
def _load(root,*,renamed=None,retired=None,migrate_events=False,locked=False,metadata=None):
    """Read public arrays and tracked metadata; pending committed after-image wins.

    This helper never writes, so proposal/import previews are strictly read-only.
    Callers already holding the workspace lock may use it directly.
    """
    root=Path(root).resolve()
    generation=(_stamp(root/GENERATION),_stamp(root/META),_stamp(root/STATE))
    journal=_journal(root)
    overlay=journal['writes'] if journal else {};deleted=set(journal['deletes']) if journal else set()
    meta=deepcopy(overlay[META]) if META in overlay else metadata if metadata is not None else _read_metadata(root)
    if STATE in overlay:meta={**meta,**deepcopy(overlay[STATE])}
    if not isinstance(meta,dict) or meta.get('schema_version')!=1:raise ValueError('模板元数据版本无效')
    for key,default in _meta().items():meta.setdefault(key,deepcopy(default))
    unavailable = set(schema.RETIRED_BUILTIN_IDS)
    unavailable.update(uid for uid,entry in meta['tombstones']['event'].items()
                       if entry.get('actor') == '事件目录迁移')
    public={'schema_version':1,'events':[],'groups':[]}
    for kind,folder in FOLDERS.items():
        values={e['id']:e for e in schema.builtin_events()} if kind=='event' else {}
        defaults=dict(values)
        for uid in meta['tombstones'].get(kind,{}):values.pop(uid,None)
        template_dir=(root/'templates').resolve()
        location=(template_dir/folder).resolve()
        if not location.is_relative_to(template_dir):raise ValueError('模板事务路径无效')
        records={}
        if location.is_dir():
            with os.scandir(location) as entries:
                for entry in entries:
                    if Path(entry.name).suffix.lower()!='.json':continue
                    try:state=entry.stat(follow_symlinks=False)
                    except FileNotFoundError:continue
                    records[f'templates/{folder}/{entry.name}']=(Path(entry.path),state)
        relatives=set(records)
        relatives.update(p for p in overlay if p.startswith(f'templates/{folder}/'))
        for relative in sorted(relatives-deleted):
            if not schema.ID.fullmatch(Path(relative).stem):raise ValueError('模板事务路径无效')
            if relative in overlay:
                path=_safe_path(root,relative)
                value=deepcopy(overlay[relative])
            else:
                path,state=records[relative]
                if stat.S_ISLNK(state.st_mode) or getattr(state,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    path=_safe_path(root,relative)
                    stamp=_stamp(path)
                else:stamp=_file_stamp(state)
                value=_read_record(path,stamp)
            if not isinstance(value,dict) or value.get('id')!=path.stem:raise ValueError('模板文件身份与路径不一致')
            if kind == 'event' and value['name'].endswith('（旧版）'):
                unavailable.add(value['id'])
                values.pop(value['id'],None)
                if retired is not None:
                    retired[relative] = value
                continue
            if kind == 'group' and value['event_id'] in unavailable:
                if retired is not None and value['id'] not in meta['tombstones']['group']:
                    retired[relative] = value
                continue
            default=values.get(value['id'],{})
            if kind=='event' and (default or migrate_events):
                updated=rules.explanation_event(value)
                if renamed is not None and updated!=value:renamed[value['id']]=updated
                value=updated
            if value['id'] not in meta['tombstones'].get(kind,{}):values[value['id']]=value
        if kind=='event':
            unavailable.difference_update(values)
            changes=rules.disambiguate_existing(values.values(),defaults)
            if renamed is not None:renamed.update(changes)
        public[folder]=schema.order_events(values.values()) if kind=='event' else sorted(values.values(),key=lambda row:row['id'])
    # A writer that started after the first journal read owns the complete logical
    # after-image; retry instead of exposing a partially replaced file batch.
    if meta.get('syntax_version') in KEYED_SYNTAX_VERSIONS or any(group.get('syntax_version') in KEYED_SYNTAX_VERSIONS for group in public['groups']):
        from template_v04 import catalog
        registered={event['name'] for event in public['events']}
        for name in catalog()['events']:
            if name not in registered:
                uid='v04_'+hashlib.sha256(name.encode()).hexdigest()[:16]
                public['events'].append({'id':uid,'name':name,'category':'解释类','parameters':[]})
    if locked:return public,meta
    if journal is None and ((root/JOURNAL).exists() or generation!=(_stamp(root/GENERATION),_stamp(root/META),_stamp(root/STATE))):
        return _load(root,renamed=renamed,retired=retired,migrate_events=migrate_events)
    return public,meta


def _revision(public,meta,*,metadata_digest=None):
    if metadata_digest is None and isinstance(meta,_LoadedMetadata) and meta==meta.original:
        metadata_digest=meta.digest
    return json_store.digest({'library':public,'metadata':metadata_digest or json_store.digest(meta)})


def _snapshot(public,meta,*,metadata_digest=None):
    return {**deepcopy(public),'revision':_revision(public,meta,metadata_digest=metadata_digest)}


def snapshot(root):
    recover(root)
    return _snapshot(*_load(root))


class EffectiveEntities(dict):
    """Validated, read-only catalog generation shared by the HTTP service."""
    def __init__(self,data):
        super().__init__(data)
        self.by_id={row['id']:row for row in self['items']}
        self.complete=frozenset(self['complete_categories'])
        self.official_s1=None


def _catalog(root, entities=None, *, include_season_cards=True):
    """Return effective IDs plus authoritative categories (missing != deleted)."""
    root=Path(root);catalog={};complete=set()
    if isinstance(entities,EffectiveEntities):
        catalog={**_season_cards(root),**entities.by_id} if include_season_cards else dict(entities.by_id)
        return catalog,set(entities.complete)
    if entities is not None:
        if isinstance(entities,dict) and 'items' in entities:
            schema.fields(entities,{'items','complete_categories'},{'items','complete_categories'})
            rows=entities['items'];categories=entities['complete_categories']
            if not isinstance(categories,list) or any(not isinstance(c,str) or c not in schema.CATEGORIES for c in categories):raise ValueError('实体完整类别列表无效')
            complete=set(categories)
        else:
            rows=list(entities.values()) if isinstance(entities,dict) else entities
            complete=set(schema.CATEGORIES)
        if not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('id'),str) or not isinstance(row.get('category'),str) or row['category'] not in schema.CATEGORIES for row in rows):raise ValueError('实体资料格式无效')
        current={row['id']:deepcopy(row) for row in rows}
        return {**_season_cards(root),**current} if include_season_cards else current,complete
    for category in sorted(schema.CATEGORIES):
        path=root/'entities'/(category+'.json')
        try:rows=json_store.read(path)
        except (ValueError,OSError):continue
        if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) for r in rows):continue
        complete.add(category)
        for row in rows:catalog[row['id']]={**deepcopy(row),'category':category}
    # The public package supplies the semantic card projection on website copies.
    try:published=json_store.read(root/'website-data/cards.json')
    except (ValueError,OSError):published=None
    if isinstance(published,list) and all(isinstance(r,dict) and isinstance(r.get('id'),str) and r.get('category') in schema.CATEGORIES for r in published):
        categories={r['category'] for r in published}
        for row in published:
            if row['category'] not in complete:catalog[row['id']]=deepcopy(row)
        complete.update(categories)
    return {**_season_cards(root),**catalog} if include_season_cards else catalog,complete


def _index(path,load):
    stamp=_stamp(path)
    cached=_index_cache.get(path)
    if cached is None or cached[0]!=stamp:
        cached=stamp,load()
        if len(_index_cache)>=24:_index_cache.clear()
        _index_cache[path]=cached
    return cached[1]


def _season_cards(root, season='S2'):
    path=Path(root)/'website-data'/'seasons'/season/'cards.json'
    def load():
        rows=json_store.read(path,[])
        if not isinstance(rows,list):raise ValueError('该赛季卡牌资料格式无效')
        return {row['id']:row for row in rows if isinstance(row,dict) and isinstance(row.get('id'),str)
                and row.get('category') in schema.CATEGORIES}
    return _index(path,load)


def _notes(root):
    path=Path(root)/'knowledge/index.meta.json'
    def load():
        index=json_store.read(path,{'notes':[]})
        if not isinstance(index,dict) or not isinstance(index.get('notes'),list):raise ValueError('阵容笔记索引无效')
        return {row['id']:row for row in index['notes'] if isinstance(row,dict) and isinstance(row.get('id'),str)}
    return _index(path,load)


def validation_context(root, *, entities=None, before=None, metadata=None):
    """Catalog, notes and record-scoped previously known references for validators.

    A tracked archive is usable only while the BEFORE record still associates
    that entity. Removing an association revokes it; new records cannot borrow
    another group's archive. Baselines support existing libraries without an
    archive until their next real save.
    """
    if before is None or metadata is None:
        current,meta=_load(root)
        if before is None:before=current
        if metadata is None:metadata=meta
    events={e['id']:e for e in before['events']};retired={}
    for group in before['groups']:
        archived={**metadata.get('baselines',{}).get(group['id'],{}),
                  **metadata.get('entity_archive',{}).get(group['id'],{})}
        known=set(_references(group,events,bindings=metadata.get('entity_bindings',{}).get(group['id'],{})))|{ref['id'] for ref in group.get('related_entities',[])}
        retired[group['id']]={eid:deepcopy(archived[eid]) for eid in known
                              if isinstance(archived.get(eid),dict) and archived[eid].get('id')==eid}
    return _catalog(root,entities)[0],_notes(root),retired


def validate(root, events, groups, *, entities=None, before=None, metadata=None):
    catalog,notes,retired=validation_context(root,entities=entities,before=before,metadata=metadata)
    suggestions=event_validation_context(root,before=before,metadata=metadata)
    return schema.validate_library({'schema_version':1,'events':events,'groups':groups},catalog,notes,
                                   retired_entities=retired,retired_suggestions=suggestions)


def _suggestion_refs(event):
    return {p['id']:{v['id'] for v in p.get('suggestions',[]) if isinstance(v,dict) and isinstance(v.get('id'),str)}
            for p in event['parameters'] if p['type']=='entity'}


def event_validation_context(root, *, before=None, metadata=None):
    """Known retired suggestions scoped to event and stable parameter identity."""
    if before is None or metadata is None:
        current,meta=_load(root)
        if before is None:before=current
        if metadata is None:metadata=meta
    result={}
    for event in before['events']:
        archive=metadata.get('event_entity_archive',{}).get(event['id'],{})
        result[event['id']]={pid:{eid:deepcopy(archive[pid][eid]) for eid in refs
                                 if isinstance(archive.get(pid,{}).get(eid),dict) and archive[pid][eid].get('id')==eid}
                             for pid,refs in _suggestion_refs(event).items()}
    return result


def check_utterance_flags(old, new):
    if new.get('fixed') and new.get('ignored') and not (old.get('fixed') and old.get('ignored')):
        raise Conflict('同一条话术只能固定或忽略')


def check_fixed_utterances(before, after, toggle=None, authorized_fixed=()):
    def rows(library):
        return {(group['id'], row['id']): row for group in library['groups'] for row in group['utterances']}
    previous, current = rows(before), rows(after)
    for key in previous.keys() | current.keys():
        old, new = previous.get(key, {}), current.get(key, {})
        check_utterance_flags(old, new)
        if key != toggle and key not in authorized_fixed and (bool(old.get('fixed')) != bool(new.get('fixed'))
                or old.get('fixed') and old['text'] != new.get('text')):
            raise Conflict('固定话术不能修改或删除，请先取消固定')


def editor_utterance_targets(current, changes, *, pin=False, explicit=()):
    """Authorize text edits and fix new or edited speech when committing an existing group."""
    if not isinstance(changes,list):
        return set()
    groups={group['id']:group for group in current['groups']}
    targets=set()
    for change in changes:
        if not isinstance(change,dict) or change.get('kind')!='group' or change.get('action')!='put':
            continue
        previous=groups.get(change.get('id')) if isinstance(change.get('id'),str) else None
        value=change.get('value')
        rows=value.get('utterances') if isinstance(value,dict) else None
        if not previous or not isinstance(rows,list):
            continue
        originals={row['id']:row for row in previous['utterances']}
        for row in rows:
            if (not isinstance(row,dict) or not isinstance(row.get('id'),str)
                    or not isinstance(row.get('text'),str) or type(row.get('fixed',False)) is not bool):
                continue
            old=originals.get(row['id'])
            key=(previous['id'],row['id'])
            if old is None and pin and not row.get('fixed') and not row.get('ignored'):
                row['fixed']=True
                targets.add(key)
            elif old and old['text']!=row['text'] and (
                    bool(old.get('fixed'))==bool(row.get('fixed')) or key in explicit):
                targets.add(key)
                if pin and not row.get('ignored'):
                    row['fixed']=True
    return targets


def related_copy_changes(current, changes):
    """Authorize inherited fixed flags only on a verified new copy."""
    if not isinstance(changes,list) or not any(isinstance(change,dict) and 'related_copy_source' in change for change in changes):
        return changes,set()
    groups={group['id']:group for group in current['groups']}
    result,authorized=[],set()
    for change in changes:
        if not isinstance(change,dict) or 'related_copy_source' not in change:
            result.append(change)
            continue
        change=dict(change)
        source=groups.get(schema.identity(change.pop('related_copy_source')))
        target=change.get('value')
        if (change.get('kind')!='group' or change.get('action')!='put' or not isinstance(target,dict)
                or schema.identity(change.get('id')) in groups or not source
                or source.get('syntax_version') not in KEYED_SYNTAX_VERSIONS or target.get('syntax_version') not in KEYED_SYNTAX_VERSIONS
                or source['event_id']==target.get('event_id')):
            raise Conflict('只能从已有模板组新建关联模板组')
        originals=source['utterances']
        original_ids={row['id'] for row in originals}
        rows=target.get('utterances')
        if (not isinstance(rows,list) or len(rows)!=len(originals)
                or bool(source.get('ignored'))!=bool(target.get('ignored'))
                or any(not isinstance(row,dict) or not isinstance(row.get('id'),str)
                       or row['id'] in original_ids or row.get('text')!=original['text']
                       or any(bool(row.get(flag))!=bool(original.get(flag)) for flag in ('fixed','ignored'))
                       for original,row in zip(originals,rows))):
            raise Conflict('关联模板的话术内容、顺序或状态与来源不一致')
        authorized.update((change['id'],row['id']) for row in rows if row.get('fixed'))
        result.append(change)
    return result,authorized


@timed('template_validate')
def _project(root, public, revision, meta, changes, entities=None, allow_conflicts=False, authorized_fixed=(), *, revision_checked=False):
    if not revision_checked and revision!=_revision(public,meta):raise Conflict('模板库已更新，请刷新；草稿已保留')
    if not isinstance(changes,list) or len(changes)>5000:raise ValueError('模板修改必须为列表，且不能超过 5000 项')
    maps={kind:{item['id']:item for item in public[folder]} for kind,folder in FOLDERS.items()}
    seen=set()
    blocked=None
    for change in changes:
        schema.fields(change,{'kind','action','id','value'},{'kind','action','id'})
        kind=change['kind'];uid=schema.identity(change['id']);action=change['action']
        if not isinstance(kind,str) or kind not in maps or action not in ('put','delete'):raise ValueError('模板修改类型无效')
        if (kind,uid) in seen:raise ValueError('同一模板记录只能修改一次')
        seen.add((kind,uid))
        if not allow_conflicts:
            if blocked is None:
                from templates_sync import blocked_records
                blocked=blocked_records(root)
            if (kind,uid) in blocked:raise Conflict('该模板记录存在同步冲突，请先解决')
        if action=='delete':
            if 'value' in change:raise ValueError('删除记录不能携带值')
            maps[kind].pop(uid,None)
        else:
            if not isinstance(change.get('value'),dict) or change['value'].get('id')!=uid:raise ValueError('模板修改身份不一致')
            prior=maps[kind].get(uid,{})
            if (kind=='group' and prior.get('syntax_version') in KEYED_SYNTAX_VERSIONS
                    and change['value'].get('syntax_version') not in KEYED_SYNTAX_VERSIONS):
                raise Conflict('正式模板已使用额外信息键。重新预览旧稿后再提交。')
            maps[kind][uid]=deepcopy(change['value'])
    for kind,uid in seen:
        if kind=='group' and uid in maps['group']:
            group=maps['group'][uid]
            event=maps['event'].get(group.get('event_id'))
            if event:
                maps['group'][uid]=upgrade_rule(group,event['name'])
    groups=[maps['group'][uid] for uid in sorted(maps['group'])]
    if any(kind=='event' for kind,_ in seen):
        projected=validate(root,[maps['event'][uid] for uid in sorted(maps['event'])],groups,
                           entities=entities,before=public,metadata=meta)
        check_fixed_utterances(public,projected,authorized_fixed=authorized_fixed)
        return projected
    targets={uid for _,uid in seen}
    previous={**public,'groups':[group for group in public['groups'] if group['id'] in targets]}
    updated=[group for group in groups if group['id'] in targets]
    if updated:
        catalog,notes,retired=validation_context(root,entities=entities,before=previous,metadata=meta)
        for group in updated:
            schema.validate_group(group,maps['event'],{**retired.get(group['id'],{}),**catalog},notes)
            group.setdefault('related_entities',[])
    check_fixed_utterances(previous,{'groups':updated},authorized_fixed=authorized_fixed)
    projected={**public,'groups':groups}
    return projected


def preview_changes(root,revision,changes,*,entities=None,authorized_fixed=()):
    public,meta=_load(root)
    projected=_project(root,public,revision,meta,changes,entities,authorized_fixed=authorized_fixed)
    return _snapshot(projected,meta)


def merged_group_ids(aliases):
    return {source: entry['merged_into'] for source, entry in aliases.items()}


def merged_reference(tombstones, group_id, utterance_id=None):
    groups = tombstones.get('group', {})
    visited = set()
    while group_id not in visited:
        entry = groups.get(group_id, {})
        if not entry.get('merged_into'):
            break
        visited.add(group_id)
        group_id = entry['merged_into']
        if utterance_id is not None:
            utterance_id = entry.get('utterance_aliases', {}).get(utterance_id)
    return group_id, utterance_id


def _merge_projected(root, before, after, meta, changes, entities):
    from template_group_edit import formal_merge_key, merge_formal_group
    from templates_sync import blocked_records

    touched = {row['id'] for row in changes if row['kind']=='group' and row['action']=='put'}
    groups = {group['id']: group for group in after['groups']}
    names = {(groups[uid]['event_id'], groups[uid]['name'].strip()) for uid in touched}
    existing = {group['id']: group for group in before['groups']}
    order = dict.fromkeys([*existing, *(row['id'] for row in changes if row['kind']=='group')])
    peers = {}
    for uid in order:
        if uid in groups:
            group = groups[uid]
            key = group['event_id'], group['name'].strip()
            if key in names:
                peers.setdefault(key, []).append(group)
    peers = [rows for rows in peers.values() if len(rows)>1]
    if not peers:
        return after, {}, set()

    catalog, notes = _catalog(root, entities)[0], _notes(root)
    events = {event['id']: event for event in after['events']}
    blocked = blocked_records(root)
    aliases, authorized = {}, set()
    for rows in peers:
        variants = {}
        for group in rows:
            uid = group['id']
            archived = {**meta['baselines'].get(uid, {}), **meta['entity_archive'].get(uid, {})}
            references = {eid: row for eid, row in archived.items() if isinstance(row, dict)}
            key = formal_merge_key(group, events[group['event_id']], {**references, **catalog}, notes)
            if key is not None:
                variants.setdefault(key, []).append(group)
        for equivalent in variants.values():
            if len(equivalent)<2 or not any(group['id'] in touched for group in equivalent):
                continue
            if any(('group', group['id']) in blocked for group in equivalent):
                raise Conflict('同名模板组存在同步冲突，请先解决')
            winner, *duplicates = equivalent
            target = deepcopy(winner)
            for source in duplicates:
                moved = merge_formal_group(target, source)
                aliases[source['id']] = {'merged_into': target['id'], 'utterance_aliases': moved}
                for row in existing.get(source['id'], {}).get('utterances', []):
                    if row.get('fixed'):
                        authorized.add((source['id'], row['id']))
                for row in source['utterances']:
                    if row.get('fixed'):
                        authorized.add((target['id'], moved[row['id']]))
                del groups[source['id']]
            groups[target['id']] = target
    return {**after, 'groups': [groups[uid] for uid in sorted(groups)]}, aliases, authorized


def approval_projection(root, revision, changes, *, entities=None, authorized_fixed=(), merge_groups=False):
    """Plan exact, replayable writes after checking the requested edits."""
    public, meta = _load(root)
    projected = _project(root, public, revision, meta, changes, entities, authorized_fixed=authorized_fixed)
    if not merge_groups:
        return projected, changes, {}, authorized_fixed
    projected, aliases, moved_fixed = _merge_projected(root, public, projected, meta, changes, entities)
    if not aliases:
        return projected, changes, {}, authorized_fixed
    old = {row['id']: row for row in public['groups']}
    new = {row['id']: row for row in projected['groups']}
    actual = [change for change in changes if change['kind']!='group']
    for uid in sorted(old.keys() | new.keys()):
        if old.get(uid) != new.get(uid):
            actual.append({'kind': 'group', 'id': uid, 'action': 'put', 'value': new[uid]} if uid in new
                          else {'kind': 'group', 'id': uid, 'action': 'delete'})
    return projected, actual, aliases, set(authorized_fixed) | moved_fixed


_SEMANTIC_KEYS={'id','name','category','aliases','description','effect','skills','options','properties','faction','tier','awakened','stats','attributes','type'}
_NOISE={'history','sources','source','retrieved_at','updated_at','created_at','fetched_at','checked_at','version','timestamp','time','date','image','images','icon','thumb','portrait','portraitV2','bgImg','banShenImg','avatar','image_url','thumb_url','official_url','url','skills_source','roleData','isOwn','ProficiencyLv','championRate'}


def semantic(entity):
    """Stable gameplay semantics, recursively excluding acquisition/media fields."""
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in sorted(value.items()) if k not in _NOISE and not k.endswith(('_at','_url','_path')) and not any(word in k.lower() for word in ('image','icon','thumb','portrait','timestamp'))}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    return clean({key:value for key,value in entity.items() if key in _SEMANTIC_KEYS})


def _bindings(group,events,catalog,previous=None):
    """Selectors track every matching version, retaining known renamed/deleted IDs."""
    from templates_entities import resolve
    previous=previous or {};result={}
    params={p['key']:p for p in events.get(group['event_id'],{}).get('parameters',[])}
    for condition in group['conditions']:
        parameter=params.get(condition['parameter_key'],{});value=condition['value']
        if parameter.get('type')!='entity' or not isinstance(value,dict):continue
        selector={'key':condition['parameter_key'],'categories':sorted(parameter.get('entity_categories',[])),
                  'name':value['name'].strip(),'anchor':value['id']}
        old=previous.get(condition['id'],{})
        ids=set(old.get('ids',[])) if old.get('selector')==selector else set()
        # The canonical anchor is stable even after a catalog rename/removal.
        ids.add(value['id'])
        try:ids.update(row['id'] for row in resolve(value['name'],parameter,catalog))
        except ValueError:pass # Existing retired selectors remain editable and monitorable.
        result[condition['id']]={'selector':selector,'ids':sorted(ids)}
    return result


def _references(group,events,catalog=None,bindings=None):
    refs={}
    if 'expression' in group:
        refs.update({r['id']:r['name'] for r in group.get('related_entities',[])})
    player=group['scope'].get('player_id')
    if player:refs[player]=player
    event=events.get(group['event_id'],{})
    params={p['key']:p for p in event.get('parameters',[])}
    for condition in group['conditions']:
        if params.get(condition['parameter_key'],{}).get('type')=='entity' and isinstance(condition['value'],dict):
            refs[condition['value']['id']]=condition['value']['name']
    links=_bindings(group,events,catalog if catalog is not None else {},bindings)
    for link in links.values():
        for eid in link.get('ids',[]):refs.setdefault(eid,link.get('selector',{}).get('name',eid))
    return refs


def entity_link_projection(root,entities=None):
    """Read-only projection; derived fields never contaminate editable records."""
    public,meta=_load(root);catalog,_=_catalog(root,entities)
    return project_entity_links(public,meta,catalog)


def project_entity_links(public,meta,catalog):
    events={e['id']:e for e in public['events']}
    result={};conditions={}
    for group in public['groups']:
        archive={**meta.get('baselines',{}).get(group['id'],{}),**meta.get('entity_archive',{}).get(group['id'],{})}
        bindings=_bindings(group,events,catalog,meta.get('entity_bindings',{}).get(group['id'],{}))
        refs=_references(group,events,bindings=bindings)
        def render(refs):return [{'id':eid,'name':(catalog.get(eid) or archive.get(eid) or {}).get('name',name)} for eid,name in sorted(refs.items())]
        result[group['id']]=render(refs)
        conditions[group['id']]={cid:render({eid:link['selector']['name'] for eid in link['ids']}) for cid,link in bindings.items()}
    return {'entity_links':result,'entity_condition_links':conditions}


def entity_links(root,entities=None):
    return entity_link_projection(root,entities)['entity_links']


def _baseline(meta,before,after,catalog,*,group_ids=None):
    """New links start at today's baseline; existing links retain unreviewed deltas."""
    events={e['id']:e for e in after['events']};existing=meta['baselines']
    retained={uid:value for uid,value in existing.items() if group_ids is not None and uid not in group_ids}
    archives={uid:value for uid,value in meta['entity_archive'].items() if group_ids is not None and uid not in group_ids}
    bindings={uid:value for uid,value in meta['entity_bindings'].items() if group_ids is not None and uid not in group_ids}
    old_groups={g['id']:g for g in before['groups']};old_events={e['id']:e for e in before['events']}
    for group in after['groups']:
        if group_ids is not None and group['id'] not in group_ids:continue
        old=existing.get(group['id'],{})
        bindings[group['id']]=_bindings(group,events,catalog,meta.get('entity_bindings',{}).get(group['id'],{}))
        prior=_bindings(old_groups[group['id']],old_events,{},meta.get('entity_bindings',{}).get(group['id'],{})) if group['id'] in old_groups else {}
        continuing={eid for cid,link in bindings[group['id']].items() if prior.get(cid,{}).get('selector')==link['selector'] for eid in link['ids']}
        refs=_references(group,events,bindings=bindings[group['id']])
        retained[group['id']]={eid:deepcopy(old[eid]) if eid in old else None if eid in continuing else semantic(catalog[eid]) if eid in catalog else None
                               for eid in refs}
        archived={**old,**meta.get('entity_archive',{}).get(group['id'],{})}
        archives[group['id']]={eid:semantic(catalog[eid]) if eid in catalog else deepcopy(archived[eid])
                               for eid in refs if eid in catalog or isinstance(archived.get(eid),dict)}
        for ref in group.get('related_entities',[]):
            eid=ref['id']
            if eid in catalog:archives[group['id']][eid]=semantic(catalog[eid])
            elif isinstance(archived.get(eid),dict):archives[group['id']][eid]=deepcopy(archived[eid])
    meta['baselines']=retained
    meta['entity_archive']=archives
    meta['entity_bindings']=bindings
    if group_ids is not None:return
    event_archive={}
    for event in after['events']:
        archived=meta.get('event_entity_archive',{}).get(event['id'],{})
        event_archive[event['id']]={pid:{eid:semantic(catalog[eid]) if eid in catalog else deepcopy(archived[pid][eid])
                                        for eid in refs if eid in catalog or isinstance(archived.get(pid,{}).get(eid),dict)}
                                    for pid,refs in _suggestion_refs(event).items()}
    meta['event_entity_archive']=event_archive


def _commit(root,before,after,meta,actor,changes,*,entities=None,extra_writes=None,manual=None,authorized_fixed=(),validated=False,aliases=None):
    """Caller holds workspace lock. Validate before journal (the commit point)."""
    root=Path(root);actor=_actor(actor)
    if not validated:
        after=validate(root,after['events'],after['groups'],entities=entities,before=before,metadata=meta)
        check_fixed_utterances(before,after,authorized_fixed=authorized_fixed)
    newmeta=deepcopy({key:value for key,value in meta.items() if key!='audit'})
    newmeta['audit']=meta['audit']
    versions={group.get('syntax_version') for group in after['groups']} | {meta.get('syntax_version')}
    for version in reversed(KEYED_SYNTAX_VERSIONS):
        if version in versions:
            newmeta['syntax_version']=version
            break
    changed=[]
    for kind,folder in FOLDERS.items():
        old={v['id']:v for v in before[folder]};new={v['id']:v for v in after[folder]}
        for uid in sorted(set(old)|set(new)):
            if old.get(uid)==new.get(uid):continue
            change={'kind':kind,'action':'put' if uid in new else 'delete','id':uid}
            if uid in new:change['value']=new[uid]
            changed.append(change)
            if uid in new:newmeta['tombstones'].setdefault(kind,{}).pop(uid,None)
            else:newmeta['tombstones'].setdefault(kind,{})[uid]={'actor':actor,'at':_now(),'revision':_revision(before,meta),
                **((aliases or {}).get(uid, {}) if kind=='group' else {})}
    if not changed and newmeta==meta and not extra_writes:return _snapshot(before,meta)
    changed_ids={(item['kind'],item['id']) for item in changed}
    audit_snapshots={name:{folder:[deepcopy(record) for record in data[folder] if (kind,record['id']) in changed_ids]
                           for kind,folder in FOLDERS.items()}
                     for name,data in (('before',before),('after',after))}
    dependency_fields=('event_id','scope','related_entities','conditions','expression','condition_tree')
    old_groups={row['id']:row for row in audit_snapshots['before']['groups']}
    next_groups={row['id']:row for row in audit_snapshots['after']['groups']}
    dependency_ids={uid for uid in old_groups.keys()|next_groups.keys() if uid not in old_groups or uid not in next_groups
                    or any(old_groups[uid].get(key)!=next_groups[uid].get(key) for key in dependency_fields)}
    if audit_snapshots['before']['events'] or audit_snapshots['after']['events']:
        _baseline(newmeta,before,after,_catalog(root,entities)[0])
    elif dependency_ids:
        _baseline(newmeta,before,after,_catalog(root,entities)[0],group_ids=dependency_ids)
    entry={'id':uuid.uuid4().hex,'actor':actor,'at':_now(),'changes':changed,
           **({'manual':manual} if manual else {}),**audit_snapshots}
    return _persist_locked(root,before,after,newmeta,extra_writes=extra_writes,entities=entities,
                           previous_meta=None if extra_writes else meta,audit_entry=entry)


def _persist_locked(root,before,after,meta,*,extra_writes=None,entities=None,previous_meta=None,audit_entry=None):
    root=Path(root);writes={};deletes=[]
    if previous_meta is None:
        writes[META]=meta
        if (root/STATE).exists():deletes.append(STATE)
    elif previous_meta!=meta or not (root/META).exists():
        if meta['audit'] or (root/STATE).exists():
            writes[STATE]={key:value for key,value in meta.items() if key not in ('audit','schema_version')}
        else:writes[META]=meta
    if audit_entry is not None:writes[REVIEW_HISTORY+'/'+audit_entry['id']+'.json']=audit_entry
    for relative,value in (extra_writes or {}).items():
        if not relative.startswith('templates/resolutions/'):
            raise ValueError('附加模板事务只能写入冲突解决记录')
        _safe_path(root,relative);writes[relative]=deepcopy(value)
    for kind,folder in FOLDERS.items():
        old={record['id']:record for record in before[folder]}
        for value in after[folder]:
            if old.get(value['id'])!=value:writes[_path(kind,value['id'])]=value
        surviving={v['id'] for v in after[folder]}
        for value in before[folder]:
            if value['id'] not in surviving:deletes.append(_path(kind,value['id']))
    published=_published_document(root,after,meta,entities)
    published_path=_safe_path(root,PUBLISHED)
    stamp=_stamp(published_path)
    if stamp is None or published!=_read_record(published_path,stamp):writes[PUBLISHED]=published
    json_store.write_file(root/JOURNAL,{'schema_version':1,'writes':writes,'deletes':deletes})
    _recover_locked(root)
    return _snapshot(after,_read_metadata(root) if META in writes or STATE in writes else previous_meta)


def review_history(root):
    rows=[]
    for path in sorted((Path(root)/REVIEW_HISTORY).glob('*.json')):
        stamp=_stamp(path)
        if stamp is not None:
            row=_read_record(path,stamp)
            if row is not None:rows.append(row)
    return rows


def review_metadata_key(root):
    path=Path(root).resolve()/META
    return path,_stamp(path),_stamp(path.parent/'library.state.json')


def review_metadata(key,meta=None):
    with _review_cache_lock:cached=_review_cache.get(key)
    if cached is None:
        if meta is None:meta=_read_metadata(key[0].parent.parent)
        if not isinstance(meta,dict) or meta.get('schema_version')!=1:raise ValueError('模板元数据版本无效')
        digest=meta.digest if isinstance(meta,_LoadedMetadata) and meta==meta.original else json_store.digest({**_meta(),**meta})
        cached=meta['tombstones'],digest
        with _review_cache_lock:
            if len(_review_cache)>=8:_review_cache.pop(next(iter(_review_cache)))
            _review_cache[key]=cached
    tombstones,digest=cached
    return {**_meta(),'tombstones':tombstones},digest


def set_review_status(root,revision,group_id,actor,request):
    """Journal the record and its small audit entry without rewriting library history."""
    import template_workflow as workflow
    from templates_sync import is_blocked
    schema.identity(group_id)
    with store_lock(root,wait=True):
        _recover_locked(root)
        metadata,digest=review_metadata(review_metadata_key(root))
        before,meta=_load(root,locked=True,metadata=metadata)
        if revision!=_revision(before,meta,metadata_digest=digest):raise Conflict('模板库已更新，请刷新后重试')
        change=(workflow.review_status_change(before,group_id,actor,request['status'])
                if 'status' in request else workflow.review_change(before,group_id,actor))
        if change is None:return {**before,'revision':revision}
        if is_blocked(root,'group',group_id):raise Conflict('该模板记录存在同步冲突，请先解决')
        value=change['value']
        original=next(group for group in before['groups'] if group['id']==group_id)
        after={**before,'groups':[value if group['id']==group_id else group for group in before['groups']]}
        entry={'id':uuid.uuid4().hex,'actor':_actor(actor),'at':_now(),'changes':[change],
               'manual':{'source':'review-status'},'before':{'groups':[original]},'after':{'groups':[value]}}
        writes={_path('group',group_id):value,REVIEW_HISTORY+'/'+entry['id']+'.json':entry}
        json_store.write_file(Path(root)/JOURNAL,{'schema_version':1,'writes':writes,'deletes':[]})
        _recover_locked(root)
        return {**after,'revision':_revision(after,meta,metadata_digest=digest)}


def apply(root,revision,changes,actor='admin',*,entities=None,_allow_conflicts=False,manual=None,authorized_fixed=(),prepare=None,editor=False,aliases=None):
    with store_lock(root,wait=True):
        _recover_locked(root);public,meta=_load(root)
        if prepare is not None:
            if revision!=_revision(public,meta):raise Conflict('模板库已更新，请刷新；草稿已保留')
            changes=prepare({**public,'revision':revision})
        if editor:
            changes, inherited=related_copy_changes(public,changes)
            authorized_fixed=set(authorized_fixed)|inherited|editor_utterance_targets(public,changes,pin=True)
        after=_project(root,public,revision,meta,changes,entities,_allow_conflicts,authorized_fixed,revision_checked=prepare is not None)
        if editor:
            after,aliases,moved_fixed=_merge_projected(root,public,after,meta,changes,entities)
            if aliases:
                check_fixed_utterances(public,after,authorized_fixed=set(authorized_fixed)|moved_fixed)
        saved=_commit(root,public,after,meta,actor,changes,entities=entities,manual=manual,
                      authorized_fixed=authorized_fixed,validated=True,aliases=aliases)
        return {**saved, 'merged_groups':merged_group_ids(aliases)} if aliases else saved


def set_utterance_fixed(root, revision, group_id, utterance_id, fixed, actor, *, entities=None):
    from templates_sync import is_blocked
    schema.identity(group_id)
    schema.identity(utterance_id)
    if type(fixed) is not bool:
        raise ValueError('话术固定状态必须是布尔值')
    with store_lock(root,wait=True):
        _recover_locked(root)
        before, meta = _load(root)
        if revision != _revision(before,meta):
            raise Conflict('模板库已更新，请刷新后重试')
        if is_blocked(root,'group',group_id):
            raise Conflict('该模板记录存在同步冲突，请先解决')
        current = next((g for g in before['groups'] if g['id'] == group_id), None)
        group = deepcopy(current)
        row = next((u for u in (group or {}).get('utterances',[]) if u['id'] == utterance_id), None)
        if row is None:
            raise Conflict('话术已不存在，请刷新后重试')
        if bool(row.get('fixed')) == fixed:
            return _snapshot(before,meta)
        check_utterance_flags(row, {**row,'fixed':fixed})
        row['fixed'] = fixed
        after={**before,'groups':[group if g['id']==group_id else g for g in before['groups']]}
        return _commit(root,before,after,meta,actor,[],entities=entities,manual={'source':'manual'},
                       validated=True)


def _exportable(public):
    groups = []
    for group in public['groups']:
        if group.get('ignored'):
            continue
        utterances = [row for row in group['utterances'] if not row.get('ignored')]
        if utterances:
            groups.append({**group, 'utterances': utterances})
    return {'events': public['events'], 'groups': groups}


def _for_scope(public,season,mode=None):
    return {**public,'groups':[group for group in public['groups']
                              if schema.group_applies(group,season,mode)]}


@timed('template_publish')
def _published_document(root,public,meta,entities,season='S1',mode=None):
    from template_package import encode
    from template_v04 import runtime_tree
    projected=_exportable(_for_scope(public,season,mode))
    if meta.get('syntax_version') in KEYED_SYNTAX_VERSIONS or any(group.get('syntax_version') in KEYED_SYNTAX_VERSIONS for group in public['groups']):
        return runtime_tree(projected,_catalog(root,entities)[0],_notes(root),meta)
    key=Path(root).resolve(),season,mode
    if len(_published_cache)>=8 and key not in _published_cache:_published_cache.clear()
    return encode(projected,_catalog(root,entities)[0],_notes(root),meta,
                  all_groups=public['groups'],root=root,authoring=False,group_cache=_published_cache.setdefault(key,{}))


def export_library(root,group_ids=None,*,rules_format=False,entities=None,authoring=False):
    recover(root)
    public,meta=_load(root)
    if group_ids is not None:
        if not isinstance(group_ids,list) or any(not isinstance(uid,str) for uid in group_ids):raise ValueError('导出组身份必须为列表')
        wanted=set(group_ids);available={g['id'] for g in public['groups']}
        if wanted-available:raise ValueError('导出组不存在')
        groups=[g for g in public['groups'] if g['id'] in wanted]
    else:groups=public['groups']
    projected=_exportable({'events':public['events'],'groups':groups})
    groups=projected['groups']
    event_ids={g['event_id'] for g in groups}
    events=[e for e in public['events'] if group_ids is None or e['id'] in event_ids]
    if rules_format or any('expression' in group for group in groups):
        from template_package import encode
        return encode({'events':events,'groups':groups},_catalog(root,entities)[0],_notes(root),meta,
                      all_groups=public['groups'],root=root,authoring=authoring,stable_ids=authoring)
    from templates_portable import encode
    return encode({'events':events,'groups':groups})


def refresh_published(root,entities=None,*,migrate_events=False,season='S1',format=None,mode=None):
    """Reconcile the derived runtime file after startup or an external sync."""
    with store_lock(root,wait=True):
        _recover_locked(root)
        renamed={}
        retired={}
        try:
            public,meta=_load(root,renamed=renamed,retired=retired,migrate_events=migrate_events)
            if format == 'v3' and meta.get('syntax_version') in KEYED_SYNTAX_VERSIONS:
                if season != 'S1' or not (Path(root)/PUBLISHED_V3).is_file():
                    raise KeyError('未保存该赛季的 v3 发布快照')
                legacy=json_store.read(Path(root)/PUBLISHED_V3)
                return _for_scope(legacy,season,mode) if mode is not None else legacy
            result=_published_document(root,public,meta,entities,season,mode)
        except ValueError:
            if format=='v3' or season!='S1' or mode is not None or not (Path(root)/PUBLISHED).is_file():
                raise
            import logging
            from src.python.condition.v04 import load_library
            logging.getLogger(__name__).exception('模板库发布校验未通过，继续使用上一版本')
            result=json_store.read(Path(root)/PUBLISHED)
            if '解释事件' in result:
                load_library(result,strict=format=='v'+CURRENT_VERSION)
            elif format in ('v0.4','v'+CURRENT_VERSION):
                raise
            return result
        if format in ('v0.4','v'+CURRENT_VERSION) and '解释事件' not in result:
            raise KeyError('该模板库尚未切换至额外信息键格式')
        if season!='S1' or mode is not None:return deepcopy(result)
        if renamed or retired:
            writes={_path('event',uid):row for uid,row in renamed.items() if row in public['events']}
            if retired:
                revision = _revision(public,meta)
                for relative,record in retired.items():
                    kind = 'event' if Path(relative).parent.name == 'events' else 'group'
                    entry = meta['tombstones'][kind].setdefault(record['id'],
                            {'actor':'事件目录迁移','at':_now(),'revision':revision})
                    entry.setdefault('record',record)
                writes[META]=meta
            writes[PUBLISHED]=result
            deletes=sorted(retired)
            if META in writes and (Path(root)/STATE).exists():deletes.append(STATE)
            json_store.write_file(Path(root)/JOURNAL,{'schema_version':1,'writes':writes,'deletes':deletes})
            _recover_locked(root)
        else:json_store.write_file(_safe_path(root,PUBLISHED),result)
        return deepcopy(result)


def preview_import(root,document,*,entities=None,content_only=False):
    public,meta=_load(root);revision=_revision(public,meta)
    result={'revision':revision,'changes':[],'summary':{'created':0,'updated':0,'unchanged':0},'errors':[],'preserved_fixed':[]}
    try:
        from templates_portable import decode
        from template_workflow import equivalent
        catalog,notes,retired=validation_context(root,entities=entities,before=public,metadata=meta)
        doc=decode(document,public,catalog,notes,retired_entities=retired,
                   retired_suggestions=event_validation_context(root,before=public,metadata=meta))
        events={row['id']:row for row in [*public['events'],*doc['events']]}
        for kind,folder in FOLDERS.items():
            current={v['id']:v for v in public[folder]}
            for value in doc[folder]:
                old=current.get(value['id'])
                if kind=='group' and old:
                    result['preserved_fixed'].extend(
                        {'group_id':old['id'],'group_name':old['name'],'utterance_id':row['id'],'text':row['text']}
                        for row in old['utterances'] if row.get('fixed'))
                if value==old or content_only and kind=='group' and equivalent(old,value,events,catalog):
                    result['summary']['unchanged']+=1;continue
                result['summary']['created' if old is None else 'updated']+=1
                result['changes'].append({'kind':kind,'action':'put','id':value['id'],'value':value})
        _project(root,public,revision,meta,result['changes'],entities)
    except (ValueError,TypeError,KeyError) as exc:
        result['errors']=[str(exc)];result['changes']=[]
        result['preserved_fixed']=[]
        result['summary']={'created':0,'updated':0,'unchanged':0}
    return result


def _warnings(public,meta,catalog,complete):
    result=[];events={e['id']:e for e in public['events']}
    for group in public['groups']:
        baseline=meta['baselines'].get(group['id'],{});changes=[];current={}
        for eid,name in _references(group,events,catalog,meta.get('entity_bindings',{}).get(group['id'],{})).items():
            before=baseline.get(eid);entity=catalog.get(eid)
            if entity is None and (not before or before.get('category') not in complete):continue
            after=semantic(entity) if entity else None;current[eid]=after
            if before!=after:changes.append({'id':eid,'name':(entity or before or {}).get('name',name),'before':deepcopy(before),'after':after})
        if changes:
            result.append({'group_id':group['id'],'group_name':group['name'],
                           'revision':json_store.digest({'group':group,'baseline':baseline,'current':current}),
                           'entities':sorted(changes,key=lambda row:row['id'])})
    return result


def warnings(root,entities=None):
    public,meta=_load(root);catalog,complete=_catalog(root,entities)
    return _warnings(public,meta,catalog,complete)


def confirm_warning(root,group_id,revision,actor='admin',*,entities=None):
    actor=_actor(actor)
    with store_lock(root,wait=True):
        _recover_locked(root);public,meta=_load(root);catalog,complete=_catalog(root,entities)
        warning=next((w for w in _warnings(public,meta,catalog,complete) if w['group_id']==group_id),None)
        if warning is None or warning['revision']!=revision:raise Conflict('关联实体或话术组已变化，请重新查看后确认')
        newmeta=deepcopy(meta)
        group=next(g for g in public['groups'] if g['id']==group_id)
        newmeta.setdefault('entity_bindings',{})[group_id]=_bindings(group,{e['id']:e for e in public['events']},catalog,meta.get('entity_bindings',{}).get(group_id,{}))
        for entity in warning['entities']:
            # A schema-1 library created before entity_archive existed still has
            # its last known record in the baseline. Preserve it before acking a
            # deletion, otherwise the next unrelated save could not validate it.
            if isinstance(entity['before'],dict):
                newmeta.setdefault('entity_archive',{}).setdefault(group_id,{}).setdefault(entity['id'],deepcopy(entity['before']))
            newmeta['baselines'][group_id][entity['id']]=deepcopy(entity['after'])
        newmeta['audit'].append({'id':uuid.uuid4().hex,'actor':actor,'at':_now(),'action':'confirm_warning','group_id':group_id,'warning_revision':revision})
        result=_persist_locked(root,public,public,newmeta,entities=entities)
        return {'confirmed':True,'group_id':group_id,'revision':result['revision']}
