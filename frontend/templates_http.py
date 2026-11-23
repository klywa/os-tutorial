"""Shared local/public HTTP operations for the template content domain."""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
from threading import RLock
from urllib.parse import parse_qs, urlsplit

import template_feedback as feedback
import json_store
import seasons
import template_workflow as workflow
import templates_store as library
from templates_proposals import TemplateProposals
from workspace import Conflict


PREFIX='/api/templates'
_read_lock = RLock()
_entities_lock = RLock()


def _stamp(stat):
    return stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns


def _file_stamp(path):
    try:
        return _stamp(path.stat())
    except FileNotFoundError:
        return None


def _json_files(folder, recursive=False):
    """DirEntry.stat uses the directory listing's metadata on Windows."""
    result = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if recursive and entry.is_dir(follow_symlinks=False):
                    result.extend(_json_files(entry.path, recursive=True))
                elif entry.name.endswith('.json'):
                    result.append((entry.path, _stamp(entry.stat())))
    except FileNotFoundError:
        pass
    return sorted(result)


def _entity_generation(server):
    root = Path(server.root)
    files = []
    records = []
    if hasattr(server,'public_origin'):
        from site_access import state_dir
        card_dir = state_dir(server)/'cards'
        files.append(card_dir/'current.json')
        version = json_store.read(card_dir/'current.json', {}).get('version')
        if isinstance(version,str) and re.fullmatch('[0-9a-f]{64}',version):
            files.append(card_dir/'versions'/version/'cards.json')
        files.append(root/'website-data/cards.json')
    else:
        files.append(root/'raw/knowledge/pending-cards.json')
        records.extend(_json_files(root/'knowledge/cards', recursive=True))
    for folder in ('entities','website-data/entities'):
        records.extend(_json_files(root/folder))
    return root, tuple(_file_stamp(path) for path in files), tuple(records)


def _read_generation(server):
    from card_tags import database as tag_database
    root = Path(server.root)
    files = [root/library.META, root/library.STATE, root/library.JOURNAL, library.rules.SOURCE, root/'knowledge/index.meta.json',
             root/'src/condition/card-tags.json', root/'website-data/seasons/S2/cards.json', tag_database(root)]
    records = _json_files(root/'templates/events') + _json_files(root/'templates/groups') + _json_files(root/library.REVIEW_HISTORY)
    return _entity_generation(server), tuple(_file_stamp(path) for path in files), tuple(records)


def _read_projection(server, part, known_generation=None):
    """Share only public content; notification receipts remain per user."""
    library.recover(server.root)
    with _read_lock:
        while True:
            generation = _read_generation(server)
            cached = getattr(server, '_template_read_cache', {})
            if cached.get('generation') != generation:
                metadata_key=library.review_metadata_key(server.root)
                public, meta = library._load(server.root)
                catalog, complete = library._catalog(server.root, effective_entities(server))
                cached = dict(generation=generation, public=public, meta=meta, catalog=catalog, complete=complete)
                if not (Path(server.root)/library.JOURNAL).exists() and metadata_key==library.review_metadata_key(server.root):
                    cached['metadata_digest']=library.review_metadata(metadata_key,meta)[1]
            if part == 'snapshot' and known_generation and cached.get(part, {}).get('read_generation') == known_generation:
                return {'unchanged': True}
            if part not in cached:
                public, meta, catalog = cached['public'], cached['meta'], cached['catalog']
                if part.startswith('revisions:'):
                    cached[part] = {'items':workflow.revisions(server.root,part.split(':',1)[1],loaded=(public,meta))}
                elif part == 'warnings':
                    cached[part] = library._warnings(public, meta, catalog, cached['complete'])
                else:
                    data = library._snapshot(public, meta,metadata_digest=cached.get('metadata_digest'))
                    data['read_generation'] = hashlib.sha256(repr(generation).encode()).hexdigest()
                    events = {e['id']:e for e in data['events']}
                    data['condition_catalog'] = library.rules.library_catalog(events.values(),root=server.root)
                    notes = library._notes(server.root)
                    scope_names = {}
                    utterance_bindings = {}
                    from src.python.condition import literal_in_bindings
                    for group in data['groups']:
                        refs = {**meta.get('entity_archive',{}).get(group['id'],{}),**catalog}
                        event = events[group['event_id']]
                        group.update(library.rules.editor_rule(group,event,refs))
                        if 'in' in group['expression']:
                            bindings = literal_in_bindings(group['expression'],event['name'],data['condition_catalog'])
                            if bindings:
                                utterance_bindings[group['id']] = bindings
                        player = group['scope']['player_id']
                        lineup = group['scope']['lineup_note_id']
                        if player in refs:
                            scope_names[player] = refs[player]['name']
                        if lineup in notes:
                            scope_names[lineup] = notes[lineup]['title']
                    data['scope_names'] = scope_names
                    data['utterance_bindings'] = utterance_bindings
                    data.update(library.project_entity_links(public,meta,catalog))
                    cached[part] = data
                if _read_generation(server) != generation:
                    continue
            server._template_read_cache = cached
            return deepcopy(cached[part])


