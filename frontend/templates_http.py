"""Shared local/public HTTP operations for the template content domain."""
from contextlib import nullcontext
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import json_store
import templates_store as library
from templates_proposals import TemplateProposals
from workspace import Conflict


PREFIX='/api/templates'


def is_template_path(path):
    return path==PREFIX or path.startswith(PREFIX+'/')


def effective_entities(server):
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
            entity_provider=lambda:effective_entities(server))
    return server.template_proposals


def _identity(actor,editor=False,admin=False):
    if not actor:raise PermissionError('请先登录')
    if editor and actor.get('role') not in ('admin','annotator'):raise PermissionError('浏览者没有模板编辑权限')
    if admin and actor.get('role')!='admin':raise PermissionError('只有管理员可以解决模板同步冲突')


def _warning_tokens(items):
    return sorted({json_store.digest({'group_id':item['group_id'],'entity_id':entity['id'],
        'before':entity['before'],'after':entity['after']}) for item in items for entity in item['entities']})


def get(server,actor,path,request_url):
    _identity(actor)
    query=parse_qs(urlsplit(request_url).query,keep_blank_values=True)
    if path==PREFIX:
        data=library.snapshot(server.root)
        data.update(library.entity_link_projection(server.root,entities=effective_entities(server)))
        return data
    if path==PREFIX+'/export':
        ids=None
        if 'group_ids' in query:ids=[s for s in query['group_ids'][0].split(',') if s]
        return library.export_library(server.root,ids)
    if path==PREFIX+'/proposals':
        _identity(actor,editor=True)
        return proposal_store(server).list(actor)
    if path==PREFIX+'/warnings':
        items=library.warnings(server.root,entities=effective_entities(server))
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


def mutate(server,actor,path,command,data,public=False):
    _identity(actor,editor=True)
    if not isinstance(data,dict):raise ValueError('请求必须为JSON对象')
    if command!='POST':raise KeyError('模板接口只接受POST修改')
    from site_access import state_dir,enqueue_sync,formal_save,assert_formal_write
    from website_sync import save_lock
    service=proposal_store(server)
    if service.receipt.exists():
        with save_lock(state_dir(server)):service.recover()
    if path==PREFIX+'/import/preview':
        return library.preview_import(server.root,data.get('document'),entities=effective_entities(server))
    if path==PREFIX+'/warnings/seen':
        current=get(server,actor,PREFIX+'/warnings',PREFIX+'/warnings')
        if data.get('notification_revision')!=current['notification_revision']:raise Conflict('实体变化已更新，请重新核对')
        service.mark_seen(actor['username'],current['notification_revision'],_warning_tokens(current['items']))
        return {'ok':True}
    proposal=re.fullmatch(re.escape(PREFIX)+r'/proposals/([A-Za-z0-9_-]+)/((?:approve|reject|withdraw))',path)
    if proposal and proposal[2]!='approve':return service.action(actor,proposal[1],proposal[2],data)
    if path in (PREFIX+'/changes',PREFIX+'/import/commit') and actor['role']=='annotator':
        return {'proposal':service.submit(actor,data)}
    if not (path in (PREFIX+'/changes',PREFIX+'/import/commit',PREFIX+'/warnings/confirm') or proposal
            or re.fullmatch(re.escape(PREFIX)+r'/sync-conflicts/[A-Za-z0-9_-]+/resolve',path)):
        raise KeyError('模板接口不存在')
    if proposal and actor['role']!='admin':raise PermissionError('只有管理员可以审批模板提案')
    with save_lock(state_dir(server)),formal_save(server) if public else nullcontext():
        if public:
            getattr(server.sync,'_assert_active',lambda:None)()
            assert_formal_write(server,public=True)
        service.recover()
        if path==PREFIX+'/warnings/confirm':
            result=library.confirm_warning(server.root,data.get('group_id'),data.get('revision'),
                actor=actor['username'],entities=effective_entities(server))
            if not isinstance(result,dict):result={'ok':True}
        elif proposal:result=service.action(actor,proposal[1],proposal[2],data)
        elif '/sync-conflicts/' in path:
            _identity(actor,admin=True)
            import templates_sync
            result=templates_sync.resolve_conflict(server.root,path.split('/')[-2],
                data.get('revision'),data.get('value'),actor['username'],entities=effective_entities(server))
        else:
            result=library.apply(server.root,data.get('revision'),data.get('changes'),
                actor=actor['username'],entities=effective_entities(server))
        if public:result={**result,'sync':enqueue_sync(server)}
        return result