def is_template_path(path):
    return path==PREFIX or path.startswith(PREFIX+'/')


def effective_entities(server):
    """Reuse the verified active catalog across previews, saves and page reads."""
    with _entities_lock:
        while True:
            generation = _entity_generation(server)
            cached = getattr(server, '_template_entities_cache', None)
            if cached is not None and cached[0] == generation:
                return cached[1]
            result = library.EffectiveEntities(_load_effective_entities(server))
            if generation == _entity_generation(server):
                server._template_entities_cache = generation, result
                return result


def _load_effective_entities(server):
    """Use the same active card version users see, plus complete player definitions."""
    import templates_schema
    rows={};complete=set()
    root=Path(server.root)
    for parent in (root/'website-data/entities',root/'entities'):
        if parent.is_dir():
            for file in parent.glob('*.json'):
                if file.stem not in templates_schema.CATEGORIES:continue
                try:values=json_store.read(file)
                except (ValueError,OSError):continue
                if isinstance(values,list) and all(isinstance(v,dict) and isinstance(v.get('id'),str) for v in values):
                    rows={key:value for key,value in rows.items() if value.get('category')!=file.stem}
                    complete.add(file.stem)
                    for row in values:
                        rows[row['id']]={**row,'category':file.stem}
    cards=None
    if hasattr(server,'public_origin'):
        from card_publication import resolve
        from site_access import state_dir
        folder,_=resolve(root,state_dir(server))
        cards=json_store.read(folder/'cards.json',[])
    elif (root/'knowledge/cards/index.meta.json').exists():
        from reference_store import json_cards
        cards=json_cards(root)
    if cards is not None:
        if not isinstance(cards,list) or any(not isinstance(row,dict) or not isinstance(row.get('id'),str)
            or row.get('category') not in templates_schema.CATEGORIES for row in cards):
            raise ValueError('有效卡牌资料暂不可用，保留上次模板预警状态')
        # A successfully published card dataset is a complete catalog. Never
        # retain a bundled old card that the current version actually removed.
        rows={row['id']:row for row in cards}
        complete=set(templates_schema.CATEGORIES)
    return {'items':list(rows.values()),'complete_categories':sorted(complete)}


def proposal_store(server):
    if not hasattr(server,'template_proposals'):
        from site_access import state_dir
        server.template_proposals=TemplateProposals(server.root,state_dir(server)/'template-proposals.sqlite3',
            entity_provider=lambda:effective_entities(server), workflow_enabled=True)
    return server.template_proposals


def _identity(actor,editor=False,admin=False):
    if not actor:raise PermissionError('请先登录')
    if editor and actor.get('role') not in ('admin','annotator','quality'):raise PermissionError('浏览者没有模板编辑权限')
    if admin and actor.get('role')!='admin':raise PermissionError('只有管理员可以解决模板同步冲突')


def _warning_tokens(items):
    return sorted({json_store.digest({'group_id':item['group_id'],'entity_id':entity['id'],
        'before':entity['before'],'after':entity['after']}) for item in items for entity in item['entities']})


def get(server,actor,path,request_url):
    _identity(actor)
    query=parse_qs(urlsplit(request_url).query,keep_blank_values=True)
    if path==PREFIX:
        if query.get('legacy')==['1']:
            return seasons.template_read(server.root,seasons.selected(request_url),path)
        return _read_projection(server, 'snapshot', query.get('if_generation',[None])[0])
    if path==PREFIX+'/official':
        season=seasons.selected(request_url)
        return workflow.official(server.root,season,effective_entities(server) if season=='S1' else None)
    history=re.fullmatch(PREFIX+r'/groups/([A-Za-z0-9_-]+)/revisions',path)
    if history:
        return _read_projection(server,'revisions:'+history[1])
    if path==PREFIX+'/export':
        ids=None
        if 'group_ids' in query:ids=[s for s in query['group_ids'][0].split(',') if s]
        return library.export_library(server.root,ids,rules_format=True,entities=effective_entities(server),
                                      authoring=query.get('authoring')==['1'])
    if path==PREFIX+'/published':
        return library.refresh_published(server.root,entities=effective_entities(server),season=seasons.selected(request_url))
    if path in (PREFIX+'/comments', PREFIX+'/history'):
        _identity(actor,editor=True)
        group_id=query.get('group_id',[None])[0]
        service=proposal_store(server)
        if path.endswith('/comments'):
            if query.get('counts') == ['1']:return {'items':feedback.comment_counts(service)}
            return {'items':feedback.comments(service,query.get('status',['open'])[0],group_id)}
        if not group_id and query.get('latest')==['1']:return {'items':feedback.latest_history(service,actor)}
        return {'items':feedback.history(service,actor,group_id,latest=query.get('latest')==['1'])}
    if path==PREFIX+'/proposals':
        _identity(actor,editor=True)
        service=proposal_store(server)
        proposal_id=query.get('proposal_id',[None])[0]
        if query.get('view')==['card-preview']:return service.card_previews(actor,proposal_id)
        return service.list(actor,proposal_id,summary=query.get('view')==['summary'])
    if path==PREFIX+'/warnings':
        items=_read_projection(server, 'warnings')
        tokens=_warning_tokens(items);revision=json_store.digest(tokens)
        unseen_items=[]
        if items and actor.get('role') in ('admin','annotator'):
            unseen_tokens=proposal_store(server).unseen_tokens(actor['username'],tokens)
            for item in items:
                entities=[entity for entity in item['entities'] if _warning_tokens([{**item,'entities':[entity]}])[0] in unseen_tokens]
                if entities:unseen_items.append({**item,'entities':entities})
        return {'items':items,'unseen_items':unseen_items,'notification_revision':revision,'unseen':bool(unseen_items)}
    if path==PREFIX+'/sync-conflicts':
        _identity(actor,admin=True)
        import templates_sync
        return templates_sync.list_conflicts(server.root)
    raise KeyError('模板接口不存在')


def _proposal_ack(result):
    keys=('id','author','created_at','source','batch_id','status','proposal_revision','revision',
          'changes','group_review_overrides','formal_write','sync')
    ids={change['id'] for change in result['changes'] if change['kind']=='group'}
    return {**{key:result[key] for key in keys if key in result},
            'base':{'groups':[group for group in result['base']['groups'] if group['id'] in ids],'events':[]},
            'reviews':result['reviews'][-1:]}


def _proposal_response(result,data):
    if 'base' not in result:return result
    if data.get('summary') is True:
        from templates_proposals import proposal_summary
        return proposal_summary(result)
    if data.get('compact') is True:return _proposal_ack(result)
    return result


def _editor_changes(data,current):
    if 'group_patches' not in data:return data.get('changes')
    from template_group_edit import apply_fields
    patches=data['group_patches']
    if not isinstance(patches,list) or len(patches)>5000 or not isinstance(data.get('changes',[]),list):
        raise ValueError('模板字段修改必须为列表')
    groups={group['id']:group for group in current['groups']}
    changes=list(data.get('changes',[]))
    for patch in patches:
        if not isinstance(patch,dict) or set(patch)!={'id','fields'} or not isinstance(patch['id'],str):
            raise ValueError('模板字段修改格式无效')
        gid=patch['id']
        if gid not in groups:raise Conflict('模板组已不存在')
        changes.append({'kind':'group','action':'put','id':gid,'value':apply_fields(groups[gid],patch['fields'])})
    return changes


def mutate(server,actor,path,command,data,public=False):
    _identity(actor,editor=True)
    if path==PREFIX+'/warnings/confirm' and actor['role']!='admin':
        raise PermissionError('只有管理员可以确认关联资料变更')
    if not isinstance(data,dict):raise ValueError('请求必须为JSON对象')
    if command!='POST':raise KeyError('模板接口只接受POST修改')
    from site_access import state_dir,enqueue_sync,formal_save,assert_formal_write,sync_status
    from website_sync import save_lock
    service=proposal_store(server)
    def flush_approval():
        if public and service.pending_sync.exists() and sync_status(server).get('state')!='conflict':
            return service.enqueue_pending(lambda:enqueue_sync(server))
    if service.receipt.exists() or (public and service.pending_sync.exists()):
        with save_lock(state_dir(server)):
            service.recover()
            flush_approval()
    if path==PREFIX+'/comments':return feedback.annotate(service,actor,data)
    thread=re.fullmatch(re.escape(PREFIX)+r'/comments/([A-Za-z0-9_-]+)/(reply|edit|close|reopen)',path)
    if thread:return feedback.annotate(service,actor,data,thread[1],thread[2])
    if path==PREFIX+'/import/preview':
        return library.preview_import(server.root,data.get('document'),entities=effective_entities(server),content_only=True)
    if path==PREFIX+'/warnings/seen':
        current=get(server,actor,PREFIX+'/warnings',PREFIX+'/warnings')
        if data.get('notification_revision')!=current['notification_revision']:raise Conflict('实体变化已更新，请重新核对')
        service.mark_seen(actor['username'],current['notification_revision'],_warning_tokens(current['items']))
        return {'ok':True}
    discussion=re.fullmatch(re.escape(PREFIX)+r'/proposals/([A-Za-z0-9_-]+)/comments',path)
    if discussion:return service.discuss(actor,discussion[1],data)
    proposal=re.fullmatch(re.escape(PREFIX)+r'/proposals/([A-Za-z0-9_-]+)/((?:approve|edit|reject|withdraw))',path)
    if proposal and proposal[2]!='approve':
        result=service.action(actor,proposal[1],proposal[2],data)
        if data.get('compact') is True or proposal[2]=='edit' and isinstance(data.get('group_editor'),dict):
            return _proposal_ack(result)
        return _proposal_response(result,data)
    manual={'source':'manual'}
    source='editor'
    group_action=re.fullmatch(PREFIX+r'/groups/([A-Za-z0-9_-]+)/(review|restore(?:/preview)?)',path)
    if (path in (PREFIX+'/changes',PREFIX+'/import/commit') or group_action) and not isinstance(data.get('revision'),str):
        raise ValueError('请求缺少有效的模板库修订号')
    if group_action and group_action[2]=='review' and 'status' not in data and actor['role'] not in workflow.REVIEWERS:
        raise PermissionError('只有管理员或质检员可以复核模板')
    if group_action and group_action[2]=='review' and actor['role']=='annotator':
        current=library.snapshot(server.root)
        if data.get('revision')!=current['revision']:raise Conflict('模板库已更新，请刷新后重试')
        change=workflow.review_status_change(current,group_action[1],actor,data['status'])
        if change is None:return current
        return {'proposal':service.submit(actor,{**data,'changes':[change],'source':'review-status'},workflow_source='review-status')}
    if group_action and (group_action[2]=='restore/preview' or group_action[2]=='restore' and actor['role']=='annotator'):
        entities=effective_entities(server)
        current=library.snapshot(server.root)
        if data.get('revision')!=current['revision']:raise Conflict('模板库已更新，请刷新后重试')
        change=workflow.restore_change(server.root,current,group_action[1],data.get('revision_id'))
        changes=[change] if change else []
        library.preview_changes(server.root,current['revision'],changes,entities=entities)
        if group_action[2]=='restore/preview':
            return {'change':change,'revision':current['revision']}
        if not changes:return current
        return {'proposal':service.submit(actor,{**data,'changes':changes,'source':'restore'},workflow_source='restore',
                                          restored_from=data['revision_id'])}
    if path==PREFIX+'/import/commit':
        data={**data,'source':feedback.text(data.get('source','import'),'来源',200)}
        source='file-import' if data['source']=='file-import' else 'import'
        if data.get('bypass_review') is not True:return {'proposal':service.submit(actor,data,workflow_source=source)}
        if actor['role']!='admin':raise PermissionError('只有管理员可以直接导入')
        import uuid
        manual={'source':data['source'],'batch_id':feedback.text(data.get('batch_id',uuid.uuid4().hex),'批次',200),
                'reason':feedback.text(data.get('reason'),'直接导入原因')}
    if path==PREFIX+'/changes' and actor['role']=='annotator':
        return {'proposal':service.submit(actor,data,workflow_source='editor',prepare=lambda current:_editor_changes(data,current))}
    fixing = path == PREFIX+'/utterances/fixed'
    if fixing:
        _identity(actor,admin=True)
    if not (path in (PREFIX+'/changes',PREFIX+'/import/commit',PREFIX+'/warnings/confirm') or fixing or proposal or group_action
            or re.fullmatch(re.escape(PREFIX)+r'/sync-conflicts/[A-Za-z0-9_-]+/resolve',path)):
        raise KeyError('模板接口不存在')
    if proposal and actor['role']!='admin':raise PermissionError('只有管理员可以审批模板提案')
    with save_lock(state_dir(server)),formal_save(server) if public else nullcontext():
        service.recover()
        flush_approval()
        if proposal:
            previous=service.approved_retry(actor,proposal[1],data)
            if previous:
                result={**previous,**({'sync':sync_status(server)} if public else {})}
                return _proposal_response(result,data)
        if public:
            getattr(server.sync,'_assert_active',lambda:None)()
            assert_formal_write(server,public=True)
        if path==PREFIX+'/warnings/confirm':
            result=library.confirm_warning(server.root,data.get('group_id'),data.get('revision'),
                actor=actor['username'],entities=effective_entities(server))
            if not isinstance(result,dict):result={'ok':True}
        elif fixing:
            result=library.set_utterance_fixed(server.root,data.get('revision'),data.get('group_id'),
                data.get('utterance_id'),data.get('fixed'),actor['username'],entities=effective_entities(server))
        elif proposal:result=service.action(actor,proposal[1],proposal[2],data,needs_sync=public)
        elif group_action and group_action[2]=='review':
            result=library.set_review_status(server.root,data['revision'],group_action[1],actor,data)
        elif '/sync-conflicts/' in path:
            _identity(actor,admin=True)
            import templates_sync
            result=templates_sync.resolve_conflict(server.root,path.split('/')[-2],
                data.get('revision'),data.get('value'),actor['username'],entities=effective_entities(server))
        elif path==PREFIX+'/changes':
            from template_group_edit import fork_direct_changes
            entities=effective_entities(server)
            def prepare(current):
                changes=_editor_changes(data,current)
                if actor['role']=='quality':
                    existing={group['id'] for group in current['groups']}
                    if not isinstance(changes,list) or any(not isinstance(change,dict) or change.get('kind')!='group'
                            or change.get('action')!='put' or change.get('id') not in existing for change in changes):
                        raise PermissionError('质检员只能编辑已有模板组')
                transformed=fork_direct_changes(current,changes)
                if actor['role']=='quality' and transformed!=changes:
                    raise PermissionError('触发动作变化需要新建模板组，请由有新建权限的账号处理')
                return workflow.prepare(server.root,current,transformed,actor,source=source,entities=entities)
            result=library.apply(server.root,data['revision'],None,actor=actor['username'],entities=entities,
                                 manual=manual,prepare=prepare)
        else:
            entities=effective_entities(server)
            current=library.snapshot(server.root)
            if data.get('revision')!=current['revision']:raise Conflict('模板库已更新，请刷新后重试')
            changes=data.get('changes')
            if group_action:
                change=workflow.restore_change(server.root,current,group_action[1],data.get('revision_id'))
                changes=[change] if change else []
                manual={'source':'restore','restored_from':data.get('revision_id')}
            changes=workflow.prepare(server.root,current,changes,actor,source=source,entities=entities)
            result=library.apply(server.root,current['revision'],changes,
                actor=actor['username'],entities=entities,manual=manual)
        if public:
            sync=flush_approval() if proposal else enqueue_sync(server)
            result={**result,'sync':sync if sync is not None else sync_status(server)}
        if proposal:return _proposal_response(result,data)
        return result
